"""스냅샷 동기화와 적재. 자동 수집은 공식 API만 쓰고, 실제 수집이 안 되는 환경에서는 샘플 스냅샷을 쓰고 그 사실을 provenance에 남긴다."""
from __future__ import annotations

import json
import os
import time

import pandas as pd

from ..taxonomy import ETF_TYPES, TYPE_BY_KEY
from . import krx
from .datagokr import DataGoKrClient
from .registry import SOURCES

PKG_DATA = os.path.join(os.path.dirname(__file__), "data")
SAMPLE_ETF = os.path.join(PKG_DATA, "etf_list_sample.csv")
DEFAULT_DIR = os.environ.get("ETFREC_SOURCES_DIR", os.path.join("data", "sources"))


def check_sources(timeout: int = 8) -> list:
    """각 출처 루트에 HEAD/GET을 보내 접근 가능 여부만 본다(자동 수집 전 점검)."""
    import urllib.request
    out = []
    for key, s in SOURCES.items():
        if not s.get("url"):
            out.append(dict(key=key, name=s["name"], url="", status="n/a"))
            continue
        try:
            req = urllib.request.Request(s["url"], headers={"User-Agent": "Mozilla/5.0 (etfrec education project)"}, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out.append(dict(key=key, name=s["name"], url=s["url"], status=f"ok {r.status}"))
        except Exception as e:  # noqa: BLE001 - 점검 결과를 보고만 한다
            out.append(dict(key=key, name=s["name"], url=s["url"], status=f"fail: {type(e).__name__}: {str(e)[:80]}"))
    return out


def sync_all(out_dir: str = DEFAULT_DIR, datagokr_key: str = None, bas_dt: str = None, timeout: int = 20,
             krx_csv: str = None, krx_key: str = None) -> dict:
    """공개 데이터 스냅샷을 만든다. 자동 수집은 공식 API(KRX Open API·공공데이터포털)만 쓰고, ETF 전종목 기본정보는
    이용자가 정보데이터시스템에서 직접 내려받은 CSV(``krx_csv``)를 정규화해 저장한다(화면용 JSON 엔드포인트 호출 없음)."""
    os.makedirs(out_dir, exist_ok=True)
    prov = dict(synced_at=time.strftime("%Y-%m-%dT%H:%M:%S"), items={}, policy="official-apis-and-manual-download-only")
    list_path = os.path.join(out_dir, "krx_etf_list.csv")
    if krx_csv:
        try:
            df = krx.read_krx_csv(krx_csv)
            df.to_csv(list_path, index=False, encoding="utf-8-sig")
            prov["items"]["krx_etf_list"] = dict(status="ok", rows=int(len(df)), source="krx_data", method="manual_csv", file=os.path.abspath(krx_csv),
                                                 summary=krx.summarize(df), note=krx.KRX_SOURCE_NOTE)
        except Exception as e:  # noqa: BLE001
            prov["items"]["krx_etf_list"] = dict(status="fail", error=f"{type(e).__name__}: {str(e)[:160]}", source="krx_data", method="manual_csv")
    elif os.path.exists(list_path):
        prov["items"]["krx_etf_list"] = dict(status="kept", source="krx_data", method="manual_csv", file=list_path)
    else:
        prov["items"]["krx_etf_list"] = dict(status="missing", source="krx_data",
                                             note="KRX 정보데이터시스템 › 기본 통계 › 증권상품 › ETF › 전종목 기본정보에서 CSV를 내려받아 --krx-csv 로 지정하세요")
    kclient = krx.KrxOpenApiClient(krx_key, timeout=timeout)
    if kclient.available:
        try:
            day = bas_dt or time.strftime("%Y%m%d")
            dd = kclient.etf_daily(day)
            dd.to_csv(os.path.join(out_dir, "krx_etf_daily.csv"), index=False, encoding="utf-8-sig")
            prov["items"]["krx_etf_daily"] = dict(status="ok", rows=int(len(dd)), source="krx_openapi", date=day, note=krx.KRX_SOURCE_NOTE)
            time.sleep(1.0)                                    # 호출 간 대기(일 한도·서버 부하 배려)
        except Exception as e:  # noqa: BLE001
            prov["items"]["krx_etf_daily"] = dict(status="fail", error=f"{type(e).__name__}: {str(e)[:160]}", source="krx_openapi")
    else:
        prov["items"]["krx_etf_daily"] = dict(status="skipped", reason="KRX_OPEN_API_KEY 없음", source="krx_openapi")
    client = DataGoKrClient(datagokr_key, timeout=timeout)
    if client.available:
        try:
            px = client.etf_prices(bas_dt=bas_dt)
            px.to_csv(os.path.join(out_dir, "datagokr_etf_prices.csv"), index=False, encoding="utf-8-sig")
            prov["items"]["datagokr_etf_prices"] = dict(status="ok", rows=int(len(px)), source="datagokr_etf", operation=client.operation)
        except Exception as e:  # noqa: BLE001
            prov["items"]["datagokr_etf_prices"] = dict(status="fail", error=f"{type(e).__name__}: {str(e)[:160]}", source="datagokr_etf")
    else:
        prov["items"]["datagokr_etf_prices"] = dict(status="skipped", reason="DATA_GO_KR_KEY 없음", source="datagokr_etf")
    with open(os.path.join(out_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)
    return prov


def load_etf_universe(data_dir: str = DEFAULT_DIR) -> tuple:
    """(표준 열 DataFrame, 출처 정보). 동기화된 스냅샷이 있으면 그것을, 없으면 패키지 샘플을 쓴다."""
    path = os.path.join(data_dir, "krx_etf_list.csv")
    if os.path.exists(path):
        df = krx.normalize(pd.read_csv(path, encoding="utf-8-sig"))
        prov_path = os.path.join(data_dir, "provenance.json")
        prov = json.load(open(prov_path, encoding="utf-8")) if os.path.exists(prov_path) else {}
        return df, dict(kind="snapshot", path=path, synced_at=prov.get("synced_at"), detail=prov.get("items", {}).get("krx_etf_list", {}),
                        label=f"KRX 스냅샷 {prov.get('synced_at', '')[:10]}")
    df = krx.normalize(pd.read_csv(SAMPLE_ETF, encoding="utf-8-sig"))
    return df, dict(kind="sample", path=SAMPLE_ETF, synced_at=None, detail={},
                    label="샘플 데이터(가상 종목) — KRX 정보데이터시스템에서 내려받은 CSV를 `python -m etfrec sources sync --krx-csv 파일`로 넣으면 대체됩니다")


def type_stats(df: pd.DataFrame, n_examples: int = 3) -> list:
    """유형별 개수·예시·환헤지 변형 수·총보수 중앙값(교육용 통계, 상품 추천 아님)."""
    out = []
    for t in ETF_TYPES:
        sub = df[df["etf_type"] == t["key"]]
        fee = sub["total_fee"].dropna()
        out.append(dict(key=t["key"], name=t["name"], count=int(len(sub)), hedged=int(sub["hedged"].sum()) if len(sub) else 0,
                        futures=int(sub["futures"].sum()) if len(sub) else 0,
                        fee_median=(round(float(fee.median()), 3) if len(fee) else None),
                        fee_min=(round(float(fee.min()), 3) if len(fee) else None), fee_max=(round(float(fee.max()), 3) if len(fee) else None),
                        issuers=int(sub["issuer"].nunique()) if len(sub) and "issuer" in sub else 0,
                        examples=sub["name"].head(n_examples).tolist()))
    return out
