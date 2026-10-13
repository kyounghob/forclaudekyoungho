"""etfrec — ETF 교육 콘텐츠 개인화·세그먼트 추천 시스템.

패키지 구성
    config      전역 상수(평가 K, 시드, 세그먼트 변수, 행동 점수)
    catalog     학습 단원 카탈로그(주제 20 × 수준 3)와 콘텐츠 특징
    synth       규칙을 공개한 모의 학습 로그 생성기
    data        학습자 프로필·학습 로그 데이터셋과 CSV 입출력
    features    주간 스냅샷 특징 저장소(반응 행렬, 수준, 세그먼트 코드)
    signals     인기·규칙·콘텐츠·CF·MF·MLP 신호 계산
    neural      행렬분해·MLP 학습(torch 선택 의존)
    zoo         신호 조합 설정(알고리즘 풀)과 점수 계산
    evaluation  후보 생성, Top-K 선택, 지표, 배치 평가
    router      계층 수축 세그먼트 라우터
    pipeline    학습 → 검증 → 선택 → 테스트 → 번들 저장
    service     추천 서비스(설명·가드레일·what-if·시뮬레이션)
    nlparse     한국어 자연어 온보딩 파서
    api         FastAPI 애플리케이션(REST + 정적 UI)
    cli         명령줄 인터페이스
"""

__version__ = "1.0.0"
