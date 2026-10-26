# 보관 자료

이전 개정의 산출물을 개정별로 모아 둔 폴더다. 추천 시스템 실행, 테스트, 이번 보고서 수치 재현에는 필요 없다.
이번 개정 전 설계(운영 = 성별 제외 라우터, 선택·평가 단계의 선수 필터 미적용)로 만든 자료라
현재 코드의 기본값(목적 단계 규칙, 선수 조건 필수)으로 다시 만들면 수치와 화면 문구가 달라진다.

## 폴더 구성

| 폴더 | 개정 | 출처 커밋 |
| --- | --- | --- |
| `v1_2026-10-13/` | 1차본 중간보고서(2026-10-13 제출본) | `c677568`(인용 대조용으로 저장소에 추가) |
| `v2_2026-10-20/` | 2차본 중간보고서와 비판 대응 보고서, 그 근거 자료 | `c6c88e4`(목적 단계 규칙 패키지 반영 직전의 마지막 커밋) |

## 원래 이름과 새 위치

| 새 위치 | 원래 위치 |
| --- | --- |
| `v1_2026-10-13/ETF_Education_Midterm_v1.docx` | `docs/report/중간보고서_1차본_2026-10-13.docx` |
| `v2_2026-10-20/ETF_Education_Midterm_v2.docx` | `docs/report/중간보고서_ETF_교육_콘텐츠_추천시스템.docx` |
| `v2_2026-10-20/ETF_Education_Critique_Response_v2.docx` | `docs/report/비판검토_보완보고서.docx` |
| `v2_2026-10-20/figures/fig1~fig8_*.png` | `docs/report/fig1~fig8_*.png` |
| `v2_2026-10-20/report_build/` | `docs/report/build/`(두 보고서의 빌드 스크립트) |
| `v2_2026-10-20/bundles/bundle_v1/`, `bundles/bundle_v2/` | `artifacts/bundle_v1/`, `artifacts/bundle_v2/`(결과 CSV와 manifest) |
| `v2_2026-10-20/results/` | `docs/results/`(위약 점검, 선수 벌점 민감도) |
| `v2_2026-10-20/screens/` | `docs/screens/`(화면 캡처 18장) |
| `v2_2026-10-20/scripts/` | `scripts/placebo_check.py`, `prereq_sensitivity.py`, `regression_check.py`, `results_table.py`, `ui_walkthrough.mjs` |

학습 번들(`bundle.pkl`)과 학습자 단위 파일(`learner_profiles.csv`)은 용량과 개인정보 때문에 처음부터 저장소에 올리지 않았다.
`tests/test_pipeline_service.py`는 `v2_2026-10-20/bundles/bundle_v1/test_results.csv`를 읽어 v1 결과가 노트북 기록과 같은지 확인한다.

## 당시 상태로 다시 실행하기

보관 폴더의 스크립트는 원래 위치와 당시 코드를 전제로 하므로 이 폴더에서 바로 실행하지 않는다.
당시 상태는 별도 작업 폴더로 꺼내 원래 위치에서 실행한다.

```bash
git worktree add ../etfrec_v2 c6c88e4     # 2차본 당시 코드와 파일 배치
cd ../etfrec_v2                           # 그 시점의 README 안내대로 실행(예: docs/report/build/build.sh)
```
