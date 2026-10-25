"""개인정보 최소화·가명처리·반출 k-익명화·감사 검사(etfrec.privacy)."""
import copy
import hashlib
import hmac
import json
import os
from datetime import date

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
                            pseudonymize_ids, router_leaf_audit, scrub_text)
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


def test_route_path_shows_size_bands_only(small_bundle):
    """경로 출력은 노드 크기를 구간으로만 내고 원시 평균을 내지 않는다(부모 − 형제 차분으로 숨긴 노드를 복원하지 못하게)."""
    from etfrec.router import size_band
    svc = RecommendationService(small_bundle)
    labels = set()
    for name in small_bundle.routers:
        for uid in small_bundle.test_users[:20]:
            for p in svc.recommend(int(uid), k=5, algorithm=name)["route_path"]:
                assert p["n"] is None and p["raw"] is None and p["raw_best"] is None and p["raw_champ"] is None
                labels.add(p["n_label"])
    assert "20명 미만" in labels and all(l.endswith("명") or l.endswith("명 이상") or l.endswith("명 미만") for l in labels)
    assert [size_band(n) for n in (3, 19, 20, 49, 50, 199, 200, 499, 500, 9999)] == \
        ["20명 미만", "20명 미만", "20~49명", "20~49명", "50~99명", "100~199명", "200~499명", "200~499명", "500명 이상", "500명 이상"]


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
    stream = pd.concat([raw_log.assign(session_id=[f"x{i}" for i in range(5)]),                        # 같은 세션의 두 번째 이벤트(완료)
                        raw_log.iloc[[2]].assign(session_id="x2", complete=1, drop=0, minute=raw_log.minute[2] + 9)])
    _, log2, _ = build_pseudonymized_inputs(prof, stream, "member_id", KEY)
    assert len(log2) == 5 and "session_id" not in log2.columns                    # 시도 단위로 묶고 세션 ID는 버린다
    assert log2[(log2.user == m["B-2"]) & (log2["item"] == 2)].complete.tolist() == [True]


@pytest.mark.parametrize("bad_id", [None, np.nan, pd.NA, "", "  ", "\t\n"])
@pytest.mark.parametrize("table", ["profiles", "log"])
def test_pseudonymize_rejects_missing_external_ids_before_string_conversion(bad_id, table):
    prof, raw_log = _raw_inputs()
    frame = prof if table == "profiles" else raw_log
    frame.loc[0, "member_id"] = bad_id
    with pytest.raises(ValueError, match=f"{table}.*외부 ID.*빈 값"):
        build_pseudonymized_inputs(prof, raw_log, "member_id", KEY)


@pytest.mark.parametrize("state", [[1], "corrupt", 3, True, None])
def test_hydrate_design_tolerates_non_mapping_state(state):
    payload = {"state": state, "memo": "설계 메모"}
    result = privacy.hydrate_design(payload, np.array([1000, 2000, 3000, 4000, 5000]))
    assert result == payload and result is not payload


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
    assert "result" not in saved["payload"]                                   # 서버 출력(추천 결과의 학습자 프로필)은 저장하지 않는다
    assert privacy.scrub_design(payload["result"], edges)["learner"]["profile"]["연령대"] == "40대"   # 학습자 표 꼴(연령 → 연령대)도 가린다
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



# ---------------- 최종 검토(개인정보) 반영 ----------------
def test_extra_log_columns_never_reach_the_bundle(small_bundle):
    """외부 회원 ID·분 단위 시각·IP 같은 학습 스키마 밖 열은 읽을 때 버리고(요약에 이름 기록), 번들 로그는 허용 열만 남긴다."""
    from etfrec.config import TrainConfig
    ds = Dataset.synthetic(TrainConfig(n_learners=120))
    log = ds.log.assign(user_id=[f"M{u:05d}" for u in ds.log.user], event_ts="2026-09-07 08:38:00", ip="203.0.113.0")
    prof = ds.profiles.assign(member_id=[f"M{u:05d}" for u in ds.profiles.user])
    d2 = Dataset(profiles=prof, log=log, catalog=ds.catalog)
    assert set(d2.summary()["dropped_columns"]["log"]) == {"user_id", "event_ts", "ip"}
    assert d2.summary()["dropped_columns"]["profiles"] == ["member_id"] and not {"user_id", "ip", "event_ts"} & set(d2.log.columns)
    lg, dropped = privacy.minimize_log(log, return_dropped=True)
    assert set(lg.columns) <= set(privacy.LOG_STORED_COLUMNS) and {"user_id", "event_ts", "ip", "day", "minute"} <= set(dropped)
    b = copy.copy(small_bundle)
    b.log = small_bundle.log.assign(ip="203.0.113.0")                         # 허용 목록 밖 열이 남으면 QA가 실패한다
    assert not dict((n, ok) for n, ok, _ in privacy.privacy_checks(b))["bundle_log_no_day_minute"]
    st = small_bundle.privacy["stored"]
    assert st["log_columns"] == list(small_bundle.log.columns) and not st["unclassified"]
    ut = small_bundle.privacy["users_table"]
    assert ut["quasi_extended"]["requested"][-2:] == ["학습 시간대", "관심 주제"] and not ut["unclassified"]
    assert ut["quasi_extended"]["users_below_k"] >= ut["quasi"]["users_below_k"]


def test_export_rows_do_not_follow_user_order(small_bundle):
    table, rep = privacy.export_deid(small_bundle, k=5)
    gen, _ = enforce_k_anonymity(privacy.release_frame(privacy.stored_profiles(small_bundle)), QUASI_IDENTIFIERS, 5)
    gen = gen.astype(str).rename(columns=privacy.RELEASE_HEADERS)
    same = (table.values == gen.values).all(1).mean()                           # i행 = user i인 비율(정렬 전에는 1.0)
    assert same < 0.5 and rep["row_order"].startswith("반출 값 기준 정렬")
    assert table.equals(table.sort_values(list(table.columns), kind="stable").reset_index(drop=True))


def test_api_accepts_only_listed_methods_unless_dev_mode(small_bundle, tmp_path):
    fam = {int(v) for v in small_bundle.selection["families"].values()}
    other = next(i for i, a in enumerate(small_bundle.algos) if i not in fam and a.family == "SEGPOP")
    svc = RecommendationService(small_bundle)
    with pytest.raises(ValueError):
        svc.recommend(1, k=5, algorithm=other)
    with pytest.raises(ValueError):
        svc.recommend(1, k=5, algorithm=str(other))
    assert svc.recommend(1, k=5, algorithm=min(fam))["algorithm_id"] == min(fam)
    assert RecommendationService(small_bundle, allow_any_config=True).recommend(1, k=5, algorithm=other)["algorithm_id"] == other
    c = TestClient(create_app(small_bundle, designs_dir=str(tmp_path)))
    assert c.post("/api/recommend", json={"learner_id": 1, "k": 5, "algorithm": other}).status_code == 422
    assert c.post("/api/compare", json={"learner_id": 1, "k": 5, "methods": [str(other)]}).status_code == 422
    dev = TestClient(create_app(small_bundle, designs_dir=str(tmp_path), allow_any_config=True))
    assert dev.post("/api/recommend", json={"learner_id": 1, "k": 5, "algorithm": other}).status_code == 200


def test_learner_lookup_can_be_switched_off(small_bundle, tmp_path):
    c = TestClient(create_app(small_bundle, designs_dir=str(tmp_path), expose_learners=False))
    assert c.get("/api/learners").status_code == 403 and c.get("/api/learners/1").status_code == 403
    assert c.post("/api/recommend", json={"learner": {"age": 30, "interests": [1]}, "k": 3}).status_code == 200
    for path in ("/api/recommend", "/api/compare", "/api/roadmap", "/api/types"):     # 기준 학습자 번호로 프로필·통과 단원을 열거하지 못한다
        assert c.post(path, json={"learner_id": 7}).status_code == 403, path
    on = TestClient(create_app(small_bundle, designs_dir=str(tmp_path)))
    assert all(on.post(p, json={"learner_id": 7}).status_code == 200 for p in ("/api/recommend", "/api/roadmap", "/api/types"))
    assert cli.LOOPBACK == ("127.0.0.1", "localhost", "::1")


def test_scrub_text_masks_whole_keywordless_amounts():
    E = [3020, 4110, 5350, 7282]
    cases = {"1억 2천만원": "[금액]", "1억2천만원": "[금액]", "5,000만원": "[금액]", "7000만원": "[금액]", "1억원": "[금액]", "1.5억원": "[금액]",
             "연봉 1억 2천만원": "[소득 5분위(상위 20%)]",
             "연소득은 7천만원, 1억 2천만원, 5천만원, 45세 이상": "[소득 4분위], [금액], [금액], [40대] 이상",
             "ISA는 연 2,000만원, 총 1억원까지 납입 가능. 비과세 200만원.": "ISA는 연 [금액], 총 [금액]까지 납입 가능. 비과세 [금액].",
             "국내 ETF 투자자 600만 명, 순자산 100억": "국내 ETF 투자자 600만 명, 순자산 100억",       # '원'이 없는 수치는 금액으로 보지 않는다
             "연금소득 1,500만원 넘으면": "연금소득 [금액] 넘으면", "소득 3분위": "소득 3분위"}
    for text, want in cases.items():
        assert scrub_text(text, E) == want, (text, scrub_text(text, E))


def test_scrub_text_reads_more_income_and_age_forms():
    E = [3020, 4110, 5350, 7282]
    q5, q4, q2 = "[소득 5분위(상위 20%)]", "[소득 4분위]", "[소득 2분위]"
    cases = {"연봉 1억 2000만원": q5, "연봉 1억 2,000만원": q5, "연소득 1.2억": q5, "연봉 6천": q4, "연봉 6천5백": q4, "연봉 65,000,000원": q4,
             "연소득 6000": q4, "월급 450만원": q4, "월 소득 300만원": q2, "내 소득은 5천만원이야": "내 [소득 3분위]이야",   # 월급은 12배(연 5,400만원)
             "연봉 2025년 기준": "연봉 2025년 기준", "65세": "[60세 이상]", "25세 직장인": "[29세 이하] 직장인",
             "연봉 6000 세후로는 적어": f"{q4} 세후로는 적어", "연봉 4800 회사원": "[소득 3분위] 회사원", "연봉 5,000 정도": "[소득 3분위] 정도",
             "연봉 60000000원": q4, "연봉 60,000,000": q4, "연봉 5000 월급 400": "[소득 3분위] [소득 3분위]", "연봉 2024 기준 5천만원": "연봉 2024 기준 [금액]",
             "한 달 수입 400만원인 직장인": "[소득 3분위]인 직장인", "부업 수입 50만원": "부업 수입 [금액]"}   # 띄어 쓴 다음 낱말은 단위가 아니다
    born = date.today().year - 1980
    want_born = "[" + privacy._label("age_band", privacy._age_code(born)) + "]"
    cases.update({"1980년생": want_born, "80년생": want_born})
    for text, want in cases.items():
        got = scrub_text(text, E)
        assert got == want, (text, got)
        assert scrub_text(got, E) == got, text                       # 불러올 때 다시 가려도 같다('[60세 이상]'이 '[[60세 이상] 이상]'이 되지 않음)
    assert privacy.income_from_text("45세 직장인, 연소득 1억 2천만원, 연금 준비") == (12000.0, "연소득 1억 2천만원")
    assert privacy.income_from_text("목돈 5000만원 있음")[0] is None and privacy.income_from_text("연금소득 1,500만원")[0] is None
    for text in ("연봉 " + "9" * 400 + "억", "연소득 1" + "0" * 400 + ".5억"):                 # 아주 긴 숫자도 예외 없이 처리한다
        assert scrub_text(text, E) == scrub_text(scrub_text(text, E), E) and privacy.income_from_text(text)[0] is None


def c_parse(bundle, text):
    return TestClient(create_app(bundle)).post("/api/parse", json={"text": text}).status_code


def test_design_save_drops_server_outputs_and_hides_learner_designs_when_lookup_is_off(small_bundle, tmp_path):
    on = TestClient(create_app(small_bundle, designs_dir=str(tmp_path)))
    rec = on.post("/api/recommend", json={"learner_id": 7, "k": 5}).json()
    rm = on.post("/api/roadmap", json={"learner_id": 7}).json()
    payload = {"summary": "#7 · 장기", "memo": "ISA는 연 2,000만원까지", "result": rec, "roadmap": rm,
               "state": {"source": "existing", "learnerId": 7, "learnerInfo": {"user": 7, "profile": {"성별": "여성"}}, "result": rec, "roadmap": rm}}
    assert on.post("/api/designs", json={"name": "existing7", "payload": payload}).status_code == 200
    saved = json.loads((tmp_path / "existing7.json").read_text(encoding="utf-8"))
    keys, _ = _keys_and_strings(saved)
    assert not keys & {"result", "roadmap", "learnerInfo", "profile", "topic_map", "history"} and saved["saved_with_learners"] is True
    assert saved["payload"]["memo"] == "ISA는 연 [금액]까지" and saved["payload"]["state"]["learnerId"] == 7
    off = TestClient(create_app(small_bundle, designs_dir=str(tmp_path), expose_learners=False))
    assert off.get("/api/designs").json() == [] and off.get("/api/designs/existing7").status_code == 404   # 켠 서버에서 저장한 설계는 내려보내지 않는다
    assert off.post("/api/designs", json={"name": "public1", "payload": {"summary": "새 학습자", "state": {"source": "new"}}}).status_code == 200
    assert [d["name"] for d in off.get("/api/designs").json()] == ["public1"] and off.get("/api/designs/public1").status_code == 200
    legacy = dict(saved); legacy.pop("saved_with_learners"); legacy["name"] = "legacy"; legacy["payload"] = dict(saved["payload"], result=rec)
    (tmp_path / "legacy.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    assert off.get("/api/designs/legacy").status_code == 404                   # 표시가 없는 이전 파일도 켠 서버의 것으로 본다
    got = on.get("/api/designs/legacy").json()
    assert "result" not in got["payload"] and [d["name"] for d in on.get("/api/designs").json()] == ["existing7", "legacy", "public1"]
    assert off.post("/api/designs", json={"name": "existing7", "payload": {"summary": "x"}}).status_code == 409   # 볼 수 없는 설계는 덮어쓰지도
    assert off.delete("/api/designs/existing7").status_code == 404 and (tmp_path / "existing7.json").exists()  # 지우지도 못한다
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert on.get("/api/designs").status_code == 200 and off.get("/api/designs").status_code == 200        # 깨진 파일 하나가 목록을 막지 않는다
    assert c_parse(small_bundle, "연봉 " + "9" * 400 + "억") == 200


def test_design_scrub_covers_names_lists_events_and_more_forms(small_bundle, tmp_path):
    c = TestClient(create_app(small_bundle, designs_dir=str(tmp_path)))
    payload = {"summary": "45세 이상 직장인, 연금 관심, 연봉 1억 2천만원",
               "state": {"learner": {"age": "45살", "income": "5000만원"}, "nl": {"parsed": {"warnings": ["'45세 직장인'와 일치하는 단원 제목을 찾지 못했습니다.",
                                                                                                         "'연봉 5000만원'와 일치하는 단원 제목을 찾지 못했습니다."]}},
                         "events": [{"item": 3, "week": 0, "day": 2, "hour": 20, "minute": 4085, "complete": True}],
                         "memo": "나이는 52세이고 연소득은 7000만원", "odd": {"age": [45], "income": {"value": 5000}}},
               "result": {"learner": {"profile": {"연령": "45세", "연소득(만원)": "5,000만원"}}}}
    r = c.post("/api/designs", json={"name": "45세 연봉 5000만원 홍길동", "payload": payload})
    assert r.status_code == 200
    files = os.listdir(tmp_path)
    assert len(files) == 1 and "45세" not in files[0] and "5000" not in files[0]
    saved = json.loads((tmp_path / files[0]).read_text(encoding="utf-8"))
    keys, strings = _keys_and_strings(saved)
    text = " ".join(strings)
    assert not RAW_KEYS & keys and "day" not in keys and "minute" not in keys
    assert not any(x in text for x in ("45세", "45살", "52세", "5000만원", "5,000만원", "7000만원", "1억", "2천만원"))
    ev = saved["payload"]["state"]["events"][0]
    assert ev["hour"] in (0, 1, 2, 3) and ev["item"] == 3
    assert saved["payload"]["state"]["learner"]["age_band"] == 2 and saved["payload"]["state"]["odd"] == {"age_band": None, "income_q": None}
    assert c.get("/api/designs").json()[0]["name"] == saved["name"]


def test_group_suppression_is_complementary():
    df = pd.DataFrame(dict(method="M", variable=["age_band"] * 4 + ["gender"] * 2, group=[0, 1, 2, 3, 0, 1],
                           users=[3, 40, 50, 60, 70, 83], active_users=[1, 20, 4, 30, 40, 9], ndcg_active=[0.5, 0.3, 0.2, 0.1, 0.2, 0.3]))
    out, rep = privacy.suppress_small_groups(df, 5)
    assert rep["rows_removed"] == 2 and rep["complementary_removed"] == 1 and rep["single_suppressed_partitions"] == 0
    age = out[out.variable == "age_band"]
    assert list(age.group) == [2, 3] and age.ndcg_active.isna().sum() == 2         # 활성 4명 집단과 가장 작은 다른 집단을 함께 비움
    assert out[out.variable == "gender"].ndcg_active.notna().all()


def test_pseudonymize_rejects_mapping_inside_input_via_symlink(tmp_path, monkeypatch):
    raw_p, raw_l = _raw_inputs()
    (tmp_path / "train_in").mkdir()
    os.symlink(tmp_path / "train_in", tmp_path / "vault")
    raw_p.to_csv(tmp_path / "p.csv", index=False); raw_l.to_csv(tmp_path / "l.csv", index=False)
    monkeypatch.setenv(privacy.KEY_ENV, KEY)
    with pytest.raises(SystemExit) as e:
        cli.main(["pseudonymize", "--profiles", str(tmp_path / "p.csv"), "--log", str(tmp_path / "l.csv"), "--id-col", "member_id",
                  "--out", str(tmp_path / "train_in"), "--mapping-out", str(tmp_path / "vault" / "mapping.csv")])
    assert "매핑표" in str(e.value) and not (tmp_path / "train_in" / "mapping.csv").exists()
    assert cli._paths_overlap(str(tmp_path / "a"), str(tmp_path / "a" / "b")) and not cli._paths_overlap(str(tmp_path / "a"), str(tmp_path / "b"))
