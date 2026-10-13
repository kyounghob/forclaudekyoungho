"""학습 단원 카탈로그: 주제 20개 × 수준 3단계 = 60개 단원과 콘텐츠 특징.

기본 카탈로그는 노트북 원본을 그대로 보존한다. 운영에서는 ``Catalog.from_csv``로
``item,title,topic,level,short`` 열을 가진 CSV를 읽어 같은 구조를 만든다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import BANNED_WORDS, SEED

TOPICS = [
    ("ETF 구조", ["ETF란 무엇인가", "ETF 가격은 어떻게 정해지나: NAV와 괴리율", "설정·환매와 유동성공급자(LP)의 역할"]),
    ("지수", ["지수란 무엇인가: 코스피200과 S&P500", "지수 산출 방식: 시가총액 가중과 동일 가중", "지수 정기변경과 편입·편출 효과"]),
    ("추적오차", ["추적오차의 기초", "추적오차가 생기는 이유: 보수·현금·배당", "추적오차와 추적차이를 직접 계산하기"]),
    ("비용", ["ETF 총보수 이해하기", "숨은 비용: 매매비용과 호가 스프레드", "총비용비율로 ETF 비교하기"]),
    ("분배금", ["ETF 분배금이란", "분배금 지급 구조와 재투자", "분배금과 세금: 배당소득세 이해"]),
    ("섹터 ETF", ["섹터 ETF 기초", "반도체·기술주 ETF 비교하기", "섹터 로테이션과 경기 사이클"]),
    ("채권 ETF", ["채권 ETF 기초", "채권 ETF와 금리의 관계", "듀레이션과 금리 민감도 계산"]),
    ("금 ETF", ["금 ETF 기초", "금 ETF와 인플레이션", "실질금리와 금 가격의 관계"]),
    ("환헤지", ["환율이 해외 ETF 수익률에 미치는 영향", "환헤지형과 환노출형 ETF 비교", "환헤지 비용과 금리차"]),
    ("레버리지·인버스", ["레버리지·인버스 ETF란", "일일 수익률 복리와 음의 복리 효과", "변동성 장세에서 레버리지 ETF의 위험"]),
    ("리밸런싱", ["리밸런싱이란", "정기 리밸런싱과 밴드 리밸런싱", "리밸런싱 비용과 세금 고려"]),
    ("자산배분", ["분산투자의 기초", "주식·채권 자산배분 이해하기", "상관관계와 포트폴리오 위험"]),
    ("해외 ETF", ["국내 상장 해외 ETF와 해외 상장 ETF", "해외 ETF 거래 방법과 환전", "해외 ETF 세금: 양도소득세와 손익통산"]),
    ("유동성", ["ETF 거래량과 유동성", "호가 스프레드 읽기", "괴리율이 커지는 상황 이해하기"]),
    ("테마 ETF", ["테마 ETF란", "테마 ETF의 구성 종목 확인하기", "테마 ETF의 집중 위험"]),
    ("원자재 ETF", ["원자재 ETF 기초", "선물 기반 ETF와 롤오버", "콘탱고와 백워데이션"]),
    ("리츠 ETF", ["리츠 ETF 기초", "리츠 ETF와 금리", "리츠 섹터별 특성"]),
    ("연금계좌 ETF", ["연금계좌에서 ETF 투자하기", "IRP·연금저축의 ETF 투자 규칙", "연금계좌 세액공제와 과세이연"]),
    ("액티브 ETF", ["액티브 ETF란", "액티브 ETF와 패시브 ETF 비교", "액티브 ETF의 비교지수와 상관계수"]),
    ("ESG ETF", ["ESG ETF란", "ESG 평가 방법과 한계", "ESG 지수와 그린워싱 위험"]),
]
GROUP4 = {"ETF 기초형": ["ETF 구조", "지수", "추적오차", "비용", "유동성"],
          "성장·테마형": ["섹터 ETF", "해외 ETF", "테마 ETF", "액티브 ETF", "ESG ETF", "레버리지·인버스"],
          "안정·인컴형": ["채권 ETF", "분배금", "리츠 ETF", "금 ETF", "원자재 ETF"],
          "자산배분·연금형": ["자산배분", "리밸런싱", "연금계좌 ETF", "환헤지"]}
LABELS = {"click_tier": ["신규(조회 0)", "보통(1~9)", "많음(10+)"], "pref_cluster": list(GROUP4),
          "age_band": ["29세 이하", "30대", "40대", "50대", "60세 이상"],
          "income_q": ["소득 1분위(하위 20%)", "소득 2분위", "소득 3분위", "소득 4분위", "소득 5분위(상위 20%)"],
          "gender": ["남성", "여성"]}
RADIX = np.array([3, 4, 5, 5, 2])
EXPS, RISKS, HOURS = ["없음", "1~3년", "3년 이상"], ["안정", "중립", "적극"], ["출근", "점심", "저녁", "심야"]
LEVEL_NAMES = {1: "기초", 2: "구조·계산", 3: "심화·위험"}

# 규칙·공정성 점검에 쓰는 주제 묶음
LIFE_OLD_TOPICS = ["채권 ETF", "분배금", "연금계좌 ETF", "자산배분", "리츠 ETF"]
LIFE_YOUNG_TOPICS = ["섹터 ETF", "해외 ETF", "테마 ETF", "ETF 구조"]
INC_HIGH_TOPICS = ["해외 ETF", "연금계좌 ETF", "환헤지", "자산배분"]
INC_LOW_TOPICS = ["비용", "ETF 구조", "분배금"]
RISK_HI_TOPICS = ["레버리지·인버스", "섹터 ETF", "테마 ETF", "액티브 ETF"]
RISK_LO_TOPICS = ["채권 ETF", "금 ETF", "자산배분", "리밸런싱"]


@dataclass
class Catalog:
    """단원 배열(아이템 번호 순)과 그로부터 만든 특징."""
    topics: list                       # 주제 이름 목록(TN)
    item_topic: np.ndarray             # (n_items,) 주제 번호
    item_level: np.ndarray             # (n_items,) 수준 1~3
    item_title: np.ndarray             # (n_items,) 제목
    item_short: np.ndarray             # (n_items,) 짧은 콘텐츠 여부
    group_names: list = field(default_factory=lambda: list(GROUP4))
    topic_group: np.ndarray = None     # (n_topics,) 선호 군집 번호
    X_cat: np.ndarray = None           # 아이템 × (주제 원-핫 + 수준 원-핫·0.5)
    X_txt: sp.csr_matrix = None        # 아이템 × 제목 문자 n-gram TF-IDF  [교안 4-3]

    def __post_init__(self):
        self.ti = {t: i for i, t in enumerate(self.topics)}
        self.n_topics = len(self.topics)
        self.n_items = len(self.item_topic)
        groups = GROUP4 if self.topic_group is None else None
        if groups is not None:
            self.topic_group = np.array([next(g for g, (_, v) in enumerate(GROUP4.items()) if t in v)
                                         if any(t in v for v in GROUP4.values()) else 0 for t in self.topics])
        if self.X_cat is None:
            self.X_cat = np.hstack([onehot(self.item_topic, self.n_topics), onehot(self.item_level - 1, 3) * 0.5])
        if self.X_txt is None:
            texts = [f"{self.topics[t]} {ti}" for t, ti in zip(self.item_topic, self.item_title)]
            self.X_txt = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3)).fit_transform(texts).tocsr()
        self.masks = {
            "life_old": self._topic_mask(LIFE_OLD_TOPICS), "life_young": self._topic_mask(LIFE_YOUNG_TOPICS),
            "inc_high": self._topic_mask(INC_HIGH_TOPICS), "inc_low": self._topic_mask(INC_LOW_TOPICS),
            "risk_hi": self._topic_mask(RISK_HI_TOPICS), "risk_lo": self._topic_mask(RISK_LO_TOPICS),
        }
        # 공정성 점검: 심화(수준 3) 또는 레버리지·인버스 콘텐츠
        self.advanced = (self.item_level == 3) | self._topic_mask(["레버리지·인버스"])
        bad = [t for t in self.item_title if any(b in t for b in BANNED_WORDS)]
        if bad:
            raise ValueError(f"단원 제목에 금칙어가 있습니다: {bad}")

    def _topic_mask(self, names):
        ids = [self.ti[t] for t in names if t in self.ti]
        return np.isin(self.item_topic, ids)

    @classmethod
    def default(cls, seed: int = SEED) -> "Catalog":
        tn = [t for t, _ in TOPICS]
        item_topic = np.repeat(np.arange(len(TOPICS)), 3)
        item_level = np.tile([1, 2, 3], len(TOPICS))
        item_title = np.array([TOPICS[t][1][l - 1] for t, l in zip(item_topic, item_level)])
        rs = np.random.default_rng(seed + 3)
        item_short = rs.random(len(item_topic)) < np.array([0.7, 0.45, 0.2])[item_level - 1]
        return cls(tn, item_topic, item_level, item_title, item_short)

    @classmethod
    def from_csv(cls, path: str) -> "Catalog":
        df = pd.read_csv(path)
        need = {"item", "title", "topic", "level"}
        if not need <= set(df.columns):
            raise ValueError(f"카탈로그 CSV에 {sorted(need - set(df.columns))} 열이 없습니다")
        df = df.sort_values("item").reset_index(drop=True)
        if not np.array_equal(df.item.values, np.arange(len(df))):
            raise ValueError("item 번호는 0부터 연속이어야 합니다")
        topics = list(pd.unique(df.topic))
        ti = {t: i for i, t in enumerate(topics)}
        short = df["short"].astype(bool).values if "short" in df else np.zeros(len(df), bool)
        return cls(topics, df.topic.map(ti).values.astype(int), df.level.values.astype(int),
                   df.title.values.astype(str), short)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame({"item": np.arange(self.n_items), "item_id": [f"E{i}" for i in range(self.n_items)],
                             "title": self.item_title, "topic": [self.topics[t] for t in self.item_topic],
                             "topic_id": self.item_topic, "level": self.item_level, "short": self.item_short,
                             "group": [self.group_names[self.topic_group[t]] for t in self.item_topic]})

    def item_info(self, i: int) -> dict:
        i = int(i)
        return dict(item=i, item_id=f"E{i}", title=str(self.item_title[i]), topic=self.topics[self.item_topic[i]],
                    topic_id=int(self.item_topic[i]), level=int(self.item_level[i]),
                    level_name=LEVEL_NAMES[int(self.item_level[i])], short=bool(self.item_short[i]),
                    group=self.group_names[self.topic_group[self.item_topic[i]]])


def onehot(codes, k: int) -> np.ndarray:
    """범위 밖 코드(결측 등)는 모두 0인 행으로 둔다."""
    codes = np.asarray(codes, dtype=int)
    out = np.zeros((len(codes), k), np.float32)
    valid = (codes >= 0) & (codes < k)
    out[np.flatnonzero(valid), codes[valid]] = 1
    return out
