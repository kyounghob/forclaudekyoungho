"""KRX 정보데이터시스템(data.krx.co.kr) ETF 전종목 기본정보 수집과 유형 분류.

내려받기는 사이트가 쓰는 비공식 JSON 엔드포인트(getJsonData.cmd, bld=MDCSTAT04601)를 그대로 호출한다.
공식 API가 아니므로 열 이름이 바뀔 수 있어 열 매핑은 관대하게 처리하고, 실패하면 예외 대신 상태를 돌려준다.
"""
from __future__ import annotations

import io
import json
import re
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from ..taxonomy import CLASSIFY_ORDER, TYPE_BY_KEY

KRX_JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
KRX_REFERER = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201030101"
BLD_ETF_LIST = "dbms/MDC/STAT/standard/MDCSTAT04601"      # ETF › 전종목 기본정보
# KRX 응답 열 → 표준 열. 알려진 이름을 모두 적고, 없는 열은 그대로 둔다.
COLUMN_MAP = {
    "ISU_SRT_CD": "code", "ISU_CD": "isin", "ISU_ABBRV": "name", "ISU_NM": "full_name", "ISU_ENG_NM": "name_en",
    "COM_ABBRV": "issuer", "LIST_DD": "listed", "IDX_IND_NM": "index_name", "IDX_CALC_INST_NM1": "index_provider",
    "IDX_MKT_CLSS_NM": "market_class", "IDX_ASST_CLSS_NM": "asset_class", "ETF_REPLICA_METHD_TP_CD": "replication",
    "ETF_TOT_FEE": "total_fee", "TAX_TP_CD": "tax_type", "LIST_SHRS": "listed_shares", "CU_QTY": "cu_qty", "ETF_TYP": "etf_kind",
    # 한글 열(CSV 내려받기)
    "단축코드": "code", "표준코드": "isin", "한글종목약명": "name", "한글종목명": "full_name", "영문종목명": "name_en", "운용사": "issuer",
    "상장일": "listed", "기초지수명": "index_name", "지수산출기관": "index_provider", "기초시장분류": "market_class", "기초자산분류": "asset_class",
    "복제방법": "replication", "총보수": "total_fee", "과세유형": "tax_type", "상장좌수": "listed_shares", "CU수량": "cu_qty",
}
STANDARD_COLUMNS = ["code", "isin", "name", "issuer", "listed", "index_name", "market_class", "asset_class", "replication", "total_fee", "tax_type"]


def fetch_etf_list(timeout: int = 20) -> pd.DataFrame:
    """KRX에서 ETF 전종목 기본정보를 받아 표준 열로 돌려준다. 네트워크·정책으로 막히면 예외."""
    form = urllib.parse.urlencode({"bld": BLD_ETF_LIST, "locale": "ko_KR", "share": "1", "money": "1", "csvxls_isNo": "false"}).encode()
    req = urllib.request.Request(KRX_JSON_URL, data=form, headers={
        "User-Agent": "Mozilla/5.0 (etfrec education project)", "Referer": KRX_REFERER, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    rows = None
    for key in ("output", "OutBlock_1", "block1"):
        if isinstance(payload, dict) and isinstance(payload.get(key), list):
            rows = payload[key]; break
    if rows is None:
        raise ValueError(f"예상하지 못한 KRX 응답 형식: 키 {list(payload)[:5] if isinstance(payload, dict) else type(payload)}")
    return normalize(pd.DataFrame(rows))


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
