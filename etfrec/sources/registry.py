"""공개 교육 자료·데이터 출처 목록.

``verified``는 2026-10 기준 검색으로 확인한 범위를 뜻한다: "domain" = 도메인·메뉴 이름만 확인, "page" = 해당 페이지 확인.
세부 URL은 기관 개편으로 바뀔 수 있으므로 화면에서는 기관 루트 링크와 메뉴 이름을 함께 보여 준다.

이용 범위: 이 프로젝트는 비상업 수업 프로젝트다. KRX Open API·정보데이터시스템 자료는 비상업 이용 조건이므로, 상업 서비스로 쓰려면
공공데이터포털의 이용허락 범위를 확인한 공공데이터 경로나 KRX와의 별도 데이터 이용 계약이 필요하다. 화면용 비공식 엔드포인트는 호출하지 않는다.
"""
from __future__ import annotations

SOURCES = {
    "kcie_etf_school": dict(
        name="전국투자자교육협의회 ETF스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › ETF스쿨",
        kind="온라인 교육(영상·가이드북)", access="웹(무료, 최초 1회 정보 등록)", topics=["ETF 구조", "지수", "비용", "분배금", "해외 ETF", "채권 ETF", "커버드콜 ETF"],
        use="기초 단원의 학습 자료·용어 정의, 퀴즈 문항 출처", license="기관 저작물. 교육 목적 인용 시 출처 표기, 재배포는 기관 정책 확인", verified="domain"),
    "kcie_pension_school": dict(
        name="전국투자자교육협의회 연금스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › 연금스쿨",
        kind="온라인 교육", access="웹(무료)", topics=["연금계좌 ETF", "자산배분", "절세 계좌"], use="연금·노후 목적 로드맵의 핵심 단원 자료(연금계좌·ISA 등 절세 계좌)",
        license="기관 저작물", verified="domain"),
    "kcie_life_school": dict(
        name="전국투자자교육협의회 생애자산관리스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › 생애자산관리스쿨",
        kind="온라인 교육", access="웹(무료)", topics=["자산배분", "리밸런싱", "절세 계좌"], use="장기 자산형성·분산 목적 단원 자료", license="기관 저작물", verified="domain"),
    "kcie_alt_school": dict(
        name="전국투자자교육협의회 대체투자·파생상품스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › 대체투자스쿨·파생상품스쿨",
        kind="온라인 교육", access="웹(무료)", topics=["원자재 ETF", "리츠 ETF", "레버리지·인버스"], use="원자재·리츠·파생형 단원 보조 자료", license="기관 저작물", verified="domain"),
    "kifin_leverage": dict(
        name="금융투자교육원 레버리지 ETP 사전교육", publisher="금융투자교육원(KIFIN)", url="https://www.kifin.or.kr", menu="사전교육 › 레버리지 ETP(ETF·ETN)",
        kind="의무 이러닝(일반 레버리지 ETP 과정 약 1시간, 수료 후 증권사에 이수번호 등록. 단일종목 레버리지·인버스는 2026-08-19부터 심화 과정을 더해 총 3시간, "
             "신규 투자자는 한국거래소 모의거래 5시간 별도, 2026-10 기준; 재이수 필요 여부는 기관 안내 확인)", access="웹(유료 소액: 일반 과정 4,000원, 심화 과정 비용은 기관 안내 확인)", topics=["레버리지·인버스"],
        use="레버리지·인버스 유형으로 넘어가기 전 필수 관문. 로드맵 '심화·리스크' 단계와 유형 카드에 안내", license="기관 저작물. 수료 사실만 연동(콘텐츠 복제 불가)",
        verified="domain"),
    "krx_etf_info": dict(
        name="한국거래소 ETF 정보(투자설명서·PDF·기초지수)", publisher="한국거래소(KRX)", url="https://www.krx.co.kr", menu="시장정보 › ETF/ETN",
        kind="공식 상품 정보·용어집·리포트", access="웹(무료)", topics=["ETF 구조", "추적오차", "유동성", "비용", "레버리지·인버스", "액티브 ETF"],
        use="단원 예시(실제 기초지수·PDF 구성 종목)와 용어 정의의 1차 출처", license="공공저작물 성격이나 이용 조건은 사이트 고지 확인", verified="domain"),
    "krx_index": dict(
        name="한국거래소 지수 정보", publisher="한국거래소(KRX)", url="https://www.krx.co.kr", menu="시장정보 › 지수",
        kind="지수 산출 방법론·구성 종목", access="웹(무료)", topics=["지수"], use="지수 단원의 산출 방식·정기변경 예시", license="사이트 고지 확인", verified="domain"),
    "krx_data": dict(
        name="KRX 정보데이터시스템 ETF 전종목 기본정보", publisher="한국거래소(KRX)", url="https://data.krx.co.kr", menu="기본 통계 › 증권상품 › ETF › 전종목 기본정보",
        kind="데이터(화면에서 직접 내려받는 파일. CSV는 UTF-8·cp949 모두 읽고, Excel은 openpyxl(.xlsx)·xlrd(.xls)가 설치된 경우에만 읽음)",
        access="웹(무료, 회원 로그인). 화면용 JSON 엔드포인트의 프로그램 호출(크롤링)은 이용약관·서버 부하 문제로 쓰지 않고, "
               "이용자가 내려받은 파일을 `sources sync --krx-csv 파일 [--krx-csv-date YYYYMMDD]`로 정규화한다",
        topics=["유동성", "비용"], use="ETF 유형 연결 단계의 메타데이터: 종목명·운용사·기초지수·총보수·과세유형·복제방법·기초시장·기초자산 분류 → 유형 분류·유형 통계",
        license="개인 학습·연구 범위 이용, 출처 표기. 재배포·상업적 이용 금지(이 프로젝트는 비상업 수업용. 상업 서비스는 KRX와 별도 데이터 이용 계약 필요)",
        verified="domain"),
    "krx_openapi": dict(
        name="KRX Open API(ETF 일별매매정보)", publisher="한국거래소(KRX)", url="https://openapi.krx.co.kr", menu="Open API › 인증키 발급 › 서비스별 이용 신청 › ETP",
        kind="REST API(인증키 헤더 AUTH_KEY, JSON)", access="회원 가입 후 인증키 발급과 서비스별 이용 신청(무료). 환경변수 KRX_OPEN_API_KEY",
        topics=["ETF 구조", "유동성"],
        use="공식 자동 수집 경로. sync가 받은 krx_etf_daily.csv의 종가·NAV·거래량을 단축코드로 결합해 유형 카드에 괴리율 절댓값 중앙값·거래량 중앙값을 "
            "시세 기준일과 함께 표시(기초지수명·종가는 파일에 저장만 함)",
        license="비상업적 이용, 제3자 재배포 금지, 결과물에 '한국거래소' 출처 표기. 인증키별 호출 한도는 KRX 이용 조건에서 확인(코드는 실행당 호출 상한과 "
                "호출 간격만 지킴: 기본 30회·1초). 상업 서비스는 KRX와 별도 데이터 이용 계약 필요",
        verified="domain(검색: 인증키·이용 신청 절차 확인, 엔드포인트 경로는 활용 가이드 확인 필요)"),
    "datagokr_etf": dict(
        name="공공데이터포털 금융위원회_증권상품시세정보(ETF)", publisher="금융위원회 / 공공데이터포털", url="https://www.data.go.kr/data/15094806/openapi.do",
        menu="오픈 API › 증권상품시세정보 › getETFPriceInfo", kind="REST API(JSON·XML)", access="API 키(serviceKey) 발급 후 무료",
        topics=["유동성", "ETF 구조"],
        use="종가·NAV·거래량 → 유형 카드의 괴리율·거래량 중앙값(KRX 일별 시세보다 기준일이 최근일 때 이 파일을 씀). sync는 totalCount까지 "
            "페이지를 넘겨 받고(최대 10쪽) 페이지 상한·빈 쪽으로 일부만 받으면 partial, 호출 오류는 fail(받은 쪽은 버리고 기존 파일 유지)로 기록",
        license="공공데이터 이용허락(포털 고지의 이용허락 범위 확인)", verified="page(검색 결과: 공통 요청변수·무료·JSON/XML 확인)"),
    "datagokr_listed": dict(
        name="공공데이터포털 금융위원회_KRX상장종목정보", publisher="금융위원회 / 공공데이터포털", url="https://www.data.go.kr/data/15094775/openapi.do",
        menu="오픈 API › KRX상장종목정보 › getItemInfo", kind="REST API(JSON)", access="API 키 발급 후 무료(증권상품시세정보와 같은 serviceKey)", topics=["ETF 구조"],
        use="sync 때 선택적으로 전종목 기본정보의 단축코드·ISIN을 교차 확인(키가 있을 때만, --no-cross-check로 끔). 결과는 provenance에 기록만 함. "
            "엔드포인트 경로는 활용 가이드 기준이며 키 발급 후 확인, ETF 포함 여부 미확인",
        license="공공데이터 이용허락(포털 고지의 이용허락 범위 확인)", verified="page(검색 결과: 엔드포인트·요청변수·제공 항목)"),
    "am_guidebooks": dict(
        name="자산운용사 ETF 가이드북·상품 설명 자료", publisher="삼성자산운용(KODEX)·미래에셋자산운용(TIGER)·KB자산운용(RISE, 구 KBSTAR) 등",
        url="https://www.riseetf.co.kr", menu="각 운용사 홈페이지 › 투자 가이드/자료실", kind="PDF 가이드북·상품 설명서·용어집",
        access="웹(무료 내려받기)", topics=["비용", "분배금", "환헤지", "해외 ETF", "커버드콜 ETF", "테마 ETF", "레버리지·인버스"],
        use="시각 자료와 용어 정리가 잘 되어 있어 콘텐츠 텍스트 특징으로 확장할 후보(현재 TF-IDF는 주제 이름과 단원 제목만 씀)", license="운용사 저작물. 인용·요약만, 원문 재배포 금지",
        verified="domain(RISE 사이트 확인, 가이드북 PDF 경로는 미확인)"),
    "creators_research": dict(
        name="증권사 리서치·금융 크리에이터 아카이브", publisher="증권사 리서치센터, 유튜브 채널", url="", menu="",
        kind="텍스트·영상(구조화 필요)", access="공개 자료, 채널별 이용 조건 상이", topics=["테마 ETF", "섹터 ETF"],
        use="초보자 Q&A 후보와 추천 알고리즘의 텍스트 특징 후보. 저작권·정확성 검수 후에만 사용", license="채널별 상이. 자동 수집 전 허가 확인",
        verified="n/a"),
}


def source_info(key: str) -> dict:
    s = dict(SOURCES.get(key, dict(name=key, publisher="", url="", menu="", kind="", access="", topics=[], use="", license="", verified="")))
    s["key"] = key
    return s


def sources_for_items(keys) -> list:
    return [source_info(k) for k in dict.fromkeys(keys)]
