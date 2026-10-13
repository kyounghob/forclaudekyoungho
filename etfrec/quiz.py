"""진단 퀴즈: 16문항으로 수준(1~3)과 이미 아는 단원을 추정한다.

맞힌 문항의 단원은 '진단 통과' 이벤트(quiz_pass)가 되어 추천 후보에서 빠지고, 틀린 문항은 기록하지 않는다
(진단은 배치이지 실패 기록이 아니다). 문항은 카탈로그 단원 하나에 대응한다.
"""
from __future__ import annotations

from .catalog import Catalog

QUESTIONS = [
    dict(id="q01", topic="ETF 구조", level=1, text="ETF(상장지수펀드)에 대한 설명으로 맞는 것은?",
         options=["은행 예금처럼 원금이 보장된다", "거래소에 상장되어 주식처럼 장중에 사고판다", "하루 한 번 기준가로만 거래된다", "특정 종목 하나에만 투자한다"], answer=1,
         explain="ETF는 지수를 따르는 펀드를 거래소에 상장해 주식처럼 매매한다."),
    dict(id="q02", topic="비용", level=1, text="총보수(총보수율) 연 0.5%는 무엇을 뜻하나?",
         options=["살 때 한 번 내는 수수료", "매일 순자산에서 조금씩 차감되어 1년에 약 0.5%가 빠진다", "분배금에서만 떼는 세금", "팔 때만 내는 비용"], answer=1,
         explain="총보수는 순자산에서 매일 나눠 차감되며 가격에 이미 반영된다."),
    dict(id="q03", topic="ETF 구조", level=2, text="어떤 ETF의 괴리율이 +3%라면?",
         options=["NAV가 시장가격보다 3% 높다", "시장가격이 NAV보다 3% 높아 비싸게 사는 셈이다", "분배금이 3% 나온다", "총보수가 3%다"], answer=1,
         explain="괴리율 = (시장가격 − NAV) / NAV. 양수면 순자산가치보다 비싸게 거래된다."),
    dict(id="q04", topic="환헤지", level=1, text="해외 ETF 이름 끝의 (H)는?",
         options=["고배당(High dividend)", "환헤지형: 환율 변동의 영향을 줄인 상품", "레버리지 2배", "홍콩 상장"], answer=1,
         explain="(H)는 환헤지(hedged)를 뜻한다. 환노출형은 환율 변동이 수익률에 더해진다."),
    dict(id="q05", topic="레버리지·인버스", level=2, text="지수가 하루 10% 내린 뒤 다음 날 10% 오르면, 2배 레버리지 ETF는 대략?",
         options=["원금 회복", "약 −1%", "약 −4%", "약 +4%"], answer=2,
         explain="지수는 100→90→99(−1%), 2배 레버리지는 100→80→96(−4%). 일일 복리의 음의 효과다."),
    dict(id="q06", topic="분배금", level=1, text="ETF 분배금은 주로 어디서 나오나?",
         options=["운용사가 보조금으로 준다", "보유 주식의 배당·채권 이자 등을 모아 지급한다", "총보수에서 돌려준다", "거래소가 지급한다"], answer=1,
         explain="분배금은 ETF가 보유한 자산에서 나온 배당·이자 등을 투자자에게 나눠 주는 것이다."),
    dict(id="q07", topic="지수", level=1, text="코스피200 ETF의 수익률은 무엇을 따라가도록 설계되나?",
         options=["운용역의 판단", "코스피200 지수", "삼성전자 주가", "원·달러 환율"], answer=1,
         explain="패시브 ETF는 정해진 기초지수를 그대로 따르도록 운용한다."),
    dict(id="q08", topic="연금계좌 ETF", level=2, text="연금저축·IRP 계좌에서 살 수 없는 ETF는?",
         options=["국내 상장 미국 S&P500 ETF", "국내 상장 채권 ETF", "해외 거래소에 상장된 ETF와 레버리지·인버스 ETF", "국내 상장 금 현물 ETF"], answer=2,
         explain="연금계좌는 국내 상장 ETF만 가능하며 레버리지·인버스는 편입이 제한된다."),
    dict(id="q09", topic="추적오차", level=1, text="추적오차란?",
         options=["ETF 가격과 NAV의 차이", "ETF 수익률이 기초지수 수익률과 얼마나 다르게 움직였는지의 변동성", "분배금 지급 지연", "거래량 부족"], answer=1,
         explain="추적오차는 ETF와 지수 수익률 차이의 변동성이고, 괴리율은 가격과 NAV의 차이다."),
    dict(id="q10", topic="유동성", level=2, text="호가 스프레드가 넓은 ETF를 거래하면?",
         options=["총보수가 올라간다", "사고팔 때 숨은 비용이 커진다", "분배금이 줄어든다", "아무 영향이 없다"], answer=1,
         explain="매수·매도 호가 차이는 바로 거래 비용이 된다. 거래량이 적은 ETF일수록 넓다."),
    dict(id="q11", topic="채권 ETF", level=2, text="시장 금리가 오르면 채권 ETF 가격은 보통?",
         options=["오른다", "내린다", "변화 없다", "분배금만 줄어든다"], answer=1,
         explain="금리와 채권 가격은 반대로 움직이며, 듀레이션이 길수록 더 크게 움직인다."),
    dict(id="q12", topic="커버드콜 ETF", level=1, text="커버드콜 ETF의 특징으로 맞는 것은?",
         options=["콜옵션을 팔아 받은 프리미엄을 분배금으로 주고, 그 대신 상승이 제한된다", "지수의 2배를 따른다", "채권에만 투자한다", "분배금이 없다"], answer=0,
         explain="커버드콜은 기초자산을 보유하며 콜옵션을 매도한다. 분배 재원은 옵션 프리미엄이고 상승장에선 덜 오른다."),
    dict(id="q13", topic="해외 ETF", level=3, text="국내 상장 해외주식형 ETF의 매매차익 과세는?",
         options=["비과세", "배당소득세 15.4%(보유기간 과세)", "양도소득세 22%", "증권거래세 0.18%"], answer=1,
         explain="국내 상장 해외주식형·채권·원자재 ETF의 매매차익은 배당소득으로 15.4% 과세된다. 해외 상장 ETF는 양도소득세 22%다."),
    dict(id="q14", topic="원자재 ETF", level=3, text="원유 선물 ETF에서 롤오버 비용이 커지는 시장 상태는?",
         options=["백워데이션", "콘탱고", "횡보", "환율 상승"], answer=1,
         explain="콘탱고(원월물 가격 > 근월물)에서는 만기 교체 때마다 비싸게 사고 싸게 팔아 비용이 생긴다."),
    dict(id="q15", topic="자산배분", level=1, text="분산투자의 효과가 가장 큰 자산 조합은?",
         options=["같이 오르내리는 자산끼리", "서로 다르게 움직이는(상관관계가 낮은) 자산끼리", "같은 업종 주식끼리", "같은 지수의 ETF 두 개"], answer=1,
         explain="상관관계가 낮은 자산을 섞어야 전체 변동성이 줄어든다."),
    dict(id="q16", topic="연금계좌 ETF", level=3, text="연금저축계좌 세제 혜택을 바르게 설명한 것은?",
         options=["납입액은 공제 없고 수령 시 비과세", "납입액 일정 한도까지 세액공제, 운용 수익은 과세이연, 연금 수령 시 연금소득세", "매매차익 비과세·분배금 비과세", "해외 상장 ETF도 과세이연"], answer=1,
         explain="연금저축·IRP는 납입액 세액공제와 과세이연이 핵심이며, 수령 단계에서 연금소득세를 낸다."),
]


def public_questions() -> list:
    """정답·해설을 뺀 문항 목록(화면용)."""
    return [dict(id=q["id"], topic=q["topic"], level=q["level"], text=q["text"], options=q["options"]) for q in QUESTIONS]


def score_quiz(answers: dict, catalog: Catalog) -> dict:
    """answers: {문항 id: 고른 보기 번호}. → 수준, 맞힌 단원, 진단 이벤트, 문항별 결과."""
    by_level = {1: [0, 0], 2: [0, 0], 3: [0, 0]}
    results, events, mastered = [], [], []
    for q in QUESTIONS:
        chosen = answers.get(q["id"])
        answered = chosen is not None
        correct = answered and int(chosen) == q["answer"]
        by_level[q["level"]][1] += 1
        by_level[q["level"]][0] += int(correct)
        item = catalog.unit(q["topic"], q["level"])
        results.append(dict(id=q["id"], topic=q["topic"], level=q["level"], answered=answered, correct=bool(correct),
                            correct_option=q["options"][q["answer"]], explain=q["explain"], item=item))
        if correct and item is not None:
            events.append(dict(item=int(item), week=0, complete=True, quiz=True, quiz_pass=True, save=False, drop=False, replay=False, source="diagnosis"))
            mastered.append(catalog.item_info(item))
    l1, l2, l3 = (by_level[1][0] / max(by_level[1][1], 1), by_level[2][0] / max(by_level[2][1], 1), by_level[3][0])
    level = 1
    if l1 >= 0.6 and l2 >= 0.5:
        level = 2
    if level == 2 and l2 >= 0.75 and l3 >= 2:
        level = 3
    correct_n = sum(r["correct"] for r in results)
    return dict(level=level, correct=correct_n, total=len(QUESTIONS), by_level={k: dict(correct=v[0], total=v[1]) for k, v in by_level.items()},
                results=results, events=events, mastered=mastered,
                summary=f"{correct_n}/{len(QUESTIONS)} 정답 · 진단 수준 {level} (수준1 {by_level[1][0]}/{by_level[1][1]}, 수준2 {by_level[2][0]}/{by_level[2][1]}, 수준3 {by_level[3][0]}/{by_level[3][1]})")
