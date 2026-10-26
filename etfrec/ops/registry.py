"""정책 등록부: 현재 운영 정책·이전 정책·동결 상태(registry.json)와 교체 이력(history.jsonl).

이력은 추가만 하며 각 줄이 앞 줄의 해시(prev_hash)를 품는 해시 사슬이라 중간 수정·삭제를 verify()로 찾을 수 있다.
registry.json은 임시 파일에 쓴 뒤 바꿔치기(os.replace)해 쓰는 도중 끊겨도 반쯤 쓴 파일이 남지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from .policies import public_spec

GENESIS = "0" * 64


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _hash(rec: dict) -> str:
    body = json.dumps({k: v for k, v in rec.items() if k != "hash"}, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class PolicyRegistry:
    def __init__(self, root: str):
        self.root = root
        self.path = os.path.join(root, "registry.json")
        self.history_path = os.path.join(root, "history.jsonl")
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"운영 등록부가 없습니다: {self.path} (python -m etfrec ops init으로 만드세요)")
        self.state = self._load()

    # ---------- 생성·저장 ----------
    @classmethod
    def init(cls, root: str, champion: dict, settings: dict, base_bundle: str = None, note: str = "", force: bool = False):
        path = os.path.join(root, "registry.json")
        if os.path.exists(path) and not force:
            raise FileExistsError(f"이미 등록부가 있습니다: {path} (--force로 덮어쓰면 이력은 보존되지 않습니다)")
        os.makedirs(root, exist_ok=True)
        if force:
            for p in (path, os.path.join(root, "history.jsonl")):
                if os.path.exists(p):
                    os.replace(p, p + f".bak-{time.strftime('%Y%m%d%H%M%S')}")
        state = dict(schema=1, created_at=_now(), champion=dict(champion, adopted_week=None, adopted_at=_now()), previous=[],
                     frozen=False, freeze_reason=None, last_change_week=None, settings=settings, base_bundle=base_bundle,
                     serving_bundle=None)
        cls._write(path, state)
        reg = cls(root)
        reg.append_history(dict(event="init", week=None, champion_after=public_spec(champion), settings=settings, note=note))
        return reg

    @staticmethod
    def _write(path: str, state: dict):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _load(self) -> dict:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def save(self):
        self._write(self.path, self.state)

    def mtime(self) -> float:
        return os.path.getmtime(self.path)

    # ---------- 상태 ----------
    @property
    def champion(self) -> dict:
        return self.state["champion"]

    @property
    def frozen(self) -> bool:
        return bool(self.state.get("frozen"))

    @property
    def settings(self) -> dict:
        return self.state.get("settings", {})

    def weeks_since_change(self, week: int):
        last = self.state.get("last_change_week")
        return None if last is None else int(week) - int(last)

    def promote(self, spec: dict, week: int, reason: str, record: dict = None) -> dict:
        old = self.champion
        self.state["previous"].append(old)
        self.state["champion"] = dict(spec, adopted_week=int(week), adopted_at=_now())
        self.state["last_change_week"] = int(week)
        self.save()
        return self.append_history(dict(record or {}, event="promoted", week=int(week), champion_before=public_spec(old),
                                        champion_after=public_spec(spec), reason=reason))

    def rollback(self, week, reason: str, record: dict = None, manual: bool = False) -> dict:
        if not self.state["previous"]:
            raise ValueError("되돌릴 이전 정책이 없습니다")
        cur = self.champion
        prev = self.state["previous"].pop()
        self.state["champion"] = dict(prev, adopted_week=week, adopted_at=_now(), restored_from=cur.get("version"))
        if week is not None:                                       # 수동 되돌림(week 없음)은 냉각 기간 기준 주를 바꾸지 않는다
            self.state["last_change_week"] = int(week)
        self.save()
        return self.append_history(dict(record or {}, event="manual_rollback" if manual else "rolled_back", week=week,
                                        champion_before=public_spec(cur), champion_after=public_spec(prev), reason=reason))

    def set_frozen(self, frozen: bool, reason: str) -> dict:
        self.state["frozen"] = bool(frozen); self.state["freeze_reason"] = reason if frozen else None
        self.save()
        return self.append_history(dict(event="frozen" if frozen else "unfrozen", week=None, reason=reason,
                                        champion_after=public_spec(self.champion)))

    def set_serving_bundle(self, path: str, week: int):
        self.state["serving_bundle"] = path; self.state["serving_week"] = int(week)
        self.save()

    # ---------- 이력 ----------
    def history(self) -> list:
        if not os.path.exists(self.history_path):
            return []
        with open(self.history_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def append_history(self, rec: dict) -> dict:
        hist = self.history()
        rec = dict(rec, seq=len(hist), ts=_now(), prev_hash=hist[-1]["hash"] if hist else GENESIS)
        rec["hash"] = _hash(rec)
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
        return rec

    def verify(self) -> dict:
        """해시 사슬 검사: 각 줄의 hash가 내용과 맞고 prev_hash가 앞 줄 hash와 같아야 한다."""
        prev = GENESIS
        for i, rec in enumerate(self.history()):
            if rec.get("seq") != i or rec.get("prev_hash") != prev or rec.get("hash") != _hash(rec):
                return dict(ok=False, first_bad_seq=i, records=i)
            prev = rec["hash"]
        return dict(ok=True, first_bad_seq=None, records=len(self.history()))

    def decided_weeks(self) -> set:
        return {r["week"] for r in self.history() if r.get("event") in ("promoted", "kept", "rolled_back", "skipped", "no_challenger")
                and r.get("week") is not None}
