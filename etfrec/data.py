"""학습자 프로필·학습 로그 데이터셋과 CSV 입출력.

CSV 스키마(운영 로그를 연결할 때 그대로 맞추면 된다)
    profiles.csv  user, gender(0/1), age, income(만원), exp(0~2), risk(0~2), mobile(0/1),
                  interest1, interest2(주제 이름 또는 번호), placement(1~3)
    study_log.csv user, item, week, day, hour, minute, complete, quiz, quiz_pass, save, drop, replay
                  (score·understood 열이 없으면 행동 점수 규칙으로 만든다)
    catalog.csv   item, title, topic, level, short
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .catalog import Catalog
from .config import TrainConfig
from .synth import BOOL_COLUMNS, LOG_COLUMNS, make_world

PROFILE_COLUMNS = ["user", "gender", "age", "income", "exp", "risk", "mobile", "interest1", "interest2", "placement"]


def score_attempts(log: pd.DataFrame) -> pd.DataFrame:
    """[교안 1-3] 행동 점수: 조회 1, 완료 2, 퀴즈 통과·저장 3의 최댓값. 이해 여부는 퀴즈 통과의 대리 라벨."""
    log = log.copy()
    for c in BOOL_COLUMNS:
        log[c] = log[c].astype(bool)
    log["score"] = np.maximum.reduce([np.ones(len(log)), 2 * log.complete.values, 3 * log.quiz_pass.values, 3 * log.save.values])
    log["understood"] = log.quiz_pass
    return log


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
            raise ValueError("profiles.user는 0부터 연속된 번호여야 합니다(외부 ID는 user_id 열로 따로 두세요)")
        if "score" not in self.log.columns or "understood" not in self.log.columns:
            self.log = score_attempts(self.log)
        bad_item = (self.log.item < 0) | (self.log.item >= self.catalog.n_items)
        if bad_item.any():
            raise ValueError(f"카탈로그 범위를 벗어난 item이 {int(bad_item.sum())}건 있습니다")
        bad_user = (self.log.user < 0) | (self.log.user >= self.n_users)
        if bad_user.any():
            raise ValueError(f"profiles에 없는 user가 {int(bad_user.sum())}건 있습니다")
        for c in ("interest1", "interest2"):
            self.profiles[c] = resolve_topics(self.profiles[c].values, self.catalog)
        self.profiles["placement"] = self.profiles.placement.clip(1, 3).astype(int)

    @classmethod
    def synthetic(cls, cfg: TrainConfig = None, catalog: Catalog = None) -> "Dataset":
        cfg = cfg or TrainConfig()
        catalog = catalog or Catalog.default(cfg.seed)
        world = make_world(cfg.n_learners, catalog, seed=cfg.seed, effect=cfg.effect_scale, gender_effect=cfg.gender_effect)
        meta = dict(seed=cfg.seed, effect_scale=cfg.effect_scale, gender_effect=cfg.gender_effect,
                    gender_effect_by_topic=dict(zip(catalog.topics, np.round(world["g_eff"], 3).tolist())))
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
        self.catalog.to_frame()[["item", "title", "topic", "level", "short"]].to_csv(
            os.path.join(directory, "catalog.csv"), index=False, encoding="utf-8-sig")
        with open(os.path.join(directory, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(dict(source=self.source, meta=self.meta, n_users=self.n_users, rows=len(self.log)), f,
                      ensure_ascii=False, indent=2)

    def summary(self) -> dict:
        lg = self.log
        return dict(users=int(self.n_users), items=int(self.catalog.n_items), weeks=int(lg.week.max() + 1),
                    study_attempts=int(len(lg)), complete=int(lg.complete.sum()), quiz_pass=int(lg.quiz_pass.sum()),
                    save=int(lg.save.sum()), drop=int(lg["drop"].sum()),
                    attempts_by_week={int(k): int(v) for k, v in lg.groupby("week").size().items()},
                    mastery_label_equals_quiz=bool(np.array_equal(lg.understood, lg.quiz_pass)),
                    distinct_pairs=int(lg.groupby(["user", "item"]).ngroups),
                    density=float(lg.groupby(["user", "item"]).ngroups / (self.n_users * self.catalog.n_items)),
                    source=self.source)
