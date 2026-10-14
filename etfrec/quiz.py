"""진단 퀴즈: 20문항으로 수준(1~3)과 이미 아는 단원을 추정한다.

맞힌 문항의 단원은 '진단 통과' 이벤트(quiz_pass)가 되어 추천 후보에서 빠지고, 틀린 문항은 기록하지 않는다
(진단은 배치이지 실패 기록이 아니다). 문항은 카탈로그 단원 하나에 대응하며, 한 단원에 문항이 둘 이상이면 답한 문항을 모두
맞혀야 그 단원을 통과로 기록한다(이벤트는 단원마다 한 번). ``marks_pass=False`` 문항(레버리지 거래 요건 같은 규제 상식)은
단원 내용 전체를 검사하지 않으므로 수준 판정에만 쓰고 단원을 통과 처리하지 않는다. 정답 위치는 보기 4개에 고르게 나눴다.
"""
from __future__ import annotations

from .catalog import Catalog

QUESTIONS = [
    dict(id="q01", topic="ETF 구조", level=1, text="ETF(상장지수펀드)에 대한 설명으로 맞는 것은?",
         options=["거래소에 상장되어 주식처럼 장중에 사고판다", "은행 예금처럼 원금이 보장된다", "하루 한 번 기준가로만 거래된다", "특정 종목 하나에만 투자한다"], answer=0,
         explain="ETF는 지수를 따르는 펀드를 거래소에 상장해 주식처럼 매매한다."),
    dict(id="q02", topic="비용", level=1, text="총보수(총보수율) 연 0.5%는 무엇을 뜻하나?",
         options=["살 때 한 번 내는 수수료", "분배금에서만 떼는 세금", "팔 때만 내는 비용", "매일 순자산에서 조금씩 차감되어 1년에 약 0.5%가 빠진다"], answer=3,
         explain="총보수는 순자산에서 매일 나눠 차감되며 가격에 이미 반영된다."),
    dict(id="q03", topic="ETF 구조", level=2, text="어떤 ETF의 괴리율이 +3%라면?",
         options=["NAV가 시장가격보다 3% 높다", "분배금이 3% 나온다", "시장가격이 NAV보다 3% 높아 비싸게 사는 셈이다", "총보수가 3%다"], answer=2,
         explain="괴리율 = (시장가격 − NAV) / NAV. 양수면 순자산가치보다 비싸게 거래된다."),
    dict(id="q04", topic="환헤지", level=1, text="해외 ETF 이름 끝의 (H)는?",
         options=["환헤지형: 환율 변동의 영향을 줄인 상품", "고배당(High dividend)", "레버리지 2배", "홍콩 상장"], answer=0,
         explain="(H)는 환헤지(hedged)를 뜻한다. 환노출형은 환율 변동이 수익률에 더해진다."),
    dict(id="q05", topic="레버리지·인버스", level=2, text="지수가 하루 10% 내린 뒤 다음 날 10% 오르면, 2배 레버리지 ETF는 대략?",
         options=["원금 회복", "약 −1%", "약 −4%", "약 +4%"], answer=2,
         explain="지수는 100→90→99(−1%), 2배 레버리지는 100→80→96(−4%). 일일 복리의 음의 효과다."),
    dict(id="q06", topic="분배금", level=1, text="ETF 분배금은 주로 어디서 나오나?",
         options=["운용사가 보조금으로 준다", "총보수에서 돌려준다", "거래소가 지급한다", "보유 주식의 배당·채권 이자 등을 모아 지급한다"], answer=3,
         explain="분배금은 ETF가 보유한 자산에서 나온 배당·이자 등을 투자자에게 나눠 주는 것이다."),
    dict(id="q07", topic="지수", level=1, text="코스피200 ETF의 수익률은 무엇을 따라가도록 설계되나?",
         options=["운용역의 판단", "코스피200 지수", "삼성전자 주가", "원·달러 환율"], answer=1,
         explain="패시브 ETF는 정해진 기초지수를 그대로 따르도록 운용한다."),
    dict(id="q08", topic="연금계좌 ETF", level=2, text="연금저축·IRP 계좌에서 살 수 없는 ETF는?",
         options=["국내 상장 미국 S&P500 ETF", "국내 상장 채권 ETF", "해외 거래소에 상장된 ETF와 레버리지·인버스 ETF", "국내 상장 금 현물 ETF"], answer=2,
         explain="연금계좌는 국내 상장 ETF만 가능하며 레버리지·인버스는 편입이 제한된다."),
    dict(id="q09", topic="추적오차", level=1, text="추적오차란?",
         options=["ETF 가격과 NAV의 차이", "분배금 지급 지연", "거래량 부족", "ETF 수익률이 기초지수 수익률과 얼마나 다르게 움직였는지의 변동성"], answer=3,
         explain="추적오차는 ETF와 지수 수익률 차이의 변동성이고, 괴리율은 가격과 NAV의 차이다."),
    dict(id="q10", topic="유동성", level=2, text="호가 스프레드가 넓은 ETF를 거래하면?",
         options=["사고팔 때 숨은 비용이 커진다", "총보수가 올라간다", "분배금이 줄어든다", "아무 영향이 없다"], answer=0,
         explain="매수·매도 호가 차이는 바로 거래 비용이 된다. 거래량이 적은 ETF일수록 넓다."),
    dict(id="q11", topic="채권 ETF", level=2, text="시장 금리가 오르면 채권 ETF 가격은 보통?",
         options=["오른다", "내린다", "변화 없다", "분배금만 줄어든다"], answer=1,
         explain="금리와 채권 가격은 반대로 움직이며, 듀레이션이 길수록 더 크게 움직인다."),
    dict(id="q12", topic="커버드콜 ETF", level=1, text="커버드콜 ETF의 특징으로 맞는 것은?",
         options=["지수의 2배를 따른다", "채권에만 투자한다", "분배금이 없다", "콜옵션을 팔아 받은 프리미엄을 분배금으로 주고, 그 대신 상승이 제한된다"], answer=3,
         explain="커버드콜은 기초자산을 보유하며 콜옵션을 매도한다. 분배 재원은 옵션 프리미엄이고 상승장에선 덜 오른다."),
    dict(id="q13", topic="해외 ETF", level=3, text="국내 상장 해외주식형 ETF의 매매차익 과세는?",
         options=["배당소득세 15.4%(보유기간 과세)", "비과세", "양도소득세 22%", "증권거래세 0.18%"], answer=0,
         explain="국내 상장 해외주식형·채권·원자재 ETF의 매매차익은 배당소득으로 15.4% 과세된다(실제 차익과 과표기준가 상승분 중 작은 금액 기준). 해외 거래소에 직접 상장된 ETF는 양도소득세 22%(연 250만원 기본공제, 같은 해 해외주식 손익 통산, 분리과세)다."),
    dict(id="q14", topic="원자재 ETF", level=3, text="원유 선물 ETF에서 롤오버 비용이 커지는 시장 상태는?",
         options=["백워데이션", "콘탱고", "횡보", "환율 상승"], answer=1,
         explain="콘탱고(원월물 가격 > 근월물)에서는 만기 교체 때마다 비싸게 사고 싸게 팔아 비용이 생긴다."),
    dict(id="q15", topic="자산배분", level=1, text="분산투자의 효과가 가장 큰 자산 조합은?",
         options=["같이 오르내리는 자산끼리", "같은 업종 주식끼리", "서로 다르게 움직이는(상관관계가 낮은) 자산끼리", "같은 지수의 ETF 두 개"], answer=2,
         explain="상관관계가 낮은 자산을 섞어야 전체 변동성이 줄어든다."),
    dict(id="q16", topic="연금계좌 ETF", level=3, text="연금저축계좌 세제 혜택을 바르게 설명한 것은?",
         options=["납입액은 공제 없고 수령 시 비과세", "납입액 일정 한도까지 세액공제, 운용 수익은 과세이연, 연금 수령 시 연금소득세", "매매차익 비과세·분배금 비과세", "해외 상장 ETF도 과세이연"], answer=1,
         explain="연금저축·IRP는 납입액 세액공제와 과세이연이 핵심이며, 수령 단계에서 연금소득세를 낸다."),
    dict(id="q17", topic="절세 계좌", level=1, text="ISA(개인종합자산관리계좌)의 세제 혜택으로 맞는 것은?",
         options=["순이익 200만원(서민형 400만원)까지 비과세, 초과분은 9.9% 분리과세", "모든 수익이 전액 비과세다", "매매차익에 22% 양도소득세가 붙는다", "분배금만 비과세다"], answer=0,
         explain="ISA는 계좌 안 손익을 통산해 순이익 200만원(서민형·농어민형 400만원)까지 비과세하고, 초과분은 9.9%로 분리과세한다. 의무가입 3년, 연 2,000만원 납입."),
    dict(id="q18", topic="해외 ETF", level=3, text="국내 상장 해외주식형 ETF를 팔 때 배당소득세(15.4%)가 매겨지는 금액은?",
         options=["항상 실제 매매차익 전체", "과표기준가 상승분 전체", "실제 매매차익과 과표기준가 상승분 중 작은 금액", "분배금에만 과세된다"], answer=2,
         explain="보유기간과세: 실제 매매차익과 보유 기간의 과표기준가 상승분 중 작은 금액에 15.4%가 붙는다. 과표기준가는 과세 대상 손익만 반영하므로, 시장가격이 괴리율 확대 등으로 더 올랐다면 과세는 과표기준가 상승분까지이고, 과표기준가가 내렸다면 이익이 있어도 세금이 없다. 반대로 계좌 밖에서는 손실을 다른 이익과 통산하지 못한다."),
    dict(id="q19", topic="연금계좌 ETF", level=2, text="IRP 계좌의 투자 한도 규칙으로 맞는 것은?",
         options=["주식형 ETF를 100%까지 담을 수 있다", "채권형 ETF만 담을 수 있다", "해외 상장 ETF도 담을 수 있다", "위험자산은 적립금의 70%까지, 30% 이상은 예금·안전자산이어야 한다"], answer=3,
         explain="IRP(퇴직연금)는 위험자산 총투자한도 70% 규제가 있고, 연금저축펀드에는 이 한도가 없다. 두 계좌 모두 해외 상장 ETF는 불가."),
    dict(id="q20", topic="레버리지·인버스", level=3, text="국내 개인투자자가 레버리지·인버스 ETP를 처음 매수하려면?",
         options=["아무 조건 없이 바로 살 수 있다", "사전교육 이수·증권사 등록과 기본예탁금(일반 1,000만원, 단일종목형은 현금 3,000만원)이 필요하다", "연금계좌를 먼저 개설해야 한다", "총보수만 확인하면 된다"], answer=1,
         marks_pass=False,
         explain="사전교육(약 1시간)과 기본예탁금 1,000만원이 모두 필요하다. 단일종목 레버리지·인버스는 2026년 7월 31일부터 현금 3,000만원(추가 매수 포함, 대용증권 불인정), 사전교육 총 3시간, 8월 19일부터 신규 투자자 모의거래 5시간이 더 필요하다. 요건을 못 채우면 매수 주문이 들어가지 않는다(2026-10-13 기준). 이 문항은 규제 상식이라 수준 판정에만 쓰고 단원을 통과 처리하지 않는다."),
]


def public_questions() -> list:
    """정답·해설을 뺀 문항 목록(화면용). diagnostic_only = 수준 판정에만 쓰는 문항."""
    return [dict(id=q["id"], topic=q["topic"], level=q["level"], text=q["text"], options=q["options"],
                 diagnostic_only=not q.get("marks_pass", True)) for q in QUESTIONS]


def score_quiz(answers: dict, catalog: Catalog) -> dict:
    """answers: {문항 id: 고른 보기 번호}. → 수준, 맞힌 단원, 진단 이벤트, 문항별 결과.

    답한 문항만 채점한다(수준별 정답률의 분모 = 그 수준에서 답한 문항 수). 수준 2: 수준1 정답률 60% 이상이고 수준2 정답률 50% 이상.
    수준 3: 수준 2 조건에 더해 수준2 정답률 75% 이상, 서로 다른 주제의 수준3 문항 2개 이상 정답, 수준3 정답률 60% 이상.
    """
    by_level = {1: [0, 0], 2: [0, 0], 3: [0, 0]}
    results, unit_ok, l3_topics = [], {}, set()
    for q in QUESTIONS:
        chosen = answers.get(q["id"])
        answered = chosen is not None
        correct = answered and int(chosen) == q["answer"]
        marks = q.get("marks_pass", True)
        if answered:
            by_level[q["level"]][1] += 1
            by_level[q["level"]][0] += int(correct)
        if correct and q["level"] == 3:
            l3_topics.add(q["topic"])
        item = catalog.unit(q["topic"], q["level"])
        results.append(dict(id=q["id"], topic=q["topic"], level=q["level"], answered=answered, correct=bool(correct),
                            correct_option=q["options"][q["answer"]], explain=q["explain"], item=item, marks_pass=marks))
        if answered and marks and item is not None:
            unit_ok[int(item)] = unit_ok.get(int(item), True) and bool(correct)
    events, mastered = [], []
    for item, ok in unit_ok.items():          # 문항 순서대로, 단원마다 한 번
        if ok:
            events.append(dict(item=item, week=0, complete=True, quiz=True, quiz_pass=True, save=False, drop=False, replay=False, source="diagnosis"))
            mastered.append(catalog.item_info(item))
    rate = {lv: (c / n if n else 0.0) for lv, (c, n) in by_level.items()}
    level = 1
    if rate[1] >= 0.6 and rate[2] >= 0.5:
        level = 2
    if level == 2 and rate[2] >= 0.75 and len(l3_topics) >= 2 and rate[3] >= 0.6:
        level = 3
    correct_n = sum(r["correct"] for r in results)
    answered_n = sum(r["answered"] for r in results)
    return dict(level=level, correct=correct_n, answered=answered_n, total=len(QUESTIONS),
                by_level={k: dict(correct=v[0], total=v[1]) for k, v in by_level.items()},
                results=results, events=events, mastered=mastered,
                summary=(f"{correct_n}/{answered_n} 정답(전체 {len(QUESTIONS)}문항) · 진단 수준 {level} (수준1 {by_level[1][0]}/{by_level[1][1]}, "
                         f"수준2 {by_level[2][0]}/{by_level[2][1]}, 수준3 {by_level[3][0]}/{by_level[3][1]}) · 진단 통과 단원 {len(mastered)}개"))
