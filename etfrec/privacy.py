"""개인정보: 저장 최소화·가명처리·반출 k-익명화·감사(리뷰 지적 반영). 코드가 실제로 하는 일만 적는다.

1. 저장 최소화 — 모델은 연령대·소득분위 구간 코드만 쓴다. 원시 연령·연소득은 학습 중 메모리에서 소득 5분위 경계를
   계산하는 데만 쓰고 번들에 남기지 않는다. 특징 저장소(features.FeatureStore)에는 원값 필드가 없고, 번들 프로필은
   generalize_profiles, 번들 로그는 minimize_log(일·분 삭제)를 거친다. 저장 설계는 scrub_design이 원값을 구간 코드로 바꾼다.
2. 가명처리 — pseudonymize_ids·build_pseudonymized_inputs(CLI ``pseudonymize``): 외부 회원 ID → HMAC-SHA256 가명 → 연속 번호.
   운영 원본을 학습 입력으로 바꾸는 도구이며 모의 데이터 학습에는 쓰지 않는다(모의 데이터에는 외부 ID가 없다).
3. 반출 k-익명화 — enforce_k_anonymity(CLI ``export-deid``): 일반화 계층을 한 단계씩 적용하고 남은 작은 셀은 국소 억제한다.
   모델 학습 입력은 일반화하지 않는다(학습 결과가 바뀐다). 학습은 접근 통제된 환경에서 가명 데이터로 하고,
   밖으로 나가는 학습자 표는 export-deid를 거친다.
4. 감사·검사 — privacy_audit 결과는 Bundle.privacy에 담겨 manifest.json의 ``privacy``와 /api/evaluation의 ``privacy``로 나간다.
   privacy_checks의 5개 검사는 pipeline.run_qa가 번들 조립 직후·저장 전에 실행해 manifest ``qa``에 남기며,
   하나라도 실패하면 학습이 멈추고 번들은 저장되지 않는다.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import re

import numpy as np
import pandas as pd

from .catalog import EXPS, LABELS, RISKS
from .config import GOALS, HORIZONS, SEG_VARS
from .data import OPTIONAL_PROFILE_COLUMNS, PROFILE_COLUMNS
from .features import AGE_BAND_REP, AGE_CUTS, income_quintile
from .synth import LOG_COLUMNS

K_RELEASE = 5                       # 반출·공개 표의 최소 셀 크기
MIN_LEAF_DISPLAY = 20               # 라우터 경로 출력에서 정확한 n을 보여 주는 최소 노드 크기
QUASI_IDENTIFIERS = ("age_band", "income_q", "gender", "exp", "risk", "goal", "horizon", "mobile")   # 번들에 저장되는 준식별자
STORED_PROFILE_COLUMNS = ("user", "age_band", "income_q", "gender", "exp", "risk", "mobile", "interest1", "interest2",
                          "placement", "goal", "horizon")
COLUMN_ROLES = {"user": "가명 번호(0부터 연속)", **{c: "준식별자(감사·반출 대상)" for c in QUASI_IDENTIFIERS},
                "interest1": "학습 속성(관심 주제, 반출 안 함)", "interest2": "학습 속성(관심 주제, 반출 안 함)",
                "placement": "학습 속성(진단 수준, 반출 안 함)"}
RAW_PROFILE_COLUMNS = ("age", "income", "연령", "연소득(만원)")
RAW_TIME_COLUMNS = ("day", "minute")
ACTIVE_COLUMNS = ("active_users", "active_share", "ndcg_active", "ci_low_active", "ci_high_active")
KEY_ENV = "ETFREC_PSEUDO_KEY"
MIN_KEY_LENGTH = 16
CHECK_NAMES = ("bundle_profiles_no_raw_age_income", "bundle_log_no_day_minute", "feature_store_no_raw_age_income",
               "published_group_cells_ge_5", "privacy_audit_columns_complete")
RECORDED_IN = ("Bundle.privacy → manifest.json 'privacy', /api/evaluation 'privacy'. 검사(실패 시 학습 중단·번들 미저장)는 "
               "manifest 'qa'의 " + ", ".join(CHECK_NAMES))

# 반출 표의 이름과 일반화 계층(위에서부터 한 단계씩 적용, 모든 셀 ≥ k이면 멈춘다)
RELEASE_HEADERS = {"age_band": "연령대", "income_q": "소득분위", "gender": "성별", "exp": "투자 경험", "risk": "위험성향",
                   "goal": "투자 목적", "horizon": "투자 기간", "mobile": "기기"}
_AGE, _INC = LABELS["age_band"], LABELS["income_q"]
DEFAULT_HIERARCHY = (
    ("gender", {g: "*" for g in LABELS["gender"]}),                                                     # 2 → 억제
    ("mobile", {"PC": "*", "모바일": "*"}),                                                              # 2 → 억제
    ("exp", {EXPS[0]: "없음", EXPS[1]: "있음", EXPS[2]: "있음"}),                                         # 3 → 2
    ("risk", {RISKS[0]: "안정", RISKS[1]: "중립·적극", RISKS[2]: "중립·적극"}),                            # 3 → 2
    ("horizon", {HORIZONS["short"]: "5년 미만", HORIZONS["mid"]: "5년 미만", HORIZONS["long"]: "5년 이상"}),  # 3 → 2
    ("goal", {GOALS["pension"]: "노후·인컴", GOALS["income"]: "노후·인컴", GOALS["long_term"]: "장기·분산",
              GOALS["diversify"]: "장기·분산", GOALS["trading"]: "단기 매매"}),                              # 5 → 3
    ("income_q", {_INC[0]: "소득 하위 40%", _INC[1]: "소득 하위 40%", _INC[2]: "소득 중위 20%",
                  _INC[3]: "소득 상위 40%", _INC[4]: "소득 상위 40%"}),                                       # 5 → 3
    ("age_band", {_AGE[0]: "39세 이하", _AGE[1]: "39세 이하", _AGE[2]: "40~59세", _AGE[3]: "40~59세",
                  _AGE[4]: "60세 이상"}),                                                                # 5 → 3
)

POLICY_IMPLEMENTED = [
    dict(item="원시 연령·연소득 비저장: 학습 중 메모리에서 소득 5분위 경계 계산에만 쓰고, 번들 프로필·특징 저장소·learner_profiles.csv에는 "
              "연령대·소득분위 구간만 남긴다(모델은 원래 구간 코드만 쓰므로 학습 결과는 같다)",
         enforced_by=["privacy.generalize_profiles", "features.FeatureStore(age·income 필드 없음)",
                      "QA bundle_profiles_no_raw_age_income", "QA feature_store_no_raw_age_income"]),
    dict(item="학습 이력 시각 축약: 번들 로그는 주차·4개 시간대·주 안 순서(seq)만 남기고 일(day)·분(minute)은 버린다",
         enforced_by=["privacy.minimize_log", "QA bundle_log_no_day_minute"]),
    dict(item="API 최소화: /api/learners·학습자 상세는 연령대·소득분위 코드와 이름만 반환하고, 소득 미입력 대체값은 학습 때 저장한 중앙값(집계)을 쓴다",
         enforced_by=["service.RecommendationService.learners/learner", "FeatureStore.income_median",
                      "tests/test_privacy.py"]),
    dict(item="저장 설계 최소화: /api/designs는 쓰기 전에 연령·연소득 원값을 구간 코드로 바꾸고 자유 입력 문장의 연령·소득 표현을 구간 이름으로 가린다",
         enforced_by=["privacy.scrub_design", "api.save_design"]),
    dict(item="작은 셀 비공개: 추천 경로 출력에서 20명 미만 라우터 노드는 n=null·'20명 미만'으로만 표시하고 그 노드의 원시 평균을 숨긴다. "
              "집단별 표(group_results·advanced_exposure)는 5명 미만 집단을 빼고 활성 5명 미만이면 활성 기준 값을 비운다",
         enforced_by=["router.ShrinkRouter.path", "privacy.suppress_small_groups", "QA published_group_cells_ge_5"]),
    dict(item="감사 기록: 저장 준식별자 8개 조합의 k=5 결과·열 제거 일반화 계획·export-deid 일반화 요약·실제 라우터 잎 크기를 기록하고, "
              "감사가 저장 열을 빠짐없이 다루는지 확인한다",
         enforced_by=["privacy.privacy_audit", "QA privacy_audit_columns_complete"]),
    dict(item=f"가명처리 도구(운영 원본용, 모의 데이터 학습에는 쓰지 않음): 외부 회원 ID → HMAC-SHA256 가명(16자) → 가명 순서 연속 번호. "
              f"키는 환경변수 {KEY_ENV}에서만 읽고 없거나 {MIN_KEY_LENGTH}자 미만이면 거부, 매핑표는 --mapping-out에만 쓰며 출력 폴더 안이면 거부, "
              "학습 스키마 밖 열은 버린다",
         enforced_by=["privacy.build_pseudonymized_inputs", "cli pseudonymize"]),
    dict(item="반출 k-익명화: export-deid는 저장 프로필의 준식별자 8개 열만 일반화 계층 → 국소 억제로 k 이상(기본 5)으로 만든 뒤에만 파일을 쓴다"
              "(가명 번호·관심 주제·진단 수준은 내보내지 않는다). 모델 학습 입력은 일반화하지 않는다",
         enforced_by=["privacy.enforce_k_anonymity", "privacy.export_deid", "cli export-deid"]),
    dict(item="성별의 운영 비사용: 운영 라우터(RouterNoGender)는 성별을 쓰지 않는 설정만 후보로 두고 성별을 세그먼트에서 뺀다(성별은 저장·진단에는 남는다)",
         enforced_by=["pipeline.train router_settings(allowed_ng)", "tests/test_pipeline_service.py::test_gender_flip_invariance_operational"]),
]
POLICY_ORGANIZATIONAL = [
    "권한·망 분리: 학습 환경과 운영·가명처리 환경의 권한과 네트워크를 분리한다",
    f"역할 분리: 가명처리 담당(키 {KEY_ENV}·매핑표 보관)과 모델 학습 담당을 나누고, 학습 담당은 키·매핑표에 접근하지 않는다",
    "반출 심사: export-deid 결과를 포함해 학습 환경 밖으로 나가는 자료는 반출 전에 적정성 심사를 거친다",
    "접근 기록 감사: 학습 입력·번들·매핑표 접근 기록을 남기고 주기적으로 점검한다",
    "외부 결합·공유: 다른 기관 자료와 결합하거나 공유할 때는 개인정보 이노베이션 존(또는 결합전문기관)에 준하는 통제 환경에서만 한다",
    "보관·삭제: 학습 입력·번들·저장 설계의 보관 기간을 정해 문서화하고, 기간이 지나거나 탈퇴하면 삭제한다",
    "재식별 금지: 가명정보를 특정 개인을 알아보는 목적으로 처리하지 않고, 재식별 가능성을 발견하면 처리를 멈추고 보고한다",
]
POLICY = ([f"[구현] {p['item']} (강제·확인: {', '.join(p['enforced_by'])})" for p in POLICY_IMPLEMENTED]
          + [f"[조직 정책 — 코드가 강제하지 않음] {s}" for s in POLICY_ORGANIZATIONAL])   # 이전 형식(문자열 목록) 호환


# ============================ k-익명성 ============================
def k_anonymity(df: pd.DataFrame, cols, k: int = K_RELEASE) -> dict:
    """열 조합별 그룹 크기로 k-익명성을 계산한다. 요청한 열이 df에 없으면 조용히 빼지 않고 missing에 적으며 satisfied=False."""
    requested = list(cols)
    present = [c for c in requested if c in df.columns]
    missing = [c for c in requested if c not in df.columns]
    base = dict(columns=present, requested=requested, missing=missing, k=int(k), rows=int(len(df)))
    if len(df) == 0:
        return dict(base, groups=0, min_group=0, median_group=0.0, groups_below_k=0, users_below_k=0, share_below_k=0.0, satisfied=False)
    sizes = df.groupby(present, dropna=False).size() if present else pd.Series([len(df)])   # 열이 없으면 전체가 한 그룹
    below = sizes[sizes < k]
    return dict(base, groups=int(len(sizes)), min_group=int(sizes.min()), median_group=float(sizes.median()),
                groups_below_k=int(len(below)), users_below_k=int(below.sum()), share_below_k=float(below.sum() / len(df)),
                satisfied=bool(len(below) == 0 and not missing))


def generalization_plan(df: pd.DataFrame, cols, k: int = K_RELEASE) -> dict:
    """k를 만족할 때까지 효과가 가장 큰 열을 하나씩 빼는 제안(열 제거 = 가장 거친 일반화).
    impossible=True면 열을 모두 빼도 k에 못 미친다(전체 행 수 < k). 요청 열이 없으면 satisfied=False."""
    start = k_anonymity(df, cols, k)
    remaining = list(start["columns"])
    cur, steps = k_anonymity(df, remaining, k), []
    while not cur["satisfied"] and remaining:
        best = min(remaining, key=lambda c: k_anonymity(df, [x for x in remaining if x != c], k)["users_below_k"])
        remaining = [c for c in remaining if c != best]
        cur = k_anonymity(df, remaining, k)
        steps.append(dict(drop=best, remaining=list(remaining), min_group=cur["min_group"], users_below_k=cur["users_below_k"],
                          satisfied=cur["satisfied"]))
    reachable = bool(cur["satisfied"])
    return dict(k=int(k), requested=list(cols), missing=start["missing"], initial_satisfied=start["satisfied"], steps=steps,
                kept=remaining if reachable else None, satisfied=reachable and not start["missing"], impossible=not reachable,
                note=("요청 열 일부가 없어 계획이 불완전함" if start["missing"] else "") or
                     ("열을 모두 빼도 k 미만(전체 행 수 < k)" if not reachable else ""))


def enforce_k_anonymity(df: pd.DataFrame, quasi_cols, k: int = K_RELEASE, hierarchy=None) -> tuple:
    """반출용 k-익명화. 일반화 계층을 한 단계씩 적용하다 모든 셀이 k 이상이면 멈추고, 그래도 남은 작은 셀의 행은
    가장 구체적인 열(남은 서로 다른 값이 가장 많은 열)부터 '*'로 국소 억제한다. 모든 열이 '*'인데도 k 미만인 행은 삭제한다.
    모델 학습 입력에는 쓰지 않는다(학습 결과가 바뀐다). 반환: (일반화된 df, 보고서)."""
    hierarchy = DEFAULT_HIERARCHY if hierarchy is None else hierarchy
    cols = list(quasi_cols)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"준식별자 열이 없습니다: {missing}")
    out = df.reset_index(drop=True).copy()
    for c in cols:
        out[c] = out[c].astype(object)
    pick = lambda r: {x: r[x] for x in ("groups", "min_group", "users_below_k", "satisfied")}
    st = k_anonymity(out, cols, k)
    steps = [dict(step=0, action="원본", column=None, **pick(st))]
    for col, mapping in hierarchy:
        if st["satisfied"]:
            break
        if col not in cols:
            continue
        out[col] = out[col].map(lambda v, m=mapping: m.get(v, v)).astype(object)
        st = k_anonymity(out, cols, k)
        steps.append(dict(step=len(steps), action=f"일반화 {col}", column=col, **pick(st)))
    touched, n_values, removed = np.zeros(len(out), bool), 0, 0
    if not st["satisfied"] and len(out):
        rank = sorted(cols, key=lambda c: (-out.loc[out[c] != "*", c].nunique(), cols.index(c)))
        while True:
            small = (out.groupby(cols, dropna=False)[cols[0]].transform("size") < k).values
            idx = np.flatnonzero(small)
            vals = out[rank].values[idx]
            live = vals != "*"
            if not live.any():
                break
            first, has = live.argmax(1), live.any(1)
            for j, c in enumerate(rank):
                rows = idx[has & (first == j)]
                if len(rows):
                    out.loc[rows, c] = "*"
                    touched[rows] = True; n_values += len(rows)
        drop = (out.groupby(cols, dropna=False)[cols[0]].transform("size") < k).values
        removed = int(drop.sum())
        out = out[~drop].reset_index(drop=True)
    final = k_anonymity(out, cols, k)
    report = dict(k=int(k), quasi_cols=cols, rows_in=int(len(df)), rows_out=int(len(out)), steps=steps,
                  generalized=[s["column"] for s in steps[1:]], suppressed_rows=int(touched.sum()), suppressed_values=int(n_values),
                  removed_rows=removed, final_groups=final["groups"], final_min_group=final["min_group"],
                  satisfied=bool(final["satisfied"] and len(out) > 0))
    return out, report


# ============================ 저장 최소화 ============================
def generalize_profiles(profiles: pd.DataFrame, codes: np.ndarray) -> pd.DataFrame:
    """번들 저장용 프로필: 원시 연령·연소득 대신 특징 저장소와 같은 구간 코드(age_band·income_q)."""
    out = pd.DataFrame({"user": profiles["user"].values.astype(int),
                        "age_band": np.asarray(codes)[:, SEG_VARS.index("age_band")].astype(int),
                        "income_q": np.asarray(codes)[:, SEG_VARS.index("income_q")].astype(int)})
    for c in STORED_PROFILE_COLUMNS[3:]:
        if c in profiles.columns:
            out[c] = profiles[c].values
    return out


def generalize_users_table(users: pd.DataFrame, codes) -> pd.DataFrame:
    """이전 형식 번들의 학습자 표에 있는 원값 열(연령·연소득(만원))을 같은 자리의 연령대·소득분위 이름 열로 바꾼다."""
    u = users
    for raw, new, var in (("연령", "연령대", "age_band"), ("연소득(만원)", "소득분위", "income_q")):
        if raw in u.columns:
            u = u.copy()
            if new not in u.columns:
                u.insert(u.columns.get_loc(raw), new, np.array(LABELS[var], dtype=object)[np.asarray(codes)[:, SEG_VARS.index(var)]])
            u = u.drop(columns=raw)
    return u


def minimize_log(log: pd.DataFrame) -> pd.DataFrame:
    """번들 저장용 로그: 일·분을 버리고 주차·4개 시간대만 남긴다. 같은 주 안의 시도 순서는 seq(0, 1, 2…)로만 보존한다."""
    keys = ["user", "week"] + (["minute"] if "minute" in log.columns else [])
    lg = log.sort_values(keys, kind="stable").drop(columns=[c for c in RAW_TIME_COLUMNS if c in log.columns]).reset_index(drop=True)
    lg.insert(lg.columns.get_loc("week") + 1, "seq", lg.groupby(["user", "week"]).cumcount().astype(int).values)
    return lg


def suppress_small_groups(df: pd.DataFrame, k: int = K_RELEASE) -> tuple:
    """공개 집단표(group_results·advanced_exposure)의 작은 셀 처리: users < k 행은 빼고, active_users < k이면 활성 기준 값을 비운다."""
    if df is None or len(df) == 0 or "users" not in df.columns:
        return df, dict(k=int(k), rows=0 if df is None else int(len(df)), rows_removed=0, active_masked=0, min_users=None)
    keep = (df["users"] >= k).values
    out = df[keep].reset_index(drop=True).copy()
    masked = 0
    if "active_users" in out.columns:
        small = (out["active_users"] < k).values
        masked = int(small.sum())
        if masked:
            cols = [c for c in ACTIVE_COLUMNS if c in out.columns]
            out[cols] = out[cols].astype(float)
            out.loc[small, cols] = np.nan
    return out, dict(k=int(k), rows=int(len(df)), rows_removed=int((~keep).sum()), active_masked=masked,
                     min_users=int(out["users"].min()) if len(out) else None,
                     min_active_users=(int(out["active_users"].min()) if "active_users" in out.columns and out["active_users"].notna().any() else None))


# ============================ 저장 설계 ============================
_TEXT_KEYS = ("text", "memo", "summary", "label", "matched")
_AGE_RE = re.compile(r"(?<!\d)(\d{2})\s*(세|살)(?!\s*(이하|이상))")
_INC_RE = re.compile(r"(연소득|연봉|소득|수입)\s*(약\s*)?(\d{1,3}(?:,\d{3})+|\d{3,5})\s*만\s*원?")
_INC_THOUSAND_RE = re.compile(r"(\d)\s*천\s*만\s*원")


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(str(v).replace(",", "")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _age_code(age):
    a = _num(age)
    return None if a is None else int(np.digitize(a, AGE_CUTS))


def _income_code(income, edges):
    x = _num(income)
    return None if x is None else int(income_quintile(np.array([x]), np.asarray(edges, float))[0][0])


def _label(var, code):
    return LABELS[var][code] if code is not None and 0 <= code < len(LABELS[var]) else "미상"


def scrub_text(s: str, income_edges) -> str:
    """자유 입력 문장의 연령(예: 45세)·소득(예: 연봉 5,000만원, 5천만원) 표현을 [구간 이름]으로 바꾼다. 그 밖의 표현은 가리지 못한다."""
    s = _AGE_RE.sub(lambda m: f"[{_label('age_band', _age_code(m.group(1)))}]", s)
    s = _INC_RE.sub(lambda m: f"[{_label('income_q', _income_code(m.group(3), income_edges))}]", s)
    return _INC_THOUSAND_RE.sub(lambda m: f"[{_label('income_q', _income_code(float(m.group(1)) * 1000, income_edges))}]", s)


def scrub_design(payload, income_edges):
    """저장 설계에서 원시 연령·연소득을 지운다(재귀). 숫자인 age·income 키 → age_band·income_q 코드, 학습자 표의 연령·연소득(만원) →
    연령대·소득분위 이름, 자연어 근거 {field: age|income} → 코드·구간 이름, 자유 입력(text·memo·summary·label·matched) → scrub_text."""
    def walk(o):
        if isinstance(o, list):
            return [walk(x) for x in o]
        if not isinstance(o, dict):
            return o
        o = dict(o)
        if o.get("field") in ("age", "income") and "value" in o:          # 자연어 근거 한 줄
            var = "age_band" if o["field"] == "age" else "income_q"
            code = _age_code(o["value"]) if var == "age_band" else _income_code(o["value"], income_edges)
            o.update(field=var, value=code, matched=_label(var, code))
        out, late = {}, {}
        for key, v in o.items():
            if key == "age" and (v is None or _num(v) is not None):
                late["age_band"] = _age_code(v)
            elif key == "income" and (v is None or _num(v) is not None):
                late["income_q"] = _income_code(v, income_edges)
            elif key == "연령" and _num(v) is not None:
                late["연령대"] = _label("age_band", _age_code(v))
            elif key == "연소득(만원)" and _num(v) is not None:
                late["소득분위"] = _label("income_q", _income_code(v, income_edges))
            elif key in _TEXT_KEYS and isinstance(v, str):
                out[key] = scrub_text(v, income_edges)
            else:
                out[key] = walk(v)
        out.update(late)                                                    # 원값에서 나온 구간이 우선
        return out
    return walk(payload)


def hydrate_design(payload, income_rep):
    """불러오기용: state.learner의 구간 코드에서 대표값(연령 25·35·45·55·65세, 소득 분위 대표값)을 다시 채운다. 원값 복원이 아니다."""
    p = copy.deepcopy(payload)
    learner = (p.get("state") or {}).get("learner") if isinstance(p, dict) else None
    if not isinstance(learner, dict):
        return p
    ok = lambda c: isinstance(c, int) and not isinstance(c, bool) and 0 <= c < 5
    rep = []
    if learner.get("age") is None and ok(learner.get("age_band")):
        learner["age"] = int(AGE_BAND_REP[learner["age_band"]]); rep.append("age")
    if learner.get("income") is None and ok(learner.get("income_q")) and income_rep is not None:
        learner["income"] = float(np.asarray(income_rep)[learner["income_q"]]); rep.append("income")
    if rep:
        learner["band_representative"] = rep
    return p


# ============================ 가명처리 ============================
def pseudonymize_ids(values, key) -> np.ndarray:
    """외부 식별자 → HMAC-SHA256(key, str(id))의 16진수 앞 16자. 같은 키면 항상 같은 가명이고, 키 없이는 되돌리거나 다시 만들 수 없다."""
    if key is None or len(key) < MIN_KEY_LENGTH:
        raise ValueError(f"가명처리 키가 없거나 {MIN_KEY_LENGTH}자 미만입니다(환경변수 {KEY_ENV})")
    kb = key.encode("utf-8") if isinstance(key, str) else bytes(key)
    return np.array([hmac.new(kb, str(v).encode("utf-8"), hashlib.sha256).hexdigest()[:16] for v in values], dtype=object)


def build_pseudonymized_inputs(raw_profiles: pd.DataFrame, raw_log: pd.DataFrame, id_col: str, key) -> tuple:
    """운영 원본(외부 회원 ID 열 포함) → 학습 입력(profiles·study_log 스키마)과 매핑표.
    - 가명 = HMAC-SHA256 앞 16자, user = 가명 정렬 순서의 연속 번호(가입·ID 순서가 드러나지 않는다)
    - 로그: 외부 ID → user. 시각은 주차 + 4개 시간대로 축약(minute = 주 시작부터의 분, 모의 생성기와 같은 정의가 있으면
      거기서 시간대를 다시 계산)하고, day·minute 열은 형식 호환을 위해 0으로 채운다(같은 주 안의 순서는 행 순서로만 남는다)
    - 학습 스키마(data.PROFILE_COLUMNS·goal·horizon / synth.LOG_COLUMNS·score·understood) 밖의 열은 버린다
    - 원시 연령·연소득은 남긴다(소득 분위 경계 계산에 필요). 학습 환경 밖으로 내보내지 않는다
    반환 (profiles, log, mapping[external_id, pseudonym, user]). mapping은 학습 환경 밖에 따로 보관한다."""
    for name, df in (("profiles", raw_profiles), ("log", raw_log)):
        if id_col not in df.columns:
            raise ValueError(f"{name}에 외부 ID 열 '{id_col}'이 없습니다")
    need = [c for c in PROFILE_COLUMNS if c != "user" and c not in raw_profiles.columns]
    need_log = [c for c in ("item", "week", "complete", "quiz", "quiz_pass", "save", "drop", "replay") if c not in raw_log.columns]
    if need or need_log:
        raise ValueError(f"학습 스키마 열이 없습니다: profiles {need}, log {need_log}")
    ids = raw_profiles[id_col].astype(str).values
    if len(set(ids)) != len(ids):
        raise ValueError(f"프로필의 외부 ID가 중복됩니다({len(ids) - len(set(ids))}건)")
    pseud = pseudonymize_ids(ids, key)
    if len(set(pseud)) != len(pseud):
        raise ValueError("가명이 충돌했습니다. 다른 키를 쓰세요")
    user = np.empty(len(ids), int)
    user[np.argsort(pseud, kind="stable")] = np.arange(len(ids))
    mapping = pd.DataFrame({"external_id": ids, "pseudonym": pseud, "user": user}).sort_values("user").reset_index(drop=True)
    keep_p = [c for c in list(PROFILE_COLUMNS) + list(OPTIONAL_PROFILE_COLUMNS) if c != "user" and c in raw_profiles.columns]
    profiles = raw_profiles[keep_p].copy()
    profiles.insert(0, "user", user)
    profiles = profiles.sort_values("user").reset_index(drop=True)
    lookup = dict(zip(ids, user))
    lid = raw_log[id_col].astype(str)
    unknown = int((~lid.isin(lookup)).sum())
    if unknown:
        raise ValueError(f"프로필에 없는 외부 ID의 로그가 {unknown}건 있습니다")
    log = raw_log[[c for c in raw_log.columns if c in LOG_COLUMNS or c in ("score", "understood")]].copy()
    log["user"] = lid.map(lookup).astype(int).values
    if "minute" in log.columns:                                   # 주 안의 분 → 4개 시간대(출근·점심·저녁·심야)
        log["hour"] = np.digitize((log["minute"].astype(int) % 1440) // 60, [10, 15, 22])
        log = log.sort_values(["user", "week", "minute"], kind="stable")
    elif "hour" in log.columns:
        h = log["hour"].astype(int)
        log["hour"] = np.where(h.max() > 3, np.digitize(h, [10, 15, 22]), h)   # 0~23시 값이면 시간대로 바꾼다
        log = log.sort_values(["user", "week"], kind="stable")
    else:
        raise ValueError("로그에 minute 또는 hour 열이 있어야 합니다")
    log["day"] = 0
    log["minute"] = 0
    log = log[[c for c in LOG_COLUMNS if c in log.columns] + [c for c in log.columns if c not in LOG_COLUMNS]].reset_index(drop=True)
    return profiles, log, mapping


# ============================ 반출 ============================
def stored_profiles(bundle) -> pd.DataFrame:
    """번들의 저장 프로필(일반화 표). 이전 형식 번들(원시 연령·소득 포함)은 특징 저장소의 구간 코드로 바꿔 쓴다."""
    p = getattr(bundle, "profiles", None)
    if p is None:
        raise ValueError("번들에 프로필이 없습니다")
    if "age_band" in p.columns and "income_q" in p.columns:
        return p
    return generalize_profiles(p, bundle.store.codes)


def release_frame(profiles: pd.DataFrame) -> pd.DataFrame:
    """반출 후보 표 = 저장 프로필의 준식별자 8개 열만, 읽을 수 있는 이름으로. 가명 번호·관심 주제·진단 수준은 넣지 않는다."""
    miss = [c for c in QUASI_IDENTIFIERS if c not in profiles.columns]
    if miss:
        raise ValueError(f"저장 프로필에 준식별자 열이 없습니다: {miss}")
    names = {"age_band": LABELS["age_band"], "income_q": LABELS["income_q"], "gender": LABELS["gender"], "exp": EXPS, "risk": RISKS,
             "mobile": ["PC", "모바일"]}
    out = {}
    for c in QUASI_IDENTIFIERS:
        v = profiles[c].values
        if c in names:
            out[c] = [names[c][int(x)] if 0 <= int(x) < len(names[c]) else "미상" for x in v]
        else:
            out[c] = [(GOALS if c == "goal" else HORIZONS).get(str(x), str(x)) for x in v]
    return pd.DataFrame(out, dtype=object)


def export_deid(bundle, k: int = K_RELEASE, hierarchy=None) -> tuple:
    """번들 저장 프로필 → k-익명 학습자 표(한국어 열 이름)와 보고서. 결과 표를 k_anonymity로 다시 검사해 verified에 적는다."""
    if int(k) < 2:
        raise ValueError("k는 2 이상이어야 합니다")
    table, report = enforce_k_anonymity(release_frame(stored_profiles(bundle)), QUASI_IDENTIFIERS, int(k), hierarchy)
    report["verified"] = bool(k_anonymity(table, QUASI_IDENTIFIERS, int(k))["satisfied"])
    report["columns_released"] = [RELEASE_HEADERS[c] for c in QUASI_IDENTIFIERS]
    report["not_released"] = [c for c in STORED_PROFILE_COLUMNS if c not in QUASI_IDENTIFIERS]
    return table.rename(columns=RELEASE_HEADERS), report


# ============================ 감사 ============================
def router_leaf_audit(router, threshold: int = MIN_LEAF_DISPLAY) -> dict:
    """학습된 라우터 levels의 N(검증 사용자 수)으로 실제 잎(마지막 수준 노드) 크기를 센다.
    MIN_ROUTER_USERS는 잎 크기를 보장하지 않는다. 그보다 작은 노드는 상위 노드의 추정을 그대로 써서 챔피언을 정할 뿐이다.
    decision_min_n = 잎마다 '표본 ≥ min_users인 가장 깊은 조상(자기 포함)'의 크기 중 최솟값(챔피언 추정에 쓰인 평균의 최소 표본).
    λ가 매우 크면(교차 선택 결과 ∞) 수축 추정이 상위 값과 같아져 모든 잎이 루트 챔피언을 쓴다. 그래서 잎 챔피언의 종류 수
    (distinct_leaf_champions)와 루트 챔피언과 같은 잎의 비율(leaf_champion_is_root_share)을 함께 남긴다."""
    levels, dec = [], None
    for lv, L in enumerate(router.levels):
        N = np.asarray(L["N"], float)
        small = N < threshold
        dec = N.copy() if lv == 0 or L.get("pidx") is None else np.where(N >= router.min_users, N, dec[np.asarray(L["pidx"])])
        levels.append(dict(level=lv, variable=None if lv == 0 else router.order[lv - 1], nodes=int(len(N)), nodes_below=int(small.sum()),
                           users_in_nodes_below=int(N[small].sum()), min_n=int(N.min()) if len(N) else 0, users=int(N.sum())))
    leaf = levels[-1]
    champs = np.asarray(router.levels[-1]["champ"]) if router.levels else np.array([], int)
    root = int(router.levels[0]["champ"][0]) if router.levels else None
    return dict(variables=list(router.order), threshold=int(threshold), min_users_param=int(router.min_users), lam=float(router.lam),
                leaves=leaf["nodes"], leaves_below=leaf["nodes_below"], users_in_small_leaves=leaf["users_in_nodes_below"], min_leaf=leaf["min_n"],
                users=leaf["users"], decision_min_n=int(dec.min()) if dec is not None and len(dec) else 0,
                distinct_leaf_champions=int(len(np.unique(champs))), leaf_champion_is_root_share=float(np.mean(champs == root)) if len(champs) else None,
                levels=levels)


def _store_quasi(store) -> list:
    """특징 저장소에 실제로 있는 준식별자(구간 코드·원-핫·배열)."""
    if store is None:
        return []
    have = {"age_band", "income_q", "gender"} if getattr(store, "codes", None) is not None else set()
    if "exp" in (getattr(store, "blocks", None) or {}):
        have.add("exp")
    have |= {c for c in ("gender", "risk", "goal", "horizon", "mobile") if getattr(store, c, None) is not None}
    return [c for c in QUASI_IDENTIFIERS if c in have]


def privacy_audit(profiles: pd.DataFrame, routers: dict = None, store=None, k: int = K_RELEASE,
                  leaf_threshold: int = MIN_LEAF_DISPLAY, published: dict = None) -> dict:
    """번들에 실제로 저장된 것을 감사한다(기록만 한다; 강제는 privacy_checks·export-deid·suppress_small_groups).
    (a) 저장 준식별자 8개 조합의 k-익명성(k=5)·열 제거 일반화 계획·export-deid가 할 일반화/억제 요약
    (b) 학습된 라우터별 실제 잎 크기 (c) 공개 집단표의 작은 셀 처리 결과. 기록 위치는 RECORDED_IN."""
    cols = list(profiles.columns)
    plan = generalization_plan(profiles, QUASI_IDENTIFIERS, k)
    try:
        _, rel = enforce_k_anonymity(release_frame(profiles), QUASI_IDENTIFIERS, k)
        release = {x: rel[x] for x in ("rows_in", "rows_out", "steps", "generalized", "suppressed_rows", "suppressed_values",
                                       "removed_rows", "final_groups", "final_min_group", "satisfied")}
    except ValueError as e:
        release = dict(error=str(e), satisfied=False)
    return dict(
        recorded_in=RECORDED_IN, k=int(k),
        stored=dict(profile_columns=cols, column_roles={c: COLUMN_ROLES.get(c, "미분류") for c in cols},
                    unclassified=[c for c in cols if c not in COLUMN_ROLES], raw_columns=[c for c in cols if c in RAW_PROFILE_COLUMNS],
                    quasi_in_profiles=[c for c in QUASI_IDENTIFIERS if c in cols], quasi_in_store=_store_quasi(store)),
        quasi=k_anonymity(profiles, QUASI_IDENTIFIERS, k),
        generalization=plan["steps"],                                   # 열 제거 순서(이전 형식과 같은 목록)
        generalization_status={x: plan[x] for x in ("satisfied", "impossible", "kept", "missing", "initial_satisfied", "note")},
        release=release, router_leaves={name: router_leaf_audit(rt, leaf_threshold) for name, rt in (routers or {}).items()},
        published=published or {}, policy=dict(implemented=POLICY_IMPLEMENTED, organizational=POLICY_ORGANIZATIONAL),
        note=("가명 번호만으로는 충분하지 않다. 저장 준식별자 조합은 k=5를 만족하지 않을 수 있으므로(quasi) 학습자 단위 표는 "
              "export-deid로 일반화·억제한 것만 반출한다. 라우터 잎 크기는 보장되지 않는다(router_leaves)."))


def privacy_checks(bundle) -> list:
    """학습 QA용 개인정보 검사 5개: [(이름, 통과 여부, 세부)]. pipeline.run_qa가 번들 조립 직후 실행한다."""
    out = []
    p = getattr(bundle, "profiles", None)
    pc = set(p.columns) if p is not None else set()
    out.append((CHECK_NAMES[0], p is not None and not (pc & set(RAW_PROFILE_COLUMNS)) and {"age_band", "income_q"} <= pc,
                f"번들 프로필 열 {sorted(pc)}"))
    lg = getattr(bundle, "log", None)
    lc = set(lg.columns) if lg is not None else set()
    out.append((CHECK_NAMES[1], lg is not None and not (lc & set(RAW_TIME_COLUMNS)) and {"week", "hour"} <= lc
                and bool(lg["hour"].between(0, 3).all()), f"번들 로그 열 {sorted(lc)}"))
    st = getattr(bundle, "store", None)
    uc = set(st.users.columns) if st is not None else set()
    med = getattr(st, "income_median", None)
    out.append((CHECK_NAMES[2], st is not None and getattr(st, "age", None) is None and getattr(st, "income", None) is None
                and not (uc & set(RAW_PROFILE_COLUMNS)) and (med is None or np.ndim(med) == 0),
                f"원값 필드 없음, 학습자 표 열에 원값 없음, 대체 소득은 집계 스칼라({med})"))
    mins = {}
    for name in ("group_results", "exposure"):
        df = getattr(bundle, name, None)
        if df is not None and len(df):
            mins[name] = int(df["users"].min())
            if "active_users" in df.columns and df["active_users"].notna().any():
                mins[name + ".active_users"] = int(df["active_users"].min())
    out.append((CHECK_NAMES[3], all(v >= K_RELEASE for v in mins.values()), f"최소 셀 {mins} (k={K_RELEASE})"))
    a = getattr(bundle, "privacy", None) or {}
    q, s, pol = a.get("quasi", {}), a.get("stored", {}), a.get("policy", {})
    routers = set((getattr(bundle, "routers", None) or {}).keys())
    ok = (p is not None and q.get("requested") == list(QUASI_IDENTIFIERS) and not q.get("missing")       # 준식별자 8개 모두 감사
          and s.get("profile_columns") == list(p.columns) and not s.get("unclassified")                  # 저장 열이 모두 분류됨
          and set(a.get("router_leaves", {})) == routers and bool(pol.get("implemented")) and bool(pol.get("organizational")))
    out.append((CHECK_NAMES[4], bool(ok), f"감사 열 {q.get('columns')}, 누락 {q.get('missing')}, 미분류 {s.get('unclassified')}, "
                                         f"라우터 {sorted(a.get('router_leaves', {}))}"))
    return [(n, bool(v), d) for n, v, d in out]
