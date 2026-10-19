"""학습 단원 카탈로그: 주제 × 수준 3단계의 단원과 콘텐츠 특징, 선수 관계, 출처.

- 버전 1: 노트북 원본(주제 20개 = 60단원). 노트북 기록과의 일치 검사에만 쓴다.
- 버전 2(기본): 커버드콜·절세 계좌(ISA) 주제를 더한 22개 주제 = 66단원, 세제 단원 제목 보강, 단원 간 선수 관계, 공개 교육 자료 출처 참조.
운영에서는 ``Catalog.from_csv``로 ``item,title,topic,level,short[,prereqs,sources]`` 열을 가진 CSV를 읽는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import BANNED_WORDS, CATALOG_VERSION, SEED
from .lessons import lesson as _lesson

TOPICS_V1 = [
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
# 버전 2 제목 보강(세제 내용, 중간 점검 지적 반영). 버전 1 제목은 노트북 재현을 위해 그대로 둔다.
V2_TITLE_OVERRIDES = {("해외 ETF", 3): "해외 ETF 세금: 과표기준가·보유기간과세와 양도소득세",
                      ("연금계좌 ETF", 2): "IRP·연금저축의 ETF 투자 규칙과 위험자산 70% 한도",
                      ("레버리지·인버스", 3): "변동성 장세의 레버리지 위험과 거래 요건(사전교육·기본예탁금)"}
TOPICS_V2 = [(t, [V2_TITLE_OVERRIDES.get((t, l + 1), u) for l, u in enumerate(units)]) for t, units in TOPICS_V1] + [
    ("커버드콜 ETF", ["커버드콜 ETF란", "옵션 프리미엄과 분배금의 원천", "커버드콜의 상승 제한과 총수익 비교"]),
    ("절세 계좌", ["ISA 계좌란: 비과세 한도와 분리과세", "ISA 유형·납입 한도·의무가입 기간", "ISA 만기 자금의 연금계좌 전환과 절세 순서"]),
]
GROUP4 = {"ETF 기초형": ["ETF 구조", "지수", "추적오차", "비용", "유동성"],
          "성장·테마형": ["섹터 ETF", "해외 ETF", "테마 ETF", "액티브 ETF", "ESG ETF", "레버리지·인버스"],
          "안정·인컴형": ["채권 ETF", "분배금", "리츠 ETF", "금 ETF", "원자재 ETF", "커버드콜 ETF"],
          "자산배분·연금형": ["자산배분", "리밸런싱", "연금계좌 ETF", "환헤지", "절세 계좌"]}
LABELS = {"click_tier": ["신규(조회 0)", "보통(1~9)", "많음(10+)"], "pref_cluster": list(GROUP4),
          "age_band": ["29세 이하", "30대", "40대", "50대", "60세 이상"],
          "income_q": ["소득 1분위(하위 20%)", "소득 2분위", "소득 3분위", "소득 4분위", "소득 5분위(상위 20%)"],
          "gender": ["남성", "여성"]}
RADIX = np.array([3, 4, 5, 5, 2])
EXPS, RISKS, HOURS = ["없음", "1~3년", "3년 이상"], ["안정", "중립", "적극"], ["출근", "점심", "저녁", "심야"]
LEVEL_NAMES = {1: "기초", 2: "구조·계산", 3: "심화·위험"}

# 규칙·공정성 점검에 쓰는 주제 묶음
LIFE_OLD_TOPICS = ["채권 ETF", "분배금", "연금계좌 ETF", "자산배분", "리츠 ETF", "절세 계좌"]
LIFE_YOUNG_TOPICS = ["섹터 ETF", "해외 ETF", "테마 ETF", "ETF 구조"]
INC_HIGH_TOPICS = ["해외 ETF", "연금계좌 ETF", "환헤지", "자산배분"]
INC_LOW_TOPICS = ["비용", "ETF 구조", "분배금"]
RISK_HI_TOPICS = ["레버리지·인버스", "섹터 ETF", "테마 ETF", "액티브 ETF"]
RISK_LO_TOPICS = ["채권 ETF", "금 ETF", "자산배분", "리밸런싱"]

# 주제 간 선수 관계: (주제, 수준) ← [(선수 주제, 수준), ...]. 같은 주제 안에서는 수준 n−1이 항상 선수이다.
CROSS_PREREQS = {
    ("ETF 구조", 2): [("지수", 1)],
    ("추적오차", 1): [("ETF 구조", 1), ("지수", 1)],
    ("비용", 2): [("유동성", 1)],
    ("분배금", 3): [("비용", 1)],
    ("섹터 ETF", 1): [("지수", 1)],
    ("채권 ETF", 1): [("ETF 구조", 1)],
    ("금 ETF", 1): [("ETF 구조", 1)],
    ("환헤지", 1): [("해외 ETF", 1)],
    ("레버리지·인버스", 1): [("ETF 구조", 1), ("지수", 1)],
    ("레버리지·인버스", 2): [("비용", 1)],
    ("리밸런싱", 1): [("자산배분", 1)],
    ("자산배분", 1): [("ETF 구조", 1)],
    ("해외 ETF", 1): [("ETF 구조", 1), ("지수", 1)],
    ("해외 ETF", 3): [("분배금", 3)],
    ("유동성", 1): [("ETF 구조", 1)],
    ("유동성", 3): [("ETF 구조", 2)],
    ("테마 ETF", 1): [("섹터 ETF", 1)],
    ("원자재 ETF", 1): [("ETF 구조", 1)],
    ("원자재 ETF", 2): [("레버리지·인버스", 2)],
    ("리츠 ETF", 1): [("분배금", 1)],
    ("리츠 ETF", 2): [("채권 ETF", 2)],
    ("연금계좌 ETF", 1): [("비용", 1), ("분배금", 1)],
    ("연금계좌 ETF", 2): [("해외 ETF", 1), ("레버리지·인버스", 1)],
    ("액티브 ETF", 1): [("지수", 1), ("추적오차", 1)],
    ("ESG ETF", 1): [("지수", 1)],
    ("커버드콜 ETF", 1): [("분배금", 1), ("지수", 1)],
    ("커버드콜 ETF", 3): [("레버리지·인버스", 2)],
    ("절세 계좌", 1): [("분배금", 1)],
    ("절세 계좌", 3): [("연금계좌 ETF", 3)],
}
# 단원 ↔ 공개 교육 자료 출처(etfrec.sources.registry의 키). 레버리지·인버스는 금융투자교육원 사전교육을 필수로 안내한다.
TOPIC_SOURCES = {
    "ETF 구조": ["kcie_etf_school", "krx_etf_info", "am_guidebooks"], "지수": ["kcie_etf_school", "krx_index"],
    "추적오차": ["krx_etf_info", "am_guidebooks"], "비용": ["kcie_etf_school", "am_guidebooks", "krx_etf_info"],
    "분배금": ["am_guidebooks", "kcie_etf_school"], "섹터 ETF": ["am_guidebooks", "krx_etf_info"],
    "채권 ETF": ["kcie_etf_school", "am_guidebooks"], "금 ETF": ["am_guidebooks"], "환헤지": ["am_guidebooks", "kcie_etf_school"],
    "레버리지·인버스": ["kifin_leverage", "krx_etf_info", "am_guidebooks"], "리밸런싱": ["kcie_life_school"],
    "자산배분": ["kcie_life_school", "kcie_pension_school"], "해외 ETF": ["am_guidebooks", "kcie_etf_school"],
    "유동성": ["krx_etf_info", "krx_data"], "테마 ETF": ["am_guidebooks"], "원자재 ETF": ["am_guidebooks", "kcie_alt_school"],
    "리츠 ETF": ["kcie_alt_school", "am_guidebooks"], "연금계좌 ETF": ["kcie_pension_school", "am_guidebooks"],
    "액티브 ETF": ["krx_etf_info", "am_guidebooks"], "ESG ETF": ["am_guidebooks"], "커버드콜 ETF": ["am_guidebooks", "kcie_etf_school"],
    "절세 계좌": ["kcie_pension_school", "kcie_life_school", "am_guidebooks"],
}
# 단원이 다루는 핵심 개념(용어집·ETF 유형 연결에 쓴다). 버전 2에서 제목을 보강한 단원은 V2_CONCEPT_EXTRA를 앞에 붙인다.
UNIT_CONCEPTS = {
    ("ETF 구조", 1): ["상장지수펀드", "거래소 매매"], ("ETF 구조", 2): ["NAV", "괴리율"], ("ETF 구조", 3): ["설정·환매", "LP"],
    ("비용", 1): ["총보수"], ("비용", 2): ["호가 스프레드", "매매비용"], ("비용", 3): ["총비용비율"],
    ("환헤지", 1): ["환노출"], ("환헤지", 2): ["환헤지(H)"], ("환헤지", 3): ["헤지 비용"],
    ("레버리지·인버스", 1): ["레버리지", "인버스"], ("레버리지·인버스", 2): ["일일 복리", "음의 복리"],
    ("분배금", 1): ["분배금"], ("분배금", 3): ["배당소득세"], ("연금계좌 ETF", 3): ["세액공제", "과세이연"],
    ("해외 ETF", 1): ["국내상장 해외 ETF"], ("해외 ETF", 3): ["양도소득세", "손익통산"], ("원자재 ETF", 2): ["롤오버"], ("원자재 ETF", 3): ["콘탱고"],
    ("연금계좌 ETF", 2): ["편입 가능 ETF"], ("레버리지·인버스", 3): ["변동성 끌림"],
    ("절세 계좌", 1): ["ISA", "비과세 한도 200/400만원", "9.9% 분리과세"], ("절세 계좌", 2): ["납입 한도 연 2,000만원", "의무가입 3년"],
    ("절세 계좌", 3): ["연금계좌 전환", "추가 세액공제 최대 300만원", "절세 계좌 순서"],
    ("커버드콜 ETF", 1): ["커버드콜"], ("커버드콜 ETF", 2): ["옵션 프리미엄"], ("커버드콜 ETF", 3): ["상승 제한"],
    ("유동성", 2): ["호가 스프레드"], ("유동성", 3): ["괴리율"], ("채권 ETF", 2): ["금리 민감도"], ("채권 ETF", 3): ["듀레이션"],
}
V2_CONCEPT_EXTRA = {("해외 ETF", 3): ["과표기준가", "보유기간과세"], ("연금계좌 ETF", 2): ["위험자산 70% 한도"],
                    ("레버리지·인버스", 3): ["사전교육", "기본예탁금", "모의거래"]}


def find_prereq_cycle(prereqs: dict) -> list:
    """선수 관계 {단원: [선수 단원]}에서 순환 하나를 [a, b, …, a]로 돌려준다. 없으면 []."""
    state, stack = {}, []

    def visit(u):
        state[u] = 1; stack.append(u)
        for p in prereqs.get(u, []):
            if state.get(p) == 1:
                return stack[stack.index(p):] + [p]
            if state.get(p) is None:
                found = visit(p)
                if found:
                    return found
        state[u] = 2; stack.pop()
        return []

    for u in list(prereqs):
        if state.get(u) is None:
            found = visit(u)
            if found:
                return found
    return []


@dataclass
class Catalog:
    """단원 배열(아이템 번호 순)과 그로부터 만든 특징."""
    topics: list                       # 주제 이름 목록
    item_topic: np.ndarray             # (n_items,) 주제 번호
    item_level: np.ndarray             # (n_items,) 수준 1~3
    item_title: np.ndarray             # (n_items,) 제목
    item_short: np.ndarray             # (n_items,) 짧은 콘텐츠 여부
    group_names: list = field(default_factory=lambda: list(GROUP4))
    topic_group: np.ndarray = None     # (n_topics,) 선호 군집 번호
    X_cat: np.ndarray = None           # 아이템 × (주제 원-핫 + 수준 원-핫·0.5)
    X_txt: sp.csr_matrix = None        # 아이템 × 제목 문자 n-gram TF-IDF  [교안 4-3]
    prereqs: dict = None               # item → [선수 item, ...]
    sources: dict = None               # item → [출처 키, ...]
    version: int = CATALOG_VERSION

    def __post_init__(self):
        self.ti = {t: i for i, t in enumerate(self.topics)}
        self.n_topics = len(self.topics)
        self.n_items = len(self.item_topic)
        if self.topic_group is None:
            self.topic_group = np.array([next((g for g, (_, v) in enumerate(GROUP4.items()) if t in v), 0) for t in self.topics])
        if self.X_cat is None:
            self.X_cat = np.hstack([onehot(self.item_topic, self.n_topics), onehot(self.item_level - 1, 3) * 0.5])
        if self.X_txt is None:
            texts = [f"{self.topics[t]} {ti}" for t, ti in zip(self.item_topic, self.item_title)]
            self.X_txt = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3)).fit_transform(texts).tocsr()
        self.unit_index = {(int(t), int(l)): i for i, (t, l) in enumerate(zip(self.item_topic, self.item_level))}
        if self.prereqs is None:
            self.prereqs = self._default_prereqs()
        if self.sources is None:
            self.sources = {i: list(TOPIC_SOURCES.get(self.topics[self.item_topic[i]], ["am_guidebooks"])) for i in range(self.n_items)}
        P = np.zeros((self.n_items, self.n_items), bool)
        for i, ps in self.prereqs.items():
            for p in ps:
                P[i, p] = True
        self.prereq_matrix = P
        self.masks = {
            "life_old": self._topic_mask(LIFE_OLD_TOPICS), "life_young": self._topic_mask(LIFE_YOUNG_TOPICS),
            "inc_high": self._topic_mask(INC_HIGH_TOPICS), "inc_low": self._topic_mask(INC_LOW_TOPICS),
            "risk_hi": self._topic_mask(RISK_HI_TOPICS), "risk_lo": self._topic_mask(RISK_LO_TOPICS),
        }
        self.advanced = (self.item_level == 3) | self._topic_mask(["레버리지·인버스"])
        bad = [t for t in self.item_title if any(b in t for b in BANNED_WORDS)]
        if bad:
            raise ValueError(f"단원 제목에 금칙어가 있습니다: {bad}")

    # ---------- 구성 ----------
    def _topic_mask(self, names):
        ids = [self.ti[t] for t in names if t in self.ti]
        return np.isin(self.item_topic, ids)

    def unit(self, topic: str, level: int):
        """(주제 이름, 수준) → 아이템 번호. 없으면 None."""
        t = self.ti.get(topic)
        return None if t is None else self.unit_index.get((t, int(level)))

    def _default_prereqs(self) -> dict:
        out = {i: [] for i in range(self.n_items)}
        for i in range(self.n_items):
            t, l = int(self.item_topic[i]), int(self.item_level[i])
            if l > 1 and (t, l - 1) in self.unit_index:
                out[i].append(self.unit_index[(t, l - 1)])
            for pt, pl in CROSS_PREREQS.get((self.topics[t], l), []):
                p = self.unit(pt, pl)
                if p is not None and p not in out[i]:
                    out[i].append(p)
        return out

    def missing_prereqs(self, item: int, passed: np.ndarray) -> list:
        return [p for p in self.prereqs.get(int(item), []) if not passed[p]]

    def missing_prereq_count(self, passed_rows: np.ndarray) -> np.ndarray:
        """(R, n_items) 통과 행렬 → (R, n_items) 미이수 선수 단원 수."""
        return (~passed_rows).astype(np.int32) @ self.prereq_matrix.T.astype(np.int32)

    def concepts(self, item: int) -> list:
        key = (self.topics[self.item_topic[item]], int(self.item_level[item]))
        extra = V2_CONCEPT_EXTRA.get(key, []) if int(self.version) >= 2 else []
        return list(extra) + list(UNIT_CONCEPTS.get(key, []))

    @classmethod
    def default(cls, seed: int = SEED, version: int = CATALOG_VERSION) -> "Catalog":
        topics_def = TOPICS_V1 if int(version) == 1 else TOPICS_V2
        tn = [t for t, _ in topics_def]
        item_topic = np.repeat(np.arange(len(topics_def)), 3)
        item_level = np.tile([1, 2, 3], len(topics_def))
        item_title = np.array([topics_def[t][1][l - 1] for t, l in zip(item_topic, item_level)])
        rs = np.random.default_rng(seed + 3)
        item_short = rs.random(len(item_topic)) < np.array([0.7, 0.45, 0.2])[item_level - 1]
        return cls(tn, item_topic, item_level, item_title, item_short, version=int(version))

    @classmethod
    def from_csv(cls, path: str) -> "Catalog":
        df = pd.read_csv(path, dtype={"prereqs": str, "sources": str})    # 선수가 0~1개뿐인 사슬 카탈로그도 '0.0'이 아니라 '0'으로 읽는다
        need = {"item", "title", "topic", "level"}
        if not need <= set(df.columns):
            raise ValueError(f"카탈로그 CSV에 {sorted(need - set(df.columns))} 열이 없습니다")
        df = df.sort_values("item").reset_index(drop=True)
        if not np.array_equal(df.item.values, np.arange(len(df))):
            raise ValueError("item 번호는 0부터 연속이어야 합니다")
        topics = list(pd.unique(df.topic))
        ti = {t: i for i, t in enumerate(topics)}
        short = df["short"].astype(bool).values if "short" in df else np.zeros(len(df), bool)
        prereqs = None
        if "prereqs" in df.columns:
            n, prereqs = len(df), {}
            for r in df.itertuples():
                vals = [x.strip() for x in str(r.prereqs).split(";") if x.strip() and x.strip().lower() not in ("nan", "none")]
                bad = [x for x in vals if not x.isdigit() or not (0 <= int(x) < n) or int(x) == int(r.item)]
                if bad:                                     # 음수(예: -1은 마지막 단원을 가리키게 된다)·범위 밖·자기 자신은 거부
                    raise ValueError(f"item {int(r.item)}의 prereqs에 쓸 수 없는 값 {bad}(0 이상 {n} 미만, 자기 자신 제외)")
                prereqs[int(r.item)] = [int(x) for x in vals]
            cyc = find_prereq_cycle(prereqs)
            if cyc:
                raise ValueError(f"선수 관계에 순환이 있습니다: {' → '.join(map(str, cyc))}")
        sources = None
        if "sources" in df.columns:
            sources = {int(r.item): [x.strip() for x in str(r.sources).split(";") if x.strip() and x.strip() != "nan"] for r in df.itertuples()}
        return cls(topics, df.topic.map(ti).values.astype(int), df.level.values.astype(int), df.title.values.astype(str), short,
                   prereqs=prereqs, sources=sources)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame({"item": np.arange(self.n_items), "item_id": [f"E{i}" for i in range(self.n_items)],
                             "title": self.item_title, "topic": [self.topics[t] for t in self.item_topic],
                             "topic_id": self.item_topic, "level": self.item_level, "short": self.item_short,
                             "group": [self.group_names[self.topic_group[t]] for t in self.item_topic],
                             "prereqs": [";".join(str(p) for p in self.prereqs[i]) for i in range(self.n_items)],
                             "sources": [";".join(self.sources[i]) for i in range(self.n_items)],
                             "concepts": [", ".join(self.concepts(i)) for i in range(self.n_items)]})

    def item_info(self, i: int) -> dict:
        i = int(i)
        return dict(item=i, item_id=f"E{i}", title=str(self.item_title[i]), topic=self.topics[self.item_topic[i]],
                    topic_id=int(self.item_topic[i]), level=int(self.item_level[i]),
                    level_name=LEVEL_NAMES[int(self.item_level[i])], short=bool(self.item_short[i]),
                    group=self.group_names[self.topic_group[self.item_topic[i]]], prereqs=list(self.prereqs.get(i, [])),
                    sources=list(self.sources.get(i, [])), concepts=self.concepts(i),
                    minutes=8 if self.item_short[i] else 15,
                    lesson=_lesson(self.topics[self.item_topic[i]], int(self.item_level[i]), self.version))


def onehot(codes, k: int) -> np.ndarray:
    """범위 밖 코드(결측 등)는 모두 0인 행으로 둔다."""
    codes = np.asarray(codes, dtype=int)
    out = np.zeros((len(codes), k), np.float32)
    valid = (codes >= 0) & (codes < k)
    out[np.flatnonzero(valid), codes[valid]] = 1
    return out
