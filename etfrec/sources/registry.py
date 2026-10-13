"""공개 교육 자료·데이터 출처 목록.

``verified``는 2026-10 기준 검색으로 확인한 범위를 뜻한다: "domain" = 도메인·메뉴 이름만 확인, "page" = 해당 페이지 확인.
세부 URL은 기관 개편으로 바뀔 수 있으므로 화면에서는 기관 루트 링크와 메뉴 이름을 함께 보여 준다.
"""
from __future__ import annotations

SOURCES = {
    "kcie_etf_school": dict(
        name="전국투자자교육협의회 ETF스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › ETF스쿨",
        kind="온라인 교육(영상·가이드북)", access="웹(무료, 최초 1회 정보 등록)", topics=["ETF 구조", "지수", "비용", "분배금", "해외 ETF", "채권 ETF", "커버드콜 ETF"],
        use="기초 단원의 학습 자료·용어 정의, 퀴즈 문항 출처", license="기관 저작물. 교육 목적 인용 시 출처 표기, 재배포는 기관 정책 확인", verified="domain"),
    "kcie_pension_school": dict(
        name="전국투자자교육협의회 연금스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › 연금스쿨",
        kind="온라인 교육", access="웹(무료)", topics=["연금계좌 ETF", "자산배분"], use="연금·노후 목적 로드맵의 핵심 단원 자료",
        license="기관 저작물", verified="domain"),
    "kcie_life_school": dict(
        name="전국투자자교육협의회 생애자산관리스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › 생애자산관리스쿨",
        kind="온라인 교육", access="웹(무료)", topics=["자산배분", "리밸런싱"], use="장기 자산형성·분산 목적 단원 자료", license="기관 저작물", verified="domain"),
    "kcie_alt_school": dict(
        name="전국투자자교육협의회 대체투자·파생상품스쿨", publisher="전국투자자교육협의회(KCIE)", url="https://www.kcie.or.kr", menu="온라인 스쿨 › 대체투자스쿨·파생상품스쿨",
        kind="온라인 교육", access="웹(무료)", topics=["원자재 ETF", "리츠 ETF", "레버리지·인버스"], use="원자재·리츠·파생형 단원 보조 자료", license="기관 저작물", verified="domain"),
    "kifin_leverage": dict(
        name="금융투자교육원 레버리지 ETP 사전교육", publisher="금융투자교육원(KIFIN)", url="https://www.kifin.or.kr", menu="사전교육 › 레버리지 ETP(ETF·ETN)",
        kind="의무 이러닝(약 1시간, 수료 후 증권사에 이수번호 등록, 평생 1회)", access="웹(유료 소액, 2025년 기준 4,000원 안내)", topics=["레버리지·인버스"],
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
        kind="데이터(CSV·Excel 내려받기, 비공식 JSON 엔드포인트)", access="웹(무료, 로그인 불필요). 자동 수집은 비공식 엔드포인트라 변경될 수 있음",
        topics=["유동성", "비용"], use="ETF 유형 연결 단계의 메타데이터: 종목명·운용사·기초지수·총보수·과세유형·복제방법·기초시장·기초자산 분류",
        license="개인 학습·연구 범위 이용. 대량 수집 시 이용 약관 확인", verified="domain"),
    "datagokr_etf": dict(
        name="공공데이터포털 금융위원회_증권상품시세정보(ETF)", publisher="금융위원회 / 공공데이터포털", url="https://www.data.go.kr/data/15094806/openapi.do",
        menu="오픈 API › 증권상품시세정보 › getETFPriceInfo", kind="REST API(JSON·XML)", access="API 키(serviceKey) 발급 후 무료",
        topics=["유동성", "ETF 구조"], use="종가·NAV·거래량·시가총액·기초지수 종가 → 괴리율·거래량 예시와 유형 통계 보강",
        license="공공데이터 이용허락(사이트 고지)", verified="page(검색 결과: 공통 요청변수·무료·JSON/XML 확인)"),
    "datagokr_listed": dict(
        name="공공데이터포털 금융위원회_KRX상장종목정보", publisher="금융위원회 / 공공데이터포털", url="https://www.data.go.kr/data/15094775/openapi.do",
        menu="오픈 API › KRX상장종목정보", kind="REST API", access="API 키 발급 후 무료", topics=["ETF 구조"],
        use="단축코드·ISIN·시장구분·종목명 조회(종목 식별자 정합성)", license="공공데이터 이용허락", verified="page(검색 결과)"),
    "am_guidebooks": dict(
        name="자산운용사 ETF 가이드북·상품 설명 자료", publisher="삼성자산운용(KODEX)·미래에셋자산운용(TIGER)·KB자산운용(RISE, 구 KBSTAR) 등",
        url="https://www.riseetf.co.kr", menu="각 운용사 홈페이지 › 투자 가이드/자료실", kind="PDF 가이드북·상품 설명서·용어집",
        access="웹(무료 내려받기)", topics=["비용", "분배금", "환헤지", "해외 ETF", "커버드콜 ETF", "테마 ETF", "레버리지·인버스"],
        use="시각 자료와 용어 정리가 잘 되어 있어 콘텐츠 텍스트 데이터베이스(TF-IDF 특징)로 확장", license="운용사 저작물. 인용·요약만, 원문 재배포 금지",
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
