"""노트북 B(seed 42, 15,000명) 기록과 패키지 결과를 대조한다.

노트북 테스트 NDCG@5: RULE 0.17123, Global 0.17123, RouterNoGender 0.17119, RouterFull 0.17116,
RouterNoGenderIncome 0.15702, NoDemographics 0.15355, UCF 0.14268, POP 0.11875, ICF 0.11112,
CONTENT 0.09957, MF 0.09264, MF_OBS 0.07099, Random 0.05993, MLP 0.05325. 검증 최고 0.178068.
"""
import sys, time
sys.path.insert(0, ".")
from etfrec.config import TrainConfig
from etfrec.data import Dataset
from etfrec.pipeline import train

EXPECTED = {"RULE": 0.17123, "Global": 0.17123, "RouterNoGender": 0.17119, "RouterFull": 0.17116,
            "RouterNoGenderIncome": 0.15702, "NoDemographics": 0.15355, "UCF": 0.14268, "POP": 0.11875,
            "ICF": 0.11112, "CONTENT": 0.09957, "MF": 0.09264, "MF_OBS": 0.07099, "Random": 0.05993, "MLP": 0.05325}

t0 = time.time()
cfg = TrainConfig()
ds = Dataset.synthetic(cfg)
print("summary", ds.summary())
bundle = train(ds, cfg, out_dir=sys.argv[1] if len(sys.argv) > 1 else None)
got = bundle.results.set_index("method").ndcg
print(f"\n검증 최고 NDCG {bundle.selection['validation_best_ndcg']:.6f} (노트북 0.178068)")
bad = []
for k, v in EXPECTED.items():
    if k not in got.index:
        print(f"  {k:22s} 없음"); continue
    ok = abs(got[k] - v) < 5e-5
    print(f"  {k:22s} {got[k]:.5f} 기대 {v:.5f} {'OK' if ok else 'DIFF'}")
    if not ok:
        bad.append(k)
print("selection", bundle.selection["families"], bundle.selection["router_lambdas"])
print("time", round(time.time() - t0, 1), "s", "| mismatches:", bad)
