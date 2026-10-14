"""공공데이터포털 금융위원회 API 클라이언트(같은 serviceKey).

- 증권상품시세정보(ETF) ``getETFPriceInfo``: 기준일 시세·NAV. totalCount까지 pageNo를 넘겨 받고(최대 ``max_pages``쪽),
  다 받지 못하면 ``last_meta['truncated']``에 남긴다.
- KRX상장종목정보 ``getItemInfo``: 단축코드·ISIN·시장구분·종목명. 동기화 때 선택적으로 코드 정합성을 교차 확인하는 데만 쓴다.
  엔드포인트 경로는 활용 가이드 기준이며 키 발급 후 실제 호출로 확인해야 한다(ETF 포함 여부도 미확인).

서비스키는 인자 또는 환경변수 ``DATA_GO_KR_KEY``. 포털의 인코딩 키를 넣어도 이중 인코딩되지 않게 한 번 복호화한다.
오퍼레이션 경로는 ``operation`` 인자로 바꿀 수 있다. 실행당 호출 상한과 호출 간격은 KRX 클라이언트와 같은 ``net.CallBudget``으로 지킨다.
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
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


class DataGoKrClient:
    def __init__(self, service_key: str = None, base_url: str = BASE_URL, operation: str = DEFAULT_OPERATION, timeout: int = 20,
                 max_calls: int = 30, min_interval: float = 1.0):
        key = service_key or os.environ.get("DATA_GO_KR_KEY")
        self.key = urllib.parse.unquote(key) if key else None
        self.base_url, self.operation, self.timeout = base_url, operation, timeout
        self.budget = net.CallBudget(max_calls, min_interval)
        self.last_meta = {}

    @property
    def available(self) -> bool:
        return bool(self.key)

    @property
    def calls(self) -> int:
        return self.budget.calls

    def _pages(self, url: str, params: dict, num_of_rows: int, max_pages: int) -> list:
        """totalCount까지 pageNo를 올리며 item을 모은다(최대 max_pages쪽). 받은 범위는 last_meta(total_count·pages·truncated)."""
        if not self.key:
            raise RuntimeError("DATA_GO_KR_KEY가 없습니다. 공공데이터포털에서 활용 신청 후 키를 설정하세요")
        rows, total, page, items = [], None, 0, []
        while page < max_pages:
            page += 1
            q = dict(serviceKey=self.key, resultType="json", numOfRows=num_of_rows, pageNo=page, **params)
            payload = net.get_json(f"{url}?{urllib.parse.urlencode(q)}", {}, self.timeout, self.budget)
            res = (payload.get("response") or {}) if isinstance(payload, dict) else {}
            head = res.get("header") or {}
            if str(head.get("resultCode", "00")) not in ("00", "0"):
                raise RuntimeError(f"공공데이터포털 오류 {head.get('resultCode')}: {head.get('resultMsg')}")
            body = res.get("body") or {}
            items = body["items"].get("item") if isinstance(body.get("items"), dict) else []
            items = [items] if isinstance(items, dict) else list(items or [])     # 1건이면 dict로 오는 경우
            total = _int(body.get("totalCount")) if total is None else total
            rows += items
            if not items or len(items) < num_of_rows or (total is not None and len(rows) >= total):
                break
        truncated = len(rows) < total if total is not None else (page >= max_pages and len(items) >= num_of_rows)
        self.last_meta = dict(total_count=total, pages=page, truncated=bool(truncated))
        return rows

    def etf_prices(self, bas_dt: str = None, like_itms_nm: str = None, num_of_rows: int = 1000, max_pages: int = 10) -> pd.DataFrame:
        """기준일(YYYYMMDD)·종목명 검색으로 ETF 시세·NAV를 받아 표준 열(code·name·close·nav·volume)과 괴리율 premium = (clpr − nav)/nav로 정규화."""
        params = {}
        if bas_dt:
            params["basDt"] = bas_dt
        if like_itms_nm:
            params["likeItmsNm"] = like_itms_nm
        df = pd.DataFrame(self._pages(f"{self.base_url}/{self.operation}", params, num_of_rows, max_pages))
        for f in FIELDS:
            if f not in df.columns:
                df[f] = None
        return krx.normalize(df)

    def listed_info(self, bas_dt: str = None, num_of_rows: int = 1000, max_pages: int = 10) -> pd.DataFrame:
        """KRX상장종목정보(getItemInfo) → code(단축코드, 앞의 'A' 제거)·isin·name·market·date. 코드 교차 확인용."""
        df = pd.DataFrame(self._pages(LISTED_URL, {"basDt": bas_dt} if bas_dt else {}, num_of_rows, max_pages))
        for f in LISTED_FIELDS:
            if f not in df.columns:
                df[f] = None
        return pd.DataFrame(dict(code=df["srtnCd"].map(krx.clean_code), isin=df["isinCd"].map(krx._text), name=df["itmsNm"],
                                 market=df["mrktCtg"], date=df["basDt"]))
