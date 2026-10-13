"""알고리즘 풀: 신호를 교안 공식으로 묶은 설정(조합)들과 점수 계산.

설정 수(약 1,500개)는 변수·비중·정규화의 조합 수이지 독립된 기법 수가 아니다.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from .config import CONTENT_GRID, ICF_GRID, MF_GRID, SEG_LAMS, SEG_VARS, UCF_GRID
from .signals import SEG_V_ALL, SignalBank, seg_label, seg_name


@dataclass
class Algo:
    aid: int
    family: str
    name: str
    terms: list            # [(신호 이름, 가중치 규칙)], 규칙: ("c", w) | ("a", λ, w) → w·α_u | ("1-a", λ, w) → w·(1−α_u)
    V: tuple               # 세그먼트 인기에 쓴 세그먼트 변수
    lecture: str
    params: dict = field(default_factory=dict)

    @property
    def signals(self):
        return [s for s, _ in self.terms]


FAMILY_KO = {"POP": "인기", "SEGPOP": "세그먼트 인기", "PERS": "개인화 인기", "RULE": "규칙 점수", "CONTENT": "콘텐츠",
             "UCF": "사용자 CF", "ICF": "아이템 CF", "MF": "행렬분해", "HYB2": "CF+세그먼트", "HYB3": "CF+콘텐츠+세그먼트",
             "HYBR": "CF+규칙", "CTX": "맥락 보정", "MLP": "MLP (9주차)", "MF_OBS": "관측 점수 MF"}
FAMILY_LECTURE = {"POP": "3-1", "SEGPOP": "3-1·5-3", "PERS": "3-3", "RULE": "3-2", "CONTENT": "4-1·4-2·4-3", "UCF": "5-1",
                  "ICF": "5-2·5-3", "MF": "6-1·6-2", "HYB2": "5-3", "HYB3": "5-3·4-3", "HYBR": "5-3·3-2", "CTX": "5-3",
                  "MLP": "9-2/9-3", "MF_OBS": "6-2"}
CF_CORE = ["icf:10:1", "mf:16:0.01", "ucf:50:all:0.2"]
CONTENT_CORE = "cnt:both:1"
KEY_V = [(), ("age_band",), ("income_q",), ("gender",), ("age_band", "income_q"), ("age_band", "gender"),
         ("age_band", "income_q", "gender"), ("click_tier", "pref_cluster"), tuple(SEG_VARS)]


def build_zoo(bank: SignalBank, rule_parts, ctx_names) -> list:
    """신호를 교안 공식으로 묶어 설정 목록을 만든다. bank에 없는 신호를 쓰는 설정은 건너뛴다(예: torch 없음)."""
    algos = []
    skipped = []

    def add(fam, name, terms, V=(), **params):
        missing = [s for s, _ in terms if s not in bank]
        if missing:
            skipped.append((fam, name, missing))
            return
        algos.append(Algo(len(algos), fam, name, terms, tuple(V), FAMILY_LECTURE[fam], params))

    lab = lambda s: bank.info[s]["label"]
    priors = [()] + SEG_V_ALL                                     # 32개: 변수 없음(전체 인기) + 31개 조합
    # 1) [교안 3-1] 인기
    add("POP", lab("pop"), [("pop", ("c", 1.0))])
    # 2) [교안 3-1·5-3] 세그먼트 인기 31조합 × λ 3개
    for V in SEG_V_ALL:
        for lam in SEG_LAMS:
            add("SEGPOP", lab(seg_name(V, lam)), [(seg_name(V, lam), ("c", 1.0))], V, lam=lam)
    # 3) [교안 3-3] final_score = alpha * personal_norm + (1 - alpha) * popularity — popularity 자리에 세그먼트 인기
    for a in (0.5, 0.7):
        for V in priors:
            add("PERS", f"개인화 인기(α={a}, 인기={seg_label(V)})", [("personal", ("c", a)), (seg_name(V), ("c", 1 - a))], V, alpha=a)
    # 4) [교안 3-2] calculate_rule_score: base 5점 척도 + 규칙 가산점
    for base_V in [(), ("age_band", "income_q")]:
        for r in range(len(rule_parts) + 1):
            for sub in itertools.combinations(rule_parts, r):
                terms = [(seg_name(base_V), ("c", 5.0))] + [(p, ("c", float(w))) for p, w in sub]
                add("RULE", f"규칙[{'+'.join(lab(p) for p, _ in sub) or '없음'}](base={seg_label(base_V)})", terms, base_V,
                    parts=[p for p, _ in sub])
    # 5) 단일 기법
    for x, c in CONTENT_GRID:
        add("CONTENT", lab(f"cnt:{x}:{c}"), [(f"cnt:{x}:{c}", ("c", 1.0))])
    for k, d, w in UCF_GRID:
        if f"ucf:{k}:{d}:{w}" in bank:
            add("UCF", lab(f"ucf:{k}:{d}:{w}"), [(f"ucf:{k}:{d}:{w}", ("c", 1.0))], demo=d)
    for lam, c in ICF_GRID:
        if f"icf:{lam}:{c}" in bank:
            add("ICF", lab(f"icf:{lam}:{c}"), [(f"icf:{lam}:{c}", ("c", 1.0))])
    for f, r in MF_GRID:
        if f"mf:{f}:{r}" in bank:
            add("MF", lab(f"mf:{f}:{r}"), [(f"mf:{f}:{r}", ("c", 1.0))])
    # 6) [교안 5-3] final_score = alpha * cf_score + (1 - alpha) * content_score — content 자리에 세그먼트 인기 32종
    for cf in CF_CORE:
        for V in priors:
            for a in [("c", 0.3), ("c", 0.7), ("a", 3), ("a", 10), ("a", 30)]:
                if a[0] == "c":
                    terms = [(cf, ("c", a[1])), (seg_name(V), ("c", 1 - a[1]))]
                    an = f"α={a[1]}"
                else:
                    terms = [(cf, ("a", a[1], 1.0)), (seg_name(V), ("1-a", a[1], 1.0))]
                    an = f"α_u=n_u/(n_u+{a[1]})"
                if cf in bank:
                    add("HYB2", f"{lab(cf)} ⊕ 세그먼트 인기[{seg_label(V)}] ({an})", terms, V, cf=cf, alpha=list(a))
    # 7) CF + (γ·콘텐츠 + (1−γ)·세그먼트 인기)
    for cf in CF_CORE[:2]:
        for V in priors:
            for g in (0.3, 0.5, 0.7):
                terms = [(cf, ("a", 10, 1.0)), (CONTENT_CORE, ("1-a", 10, g)), (seg_name(V), ("1-a", 10, 1 - g))]
                if cf in bank:
                    add("HYB3", f"{lab(cf)} ⊕ [{g}·콘텐츠 + {1 - g:.1f}·세그먼트 인기[{seg_label(V)}]] (α_u, λ=10)", terms, V, cf=cf, gamma=g)
    # 8) CF + 규칙 점수(규칙 묶음은 가중치 합으로 나눠 0~1 척도)
    for cf in CF_CORE[:2]:
        for r in range(len(rule_parts) + 1):
            for sub in itertools.combinations(rule_parts, r):
                tot = 5.0 + sum(w for _, w in sub)
                for lam in (10, 30):
                    terms = [(cf, ("a", lam, 1.0)), ("pop", ("1-a", lam, 5.0 / tot))] + [(p, ("1-a", lam, w / tot)) for p, w in sub]
                    if cf in bank:
                        add("HYBR", f"{lab(cf)} ⊕ 규칙[{'+'.join(lab(p) for p, _ in sub) or '없음'}] (α_u, λ={lam})", terms, (), cf=cf,
                            parts=[p for p, _ in sub], lam=lam)
    # 9) 맥락 보정: (1−β)·[α_u·CF + (1−α_u)·(γ·콘텐츠 + (1−γ)·세그먼트 인기)] + β·맥락 신호
    for cx in ctx_names:
        for cf in CF_CORE[:2]:
            for V in KEY_V:
                for b in (0.2, 0.4, 0.6):
                    for g in (0.3, 0.7):
                        base = [(cf, ("a", 10, 1 - b)), (CONTENT_CORE, ("1-a", 10, g * (1 - b))), (seg_name(V), ("1-a", 10, (1 - g) * (1 - b)))]
                        if cf in bank and cx in bank:
                            add("CTX", f"{lab(cx)} β={b} + {lab(cf)} ⊕ [{g}·콘텐츠 + {1 - g:.1f}·세그먼트 인기[{seg_label(V)}]]",
                                base + [(cx, ("c", b))], V, ctx=cx, cf=cf, beta=b, gamma=g)
    for nm, fam in [("mf_observed", "MF_OBS"), ("mlp9", "MLP")]:
        if nm in bank:
            add(fam, lab(nm), [(nm, ("c", 1.0))])
    build_zoo.skipped = skipped
    return algos


build_zoo.skipped = []

ALIASES = {"income_q": "income", "age_band": "age", "pref_cluster": "pref", "click_tier": "clicks"}


def algo_uses(algo: Algo, info: dict) -> set:
    """설정이 의존하는 입력 변수(별칭을 정규화해 제외 조건 우회를 막는다)."""
    used = set()
    for signal, spec in algo.terms:
        used.update(ALIASES.get(v, v) for v in info[signal]["uses"])
        if spec[0] in ("a", "1-a"):
            used.add("clicks")
    return used


def explain(algo: Algo, info: dict) -> str:
    """사람이 읽는 계산식."""
    parts = []
    for s, spec in algo.terms:
        if spec[0] == "c":
            w = f"{spec[1]:g}"
        elif spec[0] == "a":
            w = f"{spec[2]:g}·α_u" if spec[2] != 1 else "α_u"
        else:
            w = f"{spec[2]:.2g}·(1−α_u)" if spec[2] != 1 else "(1−α_u)"
        parts.append(f"{w}·{info[s]['label']}")
    lam = [spec[1] for _, spec in algo.terms if spec[0] in ("a", "1-a")]
    tail = f"   (α_u = n_u/(n_u+{lam[0]}))" if lam else ""
    s = " + ".join(parts) + tail
    if any(n.startswith(SignalBank.CF_PREFIXES) for n, _ in algo.terms) and len(algo.terms) > 1:
        s += " [CF 신뢰도 게이트: n_i/(n_i+10); 빠진 비중은 비CF 항으로 이동]"
    return s


def term_weights(algo: Algo, bank: SignalBank, nu_rows: np.ndarray, rows: np.ndarray) -> list:
    """행별 각 항의 최종 가중치(α_u와 CF 신뢰도 게이트 반영)."""
    rows = np.asarray(rows, dtype=int); shape = (len(rows), bank.shape[1])
    weights = []; collab = []
    for name, spec in algo.terms:
        if spec[0] == "c":
            w = np.full(shape, spec[1], dtype=np.float32)
        else:
            a = nu_rows[rows, None] / (nu_rows[rows, None] + spec[1])
            w = np.broadcast_to((a if spec[0] == "a" else 1 - a) * spec[2], shape).astype(np.float32).copy()
        weights.append(w); collab.append(name.startswith(SignalBank.CF_PREFIXES))
    if any(collab) and not all(collab) and bank.item_support is not None:
        support = bank.item_support[bank.cands.cand0[rows]]
        gate = support / (support + 10.0)                         # 아이템 반응 근거 n_i/(n_i+10) — 프로젝트의 확장
        lost = np.zeros(shape, dtype=np.float32)
        for j, is_cf in enumerate(collab):
            if is_cf:
                lost += weights[j] * (1 - gate); weights[j] *= gate
        base = sum(w for w, c in zip(weights, collab) if not c)
        for j, is_cf in enumerate(collab):
            if not is_cf:
                weights[j] += np.divide(lost * weights[j], base, out=np.zeros(shape, dtype=np.float32), where=base > 0)
    return weights


def score_rows(algo: Algo, bank: SignalBank, nu_rows: np.ndarray, rows) -> np.ndarray:
    """정규화 신호의 가중합. 빈칸은 −inf."""
    rows = np.asarray(rows, dtype=int)
    weights = term_weights(algo, bank, nu_rows, rows)
    S = np.zeros((len(rows), bank.shape[1]), dtype=np.float32)
    for (name, _), w in zip(algo.terms, weights):
        S += w * bank.sig[name][rows]
    S += bank.cands.jitter[rows]
    S[~bank.cands.valid[rows]] = -np.inf
    return S


def score_algo(algo: Algo, bank: SignalBank, nu_rows: np.ndarray) -> np.ndarray:
    return score_rows(algo, bank, nu_rows, np.arange(bank.cands.R))


def decompose(algo: Algo, bank: SignalBank, nu_rows: np.ndarray, row: int) -> dict:
    """한 행의 후보별 항 기여도(가중치 × 정규화 신호). 추천 근거 화면에 쓴다."""
    weights = term_weights(algo, bank, nu_rows, np.array([row]))
    out = {}
    for (name, _), w in zip(algo.terms, weights):
        out[name] = dict(label=bank.info[name]["label"], weight=w[0].astype(float), signal=bank.sig[name][row].astype(float),
                         contribution=(w[0] * bank.sig[name][row]).astype(float))
    return out
