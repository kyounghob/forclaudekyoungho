"""공공데이터포털 금융위원회_증권상품시세정보(ETF) API 클라이언트.

서비스키는 환경변수 ``DATA_GO_KR_KEY`` 또는 인자로 준다. 오퍼레이션 경로는 포털 활용가이드 기준으로 두되
``operation`` 인자로 바꿀 수 있게 했다(포털 명세가 바뀌어도 코드 수정 없이 설정으로 대응).
응답 항목(확인된 공통 항목 기준): basDt, srtnCd, isinCd, itmsNm, clpr, vs, fltRt, nav, mkp, hipr, lopr, trqu, trPrc, mrktTotAmt,
nPptTotAmt, stLstgCnt, bssIdxIdxNm, bssIdxClpr — 실제 응답에 없는 항목은 비워 둔다.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

import pandas as pd

BASE_URL = "https://apis.data.go.kr/1160100/service/GetSecuritiesProductInfoService"
DEFAULT_OPERATION = "getETFPriceInfo"
FIELDS = ["basDt", "srtnCd", "isinCd", "itmsNm", "clpr", "vs", "fltRt", "nav", "mkp", "hipr", "lopr", "trqu", "trPrc", "mrktTotAmt",
          "nPptTotAmt", "stLstgCnt", "bssIdxIdxNm", "bssIdxClpr"]


class DataGoKrClient:
    def __init__(self, service_key: str = None, base_url: str = BASE_URL, operation: str = DEFAULT_OPERATION, timeout: int = 20):
        self.key = service_key or os.environ.get("DATA_GO_KR_KEY")
        self.base_url, self.operation, self.timeout = base_url, operation, timeout

    @property
    def available(self) -> bool:
        return bool(self.key)

    def etf_prices(self, bas_dt: str = None, like_itms_nm: str = None, num_of_rows: int = 1000, page_no: int = 1) -> pd.DataFrame:
        """기준일(YYYYMMDD)·종목명 검색으로 ETF 시세·NAV 행을 받는다. 괴리율 = (clpr − nav) / nav."""
        if not self.key:
            raise RuntimeError("DATA_GO_KR_KEY가 없습니다. 공공데이터포털에서 '금융위원회_증권상품시세정보' 활용 신청 후 키를 설정하세요")
        params = {"serviceKey": self.key, "resultType": "json", "numOfRows": num_of_rows, "pageNo": page_no}
        if bas_dt:
            params["basDt"] = bas_dt
        if like_itms_nm:
            params["likeItmsNm"] = like_itms_nm
        url = f"{self.base_url}/{self.operation}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "etfrec education project"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
        items = (((payload.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
        df = pd.DataFrame(items)
        for f in FIELDS:
            if f not in df.columns:
                df[f] = None
        for c in ("clpr", "nav", "trqu", "mrktTotAmt", "bssIdxClpr", "fltRt"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["premium_pct"] = (df["clpr"] - df["nav"]) / df["nav"] * 100
        return df
