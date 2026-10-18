"""공개 데이터·교육 자료 연결.

- registry: 전국투자자교육협의회(kcie.or.kr), 금융투자교육원(kifin.or.kr), 한국거래소, 공공데이터포털, 운용사 자료의 목록과 접근 방식
- krx: KRX 정보데이터시스템에서 이용자가 직접 내려받은 ETF 전종목 기본정보(CSV: UTF-8·cp949, Excel: openpyxl·xlrd 설치 시)의 정규화와
  유형 분류, KRX Open API(인증키) ETF 일별매매정보 클라이언트. 화면용 비공식 엔드포인트는 호출하지 않는다
- datagokr: 공공데이터포털 금융위원회 증권상품시세정보(ETF, totalCount까지 페이지 넘김)·KRX상장종목정보(코드 교차 확인용) 클라이언트
- net: 정직한 User-Agent, 클라이언트별 실행당 호출 상한과 호출 간격, 루트 주소 HEAD 점검
- sync: 스냅샷 저장(임시 파일 → 교체), 파일별 기준일·저장 시각·해시 기록, 시세 스냅샷 결합(괴리율·거래량 유형 통계), 오프라인 샘플 대체,
  화면·API용 출처 정보(public_info: 로컬 경로·오류 원문 제외)

키가 없거나 수집하지 못한 환경에서는 샘플 스냅샷으로 동작하며 화면에 '샘플'임을 표시한다. 이 프로젝트는 비상업 수업 프로젝트이며,
상업 서비스로 쓰려면 공공데이터포털의 이용허락 범위를 확인한 공공데이터 경로나 KRX와의 별도 데이터 이용 계약이 필요하다.
"""
from .registry import SOURCES, source_info
from .sync import default_dir, load_etf_universe, public_info, sync_all, type_stats

__all__ = ["SOURCES", "source_info", "default_dir", "load_etf_universe", "public_info", "sync_all", "type_stats"]
