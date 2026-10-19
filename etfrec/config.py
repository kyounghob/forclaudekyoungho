"""전역 상수. 노트북 B(ETF 교육)의 설정을 그대로 옮기되 환경변수로 조정할 수 있다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

K = 5                                   # [교안 7-2] Top-K 평가의 K
SEED = int(os.environ.get("REC_SEED", "42"))
CATALOG_VERSION = int(os.environ.get("REC_CATALOG", "2"))     # 1 = 노트북 원본 60단원(주제 20), 2 = 66단원(주제 22: 커버드콜·절세 계좌 추가) + 선수 관계
GENERATOR_VERSION = int(os.environ.get("REC_GENERATOR", "2")) # 1 = 노트북과 같은 난수 순서, 2 = 투자 목적·선수 관계 반영
SEG_VARS = ["click_tier", "pref_cluster", "age_band", "income_q", "gender"]   # 세그먼트 계층(위 → 아래)
SEG_KO = {"click_tier": "학습활동", "pref_cluster": "선호군집", "age_band": "연령대",
          "income_q": "소득분위", "gender": "성별"}
SEG_LAMS = (5, 20, 80)                  # 세그먼트 인기 수축 λ 후보 — [교안 5-3] lambda_value=10 주변
MIN_ROUTER_USERS = 20                   # 이 수 미만의 세그먼트는 상위 노드 챔피언을 쓴다
MAX_REFERENCE_USERS = int(os.environ.get("REC_REFERENCE_USERS", "4000"))   # 사용자 CF 참조 사용자 상한
N_CPU = min(2, max(1, os.cpu_count() or 1))

N_WEEKS = 4                             # 0·1주 학습, 2주 검증, 3주 평가
VAL_WEEK, TEST_WEEK = 2, 3
CLICK_CUTS = (1, 10)                    # 학습활동(조회 수): 0 → 신규, 1~9 → 보통, 10+ → 많음
EFFECT_SCALE = float(os.environ.get("REC_EFFECT", "1.0"))   # 생성기 주제 선호의 인구통계 효과 배율(0이어도 위약 아님: scripts/placebo_check.py)
GENDER_EFFECT = 0.3

# [교안 1-3] action_score 예시 2(ETF 교육). 한 학습 시도의 점수는 합이 아니라 최댓값이다.
ACTION_SCORE = {"view": 1, "complete": 2, "quiz_pass": 3, "save": 3, "replay_pass": 1, "drop": 0}
BANNED_WORDS = ["매수", "매도", "사세요", "파세요", "수익 보장", "추천 종목", "지금 사", "급등", "대박"]
NOTICE = "교육 콘텐츠 추천입니다. 특정 ETF의 매수·매도를 권유하지 않습니다."

UCF_DEMOS = {"none": (), "age": ("age",), "age+inc": ("age", "income"),
             "age+inc+gender": ("age", "income", "gender"),
             "all": ("age", "income", "gender", "experience", "risk", "device", "hour",
                     "quiz", "completion", "drop", "level")}
UCF_GRID = [(k, d, w) for k in (20, 50, 100)
            for d, ws in [("none", (0.0,)), ("age", (0.2, 0.5)), ("age+inc", (0.2, 0.5)),
                          ("age+inc+gender", (0.2, 0.5)), ("all", (0.2, 0.5))] for w in ws]
ICF_GRID = [(lam, c) for lam in (0, 5, 10, 30) for c in (0, 1)]
MF_GRID = [(f, r) for f in (8, 16, 32) for r in (0.01, 0.1)]
BPR_GRID = list(MF_GRID)                     # 확장: BPR 쌍별 손실 행렬분해 — 표본 MF와 같은 격자(공정한 튜닝 예산)
CONTENT_GRID = [(x, c) for x in ("cat", "txt", "both") for c in (0, 1)]

RULE_PARTS_V1 = [("r:pref", 3), ("r:lvl", 2), ("r:life", 2), ("r:inc", 2), ("r:risk", 2), ("r:dev", 1)]
RULE_PARTS = RULE_PARTS_V1 + [("r:goal", 2), ("r:roadmap", 2)]   # 투자 목적 일치·로드맵 단계 가산점(프로젝트 확장)
CTX_NAMES = ["ctx:next", "ctx:lvlfit"]

GOALS = {"pension": "연금·노후 대비", "income": "배당·인컴 수취", "long_term": "장기 자산형성(지수 투자)",
         "trading": "단기 매매·전술적 투자", "diversify": "분산·안정 추구"}
GOAL_KEYS = list(GOALS)
HORIZONS = {"short": "1년 미만", "mid": "1~5년", "long": "5년 이상"}
HORIZON_KEYS = list(HORIZONS)


@dataclass
class GuardrailConfig:
    """수준·선수 개념 가드레일. 수업의 확정된 교육 처방이 아니라 이 프로젝트의 시연용 정책이다."""
    block_gap: int = 2          # 추정 수준보다 이만큼 이상 높은 단원은 제외
    plus_one_max: int = 1       # 한 단계 위 단원은 목록에 최대 몇 개
    exclude_passed: bool = True # 퀴즈를 통과한 단원은 후보에서 제외
    prereq_block: bool = False  # 선수 단원을 통과하지 않은 단원은 제외(평가 기본 꺼짐, 화면 기본 켜짐)


@dataclass
class TrainConfig:
    n_learners: int = int(os.environ.get("REC_N", "15000"))
    seed: int = SEED
    effect_scale: float = EFFECT_SCALE
    gender_effect: float = GENDER_EFFECT
    val_week: int = VAL_WEEK
    test_week: int = TEST_WEEK
    operational_router: str = "RouterNoGender"
    router_lams: tuple = (0, 20, 100, 500, 3000, 1e9)
    router_reps: int = 2
    bootstrap_n: int = 500
    train_max_rows: int = int(os.environ.get("REC_TRAIN_MAX", "200000"))
    n_workers: int = N_CPU
    guardrail: GuardrailConfig = field(default_factory=GuardrailConfig)
    catalog_version: int = CATALOG_VERSION
    generator_version: int = GENERATOR_VERSION
    goal_effect: float = 0.8        # 생성기 v2: 목적 친화도가 주제 선호 로짓에 더해지는 크기
    prereq_penalty: float = 0.8     # 생성기 v2: 미이수 선수 단원 1개당 완료·통과 로짓 감소(최대 2개)

    @property
    def rule_parts(self):
        """버전 1(노트북 재현)은 원래 규칙 6개, 버전 2는 목적·로드맵 가산점을 더한 8개."""
        return RULE_PARTS_V1 if int(self.generator_version) == 1 else RULE_PARTS
