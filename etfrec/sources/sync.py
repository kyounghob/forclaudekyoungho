"""스냅샷 동기화와 적재. 실제 수집이 안 되는 환경에서는 샘플 스냅샷을 쓰고 그 사실을 provenance에 남긴다."""
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


def sync_all(out_dir: str = DEFAULT_DIR, datagokr_key: str = None, bas_dt: str = None, timeout: int = 20) -> dict:
    """KRX ETF 전종목 기본정보와(키가 있으면) 공공데이터포털 ETF 시세를 받아 저장한다."""
    os.makedirs(out_dir, exist_ok=True)
    prov = dict(synced_at=time.strftime("%Y-%m-%dT%H:%M:%S"), items={})
    try:
        df = krx.fetch_etf_list(timeout=timeout)
        df.to_csv(os.path.join(out_dir, "krx_etf_list.csv"), index=False, encoding="utf-8-sig")
        prov["items"]["krx_etf_list"] = dict(status="ok", rows=int(len(df)), source="krx_data", url=krx.KRX_JSON_URL, bld=krx.BLD_ETF_LIST,
                                             summary=krx.summarize(df))
    except Exception as e:  # noqa: BLE001
        prov["items"]["krx_etf_list"] = dict(status="fail", error=f"{type(e).__name__}: {str(e)[:160]}", source="krx_data", url=krx.KRX_JSON_URL)
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
                    label="샘플 데이터(가상 종목) — `python -m etfrec sources sync`로 실제 KRX 목록을 받으면 대체됩니다")


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
