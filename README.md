# ETF 교육 콘텐츠 개인화 추천 시스템

인공지능과추천시스템 중간보고서(`docs/report/ETF_Education_Midterm_Submission.docx`)의 추천 시스템과 실험 코드다.
추천 대상은 ETF 교육 단원 66개(22개 주제 × 3수준, 선수 관계 80개)이며, 특정 ETF의 매수·매도나 투자 적합성은 판단하지 않는다.

## 폴더 구성

| 경로 | 내용 |
| --- | --- |
| `etfrec/` | 추천 엔진: 카탈로그, 진단 20문항, 로드맵, 모의 데이터 생성, 신호·비교 기법, 평가, 추천 서비스, API, 화면(`ui/`) |
| `etfrec/sources/` | 공개 ETF 시세 데이터 연결(선택 기능, 인증키 필요) |
| `etfrec/factor_models.py` | torch 없이 쓰는 MF(ALS·BPR)·MLP NumPy 구현(표 9의 MF·MLP 행) |
| `scripts/reproduce_report.py` | 보고서 수치를 한 번에 재현(아래 스크립트를 모두 실행) |
| `scripts/purpose_stage_evaluation.py` | 표 9: 같은 후보·선수 필터에서 NDCG@5와 목적·현재 단계 정합률 |
| `scripts/goal_stage_evaluation.py` | 4.3절: 공통 기초 이수를 가정한 다음 단계의 정합률 |
| `scripts/diagnosis_recheck.py` | 표 3~5·7·10·A1: 진단 민감도와 A·B·C 사례 |
| `scripts/verify_revision.py` | 회귀 테스트 일괄 실행(unittest) |
| `scripts/reproduce_extensions.py` | 표 9의 MF·MLP 행과 4.4절 민감도: `mf_mlp_comparison.py`(MF·MLP 동일 조건 비교), `generator_sensitivity.py`(생성기 목적 효과 민감도) |
| `tests/` | pytest 테스트 |
| `results/` | 실행 결과 요약. 보고서 표별 수치는 `results/report_numbers.md`, MF·MLP와 민감도의 상세 표는 `results/extensions/extension_numbers.md` |
| `docs/report/` | 중간보고서(docx)와 확인용 PDF(맑은 고딕 대신 Noto Sans CJK KR로 렌더링) |

## 설치

Python 3.11 이상이 필요하다.

```bash
python -m pip install -r requirements.txt        # 전체(API·테스트·torch 포함)
python -m pip install -r requirements-core.txt   # 학습·평가만
```

## 보고서 수치 재현

```bash
python scripts/reproduce_report.py
```

seed 42와 20261023에서 모의 학습자 15,000명 자료를 각각 학습하고, 평가 스크립트와 MF·MLP 비교·생성기 민감도까지 실행한다.
2코어 PC에서 약 9분 걸린다(`--no-extensions`를 주면 MF·MLP·민감도를 빼고 약 3분). torch는 필요 없다.
학습 번들과 전체 결과는 `runs/`에, 보고서와 대응하는 요약은 `results/`에 저장된다.

개별 명령:

```bash
python -m etfrec train --n 15000 --seed 42 --out runs/seed42 --no-neural --prereq-policy required --operational-policy PurposeStageRule
python scripts/purpose_stage_evaluation.py --bundle runs/seed42 --out runs/purpose_stage_seed42
python scripts/goal_stage_evaluation.py --bundle runs/seed42 --out runs/goal_stage_seed42
python scripts/diagnosis_recheck.py --bundle runs/seed42 --out runs/diagnosis
python -m etfrec recommend --bundle runs/seed42 --user 1 --k 5
python -m etfrec serve --bundle runs/seed42 --host 127.0.0.1 --port 8000    # 브라우저에서 http://127.0.0.1:8000
```

`bundle.pkl`은 pickle 파일이므로 직접 학습해 만든 번들만 불러온다.

## 운영 정책: 목적 단계 규칙

```
운영 점수 = 5×정규화 전체 인기 + 3×관심 + 2×수준 일치 + 1×모바일·짧은 콘텐츠 + 2×목적 친화도 + 2×로드맵 단계
```

- 전체 인기는 후보 행별 최소–최대 정규화 값이다(모두 같으면 0). 관심·수준·기기 신호는 0 또는 1, 목적 친화도는 0~1이다.
- 로드맵 단계 점수는 현재 단계에서 학습 가능한 단원 1, 후속 단계에서 가능한 단원 0.7, 잠긴 단원 0.4, 로드맵 밖 0이다.
- 연령·소득·성별은 운영 점수에 쓰지 않는다.
- 모든 기법에 같은 후처리를 적용한다. 이미 통과한 단원과 현재 수준보다 두 단계 이상 높은 단원은 제외하고, 한 단계 위 단원은 최대 1개, 미이수 선수가 있는 단원은 제외하며, 최대 5개를 표시한다.
- 비교 기법(전체 인기, 행동 집단 인기, 콘텐츠 기반, 순수 사용자 CF, 아이템 CF, 검증 선택 규칙)은 비신경망 설정 1,747개를 2주차 검증 NDCG로 탐색해 정하고 3주차에 평가한다. 목적 단계 규칙은 검증으로 고르지 않은 고정 설계값이다.

## 주요 결과 (모의 데이터)

| 방법 | NDCG@5 seed 42 / 새 seed | 정합률: 공통 기초 단계 seed 42 / 새 seed | 정합률: 공통 기초 이수 가정 seed 42 / 새 seed |
| --- | --- | --- | --- |
| 목적 단계 규칙(운영안) | 0.103070 / 0.122274 | 63.40% / 62.12% | 53.3% / 51.0% |
| 전체 인기 | 0.100642 / 0.117224 | 63.77% / 62.76% | 39.0% / 31.5% |
| 행동 집단 인기 | 0.100797 / 0.117344 | 63.77% / 62.76% | 38.4% / 32.3% |
| 콘텐츠 기반 | 0.094280 / 0.109821 | 56.68% / 57.58% | 22.9% / 27.2% |
| 사용자 CF(행동만) | 0.098758 / 0.115218 | 62.82% / 61.72% | 30.4% / 30.4% |
| 아이템 CF | 0.098931 / 0.114966 | 63.81% / 62.62% | 34.1% / 28.8% |
| 검증 선택 규칙 | 0.108794 / 0.126179 | 61.53% / 59.95% | 28.2% / 38.8% |

- 평가 대상자(seed 42 6,544명, 새 seed 6,487명)는 모두 공통 기초 단계에 있다. 이 단계에서는 운영안의 정합률이 전체 인기보다 약간 낮다.
- 공통 기초 9단원 이수를 가정해 다음 단계로 옮기면 운영안의 정합률이 두 seed 모두 비교군보다 12%p 이상 높다(같은 표시 개수의 최대치 62.9%·63.3%).
- 검증 선택 규칙은 연령대·소득분위 집단 인기를 기준 점수로 쓰고 로드맵 단계 항이 없다. seed 42 설정에는 목적 항도 없다.
- 진단 인정이 없으면 짧은 목록(5개 미만) 비율은 52.0%이고, 진단 정답확률 가정에 따라 2.02%·0.50%·0.14%로 줄어든다.
- 정합률은 점수에 쓰는 로드맵을 기준으로 하므로 교육 효과가 아니라 로드맵과의 일관성을 나타낸다. 모의 데이터 생성기도 목적 친화도를 쓰므로 NDCG 차이는 생성 가정의 영향을 받는다.

## MF·MLP 비교와 생성기 민감도 (보고서 표 9, 4.4절)

```bash
python scripts/reproduce_extensions.py      # 이 부분만 다시 실행: 약 6분, 결과는 results/extensions/
```

**MF·MLP 동일 조건 비교.** MF(ALS, Hu 외 2008), MF(BPR, Rendle 외 2009), MLP(9주차 구조: 임베딩 8 → 은닉 16, 목표 정렬 쌍을 BPR로 학습)를 torch 없이 NumPy로 학습하고, 표 9와 같은 후보·수준·선수 필터·정답으로 평가했다. 설정은 다른 비교군처럼 2주차 검증 NDCG@5로 골랐다.

| 방법 | NDCG@5 seed 42 / 새 seed | 정합률: 공통 기초 이수 가정 seed 42 / 새 seed |
| --- | --- | --- |
| 목적 단계 규칙(운영안) | 0.103070 / 0.122274 | 53.3% / 51.0% |
| 전체 인기 | 0.100642 / 0.117224 | 39.0% / 31.5% |
| MF(ALS) | 0.099291 / 0.117096 | 31.0% / 29.9% |
| MF(BPR) | 0.099231 / 0.117004 | 28.0% / 29.6% |
| MLP | 0.098814 / 0.117326 | 30.1% / 33.9% |

- 운영안과 MF·MLP의 NDCG@5 차이는 +0.0038~+0.0053이고, 두 seed 모두 대응 부트스트랩 95% 구간이 0을 포함하지 않는다.
- 검증에서 고른 MF는 저차원(ALS k=2, BPR k=4)이었다. 단원 66개·사용자당 관측 약 5개인 자료에서 잠재요인 개인화가 인기 이상의 정보를 거의 더하지 못한다는 뜻으로 해석한다.

**생성기 목적 효과 민감도(seed 42).** 생성기의 goal_effect만 0, 0.8(기본), 1.6으로 바꿔 같은 절차를 반복했다.

| goal_effect | 운영안 NDCG@5(순위) | 전체 인기 NDCG@5(순위) | 운영안 − 전체 인기 [95% 구간] | 공통 기초 이수 가정 정합률 운영안 / 전체 인기 |
| --- | --- | --- | --- | --- |
| 0 | 0.088108 (2위) | 0.084644 (7위) | +0.0035 [+0.0015, +0.0054] | 52.6% / 39.2% |
| 0.8 | 0.103070 (2위) | 0.100642 (4위) | +0.0024 [+0.0004, +0.0042] | 53.3% / 39.0% |
| 1.6 | 0.107329 (2위) | 0.100535 (6위) | +0.0068 [+0.0049, +0.0086] | 53.7% / 38.7% |

- 생성기가 목적을 쓰지 않아도 운영안의 NDCG는 전체 인기보다 높았다. 차이의 크기는 생성 가정에 따라 달라진다.
- 1위는 세 조건 모두 인구통계 집단 인기를 쓰는 검증 선택 규칙이다. 생성기가 인구통계 효과를 넣어 자료를 만들기 때문으로 보인다. 운영안은 인구통계 배제 요건 때문에 이 규칙을 쓰지 않는다.
- 정합률은 로드맵 기준이라 생성기 설정과 거의 무관하다.

## 테스트

```bash
python -m pytest -q
python scripts/verify_revision.py
```

torch 없이 FastAPI까지 설치한 환경에서 `pytest`는 176개 통과, 7개 생략이다. 생략된 것은 torch가 필요한 신경망 테스트 5개, `ETFREC_FULL=1`일 때만 실행하는 전체 규모 재현 1개, 이전 버전 번들이 있어야 하는 비교 1개다.
`verify_revision.py`는 회귀 테스트 63개 중 61개 통과, torch 테스트 2개 생략이다.
torch 2.14.1을 설치한 환경(2026-10-25 확인)에서는 `pytest` 182개 통과·1개 생략(`ETFREC_FULL=1` 전용), `verify_revision.py` 63개 모두 통과였다. 이 실행에서는 이전 버전 번들(`artifacts/bundle_v2/bundle.pkl`, 저장소에는 올리지 않음)이 있어 그 비교 테스트도 함께 실행됐다.

## 확인 범위와 한계

- 확인 환경: Linux, Python 3.13, NumPy 2.5, pandas 3.0, scikit-learn 1.9, FastAPI 0.115. 이전 기록 환경(Python 3.12, NumPy 2.3.5, pandas 2.2.3)과 보고서 수치가 같다.
- torch가 없는 환경에서 확인했다. 원래의 torch MF·MLP 학습 경로와 이를 쓰는 테스트는 실행하지 않았고, MF·MLP 비교는 NumPy 구현(`etfrec/factor_models.py`)으로 했다. torch 경로를 쓰려면 torch를 설치한 뒤 `--no-neural` 없이 학습한다. torch 경로의 테스트는 torch가 있는 환경에서 따로 실행해 통과했다(위 ‘테스트’).
- `python -m etfrec serve`로 띄운 서버에서 API 응답(상태, 진단 20문항, 신규 사용자 추천)과 화면 로드를 확인했고 브라우저 오류는 없었다. 실제 사용자의 사용성은 확인하지 않았다.
- KRX·공공데이터포털 시세 연결은 인증키가 필요하다. 테스트는 가짜 응답으로만 확인한다.
- 모든 결과는 모의 데이터에서 얻었다. 실제 학습 효과와 진단의 타당성은 파일럿 자료로 평가한다.
- 자체 진단·퀴즈는 금융투자교육원의 레버리지 상품 사전교육이나 증권사 거래 요건을 대신하지 않는다.

## 이전 개정 자료(참고용)

아래 파일은 이번 개정 전 설계(운영 = 성별 제외 라우터, 선택·평가 단계의 선수 필터 미적용)로 만든 산출물이다.
현재 코드의 기본값(목적 단계 규칙, 선수 조건 필수)으로 다시 만들면 수치와 화면 문구가 달라지므로 이번 보고서의 근거로 쓰지 않는다.

| 경로 | 내용 |
| --- | --- |
| `docs/report/중간보고서_ETF_교육_콘텐츠_추천시스템.docx`, `docs/report/비판검토_보완보고서.docx`, `docs/report/중간보고서_1차본_2026-10-13.docx` | 이전 중간보고서, 비판 대응 보고서, 1차본 |
| `docs/report/build/`, `docs/report/fig*.png` | 이전 보고서의 빌드 스크립트와 그림 |
| `artifacts/bundle_v1/`, `artifacts/bundle_v2/` | 이전 번들의 결과 CSV와 manifest |
| `docs/results/`, `docs/screens/` | 이전 민감도 결과와 화면 캡처 |
| `scripts/placebo_check.py`, `scripts/prereq_sensitivity.py`, `scripts/regression_check.py`, `scripts/results_table.py`, `scripts/ui_walkthrough.mjs` | 이전 점검 스크립트(현재 기본값에서는 결과가 달라질 수 있음) |
