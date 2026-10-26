"""위약 세계 점검: 모의 데이터 v2를 만든 뒤 연령·연소득·성별 열만 학습자 사이에서 열마다 따로 무작위로 섞어
(행동·목적과의 연결은 끊고 분포는 유지) 같은 파이프라인으로 학습한다. 인구통계를 쓰는 설정이 검증에서 우연히 뽑히더라도
테스트에서 인구통계를 쓰지 않는 설정보다 나으면 안 된다(파이프라인이 없는 효과를 만들어 내지 않는지).

생성기의 --effect 0은 위약이 아니다: 주제 선호의 인구통계 효과만 끄고, 연령·소득은 여전히 목적·경험·성향·기기를 거쳐 행동에 들어간다.

실행: python scripts/placebo_check.py [출력 JSON=docs/results/placebo_check.json] [학습자 수=15000]
"""
import json, sys, time
sys.path.insert(0, ".")
import numpy as np
from etfrec.config import TrainConfig
from etfrec.data import Dataset
from etfrec.evaluation import bootstrap_ci
from etfrec.pipeline import train
from etfrec.zoo import algo_uses

DEMO = ("age", "income", "gender")
out = sys.argv[1] if len(sys.argv) > 1 else "docs/results/placebo_check.json"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15000
t0 = time.time()
cfg = TrainConfig(n_learners=n)
ds = Dataset.synthetic(cfg)
rng = np.random.default_rng(cfg.seed + 2026)
P = ds.profiles.copy()
for c in DEMO:
    P[c] = P[c].values[rng.permutation(len(P))]
b = train(Dataset(P, ds.log, ds.catalog, source="synthetic", meta=dict(ds.meta or {}, placebo_shuffled=list(DEMO))), cfg, out_dir=None,
          log=lambda *a, **k: None)
uses = lambda aid: sorted(set(algo_uses(b.algos[aid], b.signal_meta)) & {"age", "income", "gender"})
res = b.results.set_index("method")


def paired(a, c):
    d = np.asarray(b.per_user[a]) - np.asarray(b.per_user[c]); lo, hi = bootstrap_ci(d, 500, 42)
    return dict(a=a, b=c, diff=float(d.mean()), ci_low=float(lo), ci_high=float(hi))


sel = b.selection
report = dict(n_learners=n, seed=cfg.seed, shuffled=list(DEMO), seconds=round(time.time() - t0, 1),
              global_algorithm=b.algos[sel["families"]["Global"]].name, global_uses_demographics=uses(sel["families"]["Global"]),
              no_demographics_algorithm=b.algos[sel["families"]["NoDemographics"]].name,
              router_lambdas=sel["router_lambdas"],
              test_ndcg={m: float(res.loc[m, "ndcg"]) for m in ("Global", "NoDemographics", "RouterFull", "RouterNoGender", "RouterNoGenderIncome", "POP")},
              paired=[paired("Global", "NoDemographics"), paired("RouterFull", "RouterNoGenderIncome"), paired("RouterNoGender", "RouterNoGenderIncome")],
              qa_passed=all(q["passed"] for q in b.qa))
json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(report, ensure_ascii=False, indent=1))
