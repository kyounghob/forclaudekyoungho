"""공공데이터포털 금융위원회 API 클라이언트(같은 serviceKey).

- 증권상품시세정보(ETF) ``getETFPriceInfo``: 기준일 시세·NAV. totalCount까지 pageNo를 넘겨 받고(최대 ``max_pages``쪽, 서버가 쪽 크기를
  줄여 보내도 totalCount를 알면 계속), 다 받지 못하면 ``last_meta``의 ``truncated``와 멈춘 이유(``stop``: page_cap·empty_page)를 남긴다.
  호출 오류가 나면 받은 쪽까지의 진행(``rows_received``)을 ``last_meta``에 남기고 예외를 다시 낸다(동기화는 fail, 기존 파일 유지).
- 응답 봉투(response·header.resultCode·body)가 없으면 형식 오류로 본다(오류 응답을 '0행·휴장일'로 오인하지 않게).
- KRX상장종목정보 ``getItemInfo``: 단축코드·ISIN·시장구분·종목명. 동기화 때 선택적으로 코드 정합성을 교차 확인하는 데만 쓴다.
  엔드포인트 경로는 활용 가이드 기준이며 키 발급 후 실제 호출로 확인해야 한다(ETF 포함 여부도 미확인).

서비스키는 인자 또는 환경변수 ``DATA_GO_KR_KEY``. 포털의 인코딩 키를 넣어도 이중 인코딩되지 않게 한 번 복호화하고, 앞뒤 공백·줄바꿈은 지운다.
엔드포인트(활용 가이드 기준, 키 발급 후 확인)는 인자 또는 환경변수 ``ETFREC_DATAGOKR_BASE``·``ETFREC_DATAGOKR_OPERATION``·
``ETFREC_DATAGOKR_LISTED_URL``로 바꿀 수 있다. 실행당 호출 상한과 호출 간격은 KRX 클라이언트와 같은 ``net.CallBudget``으로 지킨다.
응답 항목(공통 항목 기준): basDt, srtnCd, isinCd, itmsNm, clpr, vs, fltRt, nav, mkp, hipr, lopr, trqu, trPrc, mrktTotAmt,
nPptTotAmt, stLstgCnt, bssIdxIdxNm, bssIdxClpr — 실제 응답에 없는 항목은 비워 둔다.
"""
from __future__ import annotations

import os
import urllib.parse

import pandas as pd

from . import krx, net

BASE_URL = "https://apis.data.go.kr/1160100/service/GetSecuritiesProductInfoService"
DEFAULT_OPERATION = "getETFPriceInfo"
LISTED_URL = "https://apis.data.go.kr/1160100/service/GetKrxListedInfoService/getItemInfo"   # 활용 가이드 기준, 키 발급 후 확인
FIELDS = ["basDt", "srtnCd", "isinCd", "itmsNm", "clpr", "vs", "fltRt", "nav", "mkp", "hipr", "lopr", "trqu", "trPrc", "mrktTotAmt",
          "nPptTotAmt", "stLstgCnt", "bssIdxIdxNm", "bssIdxClpr"]
LISTED_FIELDS = ["basDt", "srtnCd", "isinCd", "mrktCtg", "itmsNm"]


def _int(v):
    try:
        return int(str(v).strip().replace(",", ""))           # '2,500'처럼 천 단위 쉼표가 붙어 와도 읽는다
    except (TypeError, ValueError):
        return None


class DataGoKrClient:
    def __init__(self, service_key: str = None, base_url: str = None, operation: str = None, timeout: int = 20,
                 max_calls: int = 30, min_interval: float = 1.0, listed_url: str = None):
        self.raw_key = service_key or os.environ.get("DATA_GO_KR_KEY")
        key, self.key_error = net.clean_key(self.raw_key)
        if key:
            key, self.key_error = net.clean_key(urllib.parse.unquote(key))     # 복호화한 값에도 제어 문자(%0D 등)가 없어야 한다
        self.key = key
        self.base_url = (base_url or os.environ.get("ETFREC_DATAGOKR_BASE") or BASE_URL).rstrip("/")
        self.operation = operation or os.environ.get("ETFREC_DATAGOKR_OPERATION") or DEFAULT_OPERATION
        self.listed_url = listed_url or os.environ.get("ETFREC_DATAGOKR_LISTED_URL") or LISTED_URL
        self.timeout = timeout
        self.budget = net.CallBudget(max_calls, min_interval)
        self.last_meta = {}

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/{self.operation}"

    @property
    def available(self) -> bool:
        return bool(self.key)

    @property
    def calls(self) -> int:
        return self.budget.calls

    def _pages(self, url: str, params: dict, num_of_rows: int, max_pages: int) -> list:
        """totalCount까지 pageNo를 올리며 item을 모은다(최대 max_pages쪽). 받은 범위는 last_meta(total_count·pages·truncated·stop).

        멈추는 경우: 받은 행이 totalCount에 닿음(complete), 빈 쪽(empty_page), totalCount를 모를 때 짧은 쪽(last_page), 페이지 상한(page_cap).
        totalCount를 알면 쪽이 요청보다 짧아도(서버가 쪽 크기를 줄인 경우) 계속 받는다."""
        if self.key_error:
            raise ValueError(self.key_error)
        if not self.key:
            raise RuntimeError("DATA_GO_KR_KEY가 없습니다. 공공데이터포털에서 활용 신청 후 키를 설정하세요")
        rows, total, page, stop = [], None, 0, "page_cap"
        self.last_meta = {}
        try:
            while page < max_pages:
                page += 1
                q = dict(serviceKey=self.key, resultType="json", numOfRows=num_of_rows, pageNo=page, **params)
                payload = net.get_json(f"{url}?{urllib.parse.urlencode(q)}", {}, self.timeout, self.budget)
                res = payload.get("response") if isinstance(payload, dict) else None
                head = res.get("header") if isinstance(res, dict) else None
                if not isinstance(head, dict) or head.get("resultCode") is None:
                    raise ValueError(f"예상하지 못한 공공데이터포털 응답 형식(response.header.resultCode 없음): {str(payload)[:160]}")
                if str(head["resultCode"]) not in ("00", "0"):
                    raise RuntimeError(f"공공데이터포털 오류 {head.get('resultCode')}: {head.get('resultMsg')}")
                body = res.get("body")
                if not isinstance(body, dict):
                    raise ValueError("예상하지 못한 공공데이터포털 응답 형식(response.body 없음)")
                items = body["items"].get("item") if isinstance(body.get("items"), dict) else []
                items = [items] if isinstance(items, dict) else list(items or [])     # 1건이면 dict로 오는 경우
                total = _int(body.get("totalCount")) if total is None else total
                rows += items
                if total is not None and len(rows) >= total:
                    stop = "complete"
                    break
                if not items:
                    stop = "empty_page"
                    break
                if total is None and len(items) < num_of_rows:
                    stop = "last_page"
                    break
        except Exception:
            self.last_meta = dict(total_count=total, pages=page, truncated=True, stop="error", rows_received=len(rows))
            raise
        truncated = len(rows) < total if total is not None else stop == "page_cap"
        self.last_meta = dict(total_count=total, pages=page, truncated=bool(truncated), stop=stop)
        return rows

    def etf_prices(self, bas_dt: str = None, like_itms_nm: str = None, num_of_rows: int = 1000, max_pages: int = 10) -> pd.DataFrame:
        """기준일(YYYYMMDD)·종목명 검색으로 ETF 시세·NAV를 받아 표준 열(code·name·close·nav·volume)과 괴리율 premium = (clpr − nav)/nav로 정규화."""
        params = {}
        if bas_dt:
            params["basDt"] = bas_dt
        if like_itms_nm:
            params["likeItmsNm"] = like_itms_nm
        df = pd.DataFrame(self._pages(self.endpoint, params, num_of_rows, max_pages))
        for f in FIELDS:
            if f not in df.columns:
                df[f] = None
        return krx.normalize(df)

    def listed_info(self, bas_dt: str = None, num_of_rows: int = 1000, max_pages: int = 10) -> pd.DataFrame:
        """KRX상장종목정보(getItemInfo) → code(단축코드, 앞의 'A' 제거)·isin·name·market·date. 코드 교차 확인용."""
        df = pd.DataFrame(self._pages(self.listed_url, {"basDt": bas_dt} if bas_dt else {}, num_of_rows, max_pages))
        for f in LISTED_FIELDS:
            if f not in df.columns:
                df[f] = None
        return pd.DataFrame(dict(code=df["srtnCd"].map(krx.clean_code), isin=df["isinCd"].map(krx._text), name=df["itmsNm"],
                                 market=df["mrktCtg"], date=df["basDt"]))
