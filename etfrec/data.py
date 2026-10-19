"""학습자 프로필·학습 로그 데이터셋과 CSV 입출력.

CSV 스키마(운영 로그를 연결할 때 그대로 맞추면 된다)
    profiles.csv  user, gender(0/1), age, income(만원), exp(0~2), risk(0~2), mobile(0/1),
                  interest1, interest2(주제 이름 또는 번호), placement(1~3)
    study_log.csv user, item, week, day, hour, minute, complete, quiz, quiz_pass, save, drop, replay
                  (한 행 = 한 번의 학습 시도, 불리언 열은 그 시도의 다중 플래그. 퀴즈 통과 ⇒ 퀴즈 ⇒ 완료, 이탈 ⇒ 미완료로
                   정규화하고 고친 행 수와 플래그별 수정 건수를 summary.event_repairs 에 남긴다. score·understood 열이 없으면
                   행동 점수 규칙으로 만들고, 열이 있으면 그대로 쓰되 플래그를 고친 행만 규칙으로 다시 채점한다)
    catalog.csv   item, title, topic, level, short
    두 CSV에서 위 스키마(와 profiles의 goal·horizon, study_log의 score·understood) 밖의 열은 읽을 때 버리고 이름을 summary.dropped_columns에
    남긴다(외부 회원 ID·분 단위 시각·IP 같은 열이 학습·번들로 들어가지 않게. 외부 ID는 `pseudonymize`로 먼저 바꾼다).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .catalog import Catalog
from .config import GOAL_KEYS, HORIZON_KEYS, TrainConfig
from .synth import BOOL_COLUMNS, LOG_COLUMNS, make_world

PROFILE_COLUMNS = ["user", "gender", "age", "income", "exp", "risk", "mobile", "interest1", "interest2", "placement"]
OPTIONAL_PROFILE_COLUMNS = {"goal": "long_term", "horizon": "mid"}   # 없으면 기본값으로 채운다(구버전 CSV 호환)


def score_attempts(log: pd.DataFrame) -> pd.DataFrame:
    """[교안 1-3] 행동 점수: 조회 1, 완료 2, 퀴즈 통과·저장 3의 최댓값. 이해 여부는 퀴즈 통과의 대리 라벨."""
    log = log.copy()
    for c in BOOL_COLUMNS:
        log[c] = log[c].astype(bool)
    log["score"] = np.maximum.reduce([np.ones(len(log)), 2 * log.complete.values, 3 * log.quiz_pass.values, 3 * log.save.values])
    log["understood"] = log.quiz_pass
    return log


def normalize_event_flags(log: pd.DataFrame, return_mask: bool = False) -> tuple:
    """한 시도(행)의 플래그 논리를 맞춘다: 퀴즈 통과 ⇒ 퀴즈 시도 ⇒ 완료, 이탈 ⇒ 미완료(완료 증거가 있으면 이탈을 끈다).
    모의 생성기는 구성상 이미 만족하므로 바뀌는 행이 없고, 운영 로그를 연결할 때 고친 내용을 보고한다(학습 QA가 최종 확인).
    rows_changed = 플래그가 하나라도 바뀐 행 수(행 단위), flag_fixes = 플래그 수정 건수의 합(한 행이 최대 3건).
    return_mask=True면 바뀐 행의 불리언 배열도 돌려준다(그 행만 다시 채점할 때 쓴다)."""
    log = log.copy()
    for c in BOOL_COLUMNS:
        log[c] = log[c].astype(bool)
    before = log[["quiz", "complete", "drop"]].values.copy()
    rep = dict(quiz_from_pass=int((log.quiz_pass & ~log.quiz).sum()))
    log["quiz"] = log.quiz | log.quiz_pass
    rep["complete_from_quiz"] = int((log.quiz & ~log.complete).sum())
    log["complete"] = log.complete | log.quiz
    rep["drop_cleared_by_complete"] = int((log["drop"] & log.complete).sum())
    log["drop"] = log["drop"] & ~log.complete
    changed = (log[["quiz", "complete", "drop"]].values != before).any(1)
    rep["flag_fixes"] = int(rep["quiz_from_pass"] + rep["complete_from_quiz"] + rep["drop_cleared_by_complete"])
    rep["rows_changed"] = int(changed.sum())
    return (log, rep, changed) if return_mask else (log, rep)


def resolve_topics(values, catalog: Catalog) -> np.ndarray:
    """주제 이름이나 번호를 주제 번호로 바꾼다. 알 수 없는 값은 -1."""
    out = np.full(len(values), -1, dtype=int)
    for k, v in enumerate(values):
        if pd.isna(v):
            continue
        if isinstance(v, (int, np.integer)) or (isinstance(v, str) and v.strip().lstrip("-").isdigit()):
            iv = int(v)
            out[k] = iv if 0 <= iv < catalog.n_topics else -1
        else:
            out[k] = catalog.ti.get(str(v).strip(), -1)
    return out


@dataclass
class Dataset:
    profiles: pd.DataFrame
    log: pd.DataFrame
    catalog: Catalog
    source: str = "synthetic"
    meta: dict = None

    def __post_init__(self):
        self.n_users = len(self.profiles)
        self.validate()

    def validate(self):
        missing = [c for c in PROFILE_COLUMNS if c not in self.profiles.columns]
        if missing:
            raise ValueError(f"profiles에 {missing} 열이 없습니다")
        missing = [c for c in LOG_COLUMNS if c not in self.log.columns]
        if missing:
            raise ValueError(f"study_log에 {missing} 열이 없습니다")
        if not np.array_equal(self.profiles.user.values, np.arange(self.n_users)):
            raise ValueError("profiles.user는 0부터 연속된 번호여야 합니다(외부 회원 ID가 있으면 `python -m etfrec pseudonymize`로 "
                             "가명 번호로 바꾼 뒤 학습하세요)")
        # 학습 스키마 밖 열(외부 회원 ID·분 단위 시각·IP 등)은 학습에도 저장에도 쓰지 않으므로 여기서 버리고 이름만 남긴다
        keep_p = set(PROFILE_COLUMNS) | set(OPTIONAL_PROFILE_COLUMNS)
        keep_l = set(LOG_COLUMNS) | {"score", "understood"}
        self.dropped_columns = dict(profiles=[c for c in self.profiles.columns if c not in keep_p],
                                    log=[c for c in self.log.columns if c not in keep_l])
        if self.dropped_columns["profiles"]:
            self.profiles = self.profiles[[c for c in self.profiles.columns if c in keep_p]].copy()
        if self.dropped_columns["log"]:
            self.log = self.log[[c for c in self.log.columns if c in keep_l]].copy()
        self.log, self.event_repairs, changed = normalize_event_flags(self.log, return_mask=True)
        if "score" not in self.log.columns or "understood" not in self.log.columns:
            self.log = score_attempts(self.log)                       # 점수 열이 없으면 모든 행을 규칙으로 채점
        elif changed.any():                                           # 플래그를 고친 행만 다시 채점(입력 점수는 나머지 행에서 유지)
            fixed = score_attempts(self.log.loc[changed])
            self.log["score"] = self.log["score"].astype(float)
            self.log.loc[changed, "score"] = fixed["score"].values
            self.log.loc[changed, "understood"] = fixed["understood"].values
        bad_item = (self.log.item < 0) | (self.log.item >= self.catalog.n_items)
        if bad_item.any():
            raise ValueError(f"카탈로그 범위를 벗어난 item이 {int(bad_item.sum())}건 있습니다")
        bad_user = (self.log.user < 0) | (self.log.user >= self.n_users)
        if bad_user.any():
            raise ValueError(f"profiles에 없는 user가 {int(bad_user.sum())}건 있습니다")
        for c in ("interest1", "interest2"):
            self.profiles[c] = resolve_topics(self.profiles[c].values, self.catalog)
        self.profiles["placement"] = self.profiles.placement.clip(1, 3).astype(int)
        for c, default in OPTIONAL_PROFILE_COLUMNS.items():
            if c not in self.profiles.columns:
                self.profiles[c] = default
            self.profiles[c] = self.profiles[c].fillna(default).astype(str)
        bad_goal = ~self.profiles.goal.isin(GOAL_KEYS)
        if bad_goal.any():
            raise ValueError(f"goal 값은 {GOAL_KEYS} 중 하나여야 합니다: {sorted(self.profiles.goal[bad_goal].unique())[:5]}")
        bad_h = ~self.profiles.horizon.isin(HORIZON_KEYS)
        if bad_h.any():
            raise ValueError(f"horizon 값은 {HORIZON_KEYS} 중 하나여야 합니다")

    @classmethod
    def synthetic(cls, cfg: TrainConfig = None, catalog: Catalog = None) -> "Dataset":
        cfg = cfg or TrainConfig()
        catalog = catalog or Catalog.default(cfg.seed, version=cfg.catalog_version)
        world = make_world(cfg.n_learners, catalog, seed=cfg.seed, effect=cfg.effect_scale, gender_effect=cfg.gender_effect,
                           version=cfg.generator_version, goal_effect=cfg.goal_effect, prereq_penalty=cfg.prereq_penalty)
        meta = dict(seed=cfg.seed, effect_scale=cfg.effect_scale, gender_effect=cfg.gender_effect, generator_version=cfg.generator_version,
                    catalog_version=catalog.version, gender_effect_by_topic=dict(zip(catalog.topics, np.round(world["g_eff"], 3).tolist())))
        return cls(world["profiles"], world["log"], catalog, source="synthetic", meta=meta)

    @classmethod
    def from_csv(cls, directory: str, catalog: Catalog = None) -> "Dataset":
        cat_path = os.path.join(directory, "catalog.csv")
        catalog = catalog or (Catalog.from_csv(cat_path) if os.path.exists(cat_path) else Catalog.default())
        profiles = pd.read_csv(os.path.join(directory, "profiles.csv"))
        log = pd.read_csv(os.path.join(directory, "study_log.csv"))
        return cls(profiles, log, catalog, source=directory)

    def save_csv(self, directory: str):
        os.makedirs(directory, exist_ok=True)
        self.profiles.to_csv(os.path.join(directory, "profiles.csv"), index=False, encoding="utf-8-sig")
        self.log.to_csv(os.path.join(directory, "study_log.csv"), index=False, encoding="utf-8-sig")
        self.catalog.to_frame()[["item", "title", "topic", "level", "short", "prereqs", "sources"]].to_csv(
            os.path.join(directory, "catalog.csv"), index=False, encoding="utf-8-sig")
        with open(os.path.join(directory, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(dict(source=self.source, meta=self.meta, n_users=self.n_users, rows=len(self.log)), f,
                      ensure_ascii=False, indent=2)

    def summary(self) -> dict:
        lg = self.log
        return dict(users=int(self.n_users), items=int(self.catalog.n_items), weeks=int(lg.week.max() + 1),
                    study_attempts=int(len(lg)), complete=int(lg.complete.sum()), quiz_attempted=int(lg.quiz.sum()), quiz_pass=int(lg.quiz_pass.sum()),
                    save=int(lg.save.sum()), drop=int(lg["drop"].sum()), replay=int(lg.replay.sum()),
                    not_complete=int((~lg.complete.astype(bool)).sum()),
                    # 이벤트 열은 한 시도의 다중 플래그라 합이 시도 수를 넘는다. 논리 제약은 아래 세 값이 0이어야 한다.
                    drop_and_complete=int((lg["drop"].astype(bool) & lg.complete.astype(bool)).sum()),
                    pass_without_quiz=int((lg.quiz_pass.astype(bool) & ~lg.quiz.astype(bool)).sum()),
                    quiz_without_complete=int((lg.quiz.astype(bool) & ~lg.complete.astype(bool)).sum()),
                    event_repairs=getattr(self, "event_repairs", None), dropped_columns=getattr(self, "dropped_columns", None),
                    attempts_by_week={int(k): int(v) for k, v in lg.groupby("week").size().items()},
                    mastery_label_equals_quiz=bool(np.array_equal(lg.understood, lg.quiz_pass)),
                    distinct_pairs=int(lg.groupby(["user", "item"]).ngroups),
                    density=float(lg.groupby(["user", "item"]).ngroups / (self.n_users * self.catalog.n_items)),
                    goals={k: int(v) for k, v in self.profiles.goal.value_counts().items()},
                    horizons={k: int(v) for k, v in self.profiles.horizon.value_counts().items()},
                    catalog_version=int(self.catalog.version), source=self.source)
