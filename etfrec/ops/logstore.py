"""노출(impression)·반응(feedback) 기록: 주차별 JSONL, 추가만 한다.

기록에는 학습자 원본 ID·인구통계·자유 문장을 넣지 않는다. user_ref는 학습 데이터의 가명 번호(기존 학습자)이거나
None(이력만 보낸 임의 학습자, OPE에서 다시 계산할 수 없으므로 집계에서 빠진다)이다.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

EVENTS = ("view", "complete", "quiz_pass", "save")
_REQ_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _int(v, name, minimum=0):
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise ValueError(f"{name}은 {minimum} 이상의 정수여야 합니다")
    return v


def _user_ref(v):
    return None if v is None else _int(v, "user_ref")


def validate_impression(r: dict) -> dict:
    if not isinstance(r.get("request_id"), str) or not _REQ_RE.match(r["request_id"]):
        raise ValueError("request_id 형식이 잘못되었습니다")
    _int(r.get("week"), "week"); _user_ref(r.get("user_ref")); _int(r.get("k"), "k", 1)
    items, prop = r.get("items"), r.get("propensity")
    if not isinstance(items, list) or not isinstance(prop, list) or len(items) != len(prop) or len(items) > r["k"]:
        raise ValueError("items와 propensity는 길이가 같은 목록이어야 합니다(최대 k개)")
    for i, p in zip(items, prop):
        _int(i, "item")
        if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 < float(p) <= 1:
            raise ValueError("propensity는 0 초과 1 이하여야 합니다")
    if len(set(items)) != len(items):
        raise ValueError("같은 단원이 한 요청에 두 번 보일 수 없습니다")
    pol = r.get("policy")
    if not isinstance(pol, dict) or not pol.get("key") or not pol.get("hash"):
        raise ValueError("policy(key·hash)가 필요합니다")
    if len(r.get("pool", [])) != len(r.get("pool_prob", [])):
        raise ValueError("pool과 pool_prob의 길이가 다릅니다")
    return r


def validate_feedback(r: dict) -> dict:
    _int(r.get("week"), "week"); _user_ref(r.get("user_ref")); _int(r.get("item"), "item")
    if r.get("event") not in EVENTS:
        raise ValueError(f"event는 {EVENTS} 중 하나여야 합니다")
    rid = r.get("request_id")
    if rid is not None and (not isinstance(rid, str) or not _REQ_RE.match(rid)):
        raise ValueError("request_id 형식이 잘못되었습니다")
    return r


class OpsLog:
    """root/impressions/week=0003.jsonl, root/feedback/week=0003.jsonl"""

    def __init__(self, root: str):
        self.root = root

    def _path(self, kind: str, week: int) -> str:
        return os.path.join(self.root, kind, f"week={int(week):04d}.jsonl")

    def _append(self, kind: str, records, validate):
        records = [validate(dict(r)) for r in records]
        by_week = {}
        for r in records:
            r.setdefault("ts", _now())
            by_week.setdefault(int(r["week"]), []).append(r)
        with _LOCK:
            for week, rows in by_week.items():
                path = self._path(kind, week)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
        return len(records)

    def append_impressions(self, records) -> int:
        return self._append("impressions", records, validate_impression)

    def append_feedback(self, records) -> int:
        return self._append("feedback", records, validate_feedback)

    def _read(self, kind: str, week: int) -> list:
        path = self._path(kind, week)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def impressions(self, week: int) -> list:
        return self._read("impressions", week)

    def feedback(self, week: int) -> list:
        return self._read("feedback", week)

    def weeks(self, kind: str = "impressions") -> list:
        d = os.path.join(self.root, kind)
        if not os.path.isdir(d):
            return []
        return sorted(int(m.group(1)) for n in os.listdir(d) if (m := re.match(r"^week=(\d{4})\.jsonl$", n)))

    def counts(self, week: int) -> dict:
        imps = self.impressions(week)
        return dict(week=int(week), impressions=len(imps), explored=int(sum(bool(r.get("explored")) for r in imps)),
                    feedback=len(self.feedback(week)))

    def purge_user(self, user_ref: int) -> int:
        """탈퇴한 학습자의 노출·반응 기록을 모든 주차 파일에서 지운다(새로 써서 바꿔치기). 지운 줄 수를 돌려준다."""
        ref, removed = int(user_ref), 0
        with _LOCK:
            for kind in ("impressions", "feedback"):
                for w in self.weeks(kind):
                    path = self._path(kind, w)
                    with open(path, encoding="utf-8") as f:
                        lines = [ln for ln in f if ln.strip()]
                    keep = [ln for ln in lines if json.loads(ln).get("user_ref") != ref]
                    if len(keep) != len(lines):
                        tmp = path + ".tmp"
                        with open(tmp, "w", encoding="utf-8") as f:
                            f.writelines(keep)
                        os.replace(tmp, path)
                        removed += len(lines) - len(keep)
        return removed

    def prune(self, keep_weeks: int) -> list:
        """최근 keep_weeks주만 남기고 오래된 주차 파일을 지운다(보존 기간). 지운 파일 목록을 돌려준다."""
        if isinstance(keep_weeks, bool) or int(keep_weeks) < 1:
            raise ValueError("keep_weeks는 1 이상이어야 합니다")
        weeks = sorted(set(self.weeks("impressions")) | set(self.weeks("feedback")))
        if not weeks:
            return []
        cutoff = weeks[-1] - int(keep_weeks) + 1
        removed = []
        for kind in ("impressions", "feedback"):
            for w in self.weeks(kind):
                if w < cutoff:
                    os.remove(self._path(kind, w)); removed.append(f"{kind}/week={w:04d}.jsonl")
        return removed
