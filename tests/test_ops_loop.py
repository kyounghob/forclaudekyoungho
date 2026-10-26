"""자동 운영 루프: 탐색 칸 노출 확률, OPE, 검증 게이트, 등록부 해시 사슬, 주간 작업·모의 실행, 운영 API."""
import json
import os
import time

import numpy as np
import pytest

from etfrec.ops.exploration import ExplorationConfig, explore_slate, inclusion_probability
from etfrec.ops.gate import GateConfig, evaluate_gate, rollback_check
from etfrec.ops.logstore import OpsLog
from etfrec.ops.loop import default_settings, run_week, simulate
from etfrec.ops.ope import attach_rewards, paired_difference, policy_value
from etfrec.ops.policies import (algo_from_spec, declared_spec, eligibility, make_spec, spec_hash, term_weight,
                                 variant_specs)
from etfrec.ops.registry import PolicyRegistry


# ---------- 탐색 칸 ----------
def test_explore_slate_keeps_prefix_and_logs_propensity():
    order, scores, cfg = list(range(10)), np.linspace(1, 0, 10), ExplorationConfig(epsilon=0.2)
    seen = set()
    for i in range(60):
        s = explore_slate(order, scores, 5, cfg, f"req-{i}")
        assert s["items"][:4] == [0, 1, 2, 3] and s["propensity"][:4] == [1.0] * 4     # 앞 k−1칸은 운영 순위 그대로
        last = s["items"][4]; seen.add(s["explored"])
        if s["explored"]:
            assert last in range(5, 10) and np.isclose(s["propensity"][4], 0.2 / 5)
        else:
            assert last == 4 and np.isclose(s["propensity"][4], 0.8)
        assert np.isclose(inclusion_probability(last, s), s["propensity"][4])
    assert seen == {True, False}
    assert explore_slate(order, scores, 5, cfg, "same") == explore_slate(order, scores, 5, cfg, "same")   # 같은 요청 = 같은 결과
    short = explore_slate([1, 2, 3], [3, 2, 1], 5, cfg, "short")                    # 탐색할 단원이 없으면 탐색하지 않는다
    assert short["items"] == [1, 2, 3] and short["propensity"] == [1.0] * 3 and not short["explored"]
    for bad in (dict(epsilon=0.6), dict(method="greedy"), dict(temperature=0)):
        with pytest.raises(ValueError):
            ExplorationConfig(**bad)


def test_logged_propensities_match_empirical_frequencies():
    order, scores = list(range(8)), np.array([5, 4, 3, 2, 1.5, 1.0, 0.5, 0.1])
    cfg = ExplorationConfig(epsilon=0.3, method="softmax", temperature=0.5)
    n, counts = 8000, np.zeros(8)
    for i in range(n):
        for it in explore_slate(order, scores, 3, cfg, f"r{i}")["items"]:
            counts[it] += 1
    ref = explore_slate(order, scores, 3, cfg, "x")
    expected = np.array([inclusion_probability(i, ref) for i in range(8)])
    assert np.isclose(expected.sum(), 3) and np.allclose(counts / n, expected, atol=0.015)


# ---------- OPE ----------
def _logged(s, u, rewards):
    return dict(request_id=s["request_id"], user_ref=u, items=s["items"], propensity=s["propensity"],
                rewards=[float(rewards[i]) for i in s["items"]], explored=s["explored"], slot=s["slot"],
                exploit_item=s["exploit_item"], prefix=s["prefix"], pool=s["pool"], pool_prob=s["pool_prob"], epsilon=s["epsilon"])


def test_slate_ips_is_unbiased_on_toy_problem():
    rng = np.random.default_rng(0)
    n, n_items, k, cfg = 5000, 12, 3, ExplorationConfig(epsilon=0.3)
    p = rng.uniform(0.05, 0.6, size=(n, n_items))
    logged, new, old, truth_new = [], {}, {}, []
    for u in range(n):
        order = [int(x) for x in rng.permutation(n_items)]
        s = explore_slate(order, np.linspace(1, 0, n_items), k, cfg, f"u{u}")
        logged.append(_logged(s, u, rng.random(n_items) < p[u]))
        new[f"u{u}"] = [order[0], order[5], order[7]]                 # 기록 정책과 다른 단원 2개를 고르는 목표 정책
        old[f"u{u}"] = order[:k]
        truth_new.append(p[u, new[f"u{u}"]].sum())
    est = policy_value(logged, new, k)
    assert est["support"] == 1.0 and est["explore_matches"] > 100
    assert abs(est["ips"] - np.mean(truth_new)) < 3 * est["se"]
    assert abs(est["snips"] - np.mean(truth_new)) < 0.15
    d = paired_difference(logged, new, old, k)
    truth_diff = np.mean(truth_new) - np.mean([p[u, old[f"u{u}"]].sum() for u in range(n)])
    assert d["unique_matches"] > 100 and d["ci_low"] - 0.05 < truth_diff < d["ci_high"] + 0.05


def test_ope_support_and_reward_attachment():
    imp = dict(request_id="r1", user_ref=7, items=[3, 9], propensity=[1.0, 0.05], explored=True, slot=1, exploit_item=4,
               prefix=[3], pool=[9, 10], pool_prob=[0.5, 0.5], epsilon=0.1, policy=dict(key="P", version="v", hash="h"))
    logged = attach_rewards([imp, dict(imp, request_id="r2", user_ref=None)], [dict(user_ref=7, item=9, event="quiz_pass")])
    assert len(logged) == 1 and logged[0]["rewards"] == [0.0, 1.0]          # 학습자 번호가 없는 요청은 다시 계산할 수 없어 뺀다
    est = policy_value(logged, {"r1": [3, 9, 11]}, 3)                       # 11은 기록 정책에서 보일 수 없었던 단원
    assert np.isclose(est["support"], 2 / 3) and np.isclose(est["ips"], 1 / 0.05)


# ---------- 게이트 ----------
def _met(ndcg, align, prereq=0.0, gap=0.02, users=500):
    return dict(ndcg=ndcg, alignment=align, prereq_violation=prereq, exposure=dict(max_gap=gap), users=users)


def test_gate_requires_every_blocking_criterion():
    cfg = GateConfig()
    champ = _met(0.10, 0.60)
    good = dict(_met(0.11, 0.60), paired_ndcg=dict(diff=0.01, ci_low=0.004, ci_high=0.016))
    ok = evaluate_gate(cfg, champ, good, [], None, frozen=False, weeks_since_change=None)
    assert ok["passed"] and ok["failed"] == []
    cases = {"ndcg_gain": dict(good, paired_ndcg=dict(diff=0.004, ci_low=0.001, ci_high=0.007)),
             "alignment_noninferior": dict(good, alignment=0.58), "prereq_violation": dict(good, prereq_violation=0.01),
             "exposure_gap": dict(good, exposure=dict(max_gap=0.08)), "min_users": dict(good, users=50)}
    for name, chall in cases.items():
        r = evaluate_gate(cfg, champ, chall, [], None, False, None)
        assert not r["passed"] and r["failed"] == [name], name
    ci_zero = dict(good, paired_ndcg=dict(diff=0.01, ci_low=-0.001, ci_high=0.02))
    assert evaluate_gate(cfg, champ, ci_zero, [], None, False, None)["failed"] == ["ndcg_gain"]
    assert evaluate_gate(cfg, champ, good, ["보호 변수 사용: ['gender']"], None, False, None)["failed"] == ["eligibility"]
    assert evaluate_gate(cfg, champ, good, [], None, True, None)["failed"] == ["frozen"]
    assert evaluate_gate(cfg, champ, good, [], None, False, 1)["failed"] == ["cooldown"]
    worse_champ = dict(champ, exposure=dict(max_gap=0.09))                   # 5%p를 넘어도 현재 정책보다 나빠지지 않으면 허용
    assert evaluate_gate(cfg, worse_champ, dict(good, exposure=dict(max_gap=0.08)), [], None, False, None)["passed"]


def test_gate_uses_ope_only_with_enough_exploration():
    cfg, champ = GateConfig(), _met(0.10, 0.60)
    good = dict(_met(0.11, 0.60), paired_ndcg=dict(diff=0.01, ci_low=0.004, ci_high=0.016))
    bad = dict(champion=dict(ips=0.5, support=1.0), challenger=dict(ips=0.3, support=1.0),
               diff=dict(diff=-0.2, ci_low=-0.3, ci_high=-0.1, unique_matches=50))
    assert evaluate_gate(cfg, champ, good, [], bad, False, None)["failed"] == ["ope_noninferior"]
    thin = dict(bad, diff=dict(bad["diff"], unique_matches=3))
    r = evaluate_gate(cfg, champ, good, [], thin, False, None)
    assert r["passed"] and next(c for c in r["criteria"] if c["name"] == "ope_noninferior")["passed"] is None
    assert evaluate_gate(GateConfig(require_ope=True), champ, good, [], thin, False, None)["failed"] == ["ope_noninferior"]


def test_rollback_check_needs_clear_drop():
    cfg = GateConfig()
    cur = dict(ndcg=0.09, prereq_violation=0.0, paired_vs_previous=dict(diff=-0.01, ci_low=-0.015, ci_high=-0.004))
    assert rollback_check(cfg, cur, dict(ndcg=0.10))["rollback"]
    assert not rollback_check(cfg, dict(cur, paired_vs_previous=dict(diff=-0.01, ci_low=-0.02, ci_high=0.001)), dict(ndcg=0.1))["rollback"]
    assert rollback_check(cfg, dict(cur, prereq_violation=0.02, paired_vs_previous=dict(diff=0.0, ci_low=-0.01, ci_high=0.01)),
                          dict(ndcg=0.1))["rollback"]


# ---------- 후보 정책 ----------
def test_candidate_policies_keep_goal_roadmap_and_exclude_protected():
    info = {s: dict(uses=()) for s in ("pop", "r:policy_pref", "r:lvl", "r:dev", "r:goal", "r:roadmap")}
    info.update({"r:life": dict(uses=("age",)), "r:pref": dict(uses=("pref",))})
    d = declared_spec()
    assert eligibility(d, info) == [] and d["source"] == "declared"
    vs = variant_specs()
    assert len(vs) == 486 and all(eligibility(v, info) == [] for v in vs)
    assert all(term_weight(v, "r:goal") >= 1 and term_weight(v, "r:roadmap") >= 1 for v in vs)
    rule = lambda *t: make_spec("x", "x", "RULE", [(s, ("c", w)) for s, w in t], "zoo")
    assert any("보호 변수" in r for r in eligibility(rule(("pop", 5), ("r:life", 2), ("r:goal", 2), ("r:roadmap", 2)), info))
    assert any("목적 항" in r for r in eligibility(rule(("pop", 5), ("r:roadmap", 2)), info))
    assert any("r:pref" in r for r in eligibility(rule(("pop", 5), ("r:pref", 3), ("r:goal", 2), ("r:roadmap", 2)), info))
    assert spec_hash(d["terms"]) == spec_hash(list(reversed(d["terms"])))   # 항 순서와 무관한 식별
    assert algo_from_spec(d).signals == [s for s, _ in d["terms"]]


# ---------- 등록부·기록 ----------
def test_registry_hash_chain_promote_rollback_freeze(tmp_path):
    d, v = declared_spec(), variant_specs()[0]
    reg = PolicyRegistry.init(str(tmp_path), d, default_settings())
    reg.promote(v, 5, "시험 교체")
    assert reg.champion["hash"] == v["hash"] and reg.state["previous"][-1]["hash"] == d["hash"]
    assert reg.weeks_since_change(6) == 1
    reg.set_frozen(True, "점검")
    assert PolicyRegistry(str(tmp_path)).frozen
    reg.rollback(6, "되돌림 시험")
    assert PolicyRegistry(str(tmp_path)).champion["hash"] == d["hash"] and reg.verify()["ok"]
    assert [h["event"] for h in reg.history()] == ["init", "promoted", "frozen", "rolled_back"]
    lines = open(reg.history_path, encoding="utf-8").read().splitlines()
    rec = json.loads(lines[1]); rec["reason"] = "조작"; lines[1] = json.dumps(rec, ensure_ascii=False)
    open(reg.history_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    assert reg.verify() == dict(ok=False, first_bad_seq=1, records=1)          # 중간 줄 수정을 찾는다
    with pytest.raises(FileExistsError):
        PolicyRegistry.init(str(tmp_path), d, default_settings())


def test_logstore_validates_and_prunes(tmp_path):
    log = OpsLog(str(tmp_path))
    rec = dict(request_id="r1", week=3, user_ref=1, policy=dict(key="P", version="v", hash="h"), k=5, items=[1, 2], propensity=[1.0, 0.04])
    assert log.append_impressions([rec]) == 1
    for bad in (dict(rec, propensity=[1.0, 0.0]), dict(rec, items=[1, 1]), dict(rec, request_id="bad id"), dict(rec, policy={}),
                dict(rec, user_ref="학습자"), dict(rec, items=[1, 2, 3, 4, 5, 6], propensity=[1.0] * 6)):
        with pytest.raises(ValueError):
            log.append_impressions([bad])
    with pytest.raises(ValueError):
        log.append_feedback([dict(week=3, user_ref=1, item=2, event="like")])
    log.append_feedback([dict(week=3, user_ref=1, item=2, event="quiz_pass")])
    log.append_impressions([dict(rec, request_id=f"r{w}", week=w) for w in (4, 5, 6)])
    assert log.counts(3) == dict(week=3, impressions=1, explored=0, feedback=1)
    removed = log.prune(2)
    assert log.weeks() == [5, 6] and "impressions/week=0003.jsonl" in removed and "feedback/week=0003.jsonl" in removed


# ---------- 주간 작업·모의 실행 ----------
def test_simulation_runs_weekly_loop_end_to_end(tmp_path):
    ops = str(tmp_path / "ops")
    s = simulate(ops, n=500, weeks=5, start=3, seed=7)
    assert [r["week"] for r in s["weeks"]] == [3, 4] and s["history_ok"]
    assert all(r["event"] in ("promoted", "kept", "no_challenger", "rolled_back", "skipped") for r in s["weeks"])
    log = OpsLog(os.path.join(ops, "logs"))
    imps = log.impressions(3)
    assert imps and all(0 < p <= 1 for r in imps for p in r["propensity"]) and all(r["policy"]["hash"] for r in imps)
    assert sum(r["explored"] for r in imps) > 0 and log.feedback(3)
    rep = json.load(open(os.path.join(ops, "reports", "week=0003.json"), encoding="utf-8"))
    assert rep["data"]["sha256"] and rep["selection"]["evaluated"] > 400 and rep["ope"]["logging_consistency"] == 1.0
    if rep["event"] in ("promoted", "kept"):
        assert {c["name"] for c in rep["gate"]["criteria"]} >= {"ndcg_gain", "alignment_noninferior", "prereq_violation",
                                                                 "exposure_gap", "eligibility", "ope_noninferior"}
    with pytest.raises(RuntimeError, match="이미 이력"):
        run_week(ops, None, 4)                                         # 같은 주를 두 번 결정하지 않는다
    with pytest.raises(FileExistsError):
        simulate(ops, n=500, weeks=5, start=3, seed=7)


def test_ops_api_serve_logs_propensities_and_hot_reloads_policy(small_bundle, tmp_path):
    from fastapi.testclient import TestClient
    from etfrec.api import create_app
    ops = str(tmp_path / "ops")
    reg = PolicyRegistry.init(ops, declared_spec(), default_settings())
    c = TestClient(create_app(small_bundle, designs_dir=str(tmp_path / "d"), ops_dir=ops))
    week = int(small_bundle.store.week)
    rids = []
    for lid in range(1, 9):
        r = c.post("/api/serve", json={"learner_id": lid, "k": 5})
        assert r.status_code == 200, r.text
        j = r.json(); rids.append(j["request_id"])
        assert j["policy"]["key"] == "PurposeStageRule" and all(c_["passed"] for c_ in j["checks"])
        assert all(0 < it["propensity"] <= 1 for it in j["items"]) and "pool" not in j["exploration"]
    imps = OpsLog(os.path.join(ops, "logs")).impressions(week)
    assert [r["request_id"] for r in imps] == rids and all(r["user_ref"] is not None for r in imps)
    assert c.post("/api/feedback", json={"learner_id": 1, "item": imps[0]["items"][0], "event": "quiz_pass", "request_id": rids[0]}).status_code == 200
    assert c.post("/api/feedback", json={"learner_id": 1, "item": 0, "event": "like"}).status_code == 422
    assert c.post("/api/feedback", json={"learner_id": 1, "item": 999, "event": "view"}).status_code == 422
    assert "explored" not in c.post("/api/recommend", json={"learner_id": 1}).json()["items"][0]   # 미리보기는 탐색·기록 없음
    st = c.get("/api/ops/status").json()
    assert st["champion"]["key"] == "PurposeStageRule" and st["this_week"]["impressions"] == 8 and st["history_ok"]
    v = variant_specs()[100]
    reg.promote(v, 9, "시험 교체"); t = time.time() + 5; os.utime(reg.path, (t, t))
    assert c.get("/api/ops/status").json()["champion"]["hash"] == v["hash"]          # 서버 재시작 없이 새 정책
    assert c.post("/api/serve", json={"learner_id": 1}).json()["policy"]["hash"] == v["hash"]
    assert [h["event"] for h in c.get("/api/ops/history").json()] == ["init", "promoted"]
    plain = TestClient(create_app(small_bundle, designs_dir=str(tmp_path / "d2")))
    assert plain.post("/api/serve", json={"learner_id": 1}).status_code == 503


def test_service_exploration_never_breaks_guardrails(small_bundle):
    from etfrec.service import RecommendationService
    svc = RecommendationService(small_bundle)
    cfg = ExplorationConfig(epsilon=0.5)
    explored = 0
    for lid in range(1, 16):
        base = [it["item"] for it in svc.recommend(lid, k=5)["items"]]
        for i in range(6):
            r = svc.recommend(lid, k=5, exploration=cfg, request_id=f"g{lid}-{i}")
            items = [it["item"] for it in r["items"]]
            assert all(c["passed"] for c in r["checks"]) and len(set(items)) == len(items)
            assert items[:-1] == base[:len(items) - 1]                  # 앞 칸은 탐색 없는 추천과 같다
            explored += r["exploration"]["explored"]
    assert explored > 0
