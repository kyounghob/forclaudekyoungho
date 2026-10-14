"""개인정보 최소화·가명처리·반출 k-익명화·감사 검사(etfrec.privacy)."""
import copy
import hashlib
import hmac
import json
import os

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from etfrec import cli, privacy
from etfrec.api import create_app
from etfrec.catalog import LABELS, Catalog
from etfrec.data import Dataset
from etfrec.features import AGE_BAND_REP, income_quintile
from etfrec.privacy import (QUASI_IDENTIFIERS, build_pseudonymized_inputs, enforce_k_anonymity, generalization_plan, k_anonymity,
                            pseudonymize_ids, router_leaf_audit)
from etfrec.service import LearnerInput, RecommendationService

KEY = "test-pseudo-key-0123456789"
RAW_KEYS = {"age", "income", "연령", "연소득(만원)"}


def _keys_and_strings(o, keys=None, strings=None):
    keys = set() if keys is None else keys
    strings = [] if strings is None else strings
    if isinstance(o, dict):
        for k, v in o.items():
            keys.add(k); _keys_and_strings(v, keys, strings)
    elif isinstance(o, list):
        for v in o:
            _keys_and_strings(v, keys, strings)
    elif isinstance(o, str):
        strings.append(o)
    return keys, strings


# ---------------- 저장 최소화 ----------------
def test_bundle_stores_bands_not_raw_age_income_or_minutes(small_bundle):
    b = small_bundle
    assert list(b.profiles.columns) == list(privacy.STORED_PROFILE_COLUMNS) and not RAW_KEYS & set(b.profiles.columns)
    assert (b.profiles.age_band.values == b.store.codes[:, 2]).all() and (b.profiles.income_q.values == b.store.codes[:, 3]).all()
    assert not {"day", "minute"} & set(b.log.columns) and {"week", "hour", "seq"} <= set(b.log.columns)
    assert b.log.hour.between(0, 3).all()
    assert b.log.groupby(["user", "week"]).seq.apply(lambda s: s.tolist() == list(range(len(s)))).all()   # 주 안 순서만 남는다
    assert not hasattr(b.store, "age") and not hasattr(b.store, "income")
    assert {"연령대", "소득분위"} <= set(b.store.users.columns) and not RAW_KEYS & set(b.store.users.columns)
    assert np.ndim(b.store.income_median) == 0 and len(b.store.income_rep) == 5
    assert income_quintile(b.store.income_rep, b.store.income_edges)[0].tolist() == [0, 1, 2, 3, 4]   # 대표값은 자기 분위로 돌아간다


def test_learner_listing_and_detail_return_bands_not_raw(small_bundle, tmp_path):
    svc = RecommendationService(small_bundle)
    assert svc.median_income == small_bundle.store.income_median          # 소득 미입력 대체값 = 저장된 집계
    items = svc.learners("", limit=60)["items"]
    for it in items:
        assert not RAW_KEYS & set(it)
        assert it["연령대"] == LABELS["age_band"][it["age_band"]] and it["소득분위"] == LABELS["income_q"][it["income_q"]]
    assert svc.learners("40대", limit=500)["total"] == int((small_bundle.store.codes[:, 2] == 2).sum())
    d = svc.learner(3)
    assert not RAW_KEYS & set(d["profile"]) and all("day" not in h and "minute" not in h for h in d["history"])
    a, q = d["bands"]["age_band"], d["bands"]["income_q"]
    assert a["code"] == d["segment"]["age_band"]["code"] and a["representative"] == AGE_BAND_REP[a["code"]]
    assert q["code"] == d["segment"]["income_q"]["code"] and q["representative"] == small_bundle.store.income_rep[q["code"]]
    # 대표값으로 만든 새 학습자는 같은 구간 코드를 얻는다(모델 입력이 같다)
    lb, _ = svc._adhoc_batch(LearnerInput(age=a["representative"], income=q["representative"]))
    assert lb.codes[0, 2] == a["code"] and lb.codes[0, 3] == q["code"]
    c = TestClient(create_app(small_bundle, designs_dir=str(tmp_path)))
    keys, _ = _keys_and_strings(c.get("/api/learners?limit=30").json())
    keys2, _ = _keys_and_strings(c.get("/api/learners/3").json()["profile"])
    assert not RAW_KEYS & (keys | keys2) and "age_band" in keys


def test_route_path_hides_small_node_sizes(small_bundle):
    svc = RecommendationService(small_bundle)
    seen_small = False
    for uid in small_bundle.test_users[:20]:
        for p in svc.recommend(int(uid), k=5)["route_path"]:
            if p["n"] is None:
                seen_small = True
                assert p["n_label"] == "20명 미만" and p["raw"] is None and p["raw_best"] is None and p["raw_champ"] is None
            else:
                assert p["n"] >= 20 and p["n_label"] == f"{p['n']}명"
    assert seen_small


# ---------------- 가명처리 ----------------
def test_pseudonymize_is_deterministic_and_requires_key():
    a = pseudonymize_ids(["m1", "m2", "m1"], KEY)
    assert list(a) == list(pseudonymize_ids(["m1", "m2", "m1"], KEY)) and a[0] == a[2] != a[1] and len(a[0]) == 16
    assert a[0] == hmac.new(KEY.encode(), b"m1", hashlib.sha256).hexdigest()[:16]
    assert pseudonymize_ids(["m1"], KEY + "x")[0] != a[0]
    for bad in (None, "", "short-key"):
        with pytest.raises(ValueError):
            pseudonymize_ids(["m1"], bad)


def _raw_inputs():
    prof = pd.DataFrame(dict(member_id=["A-9", "B-2", "C-7"], gender=[0, 1, 0], age=[25, 47, 61], income=[3000., 5200., 4100.],
                             exp=[0, 1, 2], risk=[1, 0, 2], mobile=[1, 1, 0], interest1=[0, 1, 2], interest2=[3, 4, 5], placement=[1, 2, 3],
                             phone=["010-1111", "010-2222", "010-3333"]))
    minute = [2 * 1440 + 8 * 60 + 5, 3 * 1440 + 20 * 60, 1 * 1440 + 23 * 60 + 10, 6 * 1440 + 12 * 60, 2 * 1440 + 7 * 60]
    log = pd.DataFrame(dict(member_id=["B-2", "A-9", "B-2", "C-7", "B-2"], item=[0, 1, 2, 3, 4], week=[0, 0, 1, 1, 0], day=[m // 1440 for m in minute],
                            hour=[0] * 5, minute=minute, complete=[1, 1, 0, 1, 1], quiz=[1, 0, 0, 1, 0], quiz_pass=[1, 0, 0, 0, 0],
                            save=[0] * 5, drop=[0, 0, 1, 0, 0], replay=[0] * 5, ip=["1.2.3.4"] * 5))
    return prof, log


def test_build_pseudonymized_inputs_coarsens_and_separates_mapping():
    prof, raw_log = _raw_inputs()
    profiles, log, mapping = build_pseudonymized_inputs(prof, raw_log, "member_id", KEY)
    assert profiles.user.tolist() == [0, 1, 2] and not {"member_id", "phone"} & set(profiles.columns)
    assert mapping.sort_values("pseudonym").user.tolist() == [0, 1, 2]           # 연속 번호 = 가명 정렬 순서
    assert list(mapping.columns) == ["external_id", "pseudonym", "user"] and set(mapping.external_id) == {"A-9", "B-2", "C-7"}
    m = dict(zip(mapping.external_id, mapping.user))
    assert profiles.set_index("user").loc[m["B-2"], "age"] == 47                 # 원값은 학습 입력에만(분위 경계 계산)
    assert (log.day == 0).all() and (log.minute == 0).all() and not {"member_id", "ip"} & set(log.columns)
    b2 = log[log.user == m["B-2"]]
    assert b2.item.tolist() == [4, 0, 2] and b2.hour.tolist() == [0, 0, 3]        # 주·분 순서로 정렬, 시간대 = 출근·출근·심야
    Dataset(profiles, log, Catalog.default())                                     # 학습 입력 스키마로 바로 읽힌다


def test_pseudonymize_cli_requires_env_key_and_external_mapping(tmp_path, monkeypatch):
    prof, raw_log = _raw_inputs()
    pc, lc = tmp_path / "raw_profiles.csv", tmp_path / "raw_log.csv"
    prof.to_csv(pc, index=False); raw_log.to_csv(lc, index=False)
    out, vault = tmp_path / "train_in", tmp_path / "vault" / "mapping.csv"
    args = ["pseudonymize", "--profiles", str(pc), "--log", str(lc), "--id-col", "member_id", "--out", str(out)]
    monkeypatch.delenv(privacy.KEY_ENV, raising=False)
    with pytest.raises(SystemExit) as e:
        cli.main(args + ["--mapping-out", str(vault)])
    assert e.value.code not in (0, None) and not out.exists() and not vault.exists()
    monkeypatch.setenv(privacy.KEY_ENV, KEY)
    with pytest.raises(SystemExit):
        cli.main(args + ["--mapping-out", str(out / "mapping.csv")])               # 매핑표를 학습 입력 폴더 안에 두면 거부
    cli.main(args + ["--mapping-out", str(vault)])
    assert sorted(os.listdir(out)) == ["profiles.csv", "study_log.csv"] and vault.exists()
    text = (out / "profiles.csv").read_text(encoding="utf-8-sig") + (out / "study_log.csv").read_text(encoding="utf-8-sig")
    assert not any(s in text for s in ("A-9", "B-2", "C-7", "010-", "1.2.3.4"))
    assert set(pd.read_csv(vault, encoding="utf-8-sig").external_id) == {"A-9", "B-2", "C-7"}


# ---------------- k-익명성 ----------------
def _crafted_frame():
    base = dict(age_band="30대", income_q="소득 2분위", gender="남성", exp="없음", risk="안정", goal="연금·노후 대비", horizon="5년 이상", mobile="모바일")
    rows = [base] * 10 + [dict(base, age_band="50대")] * 10 + [dict(base, age_band="60세 이상")] * 3 + [dict(base, goal="단기 매매·전술적 투자")] * 3
    return pd.DataFrame(rows, dtype=object)


def test_enforce_k_anonymity_generalizes_then_suppresses():
    df = _crafted_frame()
    assert not k_anonymity(df, QUASI_IDENTIFIERS, 5)["satisfied"]
    out, rep = enforce_k_anonymity(df, QUASI_IDENTIFIERS, 5)
    assert rep["satisfied"] and k_anonymity(out, QUASI_IDENTIFIERS, 5)["satisfied"] and rep["final_min_group"] == 6
    assert [s["column"] for s in rep["steps"][1:]] == [c for c, _ in privacy.DEFAULT_HIERARCHY]      # 계층을 끝까지 적용해도 부족
    assert not rep["steps"][-1]["satisfied"] and rep["suppressed_rows"] == 6 and rep["suppressed_values"] == 12
    assert rep["removed_rows"] == 0 and rep["rows_out"] == len(out) == len(df)
    assert set(out.age_band) == {"39세 이하", "40~59세", "*"} and (out.gender == "*").all()
    # 이미 k를 만족하면 아무것도 바꾸지 않는다
    same, rep2 = enforce_k_anonymity(df.iloc[:20], QUASI_IDENTIFIERS, 5)
    assert rep2["satisfied"] and len(rep2["steps"]) == 1 and rep2["suppressed_rows"] == 0 and same.equals(df.iloc[:20].reset_index(drop=True))
    # k를 만들 수 없는 행은 삭제하고, 모두 삭제되면 satisfied=False
    gone, rep3 = enforce_k_anonymity(df.iloc[:3], QUASI_IDENTIFIERS, 5)
    assert rep3["removed_rows"] == 3 and len(gone) == 0 and not rep3["satisfied"]
    with pytest.raises(ValueError):
        enforce_k_anonymity(df.drop(columns=["mobile"]), QUASI_IDENTIFIERS, 5)


def test_k_anonymity_reports_missing_columns():
    df = pd.DataFrame(dict(age_band=[0] * 6, gender=[0] * 6))
    r = k_anonymity(df, ["age_band", "income_q", "gender"], k=5)
    assert r["missing"] == ["income_q"] and r["columns"] == ["age_band", "gender"] and r["min_group"] == 6 and not r["satisfied"]
    assert k_anonymity(df, ["age_band", "gender"], k=5)["satisfied"]
    assert not generalization_plan(df, ["age_band", "income_q", "gender"], k=5)["satisfied"]       # 열이 빠지면 계획도 불충족


def test_generalization_plan_flags_impossible():
    df = pd.DataFrame(dict(a=[0, 1, 2], b=[0, 0, 1]))
    plan = generalization_plan(df, ["a", "b"], k=5)
    assert plan["impossible"] and not plan["satisfied"] and plan["kept"] is None and plan["steps"][-1]["remaining"] == []


# ---------------- 감사·QA ----------------
def test_router_leaf_audit_matches_router_levels(small_bundle):
    b = small_bundle
    assert set(b.privacy["router_leaves"]) == set(b.routers)
    for name, rt in b.routers.items():
        a = b.privacy["router_leaves"][name]
        N = np.asarray(rt.levels[-1]["N"])
        assert a == router_leaf_audit(rt) and a["variables"] == list(rt.order)
        assert a["leaves"] == len(N) and a["leaves_below"] == int((N < 20).sum()) and a["min_leaf"] == int(N.min())
        assert a["users_in_small_leaves"] == int(N[N < 20].sum()) and a["users"] == int(N.sum())
        assert a["decision_min_n"] >= rt.min_users                       # 챔피언 추정은 20명 이상 노드의 평균으로만
        ch = np.asarray(rt.levels[-1]["champ"])
        assert a["lam"] == float(rt.lam) and a["distinct_leaf_champions"] == len(np.unique(ch))
        assert a["leaf_champion_is_root_share"] == float(np.mean(ch == rt.levels[0]["champ"][0]))
    assert b.privacy["router_leaves"]["RouterNoGender"]["leaves_below"] > 0   # MIN_ROUTER_USERS는 잎 크기를 보장하지 않는다
    q = b.privacy["quasi"]
    assert q["requested"] == list(QUASI_IDENTIFIERS) and q["missing"] == [] and q["k"] == 5
    assert b.privacy["stored"]["quasi_in_store"] == list(QUASI_IDENTIFIERS) and b.privacy["release"]["satisfied"]


def test_privacy_qa_checks_present_passing_and_effective(small_bundle):
    qa = {q["test"]: q for q in small_bundle.qa}
    for name in privacy.CHECK_NAMES:
        assert name in qa and qa[name]["passed"], name
    bad = {"bundle_profiles_no_raw_age_income": dict(profiles=small_bundle.profiles.assign(age=30)),
           "bundle_log_no_day_minute": dict(log=small_bundle.log.assign(minute=0)),
           "feature_store_no_raw_age_income": dict(store=copy.copy(small_bundle.store)),
           "published_group_cells_ge_5": dict(group_results=small_bundle.group_results.assign(users=3)),
           "privacy_audit_columns_complete": dict(privacy=dict(small_bundle.privacy, router_leaves={}))}
    bad["feature_store_no_raw_age_income"]["store"].income = np.ones(small_bundle.store.n)
    for name, change in bad.items():
        b = copy.copy(small_bundle)
        for k, v in change.items():
            setattr(b, k, v)
        assert not dict((n, ok) for n, ok, _ in privacy.privacy_checks(b))[name], name
    m = json.loads(json.dumps(small_bundle.manifest(), ensure_ascii=False))
    assert m["privacy"]["policy"]["implemented"] and m["privacy"]["policy"]["organizational"]
    assert all(p["enforced_by"] for p in m["privacy"]["policy"]["implemented"])


def test_design_save_replaces_raw_age_income_with_bands(small_bundle, tmp_path):
    c = TestClient(create_app(small_bundle, designs_dir=str(tmp_path)))
    edges = small_bundle.store.income_edges
    q = int(income_quintile(np.array([5230.0]), edges)[0][0])
    payload = {"summary": "홍길동 47세 · 연봉 5,230만원", "memo": "47살, 연소득 5230만원",
               "state": {"learner": {"label": "홍길동 47세", "age": 47, "income": 5230, "gender": 0, "goal": "income"},
                         "nl": {"text": "47세 직장인, 연봉 5230만원", "parsed": {"fields": {"age": 47, "income": 5230.0},
                                "evidence": [{"field": "age", "value": 47, "matched": "47세"},
                                             {"field": "income", "value": 5230.0, "matched": "연봉 5230만원"}], "text": "47세 직장인, 연봉 5230만원"}},
                         "sim": {"age_band": "", "income_q": ""}},
               "result": {"learner": {"profile": {"연령": 47, "연소득(만원)": 5230, "투자 목적": "배당·인컴 수취"}}}}
    assert c.post("/api/designs", json={"name": "p1", "payload": payload}).status_code == 200
    saved = json.loads((tmp_path / "p1.json").read_text(encoding="utf-8"))
    keys, strings = _keys_and_strings(saved)
    assert not RAW_KEYS & keys
    assert not any(("47" in s and "세" in s) or "5230" in s or "5,230" in s or "47살" in s for s in strings)
    L = saved["payload"]["state"]["learner"]
    assert L["age_band"] == 2 and L["income_q"] == q and L["goal"] == "income"
    assert saved["payload"]["result"]["learner"]["profile"]["연령대"] == "40대"
    assert saved["payload"]["state"]["nl"]["parsed"]["evidence"][0] == {"field": "age_band", "value": 2, "matched": "40대"}
    assert saved["payload"]["state"]["nl"]["text"].startswith("[40대] 직장인") and saved["payload"]["state"]["sim"] == {"age_band": "", "income_q": ""}
    got = c.get("/api/designs/p1").json()                                    # 불러올 때는 구간 대표값(원값 아님)
    G = got["payload"]["state"]["learner"]
    assert G["age"] == 45 and G["income"] == small_bundle.store.income_rep[q] and G["band_representative"] == ["age", "income"]
    assert G["age"] != 47 and G["income"] != 5230 and not ({"연령", "연소득(만원)"} & _keys_and_strings(got)[0])
    assert c.get("/api/designs").json()[0]["summary"] == saved["summary"]


def test_export_deid_cli_writes_k_anonymous_table(small_bundle, tmp_path):
    bdir = tmp_path / "bundle"
    small_bundle.save(str(bdir))
    lp = pd.read_csv(bdir / "learner_profiles.csv", encoding="utf-8-sig")
    assert {"연령대", "소득분위"} <= set(lp.columns) and not RAW_KEYS & set(lp.columns)
    out = tmp_path / "share" / "learners_k5.csv"
    cli.main(["export-deid", "--bundle", str(bdir), "--k", "5", "--out", str(out)])
    t = pd.read_csv(out, encoding="utf-8-sig", dtype=str)
    assert list(t.columns) == [privacy.RELEASE_HEADERS[c] for c in QUASI_IDENTIFIERS]
    assert t.groupby(list(t.columns), dropna=False).size().min() >= 5
    rep = json.loads((tmp_path / "share" / "learners_k5_report.json").read_text(encoding="utf-8"))
    assert rep["satisfied"] and rep["verified"] and rep["rows_in"] == small_bundle.store.n and rep["rows_out"] == len(t)
    assert rep["not_released"] == ["user", "interest1", "interest2", "placement"]
