"""개인정보 최소화·k-익명성 점검(중간 점검 지적 반영).

학습 로그는 가명 번호만 쓰더라도 연령대·소득분위·성별·경험·성향·투자 목적처럼 준식별자(quasi-identifier)가 결합되면
외부 자료와 교차해 재식별될 수 있다(모자이크 효과). 이 모듈은 (1) 라우팅에 쓰는 세그먼트 조합과 (2) 전체 준식별자 조합의
k-익명성을 계산해 k 미만 셀을 보고하고 일반화(열 제거) 제안을 만든다. 학습 파이프라인의 QA와 번들 manifest에 기록된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ROUTING_IDENTIFIERS = ("age_band", "income_q", "gender")
QUASI_IDENTIFIERS = ("age_band", "income_q", "gender", "exp", "risk", "goal")
POLICY = [
    "수집 최소화: 원시 연령·연소득은 온보딩 직후 연령대(5구간)·소득분위(5분위)로 일반화해 저장하고 원값은 보관하지 않는다",
    "가명 처리: 학습자 식별자는 일방향 해시 가명 번호로 바꾸고 매핑표는 분리 보관·접근 통제(모델 학습 부서는 매핑표 접근 불가)",
    "민감 속성 비사용: 성별은 운영 라우터·운영 설정에서 제외하고 성별 뒤집기 불변 검사로 확인",
    "시간 정보 축약: 접속 시각은 4개 시간대(출근·점심·저녁·심야)로만 저장",
    "k-익명성: 라우팅 세그먼트 조합은 잎 최소 20명(λ 수축), 준식별자 조합이 k=5 미만인 셀은 일반화(열 제거)하거나 집계에서 제외",
    "보관·삭제: 학습 로그는 목적 달성 후 통계·연구용 가명정보로만 보관하고 보관 기간을 문서화, 탈퇴 시 삭제",
    "접근 통제: 가명처리 담당과 모델 학습 담당의 권한·망 분리, 번들에는 원시 프로필이 아닌 세그먼트 코드와 집계만 저장",
    "재식별 금지: 가명정보를 특정 개인을 알아보기 위한 목적으로 처리하지 않으며, 재식별 가능성 발견 시 즉시 처리 중단·보고",
]


def k_anonymity(df: pd.DataFrame, cols, k: int = 5) -> dict:
    """열 조합별 그룹 크기로 k-익명성을 계산한다."""
    cols = [c for c in cols if c in df.columns]
    if not cols or len(df) == 0:
        return dict(columns=cols, k=k, groups=0, min_group=0, groups_below_k=0, users_below_k=0, share_below_k=0.0, satisfied=False)
    sizes = df.groupby(cols, dropna=False).size()
    below = sizes[sizes < k]
    return dict(columns=cols, k=int(k), groups=int(len(sizes)), min_group=int(sizes.min()), median_group=float(sizes.median()),
                groups_below_k=int(len(below)), users_below_k=int(below.sum()), share_below_k=float(below.sum() / len(df)),
                satisfied=bool(len(below) == 0))


def generalization_plan(df: pd.DataFrame, cols, k: int = 5) -> list:
    """k를 만족할 때까지 가장 효과가 큰 열을 하나씩 제거하는 일반화 제안(열 제거 = 가장 단순한 일반화)."""
    cols = [c for c in cols if c in df.columns]
    plan = []
    while cols and not k_anonymity(df, cols, k)["satisfied"]:
        best = min(cols, key=lambda c: k_anonymity(df, [x for x in cols if x != c], k)["users_below_k"])
        cols = [c for c in cols if c != best]
        plan.append(dict(drop=best, remaining=list(cols), **{kk: v for kk, v in k_anonymity(df, cols, k).items() if kk in ("min_group", "users_below_k", "satisfied")}))
    return plan


def privacy_audit(codes: np.ndarray, seg_vars, profiles: pd.DataFrame, k_route: int = 20, k_full: int = 5) -> dict:
    """세그먼트 코드(라우팅 변수)와 프로필 열로 k-익명성 보고서를 만든다."""
    df = pd.DataFrame({v: codes[:, j] for j, v in enumerate(seg_vars) if v in ROUTING_IDENTIFIERS})
    for c in ("exp", "risk", "goal"):
        if c in profiles.columns and len(profiles) == len(df):
            df[c] = profiles[c].values
    routing = k_anonymity(df, ROUTING_IDENTIFIERS, k_route)
    full = k_anonymity(df, QUASI_IDENTIFIERS, k_full)
    return dict(routing=routing, quasi=full, generalization=generalization_plan(df, QUASI_IDENTIFIERS, k_full), policy=POLICY,
                note="가명 번호만으로는 충분하지 않다. 준식별자 조합의 k-익명성을 학습 전에 점검하고, k 미만 셀은 일반화하거나 집계에서 제외한다.")
