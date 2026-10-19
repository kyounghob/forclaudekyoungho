"""스냅샷 동기화와 적재.

자동 수집은 공식 API(KRX Open API·공공데이터포털)만 쓰고, ETF 전종목 기본정보는 이용자가 직접 내려받은 파일을 정규화한다.
수집하지 못한 환경에서는 샘플 스냅샷을 쓰고 화면 라벨에 그 사실을 남긴다. provenance.json에는 파일마다 자료 기준일(data_as_of),
저장 시각(synced_at), 내용 해시(sha256), 일부만 받음 표시(truncated)를 기록하고, 이번 실행에서 다시 쓰지 않은 파일(kept·fail·empty·skipped)의
기록은 이전 값을 그대로 옮긴다(이번 시도의 결과는 status·reason·error·attempt에).

- 파일은 같은 폴더의 임시 파일에 다 쓴 뒤 ``os.replace``로 바꾼다. 쓰다가 실패하면 임시 파일만 지우므로 기존 스냅샷은 그대로다.
- 파일을 바꾼 직후 provenance.json도 같은 방식으로 저장한다(항목마다). 실행이 중간에 끊겨도 바뀐 파일의 기록이 남고, 기록 전체에
  ``complete: false``가 붙는다. 적재할 때 해시가 기록과 다르면 기록의 기준일을 믿지 않고 라벨에 '기록 불일치'를 표시한다.
- 필수 열이 비었거나 다른 화면의 파일로 보이는 자료(``krx.check_schema``)는 ``fail``(reason ``schema``)로 기록하고 기존 파일을 바꾸지 않는다.
- 오류 문구는 인증키 값을 가린 뒤 기록하고, 화면·API에는 ``public_info``가 고른 필드만 내보낸다(로컬 경로·원시 오류 제외).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from ..taxonomy import ETF_TYPES
from . import krx, net
from .datagokr import DataGoKrClient
from .registry import SOURCES

PKG_DATA = os.path.join(os.path.dirname(__file__), "data")
SAMPLE_ETF = os.path.join(PKG_DATA, "etf_list_sample.csv")
SOURCES_ENV = "ETFREC_SOURCES_DIR"
DEFAULT_DIR = os.environ.get(SOURCES_ENV, os.path.join("data", "sources"))     # 이전 호환용(가져올 때의 값). 실제 기본값은 default_dir()
KST = timezone(timedelta(hours=9))
FILES = dict(krx_etf_list="krx_etf_list.csv", krx_etf_daily="krx_etf_daily.csv", datagokr_etf_prices="datagokr_etf_prices.csv")
PRICE_SOURCES = [("krx_etf_daily", "KRX Open API"), ("datagokr_etf_prices", "공공데이터포털")]   # 기준일이 같으면 앞의 것
# 파일에 딸린 기록(다시 쓰지 않은 파일이면 이전 값을 그대로 옮긴다)
FILE_FIELDS = ("rows", "data_as_of", "data_as_of_source", "synced_at", "synced_at_source", "source_file", "sha256",
               "truncated", "total_count", "pages", "stop", "endpoint")
STALE_DAYS = 30
EMPTY_NOTE = "응답 0행: 휴장일이거나 해당 기준일 자료가 아직 공개되지 않았을 수 있습니다. --date YYYYMMDD로 다른 거래일을 지정하세요"
LISTED_NOTE = "getItemInfo 경로는 활용 가이드 기준(키 발급 후 확인). ETF 포함 여부는 미확인이라 found가 0이면 ETF가 빠진 응답일 수 있음"
SAMPLE_LABEL = "샘플 데이터(가상 종목) — KRX 정보데이터시스템에서 내려받은 CSV를 `python -m etfrec sources sync --krx-csv 파일`로 넣으면 대체됩니다"
MISMATCH_NOTE = "기록(provenance.json)과 파일 내용이 달라 기준일을 확인하지 못했습니다. `sources sync`를 다시 실행하세요"
STOP_NOTE = dict(page_cap="페이지 상한 {max_pages}쪽", empty_page="{pages}쪽에서 빈 쪽이 와서 멈춤", last_page="짧은 쪽을 마지막 쪽으로 봄")
# 화면·API로 내보내는 출처 정보(로컬 경로·내려받은 파일 경로·원시 오류 문구는 빼고 파일 이름만)
PUBLIC_FIELDS = ("kind", "as_of", "age_days", "stale", "label", "synced_at", "record_mismatch", "fallback_reason")
PUBLIC_PRICE_FIELDS = ("source", "source_name", "file", "as_of", "rows", "matched", "truncated", "age_days", "stale", "record_mismatch")


def default_dir() -> str:
    """스냅샷 폴더 기본값: 환경변수 ETFREC_SOURCES_DIR(호출할 때 읽음), 없으면 data/sources. CLI sync·stats와 서버가 같은 규칙을 쓴다."""
    return os.environ.get(SOURCES_ENV) or os.path.join("data", "sources")


def parse_day(v, what: str = "기준일") -> str:
    """'20261013'·'2026-10-13' → '20261013'. 숫자 8자리의 실제 날짜가 아니면 ValueError(다른 날짜로 조용히 바꾸지 않는다)."""
    digits = re.sub(r"\D", "", str(v))
    ok = len(digits) == 8
    if ok:
        try:
            datetime.strptime(digits, "%Y%m%d")
        except ValueError:
            ok = False
    if not ok:
        raise ValueError(f"{what} 형식 오류: {v!r} (YYYYMMDD 형식의 실제 날짜여야 합니다)")
    return digits


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


def _err(e: Exception, secrets=()) -> str:
    """기록용 오류 문구: 인증키 값을 가린 뒤 자른다(키 끝의 줄바꿈 때문에 헤더 오류 메시지에 키가 실리는 경우 등)."""
    return net.redact(f"{type(e).__name__}: {e}", secrets)[:240]


def _reason(e: Exception) -> str:
    """기록용 실패 사유 코드. 이 패키지가 정한 사유(KrxFileError·SchemaError의 reason)만 쓰고, 나머지는 'error'(URLError.reason은 예외 객체일 수 있다)."""
    return e.reason if isinstance(e, krx.KrxFileError) and isinstance(e.reason, str) else "error"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write(path: str, write) -> str:
    """``write(임시 경로)``로 같은 폴더에 임시 파일을 다 쓴 뒤 os.replace로 바꾸고 내용 해시를 돌려준다. 쓰다가 실패하면(디스크 가득 참,
    인코딩 오류, 중단) 임시 파일만 지우고 예외를 다시 내므로 기존 파일은 바뀌지 않는다."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=folder)
    os.close(fd)
    try:
        write(tmp)
        digest = _sha256(tmp)
        try:
            os.chmod(tmp, (os.stat(path).st_mode & 0o777) if os.path.exists(path) else 0o644)
        except OSError:
            pass
        os.replace(tmp, path)
        return digest
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _write_csv(df: pd.DataFrame, path: str) -> str:
    return _atomic_write(path, lambda tmp: df.to_csv(tmp, index=False, encoding="utf-8-sig"))


def _write_json(obj: dict, path: str) -> str:
    def write(tmp):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, default=str)     # 예상하지 못한 값이 섞여도 기록을 남긴다
    return _atomic_write(path, write)


def _read_prov(data_dir: str) -> dict:
    try:
        with open(os.path.join(data_dir, "provenance.json"), encoding="utf-8") as f:
            prov = json.load(f)
        return prov if isinstance(prov, dict) else {}
    except (OSError, ValueError):
        return {}


def _kept(prev: dict, path: str) -> dict:
    """이번 실행에서 다시 쓰지 않은 기존 파일의 기록. 저장 시각·기준일·해시·일부만 받음 표시는 이전 기록(저장 시각이 없으면 파일 수정
    시각)을 그대로 둔다. 파일이 없으면 빈 기록."""
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


def sync_all(out_dir: str = None, datagokr_key: str = None, bas_dt: str = None, timeout: int = 20, krx_csv: str = None,
             krx_key: str = None, krx_csv_date: str = None, cross_check: bool = True, max_calls: int = 30, min_interval: float = 1.0,
             max_pages: int = 10) -> dict:
    """공개 데이터 스냅샷을 만든다. 자동 수집은 공식 API(KRX Open API·공공데이터포털)만 쓰고, ETF 전종목 기본정보는 이용자가
    정보데이터시스템에서 직접 내려받은 파일(``krx_csv``)을 정규화해 저장한다(화면용 JSON 엔드포인트 호출 없음).

    - 기준일 기본값은 직전 평일. ``bas_dt``·``krx_csv_date``가 실제 날짜(YYYYMMDD)가 아니면 아무것도 하지 않고 ValueError.
    - 상태: ok · partial(페이지 상한·빈 쪽으로 일부만) · empty(응답 0행) · fail(호출 오류·형식 오류·키 형식 오류) · skipped(키 없음 등) ·
      kept(입력 없이 기존 파일 유지) · missing. ok·partial만 파일을 바꾸며, 나머지는 기존 파일과 그 기록을 그대로 둔다.
    - 네트워크 호출은 키가 있을 때만 하며, 클라이언트마다 실행당 호출 상한(max_calls)과 호출 간격(min_interval초)을 지킨다.
    - 인증키는 인자 또는 환경변수(KRX_OPEN_API_KEY·DATA_GO_KR_KEY). 기록·반환값에는 키 값이 들어가지 않는다.
    """
    out_dir = out_dir or default_dir()
    day = parse_day(bas_dt, "API 기준일(--date)") if bas_dt else previous_business_day()
    csv_day = parse_day(krx_csv_date, "내려받은 파일의 기준일(--krx-csv-date)") if krx_csv_date else None
    os.makedirs(out_dir, exist_ok=True)
    run_at = _now()
    old = _read_prov(out_dir).get("items", {})
    path = {k: os.path.join(out_dir, f) for k, f in FILES.items()}
    kc = krx.KrxOpenApiClient(krx_key, timeout=timeout, max_calls=max_calls, min_interval=min_interval)
    dc = DataGoKrClient(datagokr_key, timeout=timeout, max_calls=max_calls, min_interval=min_interval)
    secrets = [kc.raw_key, kc.key, dc.raw_key, dc.key]
    items = {}
    prov = dict(run_at=run_at, base_date=day, policy="official-apis-and-manual-download-only", scope="non-commercial-education",
                limits=dict(max_calls_per_client=max_calls, min_interval_sec=min_interval, max_pages=max_pages), complete=False, items={})

    def commit(key: str, record: dict, final: bool = False):
        """항목 하나를 확정하고 provenance.json을 바로 저장한다. 아직 처리하지 않은 항목은 이전 기록을 그대로 둔다(파일과 기록이 함께 간다)."""
        if key:
            items[key] = {k: v for k, v in record.items() if v is not None}
        prov.update(complete=final, items={**{k: v for k, v in old.items() if k not in items}, **items})
        _write_json(prov, os.path.join(out_dir, "provenance.json"))

    # 1) 전종목 기본정보: 이용자가 내려받은 파일만 쓴다
    base, prev, p = dict(source="krx_data", method="manual_download"), old.get("krx_etf_list", {}), path["krx_etf_list"]
    if krx_csv:
        try:
            df = krx.read_krx_csv(krx_csv)
            if not len(df):
                raise krx.KrxFileError("내려받은 파일에 행이 없습니다", reason="empty_file")
            problems = krx.check_schema(df, "list")
            if problems:
                raise krx.SchemaError("ETF 전종목 기본정보 형식이 아닙니다: " + "; ".join(problems))
            is_path = isinstance(krx_csv, (str, os.PathLike)) and "\n" not in str(krx_csv)
            as_of = _iso_day(csv_day) if csv_day else None
            src = "argument" if as_of else None
            if not as_of and is_path and os.path.exists(krx_csv):
                as_of, src = _mtime(krx_csv)[:10], "file_mtime"           # 기준일을 주지 않으면 내려받은 파일의 수정일
            digest = _write_csv(df, p)                                     # 임시 파일 → 교체. 실패하면 기존 파일 그대로
            commit("krx_etf_list", dict(base, status="ok", file=FILES["krx_etf_list"], rows=int(len(df)), data_as_of=as_of, data_as_of_source=src,
                                        synced_at=run_at, sha256=digest, source_file=os.path.basename(str(krx_csv)) if is_path else None,
                                        summary=krx.summarize(df), note=krx.KRX_SOURCE_NOTE))
        except Exception as e:  # noqa: BLE001 - 실패를 기록하고 기존 스냅샷은 그대로 둔다
            err = _err(e, secrets)
            if isinstance(krx_csv, (str, os.PathLike)) and "\n" not in str(krx_csv):   # 내려받은 파일의 폴더 경로(OS 사용자 이름 등)는 남기지 않는다
                for folder in {os.path.dirname(os.path.abspath(str(krx_csv))), os.path.dirname(str(krx_csv))} - {""}:
                    err = err.replace(folder + os.sep, "").replace(folder, "")
            commit("krx_etf_list", dict(base, status="fail", reason=_reason(e), error=err, **_kept(prev, p)))
    elif os.path.exists(p):
        commit("krx_etf_list", dict(base, status="kept", **_kept(prev, p)))
    else:
        commit("krx_etf_list", dict(base, status="missing",
                                    note="KRX 정보데이터시스템 › 기본 통계 › 증권상품 › ETF › 전종목 기본정보에서 파일을 내려받아 --krx-csv 로 지정하세요"))

    # 2) KRX Open API 일별매매정보(인증키가 있을 때만)
    base, prev, p = dict(source="krx_openapi", method="openapi", endpoint=kc.endpoint), old.get("krx_etf_daily", {}), path["krx_etf_daily"]
    if kc.key_error:
        commit("krx_etf_daily", dict(base, status="fail", reason="invalid_key", error=kc.key_error, **_kept(prev, p)))
    elif not kc.available:
        commit("krx_etf_daily", dict(base, status="skipped", reason="KRX_OPEN_API_KEY 없음", **_kept(prev, p)))
    else:
        try:
            dd = kc.etf_daily(day)
            if len(dd):
                problems = krx.check_schema(dd, "prices")
                if problems:
                    raise krx.SchemaError("일별매매정보 응답 형식이 예상과 다릅니다(필드 이름 확인): " + "; ".join(problems))
                digest = _write_csv(dd, p)
                commit("krx_etf_daily", dict(base, status="ok", requested=day, calls=kc.calls, file=FILES["krx_etf_daily"], rows=int(len(dd)),
                                             data_as_of=_data_day(dd, day), synced_at=run_at, sha256=digest, truncated=False, note=krx.KRX_SOURCE_NOTE))
            else:
                commit("krx_etf_daily", dict(base, status="empty", requested=day, calls=kc.calls, note=EMPTY_NOTE, **_kept(prev, p)))
        except Exception as e:  # noqa: BLE001
            commit("krx_etf_daily", dict(base, status="fail", reason=_reason(e), requested=day, calls=kc.calls,
                                         error=_err(e, secrets), **_kept(prev, p)))

    # 3) 공공데이터포털 ETF 시세(totalCount까지 페이지 넘김)와 4) 상장종목정보 코드 교차 확인(같은 serviceKey, 선택)
    base, prev, p = dict(source="datagokr_etf", method="openapi", operation=dc.operation, endpoint=dc.endpoint), old.get("datagokr_etf_prices", {}), \
        path["datagokr_etf_prices"]
    if dc.key_error:
        commit("datagokr_etf_prices", dict(base, status="fail", reason="invalid_key", error=dc.key_error, **_kept(prev, p)))
    elif not dc.available:
        commit("datagokr_etf_prices", dict(base, status="skipped", reason="DATA_GO_KR_KEY 없음", **_kept(prev, p)))
    else:
        try:
            px = dc.etf_prices(bas_dt=day, max_pages=max_pages)
            meta = dict(dc.last_meta)
            if len(px):
                problems = krx.check_schema(px, "prices")
                if problems:
                    raise krx.SchemaError("증권상품시세정보 응답 형식이 예상과 다릅니다(필드 이름 확인): " + "; ".join(problems))
                note = None
                if meta["truncated"]:
                    why = STOP_NOTE.get(meta.get("stop"), "{stop}").format(max_pages=max_pages, pages=meta.get("pages"), stop=meta.get("stop"))
                    note = f"totalCount {meta['total_count']}행 중 {len(px)}행만 받음({why})"
                digest = _write_csv(px, p)
                commit("datagokr_etf_prices", dict(base, status="partial" if meta["truncated"] else "ok", requested=day, calls=dc.calls, **meta,
                                                   file=FILES["datagokr_etf_prices"], rows=int(len(px)), data_as_of=_data_day(px, day),
                                                   synced_at=run_at, sha256=digest, note=note))
            else:
                commit("datagokr_etf_prices", dict(base, status="empty", requested=day, calls=dc.calls, attempt=meta, note=EMPTY_NOTE, **_kept(prev, p)))
        except Exception as e:  # noqa: BLE001 - 호출 오류는 받은 쪽까지 버리고 fail(기존 파일 유지), 진행 상황은 attempt에
            commit("datagokr_etf_prices", dict(base, status="fail", reason=_reason(e), requested=day, calls=dc.calls,
                                               attempt=dict(dc.last_meta) or None, error=_err(e, secrets), **_kept(prev, p)))
    base, used = dict(source="datagokr_listed", method="openapi", endpoint=dc.listed_url), dc.calls
    if dc.key_error:
        rec = dict(base, status="fail", reason="invalid_key", error=dc.key_error)
    elif not dc.available:
        rec = dict(base, status="skipped", reason="DATA_GO_KR_KEY 없음")
    elif not cross_check:
        rec = dict(base, status="skipped", reason="교차 확인 끔(--no-cross-check)")
    elif not os.path.exists(path["krx_etf_list"]):
        rec = dict(base, status="skipped", reason="비교할 전종목 기본정보 스냅샷 없음")
    else:
        try:
            li = dc.listed_info(bas_dt=day, max_pages=max_pages)
            meta = dict(requested=day, calls=dc.calls - used, **dc.last_meta)
            if len(li):
                uni = krx.normalize(pd.read_csv(path["krx_etf_list"], encoding="utf-8-sig", dtype=krx.CODE_DTYPES))
                rec = dict(base, status="partial" if meta["truncated"] else "ok", **meta, rows=int(len(li)), **cross_check_codes(li, uni), note=LISTED_NOTE)
            else:
                rec = dict(base, status="empty", **meta, note=EMPTY_NOTE)
        except Exception as e:  # noqa: BLE001
            rec = dict(base, status="fail", requested=day, calls=dc.calls - used, error=_err(e, secrets), note=LISTED_NOTE)
    commit("datagokr_listed", rec)
    commit(None, {}, final=True)
    return prov


def _record_matches(d: dict, path: str) -> bool:
    """기록에 해시가 있으면 파일 내용과 같은지. 해시가 없는 예전 기록은 확인할 수 없으므로 True."""
    want = d.get("sha256")
    if not want:
        return True
    try:
        return _sha256(path) == want
    except OSError:
        return False


def _attach_prices(df: pd.DataFrame, data_dir: str, items: dict, today: date = None) -> tuple:
    """시세 스냅샷 중 기준일이 가장 최근인 것(같으면 KRX Open API)을 단축코드로 결합한다. 없으면 시세 열을 빼고 (df, None).
    기록의 해시가 파일과 다르면 기록(기준일·일부만 받음)을 쓰지 않고 파일 자체의 날짜로 판단하며 record_mismatch를 남긴다."""
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
        mismatch = not _record_matches(d, p)
        if mismatch:
            d = {}
        as_of = _iso_day(d.get("data_as_of")) or _data_day(px) or _iso_day(d.get("synced_at")) or _iso_day(_mtime(p))
        if best is None or as_of > best[0]:
            best = (as_of, key, name, px, d, mismatch)
    cols = ["close", "nav", "volume", "premium"]
    if best is None:
        return df.drop(columns=[c for c in cols if c in df.columns]), None
    as_of, key, name, px, d, mismatch = best
    if "date" in px.columns:                                            # 같은 코드가 여러 날이면 최근 것
        px = px.assign(_day=px["date"].map(_iso_day)).sort_values("_day", na_position="first", kind="stable")
    px = px.drop_duplicates("code", keep="last")
    cols = [c for c in cols if c in px.columns]
    out = df.drop(columns=[c for c in cols if c in df.columns]).merge(px[["code"] + cols], on="code", how="left")
    age = _age_days(as_of, today)
    return out, dict(source=key, source_name=name, file=FILES[key], as_of=as_of, synced_at=d.get("synced_at"), rows=int(len(px)),
                     matched=int(df["code"].isin(px["code"]).sum()), truncated=bool(d.get("truncated", False)), age_days=age,
                     stale=bool(age is not None and age > STALE_DAYS), record_mismatch=mismatch)


def _sample(reason: str = None) -> tuple:
    if os.path.exists(SAMPLE_ETF):
        df = krx.normalize(pd.read_csv(SAMPLE_ETF, encoding="utf-8-sig", dtype=krx.CODE_DTYPES))
    else:                                   # 설치에서 샘플이 빠져도 서버는 뜬다: 빈 표와 이유만 보인다
        df = krx.normalize(pd.DataFrame(columns=["code", "name"]))
        reason = "; ".join(x for x in (reason, "샘플 파일이 설치되지 않았습니다(etfrec/sources/data/etf_list_sample.csv)") if x)
    label = SAMPLE_LABEL if not reason else f"{SAMPLE_LABEL} (저장된 스냅샷을 쓸 수 없어 샘플을 씁니다: {reason})"
    return df, dict(kind="sample", path=SAMPLE_ETF, synced_at=None, as_of=None, stale=False, detail={}, prices=None, label=label,
                    fallback_reason=reason)


def load_etf_universe(data_dir: str = None, today: date = None) -> tuple:
    """(표준 열 DataFrame, 출처 정보). 동기화된 전종목 기본정보 스냅샷이 있으면 그것을, 없으면 패키지 샘플을 쓴다.

    라벨에는 파일 자체의 기준일(없으면 저장일)을 쓰고 STALE_DAYS(30일)가 지나면 경고를 붙인다. 스냅샷을 읽지 못하거나(빈 파일 등)
    형식 검사를 통과하지 못하면 샘플로 내려가고 라벨에 그 사유를 적는다(서버 시작이 멈추지 않게). 기록의 해시가 파일과 다르면 기록의
    기준일을 쓰지 않고 '기록 불일치'를 표시한다. 시세 스냅샷(krx_etf_daily.csv 또는 datagokr_etf_prices.csv)이 있으면 단축코드로 결합해
    close·nav·volume·premium(= (종가 − NAV)/NAV, 비율) 열을 더한다.
    """
    data_dir = data_dir or default_dir()
    path = os.path.join(data_dir, FILES["krx_etf_list"])
    if not os.path.exists(path):
        return _sample()
    try:
        df = krx.normalize(pd.read_csv(path, encoding="utf-8-sig", dtype=krx.CODE_DTYPES))
        problems = krx.check_schema(df, "list")
        if problems:
            raise krx.SchemaError("; ".join(problems))
    except Exception as e:  # noqa: BLE001 - 깨진 스냅샷으로 서비스가 뜨지 않는 일이 없게 샘플로 대체
        why = {"EmptyDataError": "빈 파일", "SchemaError": "형식 검사 불통과", "UnicodeDecodeError": "인코딩 오류"}.get(type(e).__name__, type(e).__name__)
        return _sample(f"{FILES['krx_etf_list']} {why}")
    items = _read_prov(data_dir).get("items", {})
    detail = items.get("krx_etf_list") or {}
    mismatch = not _record_matches(detail, path)
    if mismatch:
        detail = {k: v for k, v in detail.items() if k in ("source", "method", "status")}
    synced = detail.get("synced_at") or _mtime(path)
    data_day = _iso_day(detail.get("data_as_of"))
    as_of = data_day or _iso_day(synced)
    word = "저장일" if not data_day else "내려받은 날" if detail.get("data_as_of_source") == "file_mtime" else "기준일"
    age = _age_days(as_of, today)
    stale = bool(age is not None and age > STALE_DAYS)
    label = f"KRX 전종목 기본정보 스냅샷({word} {as_of})" if as_of else "KRX 전종목 기본정보 스냅샷(날짜 미상)"
    if mismatch:
        label += f" — {MISMATCH_NOTE}"
    elif stale:
        label += f" — {age}일 지난 자료입니다. 정보데이터시스템에서 다시 내려받아 `sources sync --krx-csv`로 갱신하세요"
    df, prices = _attach_prices(df, data_dir, items, today)
    if prices:
        label += (f" · 시세 기준일 {prices['as_of']}({prices['source_name']}, {prices['matched']}/{len(df)}종목 결합"
                  f"{', 30일 이상 지남' if prices['stale'] else ''}{', 일부만 받음' if prices['truncated'] else ''}"
                  f"{', 기록 불일치' if prices['record_mismatch'] else ''})")
    return df, dict(kind="snapshot", path=path, synced_at=synced, as_of=as_of, age_days=age, stale=stale, detail=detail, prices=prices, label=label,
                    record_mismatch=mismatch)


def public_info(info: dict) -> dict:
    """화면·API로 내보낼 출처 정보만 고른다. 로컬 경로(path)·내려받은 파일 경로·원시 오류 문구(detail)는 빼고 파일 이름과 상태만 남긴다."""
    out = {k: info.get(k) for k in PUBLIC_FIELDS if k in info}
    out["file"] = os.path.basename(info["path"]) if info.get("path") else None
    out["status"] = (info.get("detail") or {}).get("status")
    px = info.get("prices")
    out["prices"] = {k: px.get(k) for k in PUBLIC_PRICE_FIELDS if k in px} if px else None
    return out


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
