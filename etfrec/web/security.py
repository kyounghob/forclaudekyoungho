"""웹 공개 운영의 보안 장치: 요청 속도 제한, 보안 헤더, 관리자 경로 차단, 클라이언트 IP."""
from __future__ import annotations

import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse

COOKIE = "etfrec_session"
CSRF_HEADER = "x-requested-with"          # 같은 출처 화면만 붙이는 머리글(다른 사이트의 폼 제출은 붙일 수 없다)
CSRF_VALUE = "etfrec"
# 공개 모드에서 관리자만 쓰는 API(스튜디오·운영·평가). 학습자 화면은 /api/me·/api/auth·/api/public만 쓴다.
ADMIN_PREFIXES = ("/api/meta", "/api/learners", "/api/recommend", "/api/compare", "/api/roadmap", "/api/types", "/api/parse",
                  "/api/examples", "/api/quiz/score", "/api/evaluation", "/api/designs", "/api/serve", "/api/feedback", "/api/ops",
                  "/api/sources", "/api/goals", "/api/admin")


class RateLimiter:
    """키별 미끄럼 창 횟수 제한(프로세스 메모리). 여러 프로세스로 띄우면 프로세스마다 따로 센다."""

    MAX_WINDOW = 3600                     # 가장 긴 창(가입 1시간). 이보다 오래된 기록만 남은 키는 정리한다

    def __init__(self):
        self.hits, self.lock, self.calls = {}, threading.Lock(), 0

    def _recent(self, key, window, now):
        q = [t for t in self.hits.get(key, []) if now - t < window]
        if q:
            self.hits[key] = q
        else:                                 # 조회만 한 키(없는 아이디로 로그인 시도 등)는 남기지 않는다
            self.hits.pop(key, None)
        return q

    def _sweep(self, now):
        self.calls += 1
        if self.calls % 1000 == 0:
            self.hits = {k: q for k, q in self.hits.items() if q and now - q[-1] < self.MAX_WINDOW}

    def blocked(self, key: str, limit: int, window: float) -> bool:
        with self.lock:
            return len(self._recent(key, window, time.time())) >= limit

    def hit(self, key: str, window: float):
        with self.lock:
            now = time.time()
            self.hits[key] = self._recent(key, window, now) + [now]
            self._sweep(now)

    def take(self, key: str, limit: int, window: float) -> bool:
        """한 번 쓰기(허용되면 기록하고 True)."""
        with self.lock:
            now = time.time()
            q = self._recent(key, window, now)
            if len(q) >= limit:
                return False
            self.hits[key] = q + [now]
            self._sweep(now)
            return True

    def clear(self, key: str):
        with self.lock:
            self.hits.pop(key, None)


def client_ip(request: Request, trust_proxy: bool) -> str:
    """trust_proxy면 X-Forwarded-For의 맨 오른쪽 값(앞단 프록시 하나가 직접 본 주소)을 쓴다. 맨 왼쪽 값은 사용자가 지어 보낼 수 있다."""
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd and fwd.split(",")[-1].strip():
            return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def install_security(app, hsts: bool):
    """모든 응답에 보안 헤더. 화면은 같은 출처 스크립트만 쓰므로 script-src 'self'(인라인 스크립트 금지)."""
    csp = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
           "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith(("/docs", "/redoc")):            # 로컬 모드의 API 문서 화면은 외부 스크립트를 쓴다(공개 모드는 문서 꺼짐)
            resp.headers.setdefault("Content-Security-Policy", csp)
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        if hsts:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
        return resp


def install_admin_gate(app, user_of):
    """공개 모드: 관리자 API는 관리자 세션이 있을 때만 통과. user_of(request) → 사용자 dict 또는 None."""
    @app.middleware("http")
    async def gate(request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p + "/") or path.startswith(p + "-") for p in ADMIN_PREFIXES):
            u = user_of(request)
            if u is None:
                return JSONResponse({"detail": "관리자 로그인이 필요합니다"}, status_code=401)
            if not u.get("is_admin"):
                return JSONResponse({"detail": "관리자만 쓸 수 있는 기능입니다"}, status_code=403)
        return await call_next(request)
