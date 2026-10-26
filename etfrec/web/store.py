"""학습자 저장소(SQLite): 계정·세션·프로필·학습 기록.

수집 최소화: 아이디, 비밀번호 해시(scrypt), 동의 시각·버전, 학습 목적·기간·위험성향·투자 경험·관심 주제·기기,
진단 결과, 학습 기록만 저장한다. 연령·성별·소득은 묻지도 저장하지도 않는다(운영 추천은 이 값을 쓰지 않는다).
ref는 가입 순서대로 한 번만 쓰는 가명 번호로, 학습 데이터 내보내기와 운영 루프 기록의 학습자 번호가 된다(탈퇴해도 재사용 안 함).
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from ..config import GOALS, HORIZONS

CONSENT_VERSION = "2026-10-26-v1"
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,30}$")
SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
SESSION_TTL = 14 * 24 * 3600
HOUR_BANDS = (10, 15, 22)                 # 0~23시 → 4개 시간대(출근·점심·저녁·심야), privacy.py의 가명처리와 같은 경계
EVENT_KINDS = {"complete": dict(complete=1), "save": dict(save=1), "quiz_fail": dict(complete=1, quiz=1),
               "quiz_pass": dict(complete=1, quiz=1, quiz_pass=1)}
PROFILE_FIELDS = ("goal", "horizon", "risk", "exp", "interests", "mobile")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, pw TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
  ref INTEGER UNIQUE NOT NULL, created_at TEXT NOT NULL, consent_version TEXT NOT NULL, consent_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at REAL NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS profiles(
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, data TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, item INTEGER NOT NULL, ts REAL NOT NULL,
  complete INTEGER NOT NULL DEFAULT 0, quiz INTEGER NOT NULL DEFAULT 0, quiz_pass INTEGER NOT NULL DEFAULT 0,
  save INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_user ON events(user_id, ts);
CREATE TABLE IF NOT EXISTS recs(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, ts REAL NOT NULL,
  request_id TEXT NOT NULL, items TEXT NOT NULL, shortfall INTEGER NOT NULL DEFAULT 0, explored_slot INTEGER, policy TEXT);
CREATE INDEX IF NOT EXISTS recs_user ON recs(user_id, ts);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, ts REAL NOT NULL,
  kind TEXT NOT NULL, item INTEGER, request_id TEXT, value TEXT);
CREATE INDEX IF NOT EXISTS feedback_user ON feedback(user_id, kind, ts);
"""
# 파일럿 계측: view = 단원 열람(추천 목록에서 열면 request_id), reason_rating = 추천 목록의 이유 이해도(1~5),
# diagnosis_review = 진단 면제 단원 가운데 '아직 모름'으로 되돌린 단원, exit_survey = 마무리 설문
FEEDBACK_KINDS = ("view", "reason_rating", "diagnosis_review", "exit_survey")
SURVEY_ITEMS = (("fit", "추천된 단원이 내 투자 목적에 맞았다"),            # 마무리 설문(1 전혀 아니다 ~ 5 매우 그렇다)
                ("order", "추천 순서(로드맵)가 무엇을 먼저 공부할지 정하는 데 도움이 되었다"),
                ("reason", "추천 이유 설명이 이해하기 쉬웠다"),
                ("diagnosis", "진단 결과(이미 아는 단원으로 처리된 것)가 실제 내 수준과 맞았다"),
                ("reuse", "앞으로도 이 서비스로 ETF를 공부하고 싶다"))
VIEW_DEDUP_SECONDS = 1800


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _ub64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${_b64(salt)}${_b64(h)}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        want = _ub64(h)
        got = hashlib.scrypt(pw.encode("utf-8"), salt=_ub64(salt), n=int(n), r=int(r), p=int(p), dklen=len(want))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


_DUMMY = hash_password(secrets.token_hex(8))      # 없는 아이디도 같은 시간만큼 계산해 존재 여부가 응답 시간으로 드러나지 않게


def validate_username(u: str) -> str:
    u = str(u or "").strip().lower()
    if not USERNAME_RE.match(u):
        raise ValueError("아이디는 영문 소문자·숫자·._- 3~30자입니다")
    return u


def validate_password(pw: str, username: str = "") -> str:
    if not isinstance(pw, str) or not 8 <= len(pw) <= 128:
        raise ValueError("비밀번호는 8자 이상 128자 이하입니다")
    if username and pw.lower() == username.lower():
        raise ValueError("아이디와 같은 비밀번호는 쓸 수 없습니다")
    return pw


def validate_profile(d: dict, n_topics: int) -> dict:
    out = {}
    if d.get("goal") not in GOALS:
        raise ValueError(f"투자 목적은 {list(GOALS)} 중 하나입니다")
    if d.get("horizon") not in HORIZONS:
        raise ValueError(f"투자 기간은 {list(HORIZONS)} 중 하나입니다")
    for k in ("risk", "exp"):
        v = d.get(k)
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 2:
            raise ValueError(f"{k}는 0~2 정수입니다")
        out[k] = v
    mob = d.get("mobile", 1)
    if isinstance(mob, bool) or mob not in (0, 1):
        raise ValueError("mobile은 0 또는 1입니다")
    tops = d.get("interests") or []
    if not isinstance(tops, list) or len(tops) > 2 or len(set(tops)) != len(tops) or \
            any(isinstance(t, bool) or not isinstance(t, int) or not 0 <= t < n_topics for t in tops):
        raise ValueError(f"관심 주제는 0~{n_topics - 1} 가운데 최대 2개입니다")
    out.update(goal=d["goal"], horizon=d["horizon"], mobile=int(mob), interests=[int(t) for t in tops])
    return out


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class WebStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._tx() as c:
            c.executescript(SCHEMA)

    @contextlib.contextmanager
    def _tx(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ---------- 메타 ----------
    def meta(self, key: str, default=None):
        with self._tx() as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, key: str, value: str):
        with self._tx() as c:
            c.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def service_start(self, configured: str = None) -> date:
        """주차 계산의 기준일(서비스 시작일). 한 번 정하면 meta에 남겨 재시작해도 주차가 바뀌지 않는다.
        기본값은 첫 실행 주의 월요일이라 주차가 월~일로 맞는다(주간 작업을 월요일 새벽에 돌리면 막 끝난 주를 판정)."""
        cur = self.meta("service_start")
        if cur is None:
            today = date.today()
            cur = configured or (today - timedelta(days=today.weekday())).isoformat()
            date.fromisoformat(cur)
            self.set_meta("service_start", cur)
        elif configured and configured != cur:
            raise ValueError(f"서비스 시작일이 이미 {cur}로 정해져 있습니다(주차 기준을 바꾸면 기록의 주차가 어긋납니다)")
        return date.fromisoformat(cur)

    # ---------- 계정 ----------
    def create_user(self, username: str, password: str, consent_version: str = CONSENT_VERSION, is_admin: bool = False) -> dict:
        u = validate_username(username)
        validate_password(password, u)
        pw = hash_password(password)
        with self._tx() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
                raise FileExistsError("이미 쓰고 있는 아이디입니다")
            r = c.execute("SELECT value FROM meta WHERE key='next_ref'").fetchone()
            ref = int(r["value"]) if r else 0
            c.execute("INSERT INTO meta(key, value) VALUES('next_ref', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(ref + 1),))
            now = _now_iso()
            cur = c.execute("INSERT INTO users(username, pw, is_admin, ref, created_at, consent_version, consent_at) VALUES(?,?,?,?,?,?,?)",
                            (u, pw, int(bool(is_admin)), ref, now, consent_version, now))
            uid = cur.lastrowid
        return self.user(uid)

    def user(self, uid: int) -> dict:
        with self._tx() as c:
            r = c.execute("SELECT id, username, is_admin, ref, created_at, consent_version, consent_at FROM users WHERE id=?", (uid,)).fetchone()
        return dict(r) if r else None

    def user_by_name(self, username: str):
        with self._tx() as c:
            r = c.execute("SELECT id FROM users WHERE username=?", (validate_username(username),)).fetchone()
        return self.user(r["id"]) if r else None

    def authenticate(self, username: str, password: str):
        try:
            u = validate_username(username)
        except ValueError:
            check_password(password or "", _DUMMY)
            return None
        with self._tx() as c:
            r = c.execute("SELECT id, pw FROM users WHERE username=?", (u,)).fetchone()
        if r is None:
            check_password(password or "", _DUMMY)
            return None
        return self.user(r["id"]) if check_password(password or "", r["pw"]) else None

    def set_password(self, username: str, password: str):
        u = validate_username(username)
        validate_password(password, u)
        with self._tx() as c:
            n = c.execute("UPDATE users SET pw=? WHERE username=?", (hash_password(password), u)).rowcount
            uid = c.execute("SELECT id FROM users WHERE username=?", (u,)).fetchone()
            if uid:
                c.execute("DELETE FROM sessions WHERE user_id=?", (uid["id"],))      # 비밀번호를 바꾸면 기존 세션은 모두 끊는다
        if not n:
            raise KeyError(f"없는 아이디입니다: {u}")

    def set_admin(self, username: str, flag: bool = True):
        with self._tx() as c:
            if not c.execute("UPDATE users SET is_admin=? WHERE username=?", (int(bool(flag)), validate_username(username))).rowcount:
                raise KeyError(f"없는 아이디입니다: {username}")

    def delete_user(self, uid: int) -> int:
        """탈퇴: 계정·세션·프로필·학습 기록을 모두 지운다(외래 키 CASCADE). 지운 사용자의 ref를 돌려준다."""
        with self._tx() as c:
            r = c.execute("SELECT ref FROM users WHERE id=?", (uid,)).fetchone()
            c.execute("DELETE FROM users WHERE id=?", (uid,))
        return None if r is None else int(r["ref"])

    # ---------- 세션 ----------
    def create_session(self, uid: int) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._tx() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            c.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES(?,?,?,?)",
                      (hashlib.sha256(token.encode()).hexdigest(), uid, now, now + SESSION_TTL))
        return token

    def session_user(self, token: str):
        if not token or len(token) > 200:
            return None
        th, now = hashlib.sha256(token.encode()).hexdigest(), time.time()
        with self._tx() as c:
            r = c.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash=?", (th,)).fetchone()
            if r is None:
                return None
            if r["expires_at"] < now:
                c.execute("DELETE FROM sessions WHERE token_hash=?", (th,))
                return None
            if r["expires_at"] - now < SESSION_TTL / 2:                     # 쓰는 동안은 연장(최대 14일 무활동이면 만료)
                c.execute("UPDATE sessions SET expires_at=? WHERE token_hash=?", (now + SESSION_TTL, th))
        return self.user(r["user_id"])

    def delete_session(self, token: str):
        if token:
            with self._tx() as c:
                c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    # ---------- 프로필·기록 ----------
    def profile(self, uid: int) -> dict:
        with self._tx() as c:
            r = c.execute("SELECT data FROM profiles WHERE user_id=?", (uid,)).fetchone()
        p = json.loads(r["data"]) if r else {}
        p.setdefault("placement", 1); p.setdefault("diagnosis", None)
        p["complete"] = all(p.get(k) is not None for k in ("goal", "horizon", "risk", "exp"))
        return p

    def save_profile(self, uid: int, data: dict):
        cur = {k: v for k, v in self.profile(uid).items() if k != "complete"}
        cur.update(data)
        with self._tx() as c:
            c.execute("INSERT INTO profiles(user_id, data, updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                      "data=excluded.data, updated_at=excluded.updated_at", (uid, json.dumps(cur, ensure_ascii=False), _now_iso()))

    def add_event(self, uid: int, item: int, kind: str, source: str, ts: float = None) -> dict:
        if kind not in EVENT_KINDS:
            raise ValueError(f"알 수 없는 기록 종류: {kind}")
        f = {**dict(complete=0, quiz=0, quiz_pass=0, save=0), **EVENT_KINDS[kind]}
        ts = time.time() if ts is None else float(ts)
        with self._tx() as c:
            c.execute("INSERT INTO events(user_id, item, ts, complete, quiz, quiz_pass, save, source) VALUES(?,?,?,?,?,?,?,?)",
                      (uid, int(item), ts, f["complete"], f["quiz"], f["quiz_pass"], f["save"], source))
        return dict(item=int(item), ts=ts, source=source, **f)

    def replace_diagnosis(self, uid: int, items, ts: float = None):
        ts = time.time() if ts is None else float(ts)
        with self._tx() as c:
            c.execute("DELETE FROM events WHERE user_id=? AND source='diagnosis'", (uid,))
            c.executemany("INSERT INTO events(user_id, item, ts, complete, quiz, quiz_pass, save, source) VALUES(?,?,?,1,1,1,0,'diagnosis')",
                          [(uid, int(i), ts) for i in items])

    def events(self, uid: int) -> list:
        with self._tx() as c:
            rows = c.execute("SELECT item, ts, complete, quiz, quiz_pass, save, source FROM events WHERE user_id=? ORDER BY ts, id", (uid,)).fetchall()
        return [dict(r) for r in rows]

    # ---------- 파일럿 계측 ----------
    def record_rec(self, uid: int, request_id: str, items, shortfall: int = 0, explored_slot=None, policy: str = None,
                   ts: float = None):
        """학습자에게 실제로 보인 추천 목록(순서 그대로)."""
        with self._tx() as c:
            c.execute("INSERT INTO recs(user_id, ts, request_id, items, shortfall, explored_slot, policy) VALUES(?,?,?,?,?,?,?)",
                      (uid, time.time() if ts is None else float(ts), request_id, json.dumps([int(i) for i in items]), int(shortfall),
                       None if explored_slot is None else int(explored_slot), policy))

    def rec(self, uid: int, request_id: str):
        with self._tx() as c:
            r = c.execute("SELECT ts, request_id, items FROM recs WHERE user_id=? AND request_id=?", (uid, request_id)).fetchone()
        return None if r is None else dict(ts=r["ts"], request_id=r["request_id"], items=json.loads(r["items"]))

    def add_feedback(self, uid: int, kind: str, item: int = None, request_id: str = None, value=None, ts: float = None):
        if kind not in FEEDBACK_KINDS:
            raise ValueError(f"알 수 없는 응답 종류: {kind}")
        with self._tx() as c:
            c.execute("INSERT INTO feedback(user_id, ts, kind, item, request_id, value) VALUES(?,?,?,?,?,?)",
                      (uid, time.time() if ts is None else float(ts), kind, None if item is None else int(item), request_id,
                       None if value is None else json.dumps(value, ensure_ascii=False)))

    def add_view(self, uid: int, item: int, request_id: str = None) -> bool:
        """단원 열람. 같은 경로(같은 추천 목록 또는 목록 밖)로 같은 단원을 30분 안에 다시 열면 한 번으로 센다(화면 새로 그리기 포함).
        기록했으면 True."""
        now = time.time()
        with self._tx() as c:
            r = c.execute("SELECT 1 FROM feedback WHERE user_id=? AND kind='view' AND item=? AND request_id IS ? AND ts > ?",
                          (uid, int(item), request_id, now - VIEW_DEDUP_SECONDS)).fetchone()
            if r is not None:
                return False
            c.execute("INSERT INTO feedback(user_id, ts, kind, item, request_id) VALUES(?,?,?,?,?)", (uid, now, "view", int(item), request_id))
        return True

    def feedback(self, uid: int, kind: str = None) -> list:
        q, args = "SELECT ts, kind, item, request_id, value FROM feedback WHERE user_id=?", [uid]
        if kind:
            q += " AND kind=?"; args.append(kind)
        with self._tx() as c:
            rows = c.execute(q + " ORDER BY ts, id", args).fetchall()
        return [dict(r, value=json.loads(r["value"]) if r["value"] is not None else None) for r in rows]

    def unexempt(self, uid: int, items) -> list:
        """진단으로 이수 인정한 단원 가운데 학습자가 '아직 모름'이라고 고른 단원의 인정을 거둔다(다시 추천 대상). 거둔 단원 목록."""
        items = sorted({int(i) for i in items})
        with self._tx() as c:
            have = {r["item"] for r in c.execute("SELECT item FROM events WHERE user_id=? AND source='diagnosis'", (uid,)).fetchall()}
            bad = [i for i in items if i not in have]
            if bad:
                raise ValueError(f"진단으로 인정한 단원이 아닙니다: {bad}")
            c.executemany("DELETE FROM events WHERE user_id=? AND source='diagnosis' AND item=?", [(uid, i) for i in items])
        return items

    def dump(self) -> dict:
        """파일럿 분석용 전체 자료(비밀번호 해시·세션 제외)."""
        with self._tx() as c:
            q = lambda s: [dict(r) for r in c.execute(s).fetchall()]
            out = dict(users=q("SELECT u.id, u.ref, u.is_admin, u.created_at, p.data AS profile FROM users u "
                               "LEFT JOIN profiles p ON p.user_id=u.id ORDER BY u.id"),
                       events=q("SELECT user_id, item, ts, complete, quiz, quiz_pass, save, source FROM events ORDER BY ts, id"),
                       recs=q("SELECT user_id, ts, request_id, items, shortfall, explored_slot, policy FROM recs ORDER BY ts, id"),
                       feedback=q("SELECT user_id, ts, kind, item, request_id, value FROM feedback ORDER BY ts, id"),
                       meta=q("SELECT key, value FROM meta"))
        for u in out["users"]:
            u["profile"] = json.loads(u["profile"]) if u["profile"] else {}
        for r in out["recs"]:
            r["items"] = json.loads(r["items"])
        for f in out["feedback"]:
            f["value"] = json.loads(f["value"]) if f["value"] is not None else None
        return out

    def learner_fields(self, uid: int, before: float = None) -> dict:
        """서비스의 LearnerInput 인자. 연령·성별·소득은 수집하지 않으므로 기본값(운영 순위에 쓰이지 않음)으로 둔다.
        before(시각)를 주면 그 전의 기록만 쓴다(파일럿 분석에서 추천 당시 상태를 다시 만들 때)."""
        p = self.profile(uid)
        ev = [dict(item=e["item"], week=0, complete=bool(e["complete"]), quiz=bool(e["quiz"]), quiz_pass=bool(e["quiz_pass"]),
                   save=bool(e["save"]), **({"source": "diagnosis"} if e["source"] == "diagnosis" else {}))
              for e in self.events(uid) if before is None or e["ts"] < before]
        return dict(label="나", exp=int(p.get("exp") or 0), risk=int(p.get("risk") if p.get("risk") is not None else 1),
                    mobile=int(p.get("mobile", 1)), interests=list(p.get("interests") or []), placement=int(p.get("placement", 1)),
                    goal=p.get("goal") or "long_term", horizon=p.get("horizon") or "mid", diagnosis=p.get("diagnosis"), events=ev)

    def export_user(self, uid: int) -> dict:
        u = self.user(uid)
        return dict(account={k: u[k] for k in ("username", "created_at", "consent_version", "consent_at")},
                    profile={k: v for k, v in self.profile(uid).items() if k != "complete"},
                    events=[dict(e, time=datetime.fromtimestamp(e["ts"]).isoformat(timespec="seconds")) for e in self.events(uid)],
                    recommendations=[dict(r, time=datetime.fromtimestamp(r["ts"]).isoformat(timespec="seconds")) for r in self._recs(uid)],
                    responses=[dict(f, time=datetime.fromtimestamp(f["ts"]).isoformat(timespec="seconds")) for f in self.feedback(uid)],
                    exported_at=_now_iso())

    def _recs(self, uid: int) -> list:
        with self._tx() as c:
            rows = c.execute("SELECT ts, request_id, items, shortfall FROM recs WHERE user_id=? ORDER BY ts, id", (uid,)).fetchall()
        return [dict(r, items=json.loads(r["items"])) for r in rows]

    def backup(self, out_path: str):
        """실행 중에도 일관된 사본을 만든다(SQLite 온라인 백업). 이미 있는 파일은 덮어쓰지 않는다."""
        if os.path.exists(out_path):
            raise FileExistsError(f"이미 있는 파일입니다: {out_path}")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        src, dst = sqlite3.connect(self.path), sqlite3.connect(out_path)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()

    def stats(self) -> dict:
        with self._tx() as c:
            q = lambda s: c.execute(s).fetchone()[0]
            return dict(users=q("SELECT COUNT(*) FROM users"), admins=q("SELECT COUNT(*) FROM users WHERE is_admin=1"),
                        profiles=q("SELECT COUNT(*) FROM profiles"), events=q("SELECT COUNT(*) FROM events"),
                        recommendation_lists=q("SELECT COUNT(*) FROM recs"), responses=q("SELECT COUNT(*) FROM feedback WHERE kind != 'view'"),
                        unit_views=q("SELECT COUNT(*) FROM feedback WHERE kind = 'view'"),
                        active_sessions=c.execute("SELECT COUNT(*) FROM sessions WHERE expires_at > ?", (time.time(),)).fetchone()[0],
                        last_event=c.execute("SELECT MAX(ts) FROM events").fetchone()[0])

    # ---------- 학습 데이터 내보내기 ----------
    def export_dataset(self, start: date) -> tuple:
        """학습 파이프라인 형식(profiles, study_log). user = ref(0..최대 ref, 탈퇴자는 기록 없는 기본 행으로 번호 유지).
        week = 서비스 시작일부터의 주차, hour = 4개 시간대(privacy.py와 같은 경계), day·minute = 0(시각은 남기지 않고 순서만 유지).
        source = 기록 출처(web·quiz·self·diagnosis). diagnosis는 진단 퀴즈의 이수 인정이라 특징에는 통과로만 쓰고 정답에서는 뺀다.
        연령·성별·소득은 수집하지 않아 고정 자리값이다(운영 정책은 이 값을 쓰지 않는다)."""
        with self._tx() as c:
            users = [dict(r) for r in c.execute("SELECT u.id, u.ref, p.data FROM users u LEFT JOIN profiles p ON p.user_id=u.id").fetchall()]
            evs = [dict(r) for r in c.execute("SELECT user_id, item, ts, complete, quiz, quiz_pass, save, source FROM events "
                                              "ORDER BY ts, id").fetchall()]
            r = c.execute("SELECT value FROM meta WHERE key='next_ref'").fetchone()
        n_ref = int(r["value"]) if r else 0
        ref_of = {u["id"]: u["ref"] for u in users}
        prof = {u["ref"]: json.loads(u["data"]) if u["data"] else {} for u in users}
        rows = []
        for ref in range(n_ref):
            p = prof.get(ref, {})
            t = (list(p.get("interests") or []) + [-1, -1])[:2]
            rows.append(dict(user=ref, gender=0, age=35, income=4000.0, exp=int(p.get("exp") or 0),
                             risk=int(p["risk"]) if p.get("risk") is not None else 1, mobile=int(p.get("mobile", 1)),
                             interest1=t[0], interest2=t[1],                     # 고르지 않은 칸은 −1(관심 없음, 학습 코드가 지원)
                             placement=int(p.get("placement", 1)), goal=p.get("goal") or "long_term", horizon=p.get("horizon") or "mid"))
        profiles = pd.DataFrame(rows, columns=["user", "gender", "age", "income", "exp", "risk", "mobile", "interest1", "interest2",
                                               "placement", "goal", "horizon"])
        log = []
        for e in evs:
            dt = datetime.fromtimestamp(e["ts"])
            days = (dt.date() - start).days
            if days < 0:
                continue
            log.append(dict(user=ref_of[e["user_id"]], item=int(e["item"]), week=days // 7, day=0, hour=int(np.digitize(dt.hour, HOUR_BANDS)),
                            complete=bool(e["complete"]), quiz=bool(e["quiz"]), quiz_pass=bool(e["quiz_pass"]), save=bool(e["save"]),
                            drop=False, replay=False, minute=0, source=e["source"]))
        cols = ["user", "item", "week", "day", "hour", "complete", "quiz", "quiz_pass", "save", "drop", "replay", "minute", "source"]
        return profiles, pd.DataFrame(log, columns=cols)
