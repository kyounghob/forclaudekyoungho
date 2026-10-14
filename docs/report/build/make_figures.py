"""중간보고서 그림 생성 (matplotlib, 한글 폰트 WenQuanYi Zen Hei)."""
import json, os, sys
sys.path.insert(0, "/home/user/forclaudekyoungho")
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager
from PIL import Image

ROOT = "/home/user/forclaudekyoungho"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig")
os.makedirs(OUT, exist_ok=True)
font_manager.fontManager.addfont("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
plt.rcParams["font.family"] = "WenQuanYi Zen Hei"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 10
GREEN, GOLD, GREY, BLUE, RED = "#1f6f55", "#d99a1e", "#8a97b8", "#3b6fb6", "#b2362d"


def box(ax, x, y, w, h, text, fc="#dcefe6", ec=GREEN, fs=9, weight="normal"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.02", fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight=weight, wrap=True)


def arrow(ax, x1, y1, x2, y2, color="#5d665d"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, color=color, lw=1.1))


# ---------- 그림 1: 시스템 아키텍처 ----------
def fig_architecture():
    fig, ax = plt.subplots(figsize=(9.2, 5.6)); ax.set_xlim(0, 10); ax.set_ylim(0, 6.2); ax.axis("off")
    # 데이터 계층
    ax.text(0.15, 5.95, "① 데이터 계층", fontsize=10, weight="bold", color=GREEN)
    box(ax, 0.15, 4.75, 2.1, 1.0, "학습 로그·프로필\n(profiles / study_log /\n목적·기간·진단)", fc="#f4f5f2", ec="#8a97b8")
    box(ax, 2.45, 4.75, 2.1, 1.0, "콘텐츠 카탈로그 v2\n63단원·선수 관계 76\n개념·출처 태그", fc="#f4f5f2", ec="#8a97b8")
    box(ax, 4.75, 4.75, 2.4, 1.0, "공개 데이터 커넥터\nKRX 전종목 기본정보\n공공데이터포털 시세(NAV)", fc="#f4f5f2", ec="#8a97b8")
    box(ax, 7.35, 4.75, 2.5, 1.0, "교육 자료 출처 등록부\nKCIE 스쿨·KIFIN 사전교육\nKRX 정보·운용사 가이드북", fc="#f4f5f2", ec="#8a97b8")
    # 학습 계층
    ax.text(0.15, 4.35, "② 학습·선택 (오프라인, python -m etfrec train)", fontsize=10, weight="bold", color=GREEN)
    box(ax, 0.15, 3.05, 2.4, 1.1, "특징 저장소\n반응 행렬·추정 수준·선호\n세그먼트 코드·목적", fc="#dcefe6")
    box(ax, 2.75, 3.05, 2.6, 1.1, "신호 154개\n인기·세그먼트 인기·콘텐츠\nUCF·ICF·MF·MLP·규칙·목적·로드맵", fc="#dcefe6")
    box(ax, 5.55, 3.05, 2.2, 1.1, "설정 풀 2,631개\n혼합 비중·λ·세그먼트 변수\n검증 주차 NDCG@5", fc="#dcefe6")
    box(ax, 7.95, 3.05, 1.9, 1.1, "선택 잠금\n세그먼트 라우터\n테스트·QA 80건", fc="#dcefe6")
    # 로드맵 계층 (가로)
    ax.text(0.15, 2.65, "③ 교육 설계 모듈", fontsize=10, weight="bold", color=GOLD)
    box(ax, 0.15, 1.55, 2.4, 0.9, "진단 퀴즈 16문항\n→ 수준·진단 통과 단원", fc="#fff3d6", ec=GOLD)
    box(ax, 2.75, 1.55, 2.6, 0.9, "로드맵 엔진\n진단→기초→목적별→심화→유형", fc="#fff3d6", ec=GOLD)
    box(ax, 5.55, 1.55, 2.2, 0.9, "가드레일\n수준·통과 제외·선수 단원", fc="#fff3d6", ec=GOLD)
    box(ax, 7.95, 1.55, 1.9, 0.9, "ETF 유형 분류 10종\n세금·연금·규제", fc="#fff3d6", ec=GOLD)
    # 서빙 계층
    ax.text(0.15, 1.15, "④ 서빙 (python -m etfrec serve)", fontsize=10, weight="bold", color=BLUE)
    box(ax, 0.15, 0.1, 3.2, 0.9, "모델 번들 (bundle.pkl·manifest)\n요청 중 재학습 없음", fc="#e8eef8", ec=BLUE)
    box(ax, 3.55, 0.1, 3.0, 0.9, "REST API (FastAPI)\n/recommend /roadmap /types\n/quiz /sources /compare", fc="#e8eef8", ec=BLUE)
    box(ax, 6.75, 0.1, 3.1, 0.9, "학습 설계 스튜디오 (11단계 UI)\n자연어 초안·진단·로드맵·미리보기\n시뮬레이션·유형 연결·평가", fc="#e8eef8", ec=BLUE)
    # 화살표
    for x in (1.2, 3.5, 5.95, 8.6):
        arrow(ax, x, 4.75, x, 4.18)
    arrow(ax, 2.55, 3.6, 2.75, 3.6); arrow(ax, 5.35, 3.6, 5.55, 3.6); arrow(ax, 7.75, 3.6, 7.95, 3.6)
    arrow(ax, 1.35, 2.45, 1.35, 3.05, color=GOLD); arrow(ax, 4.05, 2.45, 4.05, 3.05, color=GOLD); arrow(ax, 6.65, 2.45, 6.65, 3.05, color=GOLD)
    arrow(ax, 8.9, 3.05, 8.9, 1.0, color=BLUE); arrow(ax, 1.75, 1.55, 1.75, 1.0, color=BLUE); arrow(ax, 5.05, 1.55, 5.05, 1.0, color=BLUE)
    arrow(ax, 3.35, 0.55, 3.55, 0.55, color=BLUE); arrow(ax, 6.55, 0.55, 6.75, 0.55, color=BLUE)
    fig.savefig(os.path.join(OUT, "fig1_architecture.png"), dpi=200, bbox_inches="tight"); plt.close(fig)


# ---------- 그림 2: 로드맵 단계 흐름 ----------
def fig_roadmap_flow():
    from etfrec.catalog import Catalog
    from etfrec.roadmap import build_roadmap
    cat = Catalog.default()
    passed = np.zeros(cat.n_items, bool)
    rm = build_roadmap(cat, "pension", 0, "long", 1, passed)
    fig, ax = plt.subplots(figsize=(10, 4.6)); ax.set_xlim(0, 10); ax.set_ylim(0, 4.6); ax.axis("off")
    cols = ["#eceeea", "#dcefe6", "#dcefe6", "#fff3d6", "#e8eef8"]
    edges = ["#8a97b8", GREEN, GREEN, GOLD, BLUE]
    x = 0.1
    for i, s in enumerate(rm["stages"]):
        w = 1.9
        ax.add_patch(FancyBboxPatch((x, 3.5), w, 0.8, boxstyle="round,pad=0.02", fc=cols[i], ec=edges[i], lw=1.4))
        ax.text(x + w / 2, 3.9, f"{i + 1}. {s['name']}", ha="center", va="center", fontsize=10.5, weight="bold")
        if s["key"] == "diagnosis":
            body = "16문항 진단 퀴즈\n또는 학습 기록으로\n수준 1~3 추정\n맞힌 단원 = 진단 통과"
        elif s["key"] == "connect":
            body = "\n".join(f"· {t['name']}" for t in s["types"]) + "\n(개념 통과 시 카드 열림)"
        else:
            body = "\n".join(f"· {u['title'][:14]}" for u in s["units"][:7]) + ("\n  …" if len(s["units"]) > 7 else "")
        ax.text(x + 0.08, 3.35, body, ha="left", va="top", fontsize=8.2, linespacing=1.35)
        if i < 4:
            arrow(ax, x + w + 0.02, 3.9, x + w + 0.13, 3.9)
        x += w + 0.14
    ax.text(0.1, 0.25, "예: 투자 목적 = 연금·노후 대비, 기간 5년 이상, 안정 성향, 수준 1 · 단원 21개 · 각 단원은 선수 단원을 통과해야 열린다(잠김 → 학습 가능 → 통과).",
            fontsize=8.5, color="#5d665d")
    fig.savefig(os.path.join(OUT, "fig2_roadmap_flow.png"), dpi=200, bbox_inches="tight"); plt.close(fig)


# ---------- 그림 3: 선수 관계 그래프 (연금 로드맵 21단원) ----------
def fig_prereq_graph():
    from etfrec.catalog import Catalog
    from etfrec.roadmap import build_roadmap
    cat = Catalog.default()
    rm = build_roadmap(cat, "pension", 0, "long", 1, np.zeros(cat.n_items, bool))
    units, stage_of = [], {}
    for s in rm["stages"]:
        for u in s["units"]:
            units.append(u["item"]); stage_of[u["item"]] = s["key"]
    color = {"core": GREEN, "goal": BLUE, "advanced": GOLD}
    fig, ax = plt.subplots(figsize=(12.5, 5.6)); ax.axis("off")
    # 배치: y = 수준, x = 단계 순서 안에서 균등
    pos = {}
    by_level = {1: [], 2: [], 3: []}
    for i in units:
        by_level[int(cat.item_level[i])].append(i)
    for lv, items in by_level.items():
        n = len(items)
        for k, i in enumerate(items):
            pos[i] = ((k + 0.5) / n * 10, lv)
    for i in units:
        for p in cat.prereqs.get(i, []):
            if p in pos:
                (x1, y1), (x2, y2) = pos[p], pos[i]
                ax.annotate("", xy=(x2, y2 - 0.12), xytext=(x1, y1 + 0.12), arrowprops=dict(arrowstyle="-|>", color="#9aa39a", lw=0.9, shrinkA=0, shrinkB=0))
    for lv, items in by_level.items():
        for k, i in enumerate(items):
            x, y = pos[i]
            ax.scatter([x], [y], s=520, c=color[stage_of[i]], zorder=3, edgecolors="white", linewidths=1.2)
            dy = 0.3 + 0.17 * (k % 3 if lv == 1 else k % 2)           # 라벨을 엇갈리게 배치해 겹침을 줄인다
            t = cat.item_title[i]
            ax.text(x, y - dy, t[:13] + ("…" if len(t) > 13 else ""), ha="center", va="top", fontsize=7.2, zorder=4)
            ax.text(x, y, str(i), ha="center", va="center", fontsize=7, color="white", weight="bold", zorder=4)
    ax.set_xlim(-0.2, 10.4); ax.set_ylim(0.1, 3.6)
    for lv, lab in ((1, "수준 1 · 기초"), (2, "수준 2 · 구조·계산"), (3, "수준 3 · 심화·위험")):
        ax.text(-0.15, lv + 0.3, lab, fontsize=8.5, color="#5d665d", ha="left")
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="o", color=c, ls="", ms=9, label=l) for l, c in (("필수 기초 개념", GREEN), ("목적별 핵심 개념(연금)", BLUE), ("심화·리스크", GOLD))],
              loc="upper right", fontsize=8.5, frameon=True, framealpha=0.9)
    ax.set_title("연금·노후 대비 로드맵의 단원 21개와 선수 관계(화살표: 선수 → 후속, 숫자 = 단원 번호)", fontsize=9.5, loc="left")
    fig.savefig(os.path.join(OUT, "fig3_prereq_graph.png"), dpi=200, bbox_inches="tight"); plt.close(fig)


# ---------- 그림 4·5·6·7: 평가 결과 ----------
KO = {"RULE": "규칙(검증 1위)", "Global": "전역 1위", "RouterNoGender": "라우터(성별 제외, 운영)", "RouterFull": "라우터(성별 포함)",
      "RouterNoGenderIncome": "라우터(성별·소득 제외)", "NoDemographics": "인구통계 미사용", "UCF": "사용자 CF", "RouterNoGender+prereq": "운영 라우터+선수 가드레일",
      "POP": "인기", "ICF": "아이템 CF", "CONTENT": "콘텐츠", "MLP": "MLP(9주차)", "MF_OBS": "관측 MF", "MF": "표본 MF", "Random": "무작위",
      "MF_BPR": "BPR 행렬분해(미관측 음성)", "MLP_BPR": "MLP 쌍별(관측 음성)", "MLP_BPRU": "MLP 쌍별(미관측 음성)",
      "MLP_NEXT": "MLP 목표 정렬(다음 주 통과)"}


def fig_results():
    res = pd.read_csv(os.path.join(ROOT, "artifacts/bundle_v2/test_results.csv"), encoding="utf-8-sig")
    res = res[res.method != "Global"].sort_values("ndcg")
    fig, ax = plt.subplots(figsize=(9.2, 6.0))
    colors = [GOLD if m == "RouterNoGender" else (RED if m == "RouterNoGender+prereq" else (BLUE if ("BPR" in m or "NEXT" in m) else GREEN)) for m in res.method]
    err = ((res.ci_high - res.ci_low) / 2).fillna(0).values
    ys = np.arange(len(res))
    ax.barh(ys + 0.2, res.ndcg, xerr=err, color=colors, ecolor="#5d665d", capsize=2, height=0.38, label="전체 사용자(정답 없는 사용자 = 0 포함, 노트북 규칙)")
    if "ndcg_active" in res.columns:
        ax.barh(ys - 0.2, res.ndcg_active, color=colors, alpha=0.45, height=0.38, label="활성 사용자만(정답 없는 사용자 제외, 비판 권고 기준)")
    ax.set_yticks(ys); ax.set_yticklabels([KO.get(m, m) for m in res.method])
    for y, (v, va, pre) in enumerate(zip(res.ndcg, res.get("ndcg_active", res.ndcg), res.prereq_violation_rate)):
        ax.text(max(v, va) + 0.004, y, f"{v:.4f} / {va:.4f}  (선수 미이수 {pre:.2f})", va="center", fontsize=7.8)
    n_all = int(res.users.iloc[0]); n_act = int(res.active_users.iloc[0]) if "active_users" in res.columns else n_all
    ax.set_xlim(0, max(0.19, float(res.get("ndcg_active", res.ndcg).max()) + 0.09))
    ax.set_xlabel(f"테스트 주차 NDCG@5 (사용자 평균: 전체 n={n_all:,} / 활성 n={n_act:,}) · 오차 막대 = 전역 1위 대비 차이의 95% 구간 반폭")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.set_title("방법별 오프라인 정확도 (모의 데이터 v2, seed 42) — 전체 기준과 활성 사용자 기준", fontsize=10.5, loc="left")
    ax.grid(axis="x", alpha=0.3); ax.set_axisbelow(True)
    fig.savefig(os.path.join(OUT, "fig4_ndcg_methods.png"), dpi=200, bbox_inches="tight"); plt.close(fig)
    # 그림 5: 정확도-선수 위반 트레이드오프
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    offs = {"RULE": (6, 3), "RouterNoGender": (-128, 3), "RouterFull": None, "RouterNoGenderIncome": (6, 4), "NoDemographics": (6, -11),
            "RouterNoGender+prereq": (-4, -20), "UCF": (-60, 8), "ICF": (6, 5), "CONTENT": (6, -12), "MF": (6, -4), "MF_OBS": (6, -4), "MLP": (6, 4), "POP": (6, 4), "Random": (-45, 8),
            "MF_BPR": (6, 6), "MLP_BPR": (6, -12), "MLP_BPRU": (6, 4), "MLP_NEXT": (-114, -3)}
    for _, r in res.iterrows():
        c = GOLD if r.method == "RouterNoGender" else (RED if r.method == "RouterNoGender+prereq" else GREEN)
        ax.scatter(r.prereq_violation_rate, r.ndcg, s=70, c=c, zorder=3, edgecolors="white")
        o = offs.get(r.method, (5, 4))
        if o is not None:
            ax.annotate(KO.get(r.method, r.method), (r.prereq_violation_rate, r.ndcg), xytext=o, textcoords="offset points", fontsize=7.8)
    a = res.set_index("method")
    ax.annotate("", xy=(a.loc["RouterNoGender+prereq", "prereq_violation_rate"], a.loc["RouterNoGender+prereq", "ndcg"]),
                xytext=(a.loc["RouterNoGender", "prereq_violation_rate"], a.loc["RouterNoGender", "ndcg"]),
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.4, ls="--"))
    ax.set_xlabel("Top-5 중 선수 단원 미이수 비율"); ax.set_ylabel("NDCG@5")
    d_ = a.loc["RouterNoGender", "ndcg"] - a.loc["RouterNoGender+prereq", "ndcg"]; sl_ = a.loc["RouterNoGender+prereq", "short_list_rate"]
    ax.set_title(f"정확도와 교육 순서 준수의 트레이드오프: 선수 가드레일은 위반을 0으로 만들지만 NDCG가 {d_:.3f} {'낮아진다' if d_ > 0 else '높아진다'}\n(테스트 사용자 {sl_:.1%}가 가드레일 통과 후보 5개 미만 → 짧은 목록)", fontsize=9.3, loc="left")
    ax.grid(alpha=0.3); ax.set_axisbelow(True)
    fig.savefig(os.path.join(OUT, "fig5_prereq_tradeoff.png"), dpi=200, bbox_inches="tight"); plt.close(fig)
    # 그림 6: 라우터 λ
    m = json.load(open(os.path.join(ROOT, "artifacts/bundle_v2/manifest.json"), encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    for name, c in (("RouterFull", GREY), ("RouterNoGender", GOLD), ("RouterNoGenderIncome", BLUE)):
        rows = m["router_tuning"][name]
        xs = [r["lam"] for r in rows]; ys = [r["mean"] for r in rows]; sd = [r["std"] for r in rows]
        xl = [str(int(x)) if x < 1e8 else "∞" for x in xs]
        ax.errorbar(range(len(xs)), ys, yerr=sd, marker="o", label=KO[name], color=c, capsize=3)
    ax.set_xticks(range(len(xs))); ax.set_xticklabels(xl); ax.set_xlabel("수축 λ (0 = 세그먼트별 독립 선택, ∞ = 전역 1위만)"); ax.set_ylabel("검증 교차 NDCG@5")
    ax.legend(fontsize=8.5, frameon=False); ax.grid(alpha=0.3); ax.set_axisbelow(True)
    ax.set_title("세그먼트 라우터 λ 교차 선택: λ가 커질수록(전역에 가까울수록) 나아지며 λ=3000이 선택됨", fontsize=9.5, loc="left")
    fig.savefig(os.path.join(OUT, "fig6_router_lambda.png"), dpi=200, bbox_inches="tight"); plt.close(fig)
    # 그림 7: 목적별·집단별 — 전체 기준(진한 막대)과 활성 기준(옅은 막대)
    g = pd.read_csv(os.path.join(ROOT, "artifacts/bundle_v2/group_results.csv"), encoding="utf-8-sig")
    g = g[(g.method == "RouterNoGender")]
    labels = {"gender": ["남성", "여성"], "age_band": ["29세 이하", "30대", "40대", "50대", "60세 이상"],
              "income_q": ["소득 1분위", "2분위", "3분위", "4분위", "5분위"], "click_tier": ["활동 신규", "활동 보통", "활동 많음"],
              "goal": {"pension": "연금·노후", "income": "배당·인컴", "long_term": "장기 지수", "trading": "단기 매매", "diversify": "분산·안정"}}
    fig, axes = plt.subplots(2, 1, figsize=(9.6, 6.6), sharex=True, gridspec_kw=dict(hspace=0.12))
    names, cols, rows_ = [], [], []
    for var, col in (("goal", GREEN), ("age_band", BLUE), ("income_q", GOLD), ("gender", GREY), ("click_tier", RED)):
        for _, r in g[g.variable == var].iterrows():
            lab = labels[var][r.group] if isinstance(labels[var], dict) else labels[var][int(r.group)]
            names.append(lab); cols.append(col); rows_.append(r)
    xs = np.arange(len(names))
    for ax, key, lo, hi, ttl in ((axes[0], "ndcg", "ci_low", "ci_high", "전체 기준(정답 없는 사용자 = 0 포함)"),
                                 (axes[1], "ndcg_active", "ci_low_active", "ci_high_active", "활성 기준(다음 주 정답이 있는 사용자만)")):
        if key not in g.columns:
            continue
        v = np.array([r[key] for r in rows_], float); l = np.array([r[lo] for r in rows_], float); h = np.array([r[hi] for r in rows_], float)
        ax.bar(xs, v, yerr=[v - l, h - v], color=cols, capsize=2, ecolor="#5d665d", alpha=1.0 if key == "ndcg" else 0.55)
        ax.set_ylabel("NDCG@5"); ax.grid(axis="y", alpha=0.3); ax.set_axisbelow(True)
        ax.set_ylim(max(0, np.nanmin(l) - 0.02), np.nanmax(h) + 0.02)
        ax.set_title(ttl, fontsize=9.5, loc="left")
        if key == "ndcg_active" and "active_share" in g.columns:
            for x_, r in zip(xs, rows_):
                ax.text(x_, ax.get_ylim()[0] + 0.004, f"{r['active_share']:.2f}", ha="center", fontsize=6.8, color="white" if r['active_share'] > 0 else "#333")
    axes[1].set_xticks(xs); axes[1].set_xticklabels(names, rotation=35, ha="right", fontsize=8.2)
    fig.suptitle("운영 라우터의 집단별 NDCG@5 (95% 부트스트랩 구간) — 아래 막대 안 숫자 = 집단의 활성 비율", fontsize=9.8, x=0.01, ha="left", y=0.995)
    fig.savefig(os.path.join(OUT, "fig7_groups.png"), dpi=200, bbox_inches="tight"); plt.close(fig)


# ---------- 그림 8: 선수 페널티 민감도 ----------
def fig_sensitivity(path):
    if not os.path.exists(path):
        print("sensitivity 결과 없음 — 건너뜀"); return
    rows = json.load(open(path, encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    xs = [r["prereq_penalty"] for r in rows]
    for key, lab, c in (("RouterNoGender", "운영 라우터(가드레일 없음)", GOLD), ("RouterNoGender+prereq", "운영 라우터+선수 가드레일", RED), ("POP", "인기", GREY)):
        ax.plot(xs, [r[key]["ndcg"] for r in rows], marker="o", label=lab, color=c)
    ax2 = ax.twinx()
    ax2.plot(xs, [r["RouterNoGender"]["prereq_violation_rate"] for r in rows], marker="s", ls="--", color=GREEN, label="라우터의 선수 미이수 비율(우축)")
    ax2.set_ylabel("선수 미이수 비율"); ax2.set_ylim(0, 1)
    ax.set_xlabel("생성기의 선수 미이수 페널티 (로짓/단원, 기본 0.8)"); ax.set_ylabel("테스트 NDCG@5 (n=3,000 세계)")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, frameon=True, framealpha=0.9, loc="lower right"); ax.grid(alpha=0.3); ax.set_axisbelow(True)
    ax.set_title("선수 효과가 강한 세계일수록 가드레일의 정확도 비용이 줄어든다 (작은 모의 세계 민감도)", fontsize=9.5, loc="left")
    fig.savefig(os.path.join(OUT, "fig8_sensitivity.png"), dpi=200, bbox_inches="tight"); plt.close(fig)


# ---------- 화면 캡처 자르기 ----------
def crops():
    spec = {"01_idea_parsed.png": 2200, "03_diagnosis.png": 2300, "05_roadmap.png": 2400, "07_preview.png": 2600,
            "09_types.png": 2500, "10_compare_eval.png": 2500, "08_simulation.png": 1950, "02_basic.png": None, "11_save.png": None}
    for name, h in spec.items():
        im = Image.open(os.path.join(ROOT, "docs/screens", name))
        if h and im.height > h:
            im = im.crop((0, 0, im.width, h))
        im = im.convert("RGB"); im.thumbnail((1400, 4000))
        im.save(os.path.join(OUT, "shot_" + name.replace(".png", ".jpg")), quality=82)


if __name__ == "__main__":
    fig_architecture(); fig_roadmap_flow(); fig_prereq_graph(); fig_results(); crops()
    fig_sensitivity(sys.argv[1] if len(sys.argv) > 1 else "")
    print("figures:", sorted(os.listdir(OUT)))
