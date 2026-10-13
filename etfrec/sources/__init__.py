"""공개 데이터·교육 자료 연결.

- registry: 전국투자자교육협의회(kcie.or.kr), 금융투자교육원(kifin.or.kr), 한국거래소, 공공데이터포털, 운용사 자료의 목록과 접근 방식
- krx: KRX 정보데이터시스템 ETF 전종목 기본정보 내려받기와 유형 분류
- datagokr: 공공데이터포털 금융위원회 증권상품시세정보(ETF) API 클라이언트
- sync: 스냅샷 저장·출처 기록·오프라인 샘플 대체

이 환경(또는 사내망)에서 해당 호스트가 막혀 있으면 샘플 스냅샷으로 동작하며, 화면과 보고서에 '샘플'임을 표시한다.
"""
from .registry import SOURCES, source_info
from .sync import load_etf_universe, sync_all, type_stats

__all__ = ["SOURCES", "source_info", "load_etf_universe", "sync_all", "type_stats"]
