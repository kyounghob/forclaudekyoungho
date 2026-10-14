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
    assert len(df) == 2500 and c.last_meta == dict(total_count=2500, pages=3, truncated=False) and c.calls == 3
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
    assert len(one.etf_prices()) == 1 and one.last_meta == dict(total_count=1, pages=1, truncated=False)


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
