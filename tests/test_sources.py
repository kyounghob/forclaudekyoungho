"""공개 데이터 커넥터 테스트. 실제 네트워크는 쓰지 않는다(키 환경변수를 지우고 urlopen·opener를 가짜로 바꾼다)."""
import io
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, datetime

import pandas as pd
import pytest

from etfrec.sources import krx, load_etf_universe, net, sync_all, type_stats
from etfrec.sources.datagokr import DataGoKrClient
from etfrec.sources.sync import SAMPLE_ETF, check_sources, previous_business_day


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    """키가 설정된 기계에서도 테스트가 실제 API를 부르지 않게 한다."""
    monkeypatch.delenv("KRX_OPEN_API_KEY", raising=False)
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)


class _Resp(io.BytesIO):
    status = 200


def fake_urlopen(monkeypatch, handler):
    """urllib.request.urlopen을 바꿔 보낸 Request를 모두 기록하고 handler(url)의 JSON을 돌려준다."""
    seen = []

    def fake(req, timeout=None, **kw):
        seen.append(req)
        return _Resp(json.dumps(handler(req.full_url)).encode("utf-8"))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return seen


def qs(url: str) -> dict:
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


# Open API 일별매매정보 모양(ISU_ABBRV 없음, ISU_CD는 단축코드, 숫자는 쉼표 문자열)
OPENAPI_ROWS = [
    dict(BAS_DD="20261013", ISU_CD="990010", ISU_NM="예시 코스피200", TDD_CLSPRC="40,000", CMPPREVDD_PRC="100", FLUC_RT="0.25", NAV="40,020.00",
         ACC_TRDVOL="1,200,000", ACC_TRDVAL="48,000,000,000", MKTCAP="1,000,000,000,000", IDX_IND_NM="코스피 200", OBJ_STKPRC_IDX="400.10"),
    dict(BAS_DD="20261013", ISU_CD="990020", ISU_NM="예시 레버리지", TDD_CLSPRC="20,100", NAV="20,000.00", ACC_TRDVOL="9,000,000",
         IDX_IND_NM="코스피 200", OBJ_STKPRC_IDX="400.10"),
    dict(BAS_DD="20261013", ISU_CD="990030", ISU_NM="예시 미국S&P500(H)", TDD_CLSPRC="15,000", NAV="15,030.00", ACC_TRDVOL="300,000",
         IDX_IND_NM="S&P 500", OBJ_STKPRC_IDX="6000"),
]


def test_krx_openapi_request_and_parse(monkeypatch):
    seen = fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": OPENAPI_ROWS})
    c = krx.KrxOpenApiClient("TESTKEY", min_interval=0)
    df = c.etf_daily("20261013")
    assert len(seen) == 1 and c.calls == 1
    p = urllib.parse.urlsplit(seen[0].full_url)
    assert (p.scheme, p.netloc, p.path) == ("https", "data-dbg.krx.co.kr", "/svc/apis/etp/etf_bydd_trd") and qs(seen[0].full_url) == {"basDd": "20261013"}
    assert seen[0].get_header("Auth_key") == "TESTKEY" and seen[0].get_header("User-agent") == net.USER_AGENT
    r = df.set_index("code")
    assert list(r.index) == ["990010", "990020", "990030"] and df["isin"].isna().all()       # 단축코드인 ISU_CD는 isin으로 옮기지 않는다
    assert r.loc["990020", "name"] == "예시 레버리지" and r.loc["990020", "etf_type"] == "leverage_inverse" and not r.loc["990020", "pension_eligible"]
    assert r.loc["990010", "etf_type"] == "kr_broad" and r.loc["990030", "etf_type"] == "global_equity" and r.loc["990030", "hedged"]
    assert r.loc["990010", "close"] == 40000 and r.loc["990010", "volume"] == 1200000 and r.loc["990020", "premium"] == pytest.approx(0.005)


def test_isu_cd_isin_rule_and_full_name_fallback():
    df = krx.normalize(pd.DataFrame([
        dict(ISU_CD="KR7990040006", ISU_NM="예시 200선물인버스2X"),                                   # ISIN 모양 → isin, 단축코드는 ISIN에서
        dict(ISU_SRT_CD="990050", ISU_CD="KR7990050005", ISU_ABBRV="예시 고배당", ISU_NM="예시 고배당증권상장지수투자신탁(주식)"),
        dict(ISU_CD="KR7990070009", ISU_NM="예시 200증권상장지수투자신탁(주식)"),                     # 법정 꼬리의 '증권'으로 섹터형 오분류 금지
        dict(ISU_CD="990090", ISU_NM="예시 코스피200 베어", 추적배수="-1"),                             # 이름에 없어도 추적배수로 파생형
    ]))
    assert df["isin"].tolist()[:3] == ["KR7990040006", "KR7990050005", "KR7990070009"] and pd.isna(df["isin"].iloc[3])
    assert df["code"].tolist() == ["990040", "990050", "990070", "990090"]
    assert df["name"].tolist() == ["예시 200선물인버스2X", "예시 고배당", "예시 200", "예시 코스피200 베어"]
    assert df["etf_type"].tolist() == ["leverage_inverse", "income", "kr_broad", "leverage_inverse"]
    assert krx.clean_code(69500) == "069500" and krx.clean_code("A069500") == "069500" and krx.clean_code("0091C0") == "0091C0"


def test_openapi_call_cap_and_interval(monkeypatch):
    seen = fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": []})
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    c = krx.KrxOpenApiClient("TESTKEY", max_calls=2, min_interval=1.0)
    c.etf_daily("20261013")
    c.etf_daily("20261012")
    with pytest.raises(RuntimeError, match="실행당 호출 상한"):
        c.etf_daily("20261009")
    assert len(seen) == 2 and c.calls == 2 and len(sleeps) == 1 and 0 < sleeps[0] <= 1.0


def test_sync_without_keys_makes_no_requests(tmp_path, monkeypatch):
    seen = fake_urlopen(monkeypatch, lambda url: {})
    opened = []
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", lambda self, req, *a, **k: opened.append(req))
    prov = sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_csv_date="20261013")
    assert seen == [] and opened == []                                        # data.krx.co.kr를 포함해 어떤 호스트에도 요청 없음
    it = prov["items"]
    assert prov["policy"] == "official-apis-and-manual-download-only" and prov["scope"] == "non-commercial-education"
    assert it["krx_etf_list"]["status"] == "ok" and it["krx_etf_list"]["rows"] == 45 and it["krx_etf_list"]["data_as_of"] == "2026-10-13"
    assert it["krx_etf_list"]["synced_at"] == prov["run_at"] and it["krx_etf_list"]["method"] == "manual_download"
    assert {k: it[k]["status"] for k in ("krx_etf_daily", "datagokr_etf_prices", "datagokr_listed")} == \
        dict(krx_etf_daily="skipped", datagokr_etf_prices="skipped", datagokr_listed="skipped")
    assert not hasattr(krx, "fetch_etf_list") and not hasattr(krx, "KRX_JSON_URL")


KRX_HEADER = "표준코드,단축코드,한글종목명,한글종목약명,영문종목명,상장일,기초지수명,지수산출기관,추적배수,복제방법,기초시장분류,기초자산분류,상장좌수,운용사,CU수량,총보수,과세유형"
KRX_ROWS = [
    'KR7099990000,099990,예시 코스피200증권상장지수투자신탁(주식),예시 코스피200,EX KOSPI200,2002/10/14,코스피 200,KRX,일반 (1),실물(패시브),국내,주식,"1,000,000",예시운용A,"100,000",0.150,비과세',
    'KR7990020002,990020,예시 레버리지증권상장지수투자신탁(주식-파생형),예시 레버리지,EX LEVERAGE,2010/02/22,코스피 200,KRX,2,실물(패시브),국내,주식,"500,000",예시운용A,"100,000",0.640,배당소득세(보유기간과세)',
    'KR7990030001,990030,예시 미국S&P500증권상장지수투자신탁(주식-파생형)(H),예시 미국S&P500(H),EX US S&P500(H),2021/04/09,S&P 500,S&P,일반 (1),합성(패시브),해외,주식,"200,000",예시운용B,"50,000",0.090,배당소득세(보유기간과세)',
    'KR7990060000,990060,예시 국고채3년증권상장지수투자신탁(채권),예시 국고채3년,EX KTB3Y,2009/07/29,KIS 국고채 3년,KIS,일반 (1),실물(패시브),국내,채권,"300,000",예시운용B,"50,000",0.150,배당소득세(보유기간과세)',
]


def test_cp949_csv_with_korean_krx_headers(tmp_path):
    text = "\n".join([KRX_HEADER] + KRX_ROWS) + "\n"
    (tmp_path / "krx_cp949.csv").write_bytes(text.encode("cp949"))
    (tmp_path / "krx_utf8.csv").write_bytes(text.encode("utf-8-sig"))
    df = krx.read_krx_csv(str(tmp_path / "krx_cp949.csv"))
    assert df["code"].tolist() == ["099990", "990020", "990030", "990060"] and df["isin"].iloc[0] == "KR7099990000"
    assert df["name"].tolist() == ["예시 코스피200", "예시 레버리지", "예시 미국S&P500(H)", "예시 국고채3년"] and df["full_name"].iloc[1].endswith("(주식-파생형)")
    assert df["etf_type"].tolist() == ["kr_broad", "leverage_inverse", "global_equity", "bond"]
    assert df["pension_eligible"].tolist() == [True, False, True, True] and df["hedged"].tolist() == [False, False, True, False]
    assert df["total_fee"].tolist() == [0.15, 0.64, 0.09, 0.15] and df["issuer"].iloc[2] == "예시운용B" and df["multiplier"].iloc[1] == "2"
    pd.testing.assert_frame_equal(df, krx.read_krx_csv(str(tmp_path / "krx_utf8.csv")))
    prov = sync_all(str(tmp_path / "out"), krx_csv=str(tmp_path / "krx_cp949.csv"))
    assert prov["items"]["krx_etf_list"]["status"] == "ok" and prov["items"]["krx_etf_list"]["data_as_of_source"] == "file_mtime"
    uni, info = load_etf_universe(str(tmp_path / "out"))
    assert uni["code"].tolist()[0] == "099990" and "내려받은 날" in info["label"]              # 저장·재적재해도 앞자리 0 유지


def test_excel_needs_engine_and_fails_clearly(tmp_path, monkeypatch):
    x = tmp_path / "etf.xlsx"
    x.write_bytes(b"PK\x03\x04 placeholder")
    monkeypatch.setattr(krx, "_has_module", lambda name: False)
    with pytest.raises(krx.KrxFileError) as ei:
        krx.read_krx_csv(str(x))
    assert ei.value.reason == "excel_engine_missing" and "openpyxl" in str(ei.value)
    it = sync_all(str(tmp_path / "out"), krx_csv=str(x))["items"]["krx_etf_list"]
    assert it["status"] == "fail" and it["reason"] == "excel_engine_missing" and "file" not in it
    calls = []
    monkeypatch.setattr(krx, "_has_module", lambda name: True)
    monkeypatch.setattr(pd, "read_excel", lambda path, engine=None, **kw: calls.append((os.path.basename(str(path)), engine))
                        or pd.DataFrame({"단축코드": [69500], "한글종목약명": ["예시 레버리지"], "총보수": [0.64]}))
    df = krx.read_krx_csv(str(x))
    assert calls == [("etf.xlsx", "openpyxl")] and df.loc[0, "code"] == "069500" and df.loc[0, "etf_type"] == "leverage_inverse"
    krx.read_krx_csv(str(tmp_path / "old.xls"))
    assert calls[-1] == ("old.xls", "xlrd")


def test_empty_outblock_is_empty_and_default_date_is_previous_weekday(tmp_path, monkeypatch):
    seen = fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": []})
    prov = sync_all(str(tmp_path), krx_key="TESTKEY", bas_dt="20261012", min_interval=0)
    it = prov["items"]["krx_etf_daily"]
    assert it["status"] == "empty" and it["requested"] == "20261012" and it["calls"] == 1 and "휴장일" in it["note"]
    assert not (tmp_path / "krx_etf_daily.csv").exists() and len(seen) == 1
    assert [previous_business_day(date(2026, 10, d)) for d in (11, 12, 14)] == ["20261009", "20261009", "20261013"]
    prov2 = sync_all(str(tmp_path), krx_key="TESTKEY", min_interval=0)
    assert prov2["base_date"] == previous_business_day() and qs(seen[-1].full_url)["basDd"] == prov2["base_date"]


def _datagokr(total, day="20261013"):
    def handler(url):
        q = qs(url)
        page, n = int(q["pageNo"]), int(q["numOfRows"])
        items = [dict(basDt=day, srtnCd=f"{i:06d}", isinCd=f"KR7{i:06d}000", itmsNm=f"예시 ETF {i}", clpr="10,000", nav="9,990.00", trqu="1000")
                 for i in range((page - 1) * n, min(page * n, total))]
        return {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                             "body": {"numOfRows": n, "pageNo": page, "totalCount": total, "items": {"item": items} if items else ""}}}
    return handler


def test_datagokr_pages_until_total_count(tmp_path, monkeypatch):
    seen = fake_urlopen(monkeypatch, _datagokr(2500))
    c = DataGoKrClient("KEY%2BABC", min_interval=0)                         # 포털의 인코딩 키도 한 번만 인코딩
    df = c.etf_prices(bas_dt="20261013")
    assert len(df) == 2500 and c.last_meta == dict(total_count=2500, pages=3, truncated=False, stop="complete") and c.calls == 3
    assert [qs(r.full_url)["pageNo"] for r in seen] == ["1", "2", "3"]
    assert {k: qs(seen[0].full_url)[k] for k in ("serviceKey", "resultType", "basDt", "numOfRows")} == \
        dict(serviceKey="KEY+ABC", resultType="json", basDt="20261013", numOfRows="1000")
    assert df["code"].iloc[1] == "000001" and df["premium"].iloc[0] == pytest.approx(10 / 9990) and df["volume"].iloc[0] == 1000
    c2 = DataGoKrClient("KEY", min_interval=0)
    assert len(c2.etf_prices(bas_dt="20261013", max_pages=2)) == 2000 and c2.last_meta["truncated"]
    it = sync_all(str(tmp_path), datagokr_key="KEY", bas_dt="20261013", min_interval=0, max_pages=2)["items"]["datagokr_etf_prices"]
    assert it["status"] == "partial" and it["truncated"] and it["total_count"] == 2500 and it["rows"] == 2000 and it["pages"] == 2 and it["calls"] == 2
    fake_urlopen(monkeypatch, _datagokr(1))
    one = DataGoKrClient("KEY", min_interval=0)
    assert len(one.etf_prices()) == 1 and one.last_meta == dict(total_count=1, pages=1, truncated=False, stop="complete")


def test_listed_info_cross_check(tmp_path, monkeypatch):
    def handler(url):
        if "GetKrxListedInfoService/getItemInfo" in url:
            items = [dict(basDt="20261013", srtnCd="AS00001", isinCd="KRSAMPLE00001", mrktCtg="KOSPI", itmsNm="샘플 코스피200"),
                     dict(basDt="20261013", srtnCd="AS00002", isinCd="KRXXXXXXXXXX", mrktCtg="KOSPI", itmsNm="샘플 KRX300")]
            return {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 2, "items": {"item": items}}}}
        return {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 0, "items": ""}}}
    seen = fake_urlopen(monkeypatch, handler)
    prov = sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, datagokr_key="KEY", bas_dt="20261013", min_interval=0)
    li = prov["items"]["datagokr_listed"]
    assert li["status"] == "ok" and li["calls"] == 1 and li["checked"] == 45 and li["found"] == 2 and li["isin_mismatch"] == 1
    assert li["isin_mismatch_examples"] == ["S00002"] and prov["items"]["datagokr_etf_prices"]["status"] == "empty" and len(seen) == 2
    off = sync_all(str(tmp_path), datagokr_key="KEY", bas_dt="20261013", min_interval=0, cross_check=False)["items"]["datagokr_listed"]
    assert off["status"] == "skipped" and len(seen) == 3


def test_kept_or_failed_snapshot_keeps_old_synced_at_and_stale_label(tmp_path):
    sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_csv_date="20200102")
    pj = tmp_path / "provenance.json"
    prov = json.loads(pj.read_text(encoding="utf-8"))
    prov["items"]["krx_etf_list"]["synced_at"] = "2020-01-03T09:00:00+09:00"            # 오래전에 저장한 파일로 만든다
    pj.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    kept = sync_all(str(tmp_path))["items"]["krx_etf_list"]
    assert kept["status"] == "kept" and kept["file_kept"] and kept["synced_at"] == "2020-01-03T09:00:00+09:00" and kept["data_as_of"] == "2020-01-02"
    failed = sync_all(str(tmp_path), krx_csv=str(tmp_path / "없는파일.csv"))["items"]["krx_etf_list"]
    assert failed["status"] == "fail" and failed["file_kept"] and failed["synced_at"] == "2020-01-03T09:00:00+09:00"
    df, info = load_etf_universe(str(tmp_path), today=date(2026, 10, 14))
    assert info["kind"] == "snapshot" and info["as_of"] == "2020-01-02" and info["stale"] and info["age_days"] > 30 and len(df) == 45
    assert "기준일 2020-01-02" in info["label"] and "지난 자료" in info["label"]
    assert not load_etf_universe(str(tmp_path), today=date(2020, 1, 10))[1]["stale"]
    # 예전 형식(최상위 synced_at만 실행 시각으로 갱신)이어도 그 값을 파일 날짜로 쓰지 않는다 → 파일 수정 시각
    pj.write_text(json.dumps(dict(synced_at="2099-01-01T00:00:00", items=dict(krx_etf_list=dict(status="kept")))), encoding="utf-8")
    ts = datetime(2020, 1, 5, 12, 0).timestamp()
    os.utime(tmp_path / "krx_etf_list.csv", (ts, ts))
    info = load_etf_universe(str(tmp_path), today=date(2026, 10, 14))[1]
    assert info["as_of"] == "2020-01-05" and "저장일 2020-01-05" in info["label"] and info["stale"]
    # 손으로 고쳐 날짜가 깨진 provenance여도 적재(서비스 시작)가 멈추지 않는다
    pj.write_text(json.dumps(dict(items=dict(krx_etf_list=dict(data_as_of="??", synced_at="날짜 아님")))), encoding="utf-8")
    info = load_etf_universe(str(tmp_path), today=date(2026, 10, 14))[1]
    assert info["as_of"] is None and "날짜 미상" in info["label"] and not info["stale"]


def test_price_snapshot_adds_premium_and_volume_stats(tmp_path, monkeypatch):
    rows = [dict(BAS_DD="20261013", ISU_CD="S00001", ISU_NM="샘플 코스피200", TDD_CLSPRC="10,010", NAV="10,000.00", ACC_TRDVOL="1,000"),
            dict(BAS_DD="20261013", ISU_CD="S00002", ISU_NM="샘플 KRX300", TDD_CLSPRC="9,970", NAV="10,000.00", ACC_TRDVOL="3,000"),
            dict(BAS_DD="20261013", ISU_CD="S00037", ISU_NM="샘플 레버리지", TDD_CLSPRC="5,050", NAV="5,000.00", ACC_TRDVOL="9,000"),
            dict(BAS_DD="20261013", ISU_CD="Z99999", ISU_NM="목록에 없는 종목", TDD_CLSPRC="1,000", NAV="1,000.00", ACC_TRDVOL="1")]
    fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": rows})
    prov = sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_key="TESTKEY", bas_dt="20261013", min_interval=0)
    assert prov["items"]["krx_etf_daily"]["status"] == "ok" and prov["items"]["krx_etf_daily"]["data_as_of"] == "2026-10-13"
    df, info = load_etf_universe(str(tmp_path), today=date(2026, 10, 14))
    px = info["prices"]
    assert px["source"] == "krx_etf_daily" and px["as_of"] == "2026-10-13" and px["matched"] == 3 and not px["stale"]
    assert "시세 기준일 2026-10-13" in info["label"] and len(df) == 45 and df.set_index("code").loc["S00002", "premium"] == pytest.approx(-0.003)
    st = {t["key"]: t for t in type_stats(df)}
    assert st["kr_broad"]["premium_abs_median"] == pytest.approx(0.002) and st["kr_broad"]["volume_median"] == 2000 and st["kr_broad"]["priced"] == 2
    assert st["leverage_inverse"]["premium_abs_median"] == pytest.approx(0.01) and st["bond"]["premium_abs_median"] is None and st["bond"]["volume_median"] is None
    # 공공데이터포털 시세의 기준일이 더 최근이면 그것을 쓴다
    pd.DataFrame(dict(basDt=["20261014"], srtnCd=["S00001"], itmsNm=["샘플 코스피200"], clpr=[10100], nav=[10000.0], trqu=[500])) \
        .to_csv(tmp_path / "datagokr_etf_prices.csv", index=False, encoding="utf-8-sig")
    px2 = load_etf_universe(str(tmp_path), today=date(2026, 10, 14))[1]["prices"]
    assert px2["source"] == "datagokr_etf_prices" and px2["as_of"] == "2026-10-14" and px2["matched"] == 1
    sync_all(str(tmp_path / "noprice"), krx_csv=SAMPLE_ETF)
    df2, info2 = load_etf_universe(str(tmp_path / "noprice"))
    assert info2["prices"] is None and all(t["premium_abs_median"] is None and t["volume_median"] is None for t in type_stats(df2))


def test_check_sources_sends_one_head_per_root_with_honest_user_agent(monkeypatch):
    seen = []

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(self, req, *a, **k):
        seen.append((req.full_url, req.get_method(), req.get_header("User-agent")))
        return R()
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    out = check_sources()
    roots = {r["url"] for r in out if r["url"]}
    assert len(seen) == len(roots) == len({u for u, _, _ in seen}) < sum(1 for r in out if r["url"])
    assert all(m == "HEAD" and ua == net.USER_AGENT and urllib.parse.urlsplit(u).path == "/" for u, m, ua in seen)
    assert net.USER_AGENT == "etfrec/1.0 (non-commercial education project)" and all(r["status"] in ("ok 200", "n/a") for r in out)


# ---------- 최종 검토(데이터 수집) 반영: 원자적 교체·기록 일치·형식 검사·키 가림·페이지 넘김·CLI ----------
def _krx_file(tmp_path, name="krx4.csv"):
    p = tmp_path / name
    p.write_text("\n".join([KRX_HEADER] + KRX_ROWS) + "\n", encoding="utf-8")
    return str(p)


def _rows(path):
    return len(pd.read_csv(path, encoding="utf-8-sig"))


def test_failed_write_keeps_old_snapshot_and_record(tmp_path, monkeypatch):
    sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_csv_date="20261013")
    snap = tmp_path / "krx_etf_list.csv"
    before = snap.read_bytes()
    real = pd.DataFrame.to_csv

    def broken(self, path=None, *a, **k):                    # 디스크 가득 참처럼 쓰는 도중에 실패
        if path is not None and str(path).endswith(".tmp"):
            with open(path, "w", encoding="utf-8") as f:
                f.write("code,name\n")
            raise OSError(27, "File too large")
        return real(self, path, *a, **k)
    monkeypatch.setattr(pd.DataFrame, "to_csv", broken)
    it = sync_all(str(tmp_path), krx_csv=_krx_file(tmp_path), krx_csv_date="20261016")["items"]["krx_etf_list"]
    monkeypatch.setattr(pd.DataFrame, "to_csv", real)
    assert it["status"] == "fail" and it["file_kept"] and it["rows"] == 45 and it["data_as_of"] == "2026-10-13"
    assert snap.read_bytes() == before and not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    df, info = load_etf_universe(str(tmp_path), today=date(2026, 10, 14))
    assert len(df) == 45 and not info["record_mismatch"] and "기준일 2026-10-13" in info["label"]


def test_unreadable_snapshot_falls_back_to_sample(tmp_path):
    (tmp_path / "krx_etf_list.csv").write_bytes(b"")
    df, info = load_etf_universe(str(tmp_path))
    assert info["kind"] == "sample" and "빈 파일" in info["fallback_reason"] and "샘플" in info["label"] and len(df) == 45


def test_interrupted_sync_keeps_file_and_record_together(tmp_path, monkeypatch):
    sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_csv_date="20260801")

    def stop(self, *a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(DataGoKrClient, "etf_prices", stop)
    with pytest.raises(KeyboardInterrupt):
        sync_all(str(tmp_path), krx_csv=_krx_file(tmp_path), krx_csv_date="20261016", datagokr_key="KEY", min_interval=0)
    prov = json.loads((tmp_path / "provenance.json").read_text(encoding="utf-8"))
    assert prov["complete"] is False and prov["items"]["krx_etf_list"]["rows"] == 4 and prov["items"]["krx_etf_list"]["data_as_of"] == "2026-10-16"
    info = load_etf_universe(str(tmp_path), today=date(2026, 10, 17))[1]
    assert info["as_of"] == "2026-10-16" and not info["stale"] and not info["record_mismatch"]
    # 기록 없이 파일만 바뀌면(기록 직전 중단·손으로 덮어씀) 기록의 기준일을 믿지 않는다
    pd.read_csv(SAMPLE_ETF, encoding="utf-8-sig").to_csv(tmp_path / "krx_etf_list.csv", index=False, encoding="utf-8-sig")
    info = load_etf_universe(str(tmp_path), today=date(2026, 10, 17))[1]
    assert info["record_mismatch"] and "기록(provenance.json)과 파일 내용이 달라" in info["label"] and "저장일" in info["label"]


def test_schema_check_rejects_other_files_and_renamed_fields(tmp_path, monkeypatch):
    sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_csv_date="20261013")
    stock = tmp_path / "stocks.csv"                          # KRX 주식 전종목 기본정보(ETF 파일이 아님)
    stock.write_text("표준코드,단축코드,한글 종목명,한글 종목약명,영문 종목명,상장일,시장구분,증권구분,소속부,주식종류,액면가,상장주식수\n"
                     "KR7005930003,005930,삼성전자보통주,삼성전자,SamsungElectronics,1975/06/11,KOSPI,주권,,보통주,100,5969782550\n"
                     "KR7105560007,105560,KB금융지주보통주,KB금융,KB Financial Group,2008/10/10,KOSPI,주권,,보통주,5000,381462103\n", encoding="utf-8")
    it = sync_all(str(tmp_path), krx_csv=str(stock), krx_csv_date="20261016")["items"]["krx_etf_list"]
    assert it["status"] == "fail" and it["reason"] == "schema" and it["file_kept"] and _rows(tmp_path / "krx_etf_list.csv") == 45
    good = [dict(BAS_DD="20261013", ISU_CD="S00001", ISU_NM="샘플 코스피200", TDD_CLSPRC="10,010", NAV="10,000.00", ACC_TRDVOL="1,000")]
    fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": good})
    assert sync_all(str(tmp_path), krx_key="TESTKEY", bas_dt="20261013", min_interval=0)["items"]["krx_etf_daily"]["status"] == "ok"
    renamed = [dict(BAS_DD="20261014", ISU_CD="S00001", ISU_NM="샘플 코스피200", CLSPRC="10,020", ETF_NAV="10,000.00", TRDVOL="1,000")]
    fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": renamed})
    d = sync_all(str(tmp_path), krx_key="TESTKEY", bas_dt="20261014", min_interval=0)["items"]["krx_etf_daily"]
    assert d["status"] == "fail" and d["reason"] == "schema" and d["file_kept"] and d["data_as_of"] == "2026-10-13"
    assert load_etf_universe(str(tmp_path), today=date(2026, 10, 15))[1]["prices"]["as_of"] == "2026-10-13"


def test_keys_are_trimmed_validated_and_never_recorded(tmp_path, monkeypatch):
    seen = fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": []})
    sync_all(str(tmp_path), krx_key="MY-SECRET-KRX-KEY-1234567890\r\n", bas_dt="20261013", min_interval=0)
    assert seen[-1].get_header("Auth_key") == "MY-SECRET-KRX-KEY-1234567890"       # CRLF .env의 줄바꿈은 지운다
    prov = sync_all(str(tmp_path), krx_key="MY-SECRET\rKEY", datagokr_key="SVC%0DKEY", bas_dt="20261013", min_interval=0)
    assert prov["items"]["krx_etf_daily"]["reason"] == "invalid_key" and prov["items"]["datagokr_etf_prices"]["reason"] == "invalid_key"

    def leaky(req, timeout=None, **kw):                       # 키가 실린 오류 메시지도 가려서 기록한다
        raise ValueError(f"Invalid header value b'{req.headers.get('Auth_key')}' url={req.full_url}")
    monkeypatch.setattr(urllib.request, "urlopen", leaky)
    prov = sync_all(str(tmp_path), krx_key="MY-SECRET-KRX-KEY-1234567890", datagokr_key="SERVICE-KEY-ABCDEF", bas_dt="20261013", min_interval=0)
    text = (tmp_path / "provenance.json").read_text(encoding="utf-8") + json.dumps(prov, ensure_ascii=False)
    assert "MY-SECRET" not in text and "SERVICE-KEY-ABCDEF" not in text and "***" in prov["items"]["krx_etf_daily"]["error"]
    assert net.redact("x serviceKey=ABC%2BDEF&pageNo=1", ()) == "x serviceKey=***&pageNo=1"


def test_truncated_flag_survives_runs_that_keep_the_file(tmp_path, monkeypatch):
    sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_csv_date="20261013")
    fake_urlopen(monkeypatch, _datagokr(2500))
    first = sync_all(str(tmp_path), datagokr_key="KEY", bas_dt="20261013", min_interval=0, max_pages=1)["items"]["datagokr_etf_prices"]
    assert first["status"] == "partial" and first["truncated"] and "페이지 상한 1쪽" in first["note"]
    kept = sync_all(str(tmp_path))["items"]["datagokr_etf_prices"]                    # 키 없이 다시 실행 → 파일과 기록을 그대로 둔다
    assert kept["status"] == "skipped" and kept["file_kept"] and kept["truncated"] and kept["total_count"] == 2500
    info = load_etf_universe(str(tmp_path), today=date(2026, 10, 14))[1]
    assert info["prices"]["truncated"] and "일부만 받음" in info["label"]


def test_datagokr_envelope_short_pages_and_errors(tmp_path, monkeypatch):
    fake_urlopen(monkeypatch, lambda url: {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"})
    it = sync_all(str(tmp_path), datagokr_key="KEY", bas_dt="20261013", min_interval=0)["items"]["datagokr_etf_prices"]
    assert it["status"] == "fail" and "응답 형식" in it["error"]                     # 오류 응답을 '0행·휴장일'로 오인하지 않는다

    def small_pages(url):                                      # 서버가 쪽 크기를 100으로 줄여 보내는 경우
        page = int(qs(url)["pageNo"])
        items = [dict(basDt="20261013", srtnCd=f"{i:06d}", itmsNm=f"예시 {i}", clpr="100", nav="100") for i in range((page - 1) * 100, min(page * 100, 1050))]
        return {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 1050, "items": {"item": items} if items else ""}}}
    fake_urlopen(monkeypatch, small_pages)
    c = DataGoKrClient("KEY", min_interval=0)
    assert len(c.etf_prices(bas_dt="20261013", max_pages=11)) == 1050 and c.last_meta["stop"] == "complete" and not c.last_meta["truncated"]
    it = sync_all(str(tmp_path), datagokr_key="KEY", bas_dt="20261013", min_interval=0, max_pages=10)["items"]["datagokr_etf_prices"]
    assert it["status"] == "partial" and it["rows"] == 1000 and it["stop"] == "page_cap" and "페이지 상한 10쪽" in it["note"]
    calls = {"n": 0}

    def fails_on_page3(req, timeout=None, **kw):
        calls["n"] += 1
        if calls["n"] == 3:
            raise TimeoutError("timed out")
        return _Resp(json.dumps(_datagokr(5000)(req.full_url)).encode("utf-8"))
    monkeypatch.setattr(urllib.request, "urlopen", fails_on_page3)
    it = sync_all(str(tmp_path), datagokr_key="KEY", bas_dt="20261013", min_interval=0)["items"]["datagokr_etf_prices"]
    assert it["status"] == "fail" and it["attempt"]["rows_received"] == 2000 and it["file_kept"] and it["rows"] == 1000


def test_dates_are_validated_and_keys_are_not_cli_arguments(tmp_path):
    from etfrec.cli import main
    from etfrec.sources.sync import parse_day
    assert parse_day("2026-10-13") == "20261013"
    for bad in ("20261310", "2026-10-1", "abc"):
        with pytest.raises(ValueError):
            parse_day(bad)
    with pytest.raises(ValueError):
        sync_all(str(tmp_path), krx_csv=SAMPLE_ETF, krx_csv_date="20261310")
    assert not (tmp_path / "krx_etf_list.csv").exists()
    for argv in (["sources", "sync", "--date", "2026-10-1"], ["sources", "sync", "--krx-csv-date", "20261310"],
                 ["sources", "sync", "--krx-key", "SECRET"], ["sources", "sync", "--datagokr-key", "SECRET"]):
        with pytest.raises(SystemExit) as e:
            main(argv + ["--out", str(tmp_path)])
        assert e.value.code == 2


def test_cli_and_server_use_the_same_sources_dir(tmp_path, monkeypatch):
    from etfrec.cli import main
    monkeypatch.setenv("ETFREC_SOURCES_DIR", str(tmp_path / "served"))
    monkeypatch.chdir(tmp_path)
    main(["sources", "sync", "--krx-csv", SAMPLE_ETF, "--krx-csv-date", "20261013"])
    assert (tmp_path / "served" / "krx_etf_list.csv").exists() and not (tmp_path / "data").exists()
    assert load_etf_universe()[1]["kind"] == "snapshot"


def test_endpoints_can_be_overridden_by_environment(tmp_path, monkeypatch):
    seen = fake_urlopen(monkeypatch, lambda url: {"OutBlock_1": []})
    monkeypatch.setenv("ETFREC_KRX_API_BASE", "https://example.test/api/")
    monkeypatch.setenv("ETFREC_KRX_ETF_DAILY_PATH", "etp/other_path")
    it = sync_all(str(tmp_path), krx_key="TESTKEY", bas_dt="20261013", min_interval=0)["items"]["krx_etf_daily"]
    assert seen[-1].full_url.startswith("https://example.test/api/etp/other_path?") and it["endpoint"] == "https://example.test/api/etp/other_path"


def test_sample_snapshot_is_package_data():
    import fnmatch
    import tomllib
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "pyproject.toml"), "rb") as f:
        pkg = tomllib.load(f)["tool"]["setuptools"]["package-data"]["etfrec"]
    rel = os.path.relpath(SAMPLE_ETF, os.path.join(root, "etfrec")).replace(os.sep, "/")
    assert any(fnmatch.fnmatch(rel, pat) for pat in pkg), (rel, pkg)


def test_public_info_hides_local_paths_and_raw_errors(tmp_path):
    from etfrec.sources import public_info
    home = tmp_path / "Users" / "hong.gildong" / "Downloads"
    home.mkdir(parents=True)
    src = home / "data_4601_20261013.csv"
    src.write_bytes(open(SAMPLE_ETF, "rb").read())
    sync_all(str(tmp_path / "snap"), krx_csv=str(src), krx_csv_date="20261013")
    sync_all(str(tmp_path / "snap"), krx_csv=str(home / "없는파일.csv"))
    info = load_etf_universe(str(tmp_path / "snap"))[1]
    pub = json.dumps(public_info(info), ensure_ascii=False)
    assert "hong.gildong" not in pub and "Downloads" not in pub and str(tmp_path) not in pub
    assert json.loads(pub)["file"] == "krx_etf_list.csv" and json.loads(pub)["status"] == "fail"
    prov = (tmp_path / "snap" / "provenance.json").read_text(encoding="utf-8")
    assert "hong.gildong" not in prov and "없는파일.csv" in prov                 # 내려받은 파일은 이름만 기록(폴더 경로 제외)
