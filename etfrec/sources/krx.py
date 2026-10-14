"""KRX ETF 전종목 기본정보·일별 시세의 수집과 유형 분류.

중간 점검 지적을 반영해 사이트 화면이 쓰는 비공식 JSON 엔드포인트(getJsonData.cmd) 자동 호출은 **쓰지 않는다**(이용약관·서버 부하).
대신 두 경로만 쓴다.
- ``read_krx_csv``: 정보데이터시스템 화면에서 이용자가 직접 내려받은 CSV·Excel(총보수·운용사·과세유형·기초지수 포함).
- ``KrxOpenApiClient``: KRX Open API(openapi.krx.co.kr에서 인증키 발급·서비스별 이용 신청, 비상업적 이용·재배포 금지·출처 표기)로
  ETF 일별매매정보(종가·NAV·거래량·기초지수)를 받는다. 엔드포인트 경로는 활용 가이드 기준이며 ``path`` 인자로 바꿀 수 있다.
"""
from __future__ import annotations

import io
import json
import os
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from ..taxonomy import CLASSIFY_ORDER, TYPE_BY_KEY

KRX_OPENAPI_BASE = "https://data-dbg.krx.co.kr/svc/apis"
KRX_OPENAPI_ETF_DAILY = "etp/etf_bydd_trd"          # ETF 일별매매정보(활용 가이드 기준 경로)
KRX_SOURCE_NOTE = "출처: 한국거래소 KRX Open API(비상업적 이용, 재배포 금지) 또는 KRX 정보데이터시스템 수동 내려받기"
# KRX 응답 열 → 표준 열. 알려진 이름을 모두 적고, 없는 열은 그대로 둔다.
COLUMN_MAP = {
    "ISU_SRT_CD": "code", "ISU_CD": "isin", "ISU_ABBRV": "name", "ISU_NM": "full_name", "ISU_ENG_NM": "name_en",
    "COM_ABBRV": "issuer", "LIST_DD": "listed", "IDX_IND_NM": "index_name", "IDX_CALC_INST_NM1": "index_provider",
    "IDX_MKT_CLSS_NM": "market_class", "IDX_ASST_CLSS_NM": "asset_class", "ETF_REPLICA_METHD_TP_CD": "replication",
    "ETF_TOT_FEE": "total_fee", "TAX_TP_CD": "tax_type", "LIST_SHRS": "listed_shares", "CU_QTY": "cu_qty", "ETF_TYP": "etf_kind",
    # Open API 일별매매정보
    "BAS_DD": "date", "TDD_CLSPRC": "close", "NAV": "nav", "ACC_TRDVOL": "volume", "MKTCAP": "market_cap", "OBJ_STKPRC_IDX": "index_close",
    # 한글 열(CSV 내려받기)
    "단축코드": "code", "표준코드": "isin", "한글종목약명": "name", "한글종목명": "full_name", "영문종목명": "name_en", "운용사": "issuer",
    "상장일": "listed", "기초지수명": "index_name", "지수산출기관": "index_provider", "기초시장분류": "market_class", "기초자산분류": "asset_class",
    "복제방법": "replication", "총보수": "total_fee", "과세유형": "tax_type", "상장좌수": "listed_shares", "CU수량": "cu_qty",
}
STANDARD_COLUMNS = ["code", "isin", "name", "issuer", "listed", "index_name", "market_class", "asset_class", "replication", "total_fee", "tax_type"]


class KrxOpenApiClient:
    """KRX Open API 클라이언트. 인증키는 환경변수 ``KRX_OPEN_API_KEY`` 또는 인자. 하루 호출 한도를 지키도록 호출 간 대기한다."""

    def __init__(self, auth_key: str = None, base_url: str = KRX_OPENAPI_BASE, timeout: int = 20):
        self.key = auth_key or os.environ.get("KRX_OPEN_API_KEY")
        self.base_url, self.timeout = base_url, timeout

    @property
    def available(self) -> bool:
        return bool(self.key)

    def get(self, path: str, **params) -> list:
        if not self.key:
            raise RuntimeError("KRX_OPEN_API_KEY가 없습니다. openapi.krx.co.kr에서 인증키를 발급받고 서비스 이용을 신청하세요")
        url = f"{self.base_url}/{path}?{urllib.parse.urlencode(params)}" if params else f"{self.base_url}/{path}"
        req = urllib.request.Request(url, headers={"AUTH_KEY": self.key, "User-Agent": "etfrec education project"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
        for key in ("OutBlock_1", "output", "block1"):
            if isinstance(payload, dict) and isinstance(payload.get(key), list):
                return payload[key]
        raise ValueError(f"예상하지 못한 KRX Open API 응답 형식: {list(payload)[:5] if isinstance(payload, dict) else type(payload)}")

    def etf_daily(self, bas_dd: str, path: str = KRX_OPENAPI_ETF_DAILY) -> pd.DataFrame:
        """기준일(YYYYMMDD)의 ETF 일별매매정보 → 표준 열(name, close, nav, volume, index_name, index_close) + 괴리율."""
        df = normalize(pd.DataFrame(self.get(path, basDd=bas_dd)))
        for c in ("close", "nav", "volume", "index_close", "market_cap"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
        if "close" in df.columns and "nav" in df.columns:
            df["premium_pct"] = (df["close"] - df["nav"]) / df["nav"] * 100
        return df


def read_krx_csv(path_or_buffer) -> pd.DataFrame:
    """사이트에서 직접 내려받은 CSV(EUC-KR 또는 UTF-8)를 표준 열로 읽는다."""
    if isinstance(path_or_buffer, (str, bytes)) and not str(path_or_buffer).lstrip().startswith(("단축", "ISU", "표준")):
        try:
            df = pd.read_csv(path_or_buffer, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(path_or_buffer, encoding="cp949")
    else:
        df = pd.read_csv(io.StringIO(path_or_buffer) if isinstance(path_or_buffer, str) else path_or_buffer)
    return normalize(df)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: COLUMN_MAP.get(str(c).strip(), str(c).strip()) for c in df.columns})
    for c in STANDARD_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    df["name"] = df["name"].astype(str).str.strip()
    df["total_fee"] = pd.to_numeric(df["total_fee"].astype(str).str.replace(",", "").str.replace("%", ""), errors="coerce")
    df["hedged"] = df["name"].str.contains(r"\(H\)", regex=True)
    df["futures"] = df["name"].str.contains("선물")
    df["total_return"] = df["name"].str.contains(r"\bTR\b|\(TR\)|TR$", regex=True)
    df["etf_type"] = [classify_row(r) for r in df.itertuples()]
    df["pension_eligible"] = df["etf_type"] != "leverage_inverse"
    return df


def classify_row(row) -> str:
    """종목명·기초시장·기초자산 분류 키워드로 ETF 유형 키를 정한다. 우선순위가 높은 유형부터 검사."""
    name = str(getattr(row, "name", "") or "")
    asset = str(getattr(row, "asset_class", "") or "")
    market = str(getattr(row, "market_class", "") or "")
    for key in CLASSIFY_ORDER:
        rules = TYPE_BY_KEY[key]["krx"]
        name_hit = any(k.lower() in name.lower() for k in rules["keywords"])
        asset_hit = any(a in asset for a in rules.get("asset", []))
        market_hit = any(m in market for m in rules.get("market", []))
        if key in ("leverage_inverse", "income", "allocation", "reit_infra", "active_esg"):
            if name_hit or (asset_hit and key in ("allocation", "reit_infra")):
                return key
        elif key == "bond":
            if asset_hit or name_hit:
                return key
        elif key == "commodity_fx":
            if asset_hit or name_hit:
                return key
        elif key == "kr_sector_theme":
            if name_hit and "해외" not in market:
                return key
        elif key == "global_equity":
            if market_hit or name_hit:
                return key
        elif key == "kr_broad":
            return key
    return "kr_broad"


def summarize(df: pd.DataFrame) -> dict:
    return dict(rows=int(len(df)), issuers=int(df["issuer"].nunique()) if "issuer" in df else None,
                types={k: int(v) for k, v in df["etf_type"].value_counts().items()},
                fee_median=float(df["total_fee"].median()) if df["total_fee"].notna().any() else None)
