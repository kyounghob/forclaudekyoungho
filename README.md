# etfrec — ETF 교육 콘텐츠 개인화·로드맵 추천 시스템

학습자의 **투자 목적(연금·노후, 배당·인컴, 장기 지수 투자, 단기 매매, 분산·안정)**, 위험성향·투자 기간, 현재 지식
수준을 진단한 뒤 → **필수 기초 개념(총보수·괴리율·환헤지·레버리지 복리 효과 등) → 목적별 핵심 개념 → 심화·리스크**
순서의 학습 로드맵을 만들고 → 지금 공부할 **다음 단원 5개**를 추천하고 → 로드맵의 마지막 단계에서 목적에 맞는
**ETF 유형(교육용 안내 카드)**으로 연결합니다. 특정 ETF 상품의 매수·매도를 권유하지 않습니다.

추천 기법은 수업에서 다룬 인기·규칙·콘텐츠·사용자 CF·아이템 CF·행렬분해·MLP를 같은 후보·같은 정답·같은
후처리로 비교하고, 검증에서 고른 설정을 잠근 뒤 테스트 주차에서 평가합니다. 학습된 번들로 REST API와
11단계 웹 UI(학습 설계 스튜디오)를 제공합니다.

![학습 로드맵](docs/screens/05_roadmap.png)

## 빠른 시작

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # torch 없이 쓰려면 requirements에서 torch를 빼고 --no-neural

python -m etfrec train --out artifacts/bundle_v2        # 모의 데이터 15,000명 생성 → 학습·검증·테스트 (약 3분)
python -m etfrec serve --bundle artifacts/bundle_v2     # http://127.0.0.1:8000
```

더 빨리 보려면 `python -m etfrec demo --n 3000` (작은 규모로 학습한 뒤 바로 서버 실행).
노트북 B(60단원, 목적 없음)의 세계를 그대로 재현하려면 `--catalog-version 1 --generator-version 1`을 붙입니다.

## 로드맵: 진단 → 기초 → 목적별 핵심 → 심화 → ETF 유형 연결

| 단계 | 내용 | 구현 |
| --- | --- | --- |
| 진단 | 16문항 진단 퀴즈(단원별 1문항)로 수준 1~3과 이미 아는 단원을 추정. 맞힌 문항은 '진단 통과' 기록이 되어 후보에서 빠지고, 틀린 문항은 기록하지 않음 | `etfrec/quiz.py`, `/api/quiz`, `/api/quiz/score` |
| 필수 기초 | 모든 목적에 공통: ETF 구조·총보수·NAV와 괴리율·유동성·환헤지(H)·레버리지 일일 복리 효과 (선수 관계 닫힘까지 포함) | `taxonomy.COMMON_CORE`, `roadmap.build_roadmap` |
| 목적별 핵심 | 목적 템플릿(연금: 연금계좌 ETF·세제·자산배분 / 인컴: 분배금·커버드콜·리츠·채권 / 단기 매매: 유동성·레버리지·괴리율 …) | `taxonomy.ROADMAP_TEMPLATES` |
| 심화·리스크 | 목적별 심화 단원 + 기간(단기 → 유동성 2, 장기 → 리밸런싱 2) + 성향(안정이면 레버리지 심화 제외) | `roadmap.build_roadmap` |
| ETF 유형 연결 | 10개 유형(국내 시장대표·해외 주식형·채권형·배당·커버드콜·자산배분·레버리지·인버스 …)에 필요한 개념 단원의 통과 여부로 카드가 열림. 세금·연금계좌 편입·사전교육 규제·주의 사항과 KRX 유형 통계 표시 | `taxonomy.ETF_TYPES`, `service.types`, `/api/types` |

로드맵은 추천 엔진에 두 가지로 들어갑니다. (1) **로드맵 신호** `r:roadmap`(현재 단계의 학습 가능 단원 1.0, 다음 단계
0.7, 선수 미이수 0.4)과 **목적 일치 신호** `r:goal`이 규칙·혼합 설정 풀에 추가되어 검증에서 다른 신호와 함께 비중이
선택됩니다. (2) **선수 단원 가드레일** `prereq_block`이 선수 단원을 통과하지 않은 단원을 후보에서 뺍니다(화면 기본 켬,
오프라인 평가에는 `RouterNoGender+prereq` 행으로 효과를 따로 기록).

## 공개 데이터·교육 자료 연결

`python -m etfrec sources list|check|sync|stats`

| 출처 | 쓰임 | 접근 |
| --- | --- | --- |
| 전국투자자교육협의회 ETF스쿨·연금스쿨·생애자산관리스쿨 | 기초·연금·자산배분 단원의 학습 자료와 용어, 퀴즈 문항 출처 | 웹(무료). 단원마다 출처 링크 표시 |
| 금융투자교육원 레버리지 ETP 사전교육 | 레버리지·인버스 유형으로 넘어가기 전 필수 관문(의무 이러닝, 평생 1회) | 웹. 로드맵 심화 단계와 유형 카드에 안내 |
| 한국거래소 ETF 정보·지수 정보 | 기초지수·PDF·투자설명서·용어집: 단원 예시와 용어 정의 | 웹(무료) |
| KRX 정보데이터시스템 ETF 전종목 기본정보 | 종목명·운용사·기초지수·총보수·과세유형·기초시장·자산 분류 → 유형 분류·유형 통계 | `sources sync`가 JSON 엔드포인트로 수집(비공식, 변경 가능). 내려받은 CSV도 `sources/krx.read_krx_csv`로 읽음 |
| 공공데이터포털 증권상품시세정보(ETF) | 종가·NAV·거래량 → 괴리율 예시 | `--datagokr-key` 또는 환경변수 `DATA_GO_KR_KEY` |
| 자산운용사 가이드북(KODEX·TIGER·RISE 등) | 용어·시각 자료 → 콘텐츠 텍스트 특징 확장 | 웹(무료 PDF). 인용·요약만 |

수집 전에는 `etfrec/sources/data/etf_list_sample.csv`(가상 종목 45개, 화면에 "샘플" 표시)로 유형 통계를 계산하고,
`sources sync` 뒤에는 `data/sources/` 스냅샷과 수집 시각(provenance)을 씁니다. 저작권이 있는 교육 자료는 링크와
출처만 저장하며 본문을 복제하지 않습니다.

## 무엇이 들어 있나

| 구성 | 파일 | 역할 |
| --- | --- | --- |
| 카탈로그 | `etfrec/catalog.py` | v2: 주제 21 × 수준 3 = 63개 단원, 선수 관계 76개, 단원별 출처·개념 태그. v1(60단원)은 노트북 재현용 |
| 분류·로드맵·퀴즈 | `etfrec/taxonomy.py`, `roadmap.py`, `quiz.py` | 목적·기간·ETF 유형 분류, 단계별 로드맵 생성·우선순위 신호, 16문항 진단 |
| 생성기 | `etfrec/synth.py` | 규칙을 공개한 모의 학습 로그. v2는 투자 목적·기간을 표본추출하고 목적-주제 친화도와 선수 미이수 페널티를 반영. `--effect 0`이면 위약 세계 |
| 데이터 | `etfrec/data.py` | `profiles.csv`·`study_log.csv`·`catalog.csv` 스키마와 검증, 행동 점수(조회 1·완료 2·통과/저장 3의 최댓값) |
| 특징 저장소 | `etfrec/features.py` | 기준 주 이전 로그로 반응 행렬·추정 수준·선호·세그먼트 코드·목적·기간 |
| 신호 | `etfrec/signals.py` | 교안 공식: 인기, 세그먼트 인기(수축), 콘텐츠 코사인, 사용자 CF, 아이템 CF, MF, MLP, 규칙·맥락·목적·로드맵 신호 (154개) |
| 신경망 | `etfrec/neural.py` | 표본 MF, 관측 MF, 9주차 MLP(BCEWithLogitsLoss). 학습만 torch, 추론은 NumPy |
| 설정 풀 | `etfrec/zoo.py` | 2,631개 조합(혼합 비중·세그먼트 변수·λ), CF 신뢰도 게이트, 계산식 설명·기여도 분해 |
| 평가 | `etfrec/evaluation.py` | 후보 생성(미통과·수준·선수 가드레일), Top-K 선택, NDCG@5·Hit@5·Diversity@5·선수 미이수 비율, 부트스트랩 |
| 라우터 | `etfrec/router.py` | 계층 수축 세그먼트 라우터와 λ 교차 선택 |
| 파이프라인 | `etfrec/pipeline.py` | 학습 → 검증 → 선택 잠금 → 테스트 → QA 80건 → 번들 저장(`bundle.pkl`, `manifest.json`, 결과 CSV) |
| 공개 데이터 | `etfrec/sources/` | 출처 등록부, KRX·공공데이터포털 커넥터, 스냅샷 동기화·유형 통계, 샘플 종목 |
| 서비스 | `etfrec/service.py` | 기존·임의 학습자 추천, 근거, 가드레일 검사, 로드맵, 유형 카드, 퀴즈 채점, what-if, 기법 비교 |
| 자연어 파서 | `etfrec/nlparse.py` | "연금저축으로 노후 준비, 안정 성향, 10년 이상…" → 목적·기간·관심·수준·기기·이력 (규칙 기반) |
| API | `etfrec/api.py` | FastAPI: `/api/recommend`, `/api/roadmap`, `/api/types`, `/api/quiz`, `/api/sources`, `/api/compare`, `/api/evaluation` … |
| UI | `etfrec/ui/` | 11단계 스테퍼(아이디어 → 기본 정보·목적 → 진단 → 기록 → 로드맵 → 설정 → 미리보기 → 시뮬레이션 → ETF 유형 연결 → 비교·평가 → 저장) |

![추천 미리보기](docs/screens/07_preview.png)

## 결과 (모의 데이터 v2, seed 42, 테스트 3주차, 학습자 6,438명)

| 방법 | NDCG@5 | Diversity@5 | 선수 미이수 비율 | 전역 1위 대비 [95% 구간] |
| --- | --- | --- | --- | --- |
| 규칙(검증 1위 = 전역) | 0.1356 | 0.898 | 0.688 | 기준 |
| 라우터(성별 제외, 운영) | 0.1343 | 0.911 | 0.628 | −0.0013 [−0.0033, 0.0008] |
| 인구통계 미사용 1위 | 0.1238 | 0.960 | 0.671 | −0.0118 |
| 사용자 CF | 0.1061 | 0.944 | 0.840 | −0.0295 |
| 운영 라우터 + 선수 가드레일 | 0.1014 | 0.997 | 0.000 | −0.0342 |
| 인기 | 0.0951 | 0.994 | 0.400 | −0.0405 |
| 아이템 CF | 0.0829 | 0.976 | 0.822 | −0.0527 |
| 콘텐츠 | 0.0805 | 0.888 | 0.815 | −0.0551 |
| MLP(9주차) | 0.0734 | 1.000 | 0.353 | −0.0622 |
| 관측 MF / 표본 MF | 0.0698 / 0.0687 | 0.981 / 0.949 | 0.610 / 0.828 | −0.0658 / −0.0670 |
| 무작위 | 0.0430 | 0.973 | 0.865 | −0.0926 |

검증 1위 설정은 **규칙[관심 주제 + 수준 일치 + 투자 목적 일치](base = 연령대 + 소득분위)** 로, 목적 일치 신호가 선택
되었습니다. 세그먼트 라우터는 전역 1위와 유의한 차이가 없고, 선수 단원 가드레일은 이 모의 세계에서 NDCG를 0.034
낮추는 대신 선수 미이수 추천을 0으로 만듭니다(생성기의 선수 페널티 크기에 따라 달라지는 교육 정책 비용 — 보고서
참고). 전체 표는 `artifacts/bundle_v2/test_results.csv`, 설정 2,631개의 검증 결과는 `validation_configurations.csv`,
선택 기록·학습 감사·QA는 `manifest.json`에 있습니다. 숫자는 가상 세계의 결과이며 실제 학습자 성과가 아닙니다.

노트북 B 원본 세계(v1: 60단원, 목적 없음)의 결과는 `artifacts/bundle_v1/`에 있으며 `python scripts/regression_check.py`가
노트북 기록(RULE 0.17123, RouterNoGender 0.17119, UCF 0.14268 …)과 소수점 5자리까지 일치하는지 확인합니다.

## 실제 로그 연결

`data/` 폴더에 다음 세 파일을 두고 `python -m etfrec train --data data --out artifacts/bundle_live`를 실행합니다.

- `profiles.csv`: `user, gender, age, income, exp, risk, mobile, interest1, interest2, placement` + 선택 `goal`(pension·income·long_term·trading·diversify), `horizon`(short·mid·long)
- `study_log.csv`: `user, item, week, day, hour, minute, complete, quiz, quiz_pass, save, drop, replay`
- `catalog.csv`: `item, title, topic, level, short` + 선택 `prereqs`("0;3" 형식), `sources`("kcie_etf_school;krx_etf_info")

`python -m etfrec generate --out data/synthetic`으로 같은 스키마의 예시 파일을 만들 수 있습니다.

## API 예시

```bash
curl -s localhost:8000/api/health
curl -s -X POST localhost:8000/api/parse -H 'Content-Type: application/json' \
  -d '{"text":"45세 직장인, 연금저축과 IRP로 노후 준비. 안정 성향, 10년 이상 장기, 초급"}'
curl -s -X POST localhost:8000/api/roadmap -H 'Content-Type: application/json' \
  -d '{"learner":{"age":45,"goal":"pension","horizon":"long","risk":0,"placement":1,"events":[{"item":0,"quiz_pass":true}]}}'
curl -s -X POST localhost:8000/api/recommend -H 'Content-Type: application/json' \
  -d '{"learner":{"goal":"income","interests":[4,18],"placement":2},"k":5,"guardrail":{"prereq_block":true}}'
curl -s -X POST localhost:8000/api/types -H 'Content-Type: application/json' -d '{"goal":"trading","risk":2}'
curl -s localhost:8000/api/quiz | head -c 400; curl -s localhost:8000/api/sources | head -c 400
```

추천 응답에는 추천 단원, 점수, 신호별 기여도, 추천 근거 문장, 선수 미이수 여부, 현재 로드맵 단계 포함 여부, 출처
링크, 가드레일 검사 결과, 세그먼트 경로, 계산식, 주제×수준 배치도, 로드맵 요약이 들어 있습니다. OpenAPI 문서는 `/docs`.

## 테스트

```bash
pytest -q                       # 지표 일치·가드레일·로드맵·퀴즈·KRX 분류·파서·파이프라인·오프라인/온라인 Top-5 일치·API (약 25초)
ETFREC_FULL=1 pytest -q -k full # 노트북 기록(seed 42, v1 세계)과 소수점 5자리 일치 확인 (약 2~3분)
node scripts/ui_walkthrough.mjs # Playwright로 11단계 UI를 조작하며 docs/screens/*.png 생성
```

## 범위와 한계

- 모의 데이터이며 생성기의 연령·소득·성별·목적 효과와 선수 페널티는 가정값입니다. 위약 세계(`--effect 0`)에서는
  인구통계를 쓰는 설정의 이점이 사라지는지로 파이프라인이 없는 효과를 만들어 내지 않는지 확인합니다.
- 수준·선수 가드레일은 수업의 교육 처방이 아니라 이 프로젝트의 시연 정책입니다. 선수 가드레일은 모의 세계에서
  정확도 비용이 있으므로, 실제 로그에서는 선수 단원을 건너뛴 학습자의 통과율로 페널티 크기를 보정해야 합니다.
- KRX 정보데이터시스템 JSON 수집은 비공식 엔드포인트라 바뀔 수 있어, 내려받은 CSV 경로도 함께 지원합니다.
  교육 자료는 링크·출처만 저장합니다.
- 성별 뒤집기 불변성은 코드 수준의 입력 의존성 점검이지 인과적 공정성 증명이 아닙니다.
- 운영 인증, 실시간 재학습, 10주차 이후 NeuMF·AutoRec·순차 모델은 구현하지 않았습니다.
