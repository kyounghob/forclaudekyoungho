"""검증 게이트: 도전 정책이 모든 차단 기준을 통과할 때만 운영 정책을 바꾼다.

기준은 purpose_policy.replacement_rule을 옮긴 것이다(min_ndcg_gain 0.005, 목적·로드맵 항 필수, 현재 단계 정합률 비열등,
선수 위반 0, 정책 고정 뒤 새 자료로 확인). 여기에 보호 변수 미사용, 심화 노출 격차, 최소 표본, 교체 후 냉각 기간,
동결, 탐색 기록 기반 OPE 비열등을 더했다. 판정은 기준별 (통과 여부, 값, 기준값, 설명)으로 모두 남긴다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..purpose_policy import policy_metadata


def _rule() -> dict:
    return policy_metadata()["replacement_rule"]


@dataclass(frozen=True)
class GateConfig:
    min_ndcg_gain: float = _rule()["min_ndcg_gain"]     # 0.005
    require_ci_positive: bool = True                   # 짝 부트스트랩 95% 하한 > 0
    alignment_margin: float = 0.01                     # 정합률 비열등 한계(1%p)
    max_prereq_violation: float = _rule()["prerequisite_violation_rate"]   # 0.0
    max_exposure_gap: float = 0.05                     # 같은 변수 안 심화 노출 격차(넘더라도 현재 정책보다 나빠지지 않으면 허용)
    min_goal_weight: float = 1.0
    min_roadmap_weight: float = 1.0
    min_users: int = 200                               # 확인 주 평가 사용자 수
    min_unique_matches: int = 20                       # OPE 판정에 쓸 최소 표본(도전 정책만의 단원이 탐색으로 보인 횟수)
    min_support: float = 0.9                           # 도전 정책 목록 가운데 기록 정책에서 보일 수 있었던 비율
    ope_margin: float = 0.10                           # OPE 비열등: 차이 하한 ≥ −0.10 × 현재 정책 추정치
    require_ope: bool = False                          # True면 탐색 기록이 부족할 때도 교체를 막는다
    cooldown_weeks: int = 1                            # 교체한 다음 주는 다시 교체하지 않는다(그 주는 교체 확인·되돌리기 판정)
    bootstrap_n: int = 500
    rollback_margin: float = 0.005                     # 교체 다음 주에 NDCG가 이만큼 넘게, 구간 상한 < 0으로 떨어지면 되돌린다

    def as_dict(self) -> dict:
        return asdict(self)


def _c(name, passed, value, threshold, detail, blocking=True) -> dict:
    return dict(name=name, passed=passed, value=value, threshold=threshold, detail=detail, blocking=blocking)


def evaluate_gate(cfg: GateConfig, champion: dict, challenger: dict, eligibility_reasons: list, ope: dict,
                  frozen: bool, weeks_since_change: int) -> dict:
    """champion·challenger: metrics.policy_metrics 결과 + paired(ndcg·alignment 차이와 구간).
    ope: dict(champion=policy_value, challenger=policy_value, diff=paired_difference) 또는 None."""
    cr = []
    cr.append(_c("frozen", not frozen, bool(frozen), False, "동결 중에는 교체하지 않습니다" if frozen else "동결 아님"))
    cool = weeks_since_change is None or weeks_since_change > cfg.cooldown_weeks
    cr.append(_c("cooldown", cool, weeks_since_change, f"> {cfg.cooldown_weeks}주",
                 "직전 교체 뒤 냉각 기간" if not cool else "냉각 기간 지남"))
    cr.append(_c("min_users", challenger["users"] >= cfg.min_users, challenger["users"], cfg.min_users, "확인 주 평가 사용자 수"))
    cr.append(_c("eligibility", not eligibility_reasons, eligibility_reasons or "충족",
                 "보호 변수 미사용·목적/로드맵 항 포함", "; ".join(eligibility_reasons) or "자격 조건 충족"))
    p = challenger["paired_ndcg"]
    ok_gain = p["diff"] >= cfg.min_ndcg_gain and (not cfg.require_ci_positive or (p["ci_low"] is not None and p["ci_low"] > 0))
    cr.append(_c("ndcg_gain", bool(ok_gain), dict(diff=p["diff"], ci_low=p["ci_low"], ci_high=p["ci_high"]),
                 f"차이 ≥ {cfg.min_ndcg_gain} 그리고 95% 하한 > 0" if cfg.require_ci_positive else f"차이 ≥ {cfg.min_ndcg_gain}",
                 f"NDCG@K {champion['ndcg']:.5f} → {challenger['ndcg']:.5f}"))
    a_new, a_old = challenger["alignment"], champion["alignment"]
    ok_align = a_new is not None and a_old is not None and a_new >= a_old - cfg.alignment_margin
    cr.append(_c("alignment_noninferior", bool(ok_align), dict(champion=a_old, challenger=a_new, ci=challenger.get("paired_alignment")),
                 f"≥ 현재 − {cfg.alignment_margin}", "현재 단계 정합률(로드맵 준수 정도, 교육 효과 측정 아님)"))
    cr.append(_c("prereq_violation", challenger["prereq_violation"] <= cfg.max_prereq_violation, challenger["prereq_violation"],
                 cfg.max_prereq_violation, "선수 단원을 마치지 않은 단원 추천 비율"))
    g_new, g_old = challenger["exposure"]["max_gap"], champion["exposure"]["max_gap"]
    ok_gap = g_new <= cfg.max_exposure_gap or g_new <= g_old + 1e-12
    cr.append(_c("exposure_gap", bool(ok_gap), dict(champion=g_old, challenger=g_new), f"≤ {cfg.max_exposure_gap} 또는 현재 이하",
                 "성별·연령대·소득분위 집단 사이 심화·레버리지 노출 비율의 최대 격차(감사용, 순위 입력 아님)"))
    cr.append(_ope_criterion(cfg, ope))
    blocking = [c for c in cr if c["blocking"]]
    passed = all(c["passed"] is True or (c["passed"] is None and c["name"] == "ope_noninferior") for c in blocking)
    return dict(passed=bool(passed), criteria=cr, failed=[c["name"] for c in blocking if c["passed"] is False])


def _ope_criterion(cfg: GateConfig, ope: dict) -> dict:
    if not ope or not ope.get("diff") or ope["diff"].get("diff") is None:
        return _c("ope_noninferior", False if cfg.require_ope else None, None, "탐색 기록", "이번 주 탐색 기록 없음",
                  blocking=cfg.require_ope)
    d, ch, cp = ope["diff"], ope["challenger"], ope["champion"]
    enough = d["unique_matches"] >= cfg.min_unique_matches and (ch.get("support") or 0) >= cfg.min_support
    if not enough:
        return _c("ope_noninferior", False if cfg.require_ope else None,
                  dict(unique_matches=d["unique_matches"], support=ch.get("support")),
                  f"표본 ≥ {cfg.min_unique_matches}, 지지 ≥ {cfg.min_support}", "탐색 표본이 부족해 판정에 쓰지 않음",
                  blocking=cfg.require_ope)
    floor = -cfg.ope_margin * max(cp["ips"] or 0.0, 1e-9)
    ok = d["ci_low"] >= floor
    return _c("ope_noninferior", bool(ok), dict(diff=d["diff"], ci_low=d["ci_low"], champion=cp["ips"], challenger=ch["ips"],
                                                 unique_matches=d["unique_matches"], support=ch.get("support")),
              f"차이 하한 ≥ {floor:.4f}", "탐색 기록의 포함 확률로 추정한 요청당 성공 수(IPS) 비열등")


def rollback_check(cfg: GateConfig, current: dict, previous: dict) -> dict:
    """교체 다음 주: 현재 정책이 이전 정책보다 분명히 나빠졌거나 선수 위반이 생기면 되돌린다."""
    p = current["paired_vs_previous"]
    worse = p["diff"] < -cfg.rollback_margin and p["ci_high"] is not None and p["ci_high"] < 0
    viol = current["prereq_violation"] > cfg.max_prereq_violation
    return dict(rollback=bool(worse or viol), ndcg_diff=p, prereq_violation=current["prereq_violation"],
                reason=("NDCG 하락" if worse else "") + (" 선수 위반" if viol else ""), previous_ndcg=previous["ndcg"],
                current_ndcg=current["ndcg"])
