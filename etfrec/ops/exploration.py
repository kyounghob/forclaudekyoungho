"""탐색 칸: 마지막 한 칸만 확률 ε로 다른 적격 단원을 보여 주고, 보인 단원마다 포함 확률을 기록한다.

앞의 k−1칸은 운영 정책 순위 그대로(포함 확률 1)이고, 마지막 칸은 확률 1−ε로 운영 순위 k번째 단원,
확률 ε로 나머지 적격 단원(순위 k+1 이후) 가운데 하나를 보인다. 후보 순서는 가드레일·한 단계 위 상한·주제 상한을
이미 통과한 목록이므로 탐색해도 가드레일을 어기지 않는다. 같은 요청 번호는 같은 결과를 낸다(감사·재현용).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

EXPLORE_SALT = "etfrec-explore-v1"
METHODS = ("uniform", "softmax")


@dataclass(frozen=True)
class ExplorationConfig:
    epsilon: float = 0.10          # 마지막 칸을 탐색 단원으로 바꿀 확률
    method: str = "uniform"        # uniform: 남은 적격 단원 균등 | softmax: 점수 기반
    temperature: float = 0.5       # softmax 온도(점수는 정규화 신호의 가중합)
    min_pool: int = 1              # 탐색할 단원이 이보다 적으면 탐색하지 않는다

    def __post_init__(self):
        if isinstance(self.epsilon, bool) or not 0 <= float(self.epsilon) <= 0.5:
            raise ValueError("epsilon은 0 이상 0.5 이하여야 합니다(탐색은 마지막 한 칸에만 씁니다)")
        if self.method not in METHODS:
            raise ValueError(f"method는 {METHODS} 중 하나여야 합니다")
        if not float(self.temperature) > 0:
            raise ValueError("temperature는 양수여야 합니다")
        if isinstance(self.min_pool, bool) or int(self.min_pool) < 1:
            raise ValueError("min_pool은 1 이상이어야 합니다")

    def as_dict(self) -> dict:
        return dict(epsilon=float(self.epsilon), method=self.method, temperature=float(self.temperature), min_pool=int(self.min_pool))


def request_rng(request_id: str, salt: str = EXPLORE_SALT) -> np.random.Generator:
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("요청 번호(request_id)가 필요합니다")
    seed = int.from_bytes(hashlib.sha256(f"{salt}:{request_id}".encode("utf-8")).digest()[:8], "big")
    return np.random.default_rng(seed)


def pool_probabilities(scores, cfg: ExplorationConfig) -> np.ndarray:
    s = np.asarray(scores, dtype=float)
    if len(s) == 0:
        return s
    if cfg.method == "uniform" or not np.isfinite(s).all():
        return np.full(len(s), 1.0 / len(s))
    z = (s - s.max()) / float(cfg.temperature)
    p = np.exp(z)
    return p / p.sum()


def explore_slate(order, scores, k: int, cfg: ExplorationConfig, request_id: str) -> dict:
    """order: 가드레일을 통과한 단원 번호를 운영 점수순으로 정렬한 전체 목록, scores: 같은 순서의 점수."""
    order = [int(x) for x in order]
    scores = np.asarray(scores, dtype=float)
    if len(scores) != len(order):
        raise ValueError("order와 scores의 길이가 다릅니다")
    if isinstance(k, bool) or int(k) < 1:
        raise ValueError("k는 1 이상이어야 합니다")
    k_eff = min(int(k), len(order))
    out = dict(items=[], propensity=[], explored=False, slot=None, exploit_item=None, prefix=[], pool=[], pool_prob=[],
               epsilon=0.0, method=cfg.method, request_id=request_id)
    if k_eff == 0:
        return out
    prefix, exploit_item, pool = order[:k_eff - 1], order[k_eff - 1], order[k_eff:]
    q = pool_probabilities(scores[k_eff:], cfg)
    eps = float(cfg.epsilon) if len(pool) >= cfg.min_pool else 0.0
    rng = request_rng(request_id)
    explored = bool(eps > 0 and rng.random() < eps)
    if explored:
        j = int(rng.choice(len(pool), p=q))
        slot_item, p_slot = pool[j], eps * float(q[j])
    else:
        slot_item, p_slot = exploit_item, 1.0 - eps
    out.update(items=prefix + [slot_item], propensity=[1.0] * len(prefix) + [p_slot], explored=explored, slot=k_eff - 1,
               exploit_item=exploit_item, prefix=prefix, pool=pool, pool_prob=[round(float(x), 10) for x in q], epsilon=eps)
    return out


def inclusion_probability(item: int, logged: dict) -> float:
    """기록된 요청에서 임의 단원이 보였을 확률(OPE의 지지 범위 확인). 기록에 없는 단원은 0."""
    item = int(item)
    if item in logged.get("prefix", []):
        return 1.0
    eps = float(logged.get("epsilon", 0.0))
    if logged.get("exploit_item") is not None and item == int(logged["exploit_item"]):
        return 1.0 - eps
    pool = logged.get("pool", [])
    if item in pool:
        return eps * float(logged["pool_prob"][pool.index(item)])
    return 0.0
