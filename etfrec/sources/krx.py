"""KRX ETF 전종목 기본정보·일별 시세의 정규화와 유형 분류.

사이트 화면이 쓰는 비공식 JSON 엔드포인트(getJsonData.cmd)는 **호출하지 않는다**(이용약관·서버 부하). 경로는 둘뿐이다.
- ``read_krx_csv``: 정보데이터시스템 화면에서 이용자가 직접 내려받은 파일. CSV(UTF-8·cp949)는 항상 읽고, Excel은 pandas 엔진
  (.xlsx → openpyxl, .xls → xlrd)이 설치된 경우에만 읽는다. 엔진이 없으면 ``KrxFileError``로 원인을 알린다(동기화는 실패로 기록).
- ``KrxOpenApiClient``: KRX Open API(openapi.krx.co.kr 인증키 발급·서비스별 이용 신청, 비상업적 이용·재배포 금지·출처 표기)로
  ETF 일별매매정보(종가·NAV·거래량)를 받는다. 실행당 호출 상한과 호출 간격을 지킨다. 엔드포인트는 활용 가이드 기준이며(키 발급 후 확인)
  코드를 고치지 않고 환경변수 ``ETFREC_KRX_API_BASE``·``ETFREC_KRX_ETF_DAILY_PATH``로 바꿀 수 있다.
- ``check_schema``: 정규화한 표가 기대한 자료인지(필수 열이 채워졌는지) 본다. 동기화는 통과하지 못한 파일·응답으로 기존 스냅샷을 바꾸지 않는다.
"""
from __future__ import annotations

import importlib.util
import io
import os
import re
import urllib.parse

import numpy as np
import pandas as pd

from ..taxonomy import CLASSIFY_ORDER, TYPE_BY_KEY
from . import net

KRX_OPENAPI_BASE = "https://data-dbg.krx.co.kr/svc/apis"
KRX_OPENAPI_ETF_DAILY = "etp/etf_bydd_trd"          # ETF 일별매매정보(활용 가이드 기준 경로)
KRX_SOURCE_NOTE = "출처: 한국거래소 KRX Open API(비상업적 이용, 재배포 금지) 또는 KRX 정보데이터시스템 수동 내려받기"
# 원천 열 → 표준 열. 알려진 이름을 모두 적고, 없는 열은 그대로 둔다. ISU_CD는 값 모양을 보고 normalize에서 정한다(ISIN이면 isin, 아니면 code).
COLUMN_MAP = {
    "ISU_SRT_CD": "code", "ISU_ABBRV": "name", "ISU_NM": "full_name", "ISU_ENG_NM": "name_en",
    "COM_ABBRV": "issuer", "LIST_DD": "listed", "IDX_IND_NM": "index_name", "IDX_CALC_INST_NM1": "index_provider",
    "IDX_MKT_CLSS_NM": "market_class", "IDX_ASST_CLSS_NM": "asset_class", "ETF_REPLICA_METHD_TP_CD": "replication",
    "ETF_TOT_FEE": "total_fee", "TAX_TP_CD": "tax_type", "LIST_SHRS": "listed_shares", "CU_QTY": "cu_qty", "ETF_TYP": "etf_kind",
    # Open API 일별매매정보
    "BAS_DD": "date", "TDD_CLSPRC": "close", "NAV": "nav", "ACC_TRDVOL": "volume", "MKTCAP": "market_cap", "OBJ_STKPRC_IDX": "index_close",
    # 한글 열(정보데이터시스템 내려받기: 전종목 기본정보, 전종목 시세)
    "단축코드": "code", "표준코드": "isin", "한글종목약명": "name", "한글종목명": "full_name", "영문종목명": "name_en", "운용사": "issuer",
    "상장일": "listed", "기초지수명": "index_name", "지수산출기관": "index_provider", "추적배수": "multiplier", "기초시장분류": "market_class",
    "기초자산분류": "asset_class", "복제방법": "replication", "총보수": "total_fee", "과세유형": "tax_type", "상장좌수": "listed_shares", "CU수량": "cu_qty",
    "종목코드": "code", "종목명": "name", "종가": "close", "순자산가치(NAV)": "nav", "거래량": "volume", "시가총액": "market_cap",
    # 공공데이터포털 증권상품시세정보(ETF). nav는 이름이 같아 그대로 둔다
    "basDt": "date", "srtnCd": "code", "isinCd": "isin", "itmsNm": "name", "clpr": "close", "trqu": "volume", "mrktTotAmt": "market_cap",
    "bssIdxIdxNm": "index_name", "bssIdxClpr": "index_close",
}
STANDARD_COLUMNS = ["code", "isin", "name", "issuer", "listed", "index_name", "market_class", "asset_class", "replication", "total_fee", "tax_type"]
PRICE_COLUMNS = ["close", "nav", "volume", "market_cap", "index_close"]
# 코드 열은 문자열로 읽는다(069500이 숫자 69500으로 바뀌지 않게). 없는 열 이름은 pandas가 무시한다
CODE_DTYPES = {c: str for c in ("code", "isin", "단축코드", "표준코드", "종목코드", "ISU_SRT_CD", "ISU_CD", "srtnCd", "isinCd")}
EXCEL_ENGINES = {".xlsx": "openpyxl", ".xlsm": "openpyxl", ".xls": "xlrd"}
LEGAL_SUFFIX = re.compile(r"\s*(증권)?\s*상장지수\s*투자신탁(\([^)]*\))?")   # 법정 이름 꼬리('증권' 키워드 오분류 방지)


class KrxFileError(ValueError):
    """내려받은 파일을 읽지 못한 이유(``reason``). 동기화는 이를 실패로 기록하고 기존 스냅샷을 지우지 않는다."""

    def __init__(self, msg: str, reason: str = "read_error"):
        super().__init__(msg)
        self.reason = reason


class SchemaError(KrxFileError):
    """필수 열이 비었거나 다른 화면의 파일로 보이는 자료(``reason='schema'``)."""

    def __init__(self, msg: str):
        super().__init__(msg, reason="schema")


# 필수 열과 채워져야 하는 최소 비율. 기본정보는 ETF 전종목 기본정보에만 있는 열(기초지수명·총보수) 중 하나가 채워져야 한다
SCHEMA = dict(list=dict(required={"code": 0.9, "name": 0.9}, any_of=(("index_name", "total_fee"), 0.5)),
              prices=dict(required={"code": 0.9, "close": 0.9, "nav": 0.5}, any_of=None))
SCHEMA_LABEL = {"code": "단축코드", "name": "종목명", "close": "종가", "nav": "NAV", "index_name": "기초지수명", "total_fee": "총보수"}


def _filled(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns or not len(df):
        return 0.0
    s = df[col].map(_text) if df[col].dtype == object else df[col]
    return float(s.notna().mean())


def check_schema(df: pd.DataFrame, kind: str) -> list:
    """정규화한 표(``kind``: 'list' = 전종목 기본정보, 'prices' = 일별 시세)의 문제 목록. 비어 있으면 통과.
    예: KRX 주식 전종목 기본정보처럼 다른 화면의 파일, 필드 이름이 바뀐 API 응답(종가·NAV가 비어 있음)을 거른다."""
    rule, out = SCHEMA[kind], []
    for c, need in rule["required"].items():
        got = _filled(df, c)
        if got < need:
            out.append(f"{SCHEMA_LABEL[c]} 채움 {got:.0%} < {need:.0%}")
    if rule["any_of"]:
        cols, need = rule["any_of"]
        if max(_filled(df, c) for c in cols) < need:
            out.append("·".join(SCHEMA_LABEL[c] for c in cols) + " 열이 비어 있음(ETF 전종목 기본정보 파일이 아닐 수 있음)")
    return out


class KrxOpenApiClient:
    """KRX Open API 클라이언트. 인증키는 인자 또는 환경변수 ``KRX_OPEN_API_KEY``(요청 헤더 AUTH_KEY).

    실행당 호출 상한(``max_calls``, 기본 30회)과 호출 간격(``min_interval``, 기본 1초)을 지키고 보낸 요청 수를 ``calls``로 센다.
    인증키별 일 호출 한도는 제공처 이용 조건이므로 KRX 고지에서 확인한다(코드가 강제하지 않음).
    """

    def __init__(self, auth_key: str = None, base_url: str = None, timeout: int = 20, max_calls: int = 30, min_interval: float = 1.0,
                 daily_path: str = None):
        self.raw_key = auth_key or os.environ.get("KRX_OPEN_API_KEY")
        self.key, self.key_error = net.clean_key(self.raw_key)          # 앞뒤 줄바꿈은 지우고, 안에 제어 문자가 있으면 키를 쓰지 않는다
        self.base_url = (base_url or os.environ.get("ETFREC_KRX_API_BASE") or KRX_OPENAPI_BASE).rstrip("/")
        self.daily_path = daily_path or os.environ.get("ETFREC_KRX_ETF_DAILY_PATH") or KRX_OPENAPI_ETF_DAILY
        self.timeout = timeout
        self.budget = net.CallBudget(max_calls, min_interval)

    @property
    def available(self) -> bool:
        return bool(self.key)

    @property
    def calls(self) -> int:
        return self.budget.calls

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/{self.daily_path}"

    def get(self, path: str, **params) -> list:
        if self.key_error:
            raise ValueError(self.key_error)
        if not self.key:
            raise RuntimeError("KRX_OPEN_API_KEY가 없습니다. openapi.krx.co.kr에서 인증키를 발급받고 서비스 이용을 신청하세요")
        url = f"{self.base_url}/{path}?{urllib.parse.urlencode(params)}" if params else f"{self.base_url}/{path}"
        payload = net.get_json(url, {"AUTH_KEY": self.key}, self.timeout, self.budget)
        for key in ("OutBlock_1", "output", "block1"):
            if isinstance(payload, dict) and isinstance(payload.get(key), list):
                return payload[key]
        raise ValueError(f"예상하지 못한 KRX Open API 응답 형식: {str(payload)[:160] if isinstance(payload, dict) else type(payload)}")

    def etf_daily(self, bas_dd: str, path: str = None) -> pd.DataFrame:
        """기준일(YYYYMMDD)의 ETF 일별매매정보 → 표준 열(code·name·close·nav·volume·index_name·index_close)과 괴리율 premium."""
        return normalize(pd.DataFrame(self.get(path or self.daily_path, basDd=bas_dd)))


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _excel_engine(ext: str) -> str:
    eng = EXCEL_ENGINES[ext]
    if not _has_module(eng):
        raise KrxFileError(f"Excel({ext}) 파일을 읽으려면 {eng} 패키지가 필요합니다(pip install {eng}). "
                           "설치하지 않으려면 정보데이터시스템 화면에서 CSV로 내려받으세요", reason="excel_engine_missing")
    return eng


def read_krx_csv(path_or_buffer) -> pd.DataFrame:
    """정보데이터시스템에서 직접 내려받은 파일을 표준 열로 읽는다(이름은 호환을 위해 유지).

    경로 확장자가 .xlsx·.xlsm·.xls면 Excel(엔진 설치 시에만), 그 밖에는 CSV로 보고 UTF-8(BOM 포함) → cp949 순으로 읽는다.
    줄바꿈이 든 문자열은 CSV 본문으로, 바이트·파일 객체는 CSV 내용으로 본다.
    """
    if isinstance(path_or_buffer, (str, os.PathLike)) and "\n" not in str(path_or_buffer):
        ext = os.path.splitext(str(path_or_buffer))[1].lower()
        if ext in EXCEL_ENGINES:
            eng = _excel_engine(ext)
            try:
                return normalize(pd.read_excel(path_or_buffer, engine=eng))
            except ImportError as e:
                raise KrxFileError(f"Excel 엔진 {eng}을 불러오지 못했습니다: {e}", reason="excel_engine_missing") from e
        with open(path_or_buffer, "rb") as f:
            data = f.read()
    elif isinstance(path_or_buffer, str):
        data = path_or_buffer.encode("utf-8")
    elif isinstance(path_or_buffer, bytes):
        data = path_or_buffer
    else:
        data = path_or_buffer.read()
        data = data.encode("utf-8") if isinstance(data, str) else data
    for enc in ("utf-8-sig", "cp949"):
        try:
            return normalize(pd.read_csv(io.BytesIO(data), encoding=enc, dtype=CODE_DTYPES))
        except UnicodeDecodeError:
            continue
    raise KrxFileError("CSV 인코딩을 알 수 없습니다(UTF-8·cp949가 아님)", reason="encoding")


def _text(v):
    """앞뒤 공백을 지운 문자열. 비었거나 결측이면 None."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _short_name(s):
    """전체 이름에서 '증권상장지수투자신탁(…)' 부분만 뗀다(약명이 없을 때만 씀). 뒤의 (H) 같은 표기는 남긴다."""
    return (LEGAL_SUFFIX.sub("", s).strip() or s) if s else None


def looks_isin(s) -> bool:
    return isinstance(s, str) and len(s) == 12 and s.upper().startswith("KR")


def clean_code(v):
    """단축코드 정리: 숫자로 읽혀 앞자리 0이 빠진 값(69500 → 069500)과 앞에 붙은 'A'(A069500 → 069500)를 바로잡는다."""
    s = _text(v)
    if s is None:
        return None
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if len(s) == 7 and s[0] in "Aa" and s[1:].isalnum():
        s = s[1:]
    return s.zfill(6) if s.isdigit() and len(s) < 6 else s


def _num(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    return pd.to_numeric(s.map(_text).str.replace(",", "").str.replace("%", ""), errors="coerce")


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """원천 열 → 표준 열, 유형 분류. 약명이 없으면 전체 이름(ISU_NM·한글종목명, 법정 꼬리 제거)을 name으로 쓰고, ISU_CD는 ISIN 모양(KR로 시작하는
    12자)일 때만 isin, 아니면 code로 본다. 국내 ISIN(KR7 + 단축코드 6자리 + …)만 있으면 단축코드를 꺼낸다. 종가·NAV가 있으면 premium = (종가 − NAV)/NAV."""
    df = df.rename(columns=lambda c: str(c).replace("\ufeff", "").strip())
    isu = df.pop("ISU_CD").map(_text) if "ISU_CD" in df.columns else None
    df = df.rename(columns={c: COLUMN_MAP.get(c, c) for c in df.columns})
    df = df.loc[:, ~df.columns.duplicated()].copy()        # 두 원천 열이 같은 표준 열로 겹치면 앞의 것
    for c in STANDARD_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    df["isin"] = df["isin"].map(_text)
    df["code"] = df["code"].map(clean_code)
    if isu is not None:
        is_isin = isu.map(looks_isin)
        df["isin"] = df["isin"].where(df["isin"].notna(), isu.where(is_isin))
        df["code"] = df["code"].where(df["code"].notna(), isu.where(~is_isin).map(clean_code))
    from_isin = df["isin"].map(lambda s: s[3:9] if looks_isin(s) and s.upper().startswith("KR7") else None)
    df["code"] = df["code"].where(df["code"].notna(), from_isin)
    name = df["name"].map(_text)
    if "full_name" in df.columns:
        name = name.where(name.notna(), df["full_name"].map(_text).map(_short_name))
    df["name"] = name.fillna("").astype(str)
    df["total_fee"] = _num(df["total_fee"])
    for c in PRICE_COLUMNS:
        if c in df.columns:
            df[c] = _num(df[c])
    if "close" in df.columns and "nav" in df.columns:
        df["premium"] = (df["close"] - df["nav"]) / df["nav"].where(df["nav"] > 0)
    df["hedged"] = df["name"].str.contains(r"\(H\)", regex=True)
    df["futures"] = df["name"].str.contains("선물")
    df["total_return"] = df["name"].str.contains(r"\bTR\b|\(TR\)|TR$", regex=True)
    df["etf_type"] = [classify_row(r) for r in df.itertuples()]
    df["pension_eligible"] = df["etf_type"] != "leverage_inverse"
    return df


def _geared(text: str) -> bool:
    """추적배수 열 값이 '레버리지'·'인버스'이거나 1이 아닌 배수(2, -1, -2 …)면 파생형."""
    if "레버리지" in text or "인버스" in text:
        return True
    return any(float(x) != 1 for x in re.findall(r"-?\d+(?:\.\d+)?", text))


def classify_row(row) -> str:
    """종목명·기초시장·기초자산 분류 키워드(있으면 추적배수도)로 ETF 유형 키를 정한다. 우선순위가 높은 유형부터 검사."""
    name = str(getattr(row, "name", "") or "")
    asset = str(getattr(row, "asset_class", "") or "")
    market = str(getattr(row, "market_class", "") or "")
    if _geared(str(getattr(row, "multiplier", "") or "")):
        return "leverage_inverse"
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
