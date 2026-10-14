"""스냅샷 동기화와 적재.

자동 수집은 공식 API(KRX Open API·공공데이터포털)만 쓰고, ETF 전종목 기본정보는 이용자가 직접 내려받은 파일을 정규화한다.
수집하지 못한 환경에서는 샘플 스냅샷을 쓰고 화면 라벨에 그 사실을 남긴다. provenance.json에는 파일마다 자료 기준일(data_as_of)과
저장 시각(synced_at)을 기록하고, 이번 실행에서 다시 쓰지 않은 파일(kept·fail·empty·skipped)의 기록은 이전 값을 그대로 옮긴다.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from ..taxonomy import ETF_TYPES
from . import krx, net
from .datagokr import DataGoKrClient
from .registry import SOURCES

PKG_DATA = os.path.join(os.path.dirname(__file__), "data")
SAMPLE_ETF = os.path.join(PKG_DATA, "etf_list_sample.csv")
DEFAULT_DIR = os.environ.get("ETFREC_SOURCES_DIR", os.path.join("data", "sources"))
KST = timezone(timedelta(hours=9))
FILES = dict(krx_etf_list="krx_etf_list.csv", krx_etf_daily="krx_etf_daily.csv", datagokr_etf_prices="datagokr_etf_prices.csv")
PRICE_SOURCES = [("krx_etf_daily", "KRX Open API"), ("datagokr_etf_prices", "공공데이터포털")]   # 기준일이 같으면 앞의 것
FILE_FIELDS = ("rows", "data_as_of", "data_as_of_source", "synced_at", "synced_at_source", "source_file")
STALE_DAYS = 30
EMPTY_NOTE = "응답 0행: 휴장일이거나 해당 기준일 자료가 아직 공개되지 않았을 수 있습니다. --date YYYYMMDD로 다른 거래일을 지정하세요"
LISTED_NOTE = "getItemInfo 경로는 활용 가이드 기준(키 발급 후 확인). ETF 포함 여부는 미확인이라 found가 0이면 ETF가 빠진 응답일 수 있음"
SAMPLE_LABEL = "샘플 데이터(가상 종목) — KRX 정보데이터시스템에서 내려받은 CSV를 `python -m etfrec sources sync --krx-csv 파일`로 넣으면 대체됩니다"


def previous_business_day(today: date = None) -> str:
    """직전 평일(YYYYMMDD, 한국 시간 기준). 토·일만 건너뛰고 공휴일은 모르므로 휴장일이면 응답이 0행(empty)일 수 있다."""
    d = (today or datetime.now(KST).date()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _mtime(path: str) -> str:
    return datetime.fromtimestamp(os.path.getmtime(path)).astimezone().isoformat(timespec="seconds")


def _iso_day(v):
    """'20261013'·'2026/10/13'·'2026-10-13T…' → '2026-10-13'. 알 수 없으면 None."""
    digits = re.sub(r"\D", "", str(v or ""))[:8]
    try:
        return datetime.strptime(digits, "%Y%m%d").date().isoformat() if len(digits) == 8 else None
    except ValueError:
        return None


def _data_day(df: pd.DataFrame, fallback=None):
    days = [d for d in df["date"].map(_iso_day) if d] if "date" in df.columns else []
    return max(days) if days else _iso_day(fallback)


def _age_days(day, today: date = None):
    day = _iso_day(day)                                     # 손으로 고친 provenance의 잘못된 날짜로 적재가 멈추지 않게
    return ((today or datetime.now(KST).date()) - date.fromisoformat(day)).days if day else None


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {str(e)[:200]}"


def _read_prov(data_dir: str) -> dict:
    try:
        with open(os.path.join(data_dir, "provenance.json"), encoding="utf-8") as f:
            prov = json.load(f)
        return prov if isinstance(prov, dict) else {}
    except (OSError, ValueError):
        return {}


def _kept(prev: dict, path: str) -> dict:
    """이번 실행에서 다시 쓰지 않은 기존 파일의 기록. 저장 시각·기준일은 이전 기록(없으면 파일 수정 시각)을 그대로 둔다."""
    if not os.path.exists(path):
        return {}
    out = {k: prev[k] for k in FILE_FIELDS if prev.get(k) is not None}
    if "synced_at" not in out:
        out.update(synced_at=_mtime(path), synced_at_source="file_mtime")
    return dict(out, file=os.path.basename(path), file_kept=True)


def check_sources(timeout: int = 8) -> list:
    """출처 루트 주소마다 HEAD 요청 1회로 접근 가능 여부만 본다(같은 루트는 한 번만, 리다이렉트는 따라가지 않음, User-Agent는 net.USER_AGENT)."""
    out, seen = [], {}
    for key, s in SOURCES.items():
        if not s.get("url"):
            out.append(dict(key=key, name=s["name"], url="", status="n/a"))
            continue
        root = net.root_url(s["url"])
        if root not in seen:
            seen[root] = net.probe(root, timeout)
        out.append(dict(key=key, name=s["name"], url=root, status=seen[root]))
    return out


def cross_check_codes(listed: pd.DataFrame, uni: pd.DataFrame) -> dict:
    """전종목 기본정보의 단축코드가 상장종목정보에 있는지, 양쪽에 ISIN이 있으면 같은지 센다(식별자 정합성 점검, 결과는 기록만)."""
    ref = listed.dropna(subset=["code"]).drop_duplicates("code").set_index("code")["isin"]
    mine = uni.dropna(subset=["code"]).drop_duplicates("code").set_index("code")["isin"]
    found = mine.index.isin(ref.index)
    bad = [c for c, v in mine[found].items() if isinstance(v, str) and isinstance(ref[c], str) and v != ref[c]]
    return dict(checked=int(len(mine)), found=int(found.sum()), not_found=int((~found).sum()), isin_mismatch=len(bad),
                not_found_examples=list(mine.index[~found][:5]), isin_mismatch_examples=bad[:5])


def sync_all(out_dir: str = DEFAULT_DIR, datagokr_key: str = None, bas_dt: str = None, timeout: int = 20, krx_csv: str = None,
             krx_key: str = None, krx_csv_date: str = None, cross_check: bool = True, max_calls: int = 30, min_interval: float = 1.0,
             max_pages: int = 10) -> dict:
    """공개 데이터 스냅샷을 만든다. 자동 수집은 공식 API(KRX Open API·공공데이터포털)만 쓰고, ETF 전종목 기본정보는 이용자가
    정보데이터시스템에서 직접 내려받은 파일(``krx_csv``)을 정규화해 저장한다(화면용 JSON 엔드포인트 호출 없음).

    - 기준일 기본값은 직전 평일. 응답 0행은 'empty'로 기록하고 기존 파일을 지우지 않는다.
    - 상태: ok · partial(페이지 상한으로 일부만) · empty · fail · skipped(키 없음 등) · kept(입력 없이 기존 파일 유지) · missing.
    - 네트워크 호출은 키가 있을 때만 하며, 클라이언트마다 실행당 호출 상한(max_calls)과 호출 간격(min_interval초)을 지킨다.
    """
    os.makedirs(out_dir, exist_ok=True)
    run_at = _now()
    day = re.sub(r"\D", "", str(bas_dt)) if bas_dt else previous_business_day()
    old = _read_prov(out_dir).get("items", {})
    path = {k: os.path.join(out_dir, f) for k, f in FILES.items()}
    items = {}

    # 1) 전종목 기본정보: 이용자가 내려받은 파일만 쓴다
    base, prev = dict(source="krx_data", method="manual_download"), old.get("krx_etf_list", {})
    if krx_csv:
        try:
            df = krx.read_krx_csv(krx_csv)
            if not len(df):
                raise krx.KrxFileError("내려받은 파일에 행이 없습니다", reason="empty_file")
            is_path = isinstance(krx_csv, (str, os.PathLike))
            as_of = _iso_day(krx_csv_date) if krx_csv_date else None
            src = "argument" if as_of else None
            if not as_of and is_path and os.path.exists(krx_csv):
                as_of, src = _mtime(krx_csv)[:10], "file_mtime"           # 기준일을 주지 않으면 내려받은 파일의 수정일
            done = dict(base, status="ok", file=FILES["krx_etf_list"], rows=int(len(df)), data_as_of=as_of, data_as_of_source=src, synced_at=run_at,
                        source_file=os.path.abspath(krx_csv) if is_path else None, summary=krx.summarize(df), note=krx.KRX_SOURCE_NOTE)
            df.to_csv(path["krx_etf_list"], index=False, encoding="utf-8-sig")      # 기록을 다 만든 뒤에 파일을 바꾼다
            items["krx_etf_list"] = done
        except Exception as e:  # noqa: BLE001 - 실패를 기록하고 기존 스냅샷은 그대로 둔다
            items["krx_etf_list"] = dict(base, status="fail", reason=getattr(e, "reason", "error"), error=_err(e), **_kept(prev, path["krx_etf_list"]))
    elif os.path.exists(path["krx_etf_list"]):
        items["krx_etf_list"] = dict(base, status="kept", **_kept(prev, path["krx_etf_list"]))
    else:
        items["krx_etf_list"] = dict(base, status="missing",
                                     note="KRX 정보데이터시스템 › 기본 통계 › 증권상품 › ETF › 전종목 기본정보에서 파일을 내려받아 --krx-csv 로 지정하세요")

    # 2) KRX Open API 일별매매정보(인증키가 있을 때만)
    kc = krx.KrxOpenApiClient(krx_key, timeout=timeout, max_calls=max_calls, min_interval=min_interval)
    base, prev, p = dict(source="krx_openapi", method="openapi"), old.get("krx_etf_daily", {}), path["krx_etf_daily"]
    if not kc.available:
        items["krx_etf_daily"] = dict(base, status="skipped", reason="KRX_OPEN_API_KEY 없음", **_kept(prev, p))
    else:
        try:
            dd = kc.etf_daily(day)
            if len(dd):
                dd.to_csv(p, index=False, encoding="utf-8-sig")
                items["krx_etf_daily"] = dict(base, status="ok", requested=day, calls=kc.calls, file=FILES["krx_etf_daily"], rows=int(len(dd)),
                                              data_as_of=_data_day(dd, day), synced_at=run_at, note=krx.KRX_SOURCE_NOTE)
            else:
                items["krx_etf_daily"] = dict(base, status="empty", requested=day, calls=kc.calls, note=EMPTY_NOTE, **_kept(prev, p))
        except Exception as e:  # noqa: BLE001
            items["krx_etf_daily"] = dict(base, status="fail", requested=day, calls=kc.calls, error=_err(e), **_kept(prev, p))

    # 3) 공공데이터포털 ETF 시세(totalCount까지 페이지 넘김)와 4) 상장종목정보 코드 교차 확인(같은 serviceKey, 선택)
    dc = DataGoKrClient(datagokr_key, timeout=timeout, max_calls=max_calls, min_interval=min_interval)
    base, prev, p = dict(source="datagokr_etf", method="openapi", operation=dc.operation), old.get("datagokr_etf_prices", {}), path["datagokr_etf_prices"]
    if not dc.available:
        items["datagokr_etf_prices"] = dict(base, status="skipped", reason="DATA_GO_KR_KEY 없음", **_kept(prev, p))
    else:
        try:
            px = dc.etf_prices(bas_dt=day, max_pages=max_pages)
            meta = dict(requested=day, calls=dc.calls, **dc.last_meta)
            if len(px):
                px.to_csv(p, index=False, encoding="utf-8-sig")
                items["datagokr_etf_prices"] = dict(base, status="partial" if meta["truncated"] else "ok", **meta, file=FILES["datagokr_etf_prices"],
                                                    rows=int(len(px)), data_as_of=_data_day(px, day), synced_at=run_at,
                                                    note=f"totalCount {meta['total_count']}행 중 {len(px)}행만 받음(페이지 상한 {max_pages}쪽)" if meta["truncated"] else None)
            else:
                items["datagokr_etf_prices"] = dict(base, status="empty", **meta, note=EMPTY_NOTE, **_kept(prev, p))
        except Exception as e:  # noqa: BLE001
            items["datagokr_etf_prices"] = dict(base, status="fail", requested=day, calls=dc.calls, error=_err(e), **_kept(prev, p))
    base, used = dict(source="datagokr_listed", method="openapi"), dc.calls
    if not dc.available:
        items["datagokr_listed"] = dict(base, status="skipped", reason="DATA_GO_KR_KEY 없음")
    elif not cross_check:
        items["datagokr_listed"] = dict(base, status="skipped", reason="교차 확인 끔(--no-cross-check)")
    elif not os.path.exists(path["krx_etf_list"]):
        items["datagokr_listed"] = dict(base, status="skipped", reason="비교할 전종목 기본정보 스냅샷 없음")
    else:
        try:
            li = dc.listed_info(bas_dt=day, max_pages=max_pages)
            meta = dict(requested=day, calls=dc.calls - used, **dc.last_meta)
            if len(li):
                uni = krx.normalize(pd.read_csv(path["krx_etf_list"], encoding="utf-8-sig", dtype=krx.CODE_DTYPES))
                items["datagokr_listed"] = dict(base, status="partial" if meta["truncated"] else "ok", **meta, rows=int(len(li)),
                                                **cross_check_codes(li, uni), note=LISTED_NOTE)
            else:
                items["datagokr_listed"] = dict(base, status="empty", **meta, note=EMPTY_NOTE)
        except Exception as e:  # noqa: BLE001
            items["datagokr_listed"] = dict(base, status="fail", requested=day, calls=dc.calls - used, error=_err(e), note=LISTED_NOTE)

    prov = dict(run_at=run_at, base_date=day, policy="official-apis-and-manual-download-only", scope="non-commercial-education",
                limits=dict(max_calls_per_client=max_calls, min_interval_sec=min_interval, max_pages=max_pages),
                items={k: {kk: vv for kk, vv in v.items() if vv is not None} for k, v in items.items()})
    with open(os.path.join(out_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)
    return prov


def _attach_prices(df: pd.DataFrame, data_dir: str, items: dict, today: date = None) -> tuple:
    """시세 스냅샷 중 기준일이 가장 최근인 것(같으면 KRX Open API)을 단축코드로 결합한다. 없으면 시세 열을 빼고 (df, None)."""
    best = None
    for key, name in PRICE_SOURCES:
        p = os.path.join(data_dir, FILES[key])
        if not os.path.exists(p):
            continue
        try:
            px = krx.normalize(pd.read_csv(p, encoding="utf-8-sig", dtype=krx.CODE_DTYPES))
        except Exception:  # noqa: BLE001 - 읽지 못한 시세 파일은 건너뛰고 기본정보만으로 통계를 낸다
            continue
        px = px[px["code"].notna() & px["close"].notna()] if "close" in px.columns else px.iloc[0:0]
        if not len(px):
            continue
        d = items.get(key) or {}
        as_of = _iso_day(d.get("data_as_of")) or _data_day(px) or _iso_day(d.get("synced_at")) or _iso_day(_mtime(p))
        if best is None or as_of > best[0]:
            best = (as_of, key, name, px, d)
    cols = ["close", "nav", "volume", "premium"]
    if best is None:
        return df.drop(columns=[c for c in cols if c in df.columns]), None
    as_of, key, name, px, d = best
    if "date" in px.columns:                                            # 같은 코드가 여러 날이면 최근 것
        px = px.assign(_day=px["date"].map(_iso_day)).sort_values("_day", na_position="first", kind="stable")
    px = px.drop_duplicates("code", keep="last")
    cols = [c for c in cols if c in px.columns]
    out = df.drop(columns=[c for c in cols if c in df.columns]).merge(px[["code"] + cols], on="code", how="left")
    age = _age_days(as_of, today)
    return out, dict(source=key, source_name=name, file=FILES[key], as_of=as_of, synced_at=d.get("synced_at"), rows=int(len(px)),
                     matched=int(df["code"].isin(px["code"]).sum()), truncated=bool(d.get("truncated", False)), age_days=age,
                     stale=bool(age is not None and age > STALE_DAYS))


def load_etf_universe(data_dir: str = DEFAULT_DIR, today: date = None) -> tuple:
    """(표준 열 DataFrame, 출처 정보). 동기화된 전종목 기본정보 스냅샷이 있으면 그것을, 없으면 패키지 샘플을 쓴다.

    라벨에는 파일 자체의 기준일(없으면 저장일)을 쓰고 STALE_DAYS(30일)가 지나면 경고를 붙인다. 시세 스냅샷(krx_etf_daily.csv 또는
    datagokr_etf_prices.csv)이 있으면 단축코드로 결합해 close·nav·volume·premium(= (종가 − NAV)/NAV, 비율) 열을 더한다.
    """
    path = os.path.join(data_dir, FILES["krx_etf_list"])
    if not os.path.exists(path):
        df = krx.normalize(pd.read_csv(SAMPLE_ETF, encoding="utf-8-sig", dtype=krx.CODE_DTYPES))
        return df, dict(kind="sample", path=SAMPLE_ETF, synced_at=None, as_of=None, stale=False, detail={}, prices=None, label=SAMPLE_LABEL)
    items = _read_prov(data_dir).get("items", {})
    detail = items.get("krx_etf_list") or {}
    df = krx.normalize(pd.read_csv(path, encoding="utf-8-sig", dtype=krx.CODE_DTYPES))
    synced = detail.get("synced_at") or _mtime(path)
    data_day = _iso_day(detail.get("data_as_of"))
    as_of = data_day or _iso_day(synced)
    word = "저장일" if not data_day else "내려받은 날" if detail.get("data_as_of_source") == "file_mtime" else "기준일"
    age = _age_days(as_of, today)
    stale = bool(age is not None and age > STALE_DAYS)
    label = f"KRX 전종목 기본정보 스냅샷({word} {as_of})" if as_of else "KRX 전종목 기본정보 스냅샷(날짜 미상)"
    if stale:
        label += f" — {age}일 지난 자료입니다. 정보데이터시스템에서 다시 내려받아 `sources sync --krx-csv`로 갱신하세요"
    df, prices = _attach_prices(df, data_dir, items, today)
    if prices:
        label += (f" · 시세 기준일 {prices['as_of']}({prices['source_name']}, {prices['matched']}/{len(df)}종목 결합"
                  f"{', 30일 이상 지남' if prices['stale'] else ''}{', 일부만 받음' if prices['truncated'] else ''})")
    return df, dict(kind="snapshot", path=path, synced_at=synced, as_of=as_of, age_days=age, stale=stale, detail=detail, prices=prices, label=label)


def type_stats(df: pd.DataFrame, n_examples: int = 3) -> list:
    """유형별 개수·예시·환헤지 변형 수·총보수 중앙값. 시세가 결합돼 있으면 괴리율 절댓값 중앙값(비율, 0.001 = 0.1%)·거래량 중앙값과
    시세가 있는 종목 수(priced)도 더한다. 교육용 통계이며 상품 추천이 아니다."""
    out = []
    empty = pd.Series(dtype=float)
    for t in ETF_TYPES:
        sub = df[df["etf_type"] == t["key"]]
        fee = sub["total_fee"].dropna()
        prem = sub["premium"].abs().dropna() if "premium" in sub.columns else empty
        vol = sub["volume"].dropna() if "volume" in sub.columns else empty
        out.append(dict(key=t["key"], name=t["name"], count=int(len(sub)), hedged=int(sub["hedged"].sum()) if len(sub) else 0,
                        futures=int(sub["futures"].sum()) if len(sub) else 0,
                        fee_median=(round(float(fee.median()), 3) if len(fee) else None),
                        fee_min=(round(float(fee.min()), 3) if len(fee) else None), fee_max=(round(float(fee.max()), 3) if len(fee) else None),
                        issuers=int(sub["issuer"].nunique()) if len(sub) and "issuer" in sub else 0,
                        premium_abs_median=(round(float(prem.median()), 6) if len(prem) else None),
                        volume_median=(int(round(float(vol.median()))) if len(vol) else None), priced=int(len(prem)),
                        examples=sub["name"].head(n_examples).tolist()))
    return out
