"""공식 API 호출과 접근 점검에 쓰는 작은 HTTP 도구.

- 정직한 User-Agent(``USER_AGENT``)만 쓴다(브라우저 흉내 없음).
- ``CallBudget``: 실행당 호출 상한과 호출 간격. 인증키별 일 호출 한도는 제공처 이용 조건이라 코드가 강제하지 않으므로 고지에서 확인한다.
- ``probe``: 루트 주소에 HEAD 요청 1회(리다이렉트는 따라가지 않음).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "etfrec/1.0 (non-commercial education project)"


class CallBudget:
    """실행당 호출 상한(``max_calls``)과 호출 간 최소 간격(``min_interval``초). ``calls``는 이번 실행에서 보낸 요청 수(실패 포함)."""

    def __init__(self, max_calls: int = 30, min_interval: float = 1.0):
        self.max_calls, self.min_interval = int(max_calls), float(min_interval)
        self.calls, self._last = 0, None

    def take(self):
        if self.calls >= self.max_calls:
            raise RuntimeError(f"실행당 호출 상한 {self.max_calls}회에 도달해 더 요청하지 않았습니다")
        if self._last is not None:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
        self.calls += 1
        self._last = time.monotonic()


def get_json(url: str, headers: dict, timeout: float, budget: CallBudget):
    """예산을 확인한 뒤 GET 1회. JSON이 아니면(게이트웨이 오류 XML 등) 응답 앞부분을 담아 ValueError."""
    budget.take()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except ValueError:
        raise ValueError(f"JSON이 아닌 응답(인증키 미등록·호출 초과 같은 게이트웨이 오류일 수 있음): {raw[:160]!r}") from None


def root_url(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}/"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                                        # 3xx를 따라가지 않아 요청이 1회로 끝난다


def probe(url: str, timeout: float = 8) -> str:
    """HEAD 1회로 접근 가능 여부만 본다. 응답 코드가 오면 도달한 것(3xx는 'ok 3xx', 4xx·5xx는 'http 코드')."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            return f"ok {r.status}"
    except urllib.error.HTTPError as e:
        e.close()
        return f"ok {e.code}" if 300 <= e.code < 400 else f"http {e.code}"
    except Exception as e:  # noqa: BLE001 - 점검 결과를 보고만 한다
        return f"fail: {type(e).__name__}: {str(e)[:80]}"
