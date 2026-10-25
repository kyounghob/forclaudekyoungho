"""선수 페널티 강도에 따른 선수 가드레일 비용 민감도 (작은 모의 세계, 학습자 3,000명 · 약 40초/세계).

    python scripts/prereq_sensitivity.py [out.json]

생성기 v2의 '미이수 선수 단원 1개당 완료·통과 로짓 감소'(기본 0.8)를 0.8 → 2.0 → 4.0으로 키우며,
운영 라우터와 '운영 라우터+선수 가드레일'의 테스트 NDCG@5·선수 미이수 비율·짧은 목록 비율을 기록한다.
선수 관계가 학습 성과를 강하게 지배하는 세계일수록 가드레일의 정확도 비용이 줄고 역전된다(중간보고서 5절).
"""
import json, sys, time
sys.path.insert(0, ".")
from etfrec.config import TrainConfig
from etfrec.data import Dataset
from etfrec.pipeline import train

out = []
for pen in [0.8, 2.0, 4.0]:
    t0 = time.time()
    cfg = TrainConfig(n_learners=3000, prereq_penalty=pen, router_reps=1, bootstrap_n=100)
    b = train(Dataset.synthetic(cfg), cfg, out_dir=None, log=lambda *a, **k: None)
    res = b.results.set_index("method")
    row = dict(prereq_penalty=pen, users=int(res.loc["RULE", "users"]), validation_best=float(b.selection["validation_best_ndcg"]),
               operational=b.algos[b.selection.get("legacy_operational_algorithm", b.selection["operational_algorithm"])].name,   # 고정 정책 번들은 operational_algorithm=-1 seconds=round(time.time() - t0, 1),
               quiz_pass=int(b.dataset_summary["quiz_pass"]), attempts=int(b.dataset_summary["study_attempts"]))
    for m in ["Global", "RouterNoGender", "RouterNoGender+prereq", "POP", "UCF"]:
        if m in res.index:
            row[m] = dict(ndcg=float(res.loc[m, "ndcg"]), prereq_violation_rate=float(res.loc[m, "prereq_violation_rate"]),
                          short_list_rate=float(res.loc[m, "short_list_rate"]), diversity=float(res.loc[m, "diversity"]),
                          ci_low=float(res.loc[m, "ci_low"]), ci_high=float(res.loc[m, "ci_high"]))
    out.append(row)
    print(f"페널티 {pen}: 라우터 {row['RouterNoGender']['ndcg']:.4f} vs +prereq {row['RouterNoGender+prereq']['ndcg']:.4f} "
          f"(위반 {row['RouterNoGender']['prereq_violation_rate']:.2f} → 0, 짧은 목록 {row['RouterNoGender+prereq']['short_list_rate']:.2f}) · {row['seconds']}s")
if len(sys.argv) > 1:
    json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
