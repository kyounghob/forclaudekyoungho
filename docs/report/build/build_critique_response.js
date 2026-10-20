// 중간보고서 비판 검토 및 보완 보고서 (.docx). 실행: node build_critique_response.js out.docx
const fs = require("fs");
const path = require("path");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, PageBreak, Footer, Header, PageNumber, TableOfContents, LevelFormat, VerticalAlign, LineRuleType } = require("docx");

const HERE = __dirname;
const D = JSON.parse(fs.readFileSync(path.join(HERE, "report_data.json"), "utf8"));
const OUT = process.argv[2] || path.join(HERE, "비판검토보완보고서.docx");
const FONT = "맑은 고딕";
const PAGE_W = 11906, MARGIN = 1247, CONTENT_W = PAGE_W - 2 * MARGIN;
const GREEN = "1F6F55", SOFT = "DCEFE6", GOLD = "9A6A00", SOFT2 = "F4F5F2", GREY = "5D665D", RED = "B2362D", BLUE = "3B6FB6", TEAL = "17806D";
let tabNo = 0;
const run = (text, opt = {}) => new TextRun({ text, font: FONT, size: opt.size || 21, bold: opt.bold, italics: opt.italics, color: opt.color });
const p = (text, opt = {}) => new Paragraph({ alignment: opt.align || AlignmentType.JUSTIFIED, spacing: { after: opt.after ?? 120, line: opt.line || 312, lineRule: LineRuleType.AUTO }, indent: opt.indent, keepNext: opt.keepNext,
  children: (Array.isArray(text) ? text : [text]).map(x => typeof x === "string" ? run(x, opt) : run(x.t, { ...opt, ...x })) });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 }, children: [new TextRun({ text: t, font: FONT })] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 120 }, keepNext: true, children: [new TextRun({ text: t, font: FONT })] });
const h3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 80 }, keepNext: true, children: [new TextRun({ text: t, font: FONT })] });
const bullet = (text) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED,
  children: (Array.isArray(text) ? text : [text]).map(x => typeof x === "string" ? run(x) : run(x.t, x)) });
const note = (text, color = GREEN) => new Paragraph({ spacing: { after: 120, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED, indent: { left: 240 },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color, space: 8 } }, shading: { type: ShadingType.CLEAR, fill: SOFT2, color: "auto" },
  children: (Array.isArray(text) ? text : [text]).map(x => typeof x === "string" ? run(x, { size: 20 }) : run(x.t, { size: 20, ...x })) });
const quote = (text) => new Paragraph({ spacing: { after: 100, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED, indent: { left: 400, right: 200 },
  border: { left: { style: BorderStyle.SINGLE, size: 12, color: "BBBBBB", space: 8 } }, children: [run(text, { size: 19, italics: true, color: "333333" })] });
const spacer = (n = 120) => new Paragraph({ spacing: { after: n }, children: [] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });
// 숫자 뒤 조사: 끝자리 읽기의 받침(0 영·3 삼·6 육 = 받침, 1 일·7 칠·8 팔 = ㄹ 받침, 2·4·5·9 = 받침 없음, % = 퍼센트)
const JONG_D = { "0": 1, "1": 2, "2": 0, "3": 1, "4": 0, "5": 0, "6": 1, "7": 2, "8": 2, "9": 0 };
function jo(v, pair) {
  const s = String(v), m = s.match(/(\d)[^\d]*$/), t = s.trim().endsWith("%") ? 0 : (m ? JONG_D[m[1]] : 1);
  const [a, b] = pair.split("/");
  if (a === "으로") return s + (t === 1 ? "으로" : "로");
  return s + (t === 0 ? b : a);
}
const fmt = (x, d = 4) => (x == null || Number.isNaN(+x)) ? "–" : (+x).toFixed(d);
const pct = (x, d = 1) => (x == null || Number.isNaN(+x)) ? "–" : (100 * x).toFixed(d) + "%";
const num = (x) => (x == null ? "–" : Number(x).toLocaleString("ko-KR"));
const trunc = (t, n) => (t.length > n ? t.slice(0, n) + "…" : t);
function cell(text, opt = {}) {
  const children = (Array.isArray(text) ? text : [text]).map(t => new Paragraph({ alignment: opt.align || AlignmentType.LEFT, spacing: { after: 20, line: 264, lineRule: LineRuleType.AUTO },
    children: (Array.isArray(t) ? t : [t]).map(x => typeof x === "string" ? run(x, { size: opt.size || 18, bold: opt.bold, color: opt.color }) : run(x.t, { size: opt.size || 18, ...x })) }));
  return new TableCell({ width: { size: opt.width, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER, shading: opt.fill ? { type: ShadingType.CLEAR, fill: opt.fill, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 80, right: 80 }, children });
}
function table(headers, rows, widthsRel, opt = {}) {
  const total = widthsRel.reduce((a, b) => a + b, 0);
  const widths = widthsRel.map(w => Math.round(CONTENT_W * w / total)); widths[widths.length - 1] += CONTENT_W - widths.reduce((a, b) => a + b, 0);
  const size = opt.size || 18;
  const head = new TableRow({ tableHeader: true, children: headers.map((hh, i) => cell(hh, { width: widths[i], fill: SOFT, bold: true, size })) });
  const body = rows.map((r, ri) => new TableRow({ cantSplit: !!opt.cantSplit, children: r.map((c, i) => cell(c, { width: widths[i], size, fill: (opt.zebra && ri % 2 === 1) ? SOFT2 : undefined, align: (opt.numCols || []).includes(i) ? AlignmentType.RIGHT : AlignmentType.LEFT })) }));
  const out = [new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows: [head, ...body],
    borders: { top: { style: BorderStyle.SINGLE, size: 6, color: "BBBBBB" }, bottom: { style: BorderStyle.SINGLE, size: 6, color: "BBBBBB" }, left: { style: BorderStyle.NONE, size: 0 }, right: { style: BorderStyle.NONE, size: 0 },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: "DDDDDD" }, insideVertical: { style: BorderStyle.NONE, size: 0 } } })];
  if (opt.caption) { tabNo += 1; out.unshift(new Paragraph({ spacing: { before: 160, after: 60 }, keepNext: true, children: [run(`표 ${tabNo}. ${opt.caption}`, { size: 19, bold: true, color: GREEN })] })); }
  out.push(spacer(100));
  return out;
}

// ---------- 데이터 ----------
const KO = { RULE: "규칙(검증 1위)", Global: "전역 1위", RouterNoGender: "운영 라우터(성별 제외)", RouterFull: "라우터(성별 포함)", RouterNoGenderIncome: "라우터(성별·소득 제외)",
  NoDemographics: "인구통계 미사용", UCF: "사용자 CF", "RouterNoGender+prereq": "운영 라우터+선수 가드레일", POP: "인기", ICF: "아이템 CF", CONTENT: "콘텐츠",
  MLP: "MLP(관측 시도 BCE)", MLP_BPR: "MLP 쌍별(관측 음성)", MLP_BPRU: "MLP 쌍별(미관측 음성)", MLP_NEXT: "MLP 목표 정렬(다음 주 통과)", MF_OBS: "관측 MF", MF: "표본 MF(가중 MSE)", MF_BPR: "BPR MF(미관측 음성)", Random: "무작위" };
const R = Object.fromEntries(D.results.map(r => [r.method, r])), V1 = Object.fromEntries(D.v1_results.map(r => [r.method, r]));
const M = D.manifest, DS = M.dataset, PRIV = M.privacy || {}, sens = D.sensitivity;
const nAll = R.RULE.users, nAct = R.RULE.active_users, ratio = nAll / nAct;
const F = Object.fromEntries(D.facts.map(f => [f.key, f]));
const PR2 = Object.fromEntries((D.paired || []).map(x => [`${x.a}-${x.b}`, x])), PR1 = Object.fromEntries((D.paired_v1 || []).map(x => [`${x.a}-${x.b}`, x]));
// 신경망 비교의 사용자군: common = 네 MLP가 모두 학습한 사용자, history_no_pairs = 기록은 있지만 통과(쌍)가 없는 사용자
const NNG = D.nn_groups || null, NNG1 = D.nn_groups_v1 || null;
const CG = (g, k) => (g && g.pairs[k] && g.pairs[k].common) || null, HG = (g, k) => (g && g.pairs[k] && g.pairs[k].history_no_pairs) || null;
const PA = D.pair_audit || {}, OBSNEG = (PA.mlp9_bpr && PA.mlp9_bpr.pairs) ? 1 - PA.mlp9_bpr.pairs_with_observed_negative / PA.mlp9_bpr.pairs : null;
const sgn = (x, d = 4) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d);
const ci = (x, d = 4) => x ? `${sgn(x.diff, d)} [${sgn(x.ci_low, d)}, ${sgn(x.ci_high, d)}]` : "–";
const eff = (x) => !x ? "–" : (x.ci_low > 0 ? "유의한 개선" : (x.ci_high < 0 ? "유의한 악화" : "유의한 차이 없음"));
const effS = (x) => !x ? "판단할 수 없었" : (x.ci_low > 0 ? "유의하게 개선되었" : (x.ci_high < 0 ? "유의하게 나빠졌" : "유의한 차이가 없었"));
const two = (x1, x2) => (effS(x1) === effS(x2) ? `v1·v2 모두 ${effS(x1)}다` : `v1에서 ${effS(x1)}고 v2에서 ${effS(x2)}다`);
const CT = D.click_tier || [];
const CT_LAB = ["신규(조회 0)", "보통(1~9)", "많음(10+)"];
const ctTopAll = CT.length ? CT_LAB[+CT.reduce((a, b) => (b.ndcg > a.ndcg ? b : a)).group] : "–", ctTopAct = CT.length ? CT_LAB[+CT.reduce((a, b) => (b.ndcg_active > a.ndcg_active ? b : a)).group] : "–";
const DIVL = D.diversity_by_len || {}, DIVG = DIVL["RouterNoGender+prereq"] || {}, DIVR = DIVL.RouterNoGender || {};
const mlpAud = ((D.training_audit || {}).mlp9 || []).slice(-1)[0] || null;
const mlpPos = mlpAud ? mlpAud.positive / mlpAud.training_rows : null;
const bce0 = mlpPos ? -(mlpPos * Math.log(mlpPos) + (1 - mlpPos) * Math.log(1 - mlpPos)) : null;
const QUNITS = new Set(D.questions.map(q => q.topic + "|" + q.level)).size;
const VAR_KO = { gender: "성별", age_band: "연령대", income_q: "소득분위", click_tier: "학습활동", goal: "투자 목적" };
const GOAL_LO = (() => { const g = (D.group_results || []).filter(x => x.method === "RouterNoGender" && x.variable === "goal"); return g.length ? g.reduce((a, b) => (b.ndcg < a.ndcg ? b : a)) : null; })();
const EXPG = (() => { const by = {}; (D.exposure || []).filter(x => x.method === "RouterNoGender").forEach(x => { (by[x.variable] = by[x.variable] || []).push(x.advanced_share); });
  const g = Object.entries(by).map(([v, a]) => ({ v: VAR_KO[v] || v, gap: Math.max(...a) - Math.min(...a) })).sort((a, b) => b.gap - a.gap); return g[0] || { v: "–", gap: 0 }; })();
const TESTS = D.tests_collected;
const QSH = ((D.privacy_summary || {}).quasi || {}).share_below_k;   // 저장 준식별자 조합에서 k 미만 셀에 있는 학습자 비율
const NN2_BEST = ["MF", "MF_OBS", "MF_BPR", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"].filter(k => R[k]).reduce((a, k) => (!a || R[k].ndcg > R[a].ndcg ? k : a), null);
const nnBest2 = Math.max(...["MF", "MF_OBS", "MF_BPR", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"].filter(k => R[k]).map(k => R[k].ndcg));
const nnBest1 = Math.max(...["MF", "MF_OBS", "MF_BPR", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"].filter(k => V1[k]).map(k => V1[k].ndcg));
// A/B 표본 크기(중간보고서 7.3절과 같은 공식)
const ZQ = { a2: 1.959963985, a1: 1.644853627, a2_dunnett: 2.241402728, b80: 0.841621234 };
function abSize(p1, p2, za) { const pb = (p1 + p2) / 2; return Math.ceil(Math.pow(za * Math.sqrt(2 * pb * (1 - pb)) + ZQ.b80 * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)), 2) / Math.pow(p2 - p1, 2)); }
const niSize = (p0, m) => Math.ceil(Math.pow(ZQ.a1 + ZQ.b80, 2) * 2 * p0 * (1 - p0) / (m * m));
function Phi(x) { const t = 1 / (1 + 0.2316419 * Math.abs(x)); const d = 0.3989423 * Math.exp(-x * x / 2); const q = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - q : q; }
const ENROLL_DAYS = 56 - 7;                     // 8주 상한 안에 7일 결과까지: 등록은 49일 안에
const AB2 = abSize(0.22, 0.24, ZQ.a2), AB3 = abSize(0.22, 0.25, ZQ.a2), AB4 = abSize(0.22, 0.26, ZQ.a2), AB2one = abSize(0.22, 0.24, ZQ.a1), AB2dun = abSize(0.22, 0.24, ZQ.a2_dunnett);
const POW3 = (() => { const pb = 0.23; return Phi((0.02 * Math.sqrt(AB3) - ZQ.a2 * Math.sqrt(2 * pb * (1 - pb))) / Math.sqrt(0.22 * 0.78 + 0.24 * 0.76)); })();
// 군당 n명일 때 참 통과율 p2(대조 22%)의 양측 검정력: MDE보다 작은 효과는 검정력이 80%보다 낮아질 뿐이다
const powAt = (p2, n) => { const p1 = 0.22, pb = (p1 + p2) / 2; return Phi(((p2 - p1) * Math.sqrt(n) - ZQ.a2 * Math.sqrt(2 * pb * (1 - pb))) / Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))); };
const POW15 = powAt(0.235, AB2), POW10 = powAt(0.23, AB2);
// 1차본(2026-10-13 15시 번들) 수치
const PREV = { RULE: 0.1356, RouterNoGender: 0.1343, prereq: 0.1014, MF: 0.0686, MF_OBS: 0.0698, MLP: 0.0734, POP: 0.0951, Random: 0.0430, catalog: 63, quiz: 16, configs: 2631,
  viol: 0.628, short: 0.525, qa: 80, tests: 23, attempts: 108777, complete: 50257, quiz_pass: 24187, save: 12825, drop: 46772, test_users: 6438, zero: 2949, density: 0.102, exp_lo: 0.099, exp_hi: 0.237 };   // exp_*: 1차본 표 17 소득분위별 심화 노출(2분위·5분위)
const PREV_NCND = PREV.attempts - PREV.complete - PREV.drop, PREV_EXCESS = PREV.complete + PREV.quiz_pass + PREV.save + PREV.drop - PREV.attempts;
const EV = (() => { const sum4 = DS.complete + DS.quiz_pass + DS.save + DS.drop, ncnd = DS.not_complete - DS.drop; return { sum4, excess: sum4 - DS.study_attempts, ncnd }; })();
if (PREV_EXCESS !== PREV.quiz_pass + PREV.save - PREV_NCND || EV.excess !== DS.quiz_pass + DS.save - EV.ncnd) throw new Error("이벤트 합 분해 검산 실패");

// ---------- 판정 색 ----------
const VCOL = { "수용": GREEN, "대부분 수용": TEAL, "부분 수용": GOLD, "불수용": RED, "긍정 평가": BLUE, "사실": GREEN, "긍정": BLUE, "부분": GOLD, "오류": RED, "미검증": GREY,
  "이미 충족": GREY, "요구 수용": GREEN, "요구 부분 수용": GOLD, "정정": RED };
const vrun = (v, size) => ({ t: v, bold: true, color: VCOL[v.split("(")[0].trim()] || GREY, size });
const unitTable = (units, cap) => table(["#", "비판의 문장(요지)", "판정", "근거"], units.map((u, i) => [String(i + 1), u[0], [vrun(u[1], 17)], u[2]]), [0.5, 4.2, 1.5, 6.3],
  { caption: cap, size: 16, zebra: true });

// ---------- 2·3차 반영 사항(개인정보·KRX): 구현 결과로 채운다 ----------
const FIX9 = (D.fix9 && D.fix9.length) ? D.fix9 : ["(구현 결과로 채움)"];
const FIX10 = (D.fix10 && D.fix10.length) ? D.fix10 : ["(구현 결과로 채움)"];
const CHANGE9 = D.change9 || "비공식 호출 코드 0줄. 공식 API 2종(KRX Open API, 공공데이터포털 시세·상장종목정보) + 사람이 내려받은 파일 정규화.";
const CHANGE10 = D.change10 || "–";

// ---------- 지적 목록 ----------
const CLAIMS = [
  { id: "1", sec: "1절", short: "네 열은 한 시도에 붙는 플래그다. 차이 25,264 = 통과 24,187 + 저장 12,825 − 미완료·비이탈 11,748. 모순 행 0건, 밀도는 결과값", title: "모의 데이터 기술 통계의 ‘산술적 모순’", verdict: "불수용(표 설명 보완과 실데이터 정규화 장치는 수용)",
    quote: "표 8은 학습 시도를 108,777건으로 보고한다. 그런데 완료(50,257)·퀴즈 통과(24,187)·저장(12,825)·이탈(46,772)을 합하면 134,041건으로 25,264건을 초과하는 수학적 모순이 생긴다 … 이탈과 완료/퀴즈 통과는 동시에 성립할 수 없는데 10.2%라는 고정된 희소성 제약 아래서 난수 생성 로직이 통제 없이 할당했을 개연성이 있다 … 마르코프 체인 상태 전이 확률을 수정하고 세션 ID 기준으로 1NF 정규화해야 한다.",
    units: [
      ["15,000명 모의 학습자로 2,631개 설정을 검증한 접근은 방법론적으로 타당하다", "긍정", `수용. 2차본 설정 수는 ${num(M.configurations)}개다.`],
      ["목적별 구성의 합이 15,000명으로 맞으므로 프로필 생성기의 무결성이 검증된다", "사실", "생성기 v2의 목적·기간 분포 합계가 학습자 수와 같다."],
      ["2025년 말 1,058종목·순자산 297조 원은 KRX 결산과 일치한다", "사실", "부록 A의 출처와 같다."],
      ["네 이벤트의 합 134,041건이 시도 108,777건보다 25,264건 많으므로 수학적 모순이다", "오류", `덧셈은 맞지만 해석이 틀렸다. 네 열은 한 시도(행)에 붙는 플래그이고 서로 배타적인 범주가 아니다. 차이 ${num(PREV_EXCESS)}건은 퀴즈 통과 ${num(PREV.quiz_pass)}(이미 완료에 포함) + 저장 ${num(PREV.save)}(독립 플래그) − 미완료이면서 이탈하지 않은 시도 ${num(PREV_NCND)}(네 열 어디에도 잡히지 않음)로 정확히 분해된다. 2차본 데이터도 ${num(EV.excess)} = ${num(DS.quiz_pass)} + ${num(DS.save)} − ${num(EV.ncnd)}로 같다.`],
      ["한 시도 안의 완료·통과·저장이 정규화 없이 독립 빈도로 병합되었을 가능성이 크다", "부분", "한 시도에 여러 플래그가 함께 붙는 것은 설계 그대로다. 그러나 ‘병합’은 없다. 표는 플래그별 건수를 보고했을 뿐이고, 모델 입력인 행동 점수는 시도마다 max(조회 1, 완료 2, 통과 3, 저장 3) 하나로 줄인다. 같은 단원을 여러 주에 다시 시도하면 점수를 더하는데(etfrec/features.py), 이는 반복 학습을 더 강한 신호로 보는 설계이며 1차본에 적지 않아 2차본 4.4절에 명시했다."],
      ["이탈과 완료·통과는 동시에 성립할 수 없는데 통제 없이 할당되었을 개연성이 있다", "오류", `생성기(etfrec/synth.py)는 완료를 먼저 정하고 퀴즈 = 완료 ∧ …, 통과 = 퀴즈 ∧ …, 이탈 = ¬완료 ∧ … 로 만든다. 이탈∧완료 ${DS.drop_and_complete}건, 통과∧¬퀴즈 ${DS.pass_without_quiz}건, 퀴즈∧¬완료 ${DS.quiz_without_complete}건이며 v1 세계도 모두 0건이다.`],
      ["10.2%라는 고정된 희소성 제약 아래서 난수를 할당했다", "오류", `밀도는 생성 결과로 계산한 값(사용자×단원 고유 쌍 ÷ 전체 칸)이며 생성기에 목표 밀도가 없다. 생성기는 주마다 활동 학습자를 뽑고 각자 1~8개 단원을 효용(주제 선호·관심 주제·수준 차이·인기·단원 매력도·연령×소득 집단과 성별의 단원 선호·모바일×짧은 콘텐츠·이미 본/통과한 단원; 주제·인기 가중치와 수준 차이 벌점은 연령·경험에 따라 다름) 순위로 고른다. 인구통계가 행동에 들어가는 경로가 여기에 있다. 2차본 밀도는 단원 수가 늘어 ${pct(DS.density, 2)}다.`],
      ["모순된 로그가 들어가면 CF·MF가 생성기의 노이즈 규칙을 학습한다", "부분", "모순 행이 없으므로 전제는 성립하지 않는다. 다만 모의 데이터로 평가하면 모델이 생성기 규칙을 배우는 것은 피할 수 없는 한계라, 생성 규칙은 1차본부터 공개했다. 1차본(과 2차본 초안)은 ‘--effect 0 위약 세계’로 없는 효과를 만들어 내지 않는지 확인한다고 썼지만 실행한 기록이 없었고, 그 세계는 위약도 아니었다(연령·소득이 목적·경험·성향을 거쳐 남음). 2차본은 연령·연소득·성별 열을 학습자 사이에서 섞은 위약 세계를 실제로 돌려 인구통계의 거짓 이점이 없음을 확인했다(중간보고서 4.4절, docs/results/placebo_check.json)."],
      ["마르코프 체인 상태 전이 확률을 수정해 이벤트 종속성을 강제해야 한다", "이미 충족", "생성 규칙이 곧 상태 전이다(완료 → 퀴즈 시도 0.7 → 통과 σ(·), 미완료 → 이탈 0.8). 바꿀 결함이 없다."],
      ["세션 ID 기준으로 1NF 정규화해야 한다", "이미 충족", "로그는 한 행이 한 시도이고 모든 열이 원자값이다. 실제 이벤트 스트림(한 행 = 이벤트 하나)을 연결할 때는 session_id 열로 같은 (학습자, 단원, 세션)의 행을 한 시도로 묶고(data.events_to_attempts) 플래그 논리를 맞춘다(normalize_event_flags). 묶는 규칙은 최종 검토에서 ‘추가했다’는 서술과 달리 코드에 없다는 지적을 받고 구현했다(5절)."],
    ],
    prev: "1차본 표 8: ‘학습 시도 · 완료 · 퀴즈 통과 · 저장 · 이탈 | 108,777 · 50,257 · 24,187 · 12,825 · 46,772’, ‘사용자×단원 고유 쌍 · 밀도 | 96,008 · 10.2%’. 다섯 수를 한 칸에 나열했을 뿐 열의 정의는 없었다.",
    why: "생성기가 모순을 만들지 않으니 데이터에는 문제가 없다고 보고, 표를 읽는 사람이 어떻게 이해할지는 점검하지 않았다. 같은 이유로 다른 입력 경로(화면에서 받는 임의 학습자의 기록, 운영 로그 CSV)에서 같은 논리가 지켜지는지도 확인하지 않았다.",
    wrong: ["표 8에 ‘이벤트 열은 한 시도의 다중 플래그’라는 설명과 중첩 구조가 없어 배타적 건수로 읽힐 여지를 남겼다.", "밀도를 같은 표에 나란히 두어 생성기의 제약처럼 읽힐 수 있었다.", "화면에서 임의 학습자의 기록을 받을 때는 완료와 이탈을 함께 표시할 수 있었고 이를 막지 않았다(etfrec/service.py, 실제 결함).", "운영 로그를 CSV로 연결할 때 플래그 논리를 검사·정규화하는 장치가 없었다.", "같은 단원의 반복 시도를 합산하는 규칙을 문서에 적지 않았다."],
    reject: "‘산술 모순’, ‘생성기 난수 결함’, ‘고정 희소성 제약’, ‘마르코프 체인·1NF 수정 필요’는 위 근거로 사실과 달라 보완 대상에서 제외했다. 생성기는 고치지 않았다.",
    fix: ["etfrec/data.py normalize_event_flags: 통과 ⇒ 퀴즈 ⇒ 완료, 이탈 ⇒ 미완료로 행을 맞추고 고친 행 수를 데이터 요약(event_repairs)에 남긴다. Dataset.validate가 모든 입력에 적용한다.",
      "etfrec/data.py events_to_attempts: session_id 열이 있는 이벤트 스트림은 같은 (학습자, 단원, 세션)의 행을 한 시도로 묶는다(플래그 OR, 시각은 첫 이벤트, 세션 열은 버림). 묶지 않으면 조회 이벤트와 완료·통과 이벤트가 두 시도로 세어져 점수(1 + 3)와 조회 수가 부풀려진다. Dataset.validate와 가명처리 도구(pseudonymize)가 적용하고 묶은 수를 데이터 요약(attempt_grouping)에 남긴다.",
      "etfrec/service.py: 임의 학습자의 기록에서 완료와 이탈이 함께 들어오면 이탈을 끈다.",
      "학습 QA에 event_logic_drop_excludes_complete, event_logic_quiz_pass_requires_quiz_and_complete를 추가해 매 학습마다 확인하고, 실패하면 학습을 멈춘다.",
      "데이터 요약에 quiz_attempted·not_complete·replay와 세 가지 논리 제약 건수를 추가했다.",
      "중간보고서 4.4절 표를 ‘시도 → 완료/미완료 → 퀴즈 시도 → 통과, 이탈 ⊆ 미완료, 저장(독립)’ 구조로 바꾸고 합계 검산 행, 밀도의 성격, 점수·반복 시도 규칙을 적었다."],
    change: `QA ${PREV.qa} → ${M.qa}건(모두 통과, 이벤트 논리 검사 포함). 모의 데이터에서 고친 행은 v1·v2 모두 0건이다. 1차본과 2차본의 수치 차이는 카탈로그가 63 → ${D.catalog.n_items}단원으로 바뀌어 세계를 다시 만든 결과이며, 정규화 때문이 아니다.` },

  { id: "2.1", sec: "2.1절", short: "관례가 갈린다(scikit-learn·TorchMetrics는 0점 포함). 방법 순위는 불변이지만 집단 결론(학습활동)은 뒤집혀 두 기준을 병기", title: "정답 없는 사용자를 NDCG 0으로 산입한 평가", verdict: "부분 수용(요구는 전면 반영)",
    quote: "테스트 사용자 6,438명 중 45.8%인 2,949명은 3주차 정답이 없는데 NDCG를 0으로 일괄 처리해 평균에 산입하고 이를 ‘보수적 추정’이라 자평했다 … IDCG가 0이면 0/0으로 정의되지 않으며, 이런 사용자를 평가에서 배제하는 것이 확립된 표준이다 … 활성 3,489명만으로 재산출하면 ≈0.247 … 알고리즘 간 미세한 성능 편차를 축소하고 A/B 효과 크기 추정마저 오도한다.",
    units: [
      ["표 15에서 운영 라우터의 NDCG@5는 0.1343이다", "사실", "1차본 수치다."],
      ["테스트 6,438명 중 2,949명(45.8%)은 정답이 없다", "사실", "1차본 감사 기록과 같다."],
      ["이들을 0으로 평균에 넣고 ‘보수적 추정’이라고 자평했다", "사실", "1차본 3.2절·6.1절의 문장이다(아래 인용)."],
      ["IDCG = 0이면 NDCG는 0/0으로 정의되지 않는다", "사실", "구현은 이 경우를 0으로 정의했다(노트북과 같은 규칙)."],
      ["이런 사용자를 배제하는 것이 학계와 산업계의 확립된 표준이다", "부분", "배제하는 연구가 많지만 널리 쓰이는 구현은 갈린다. scikit-learn ndcg_score와 TorchMetrics RetrievalNormalizedDCG(기본 설정)는 정답 없는 질의를 0점으로 평균에 넣는다. 관례가 갈리므로 어느 쪽인지 밝히고 두 값을 함께 보고하는 것이 맞다."],
      ["0점 산입으로 신호가 노이즈에 의해 절반 가까이 희석된다", "부분", `절댓값이 ${fmt(1 / ratio, 3)}배로 줄어드는 것은 맞다. 그러나 정답 없는 사용자는 모든 방법에서 정확히 0이어서 ‘노이즈’가 아니라 같은 상수 배율이다. 방법 간 쌍 비교에서 이들의 차이는 0이다.`],
      ["활성 3,489명만으로 재산출하면 기준 모델은 ≈0.247이다", "사실", `0.1343 × 6,438 ÷ 3,489 = 0.2478. 2차본 번들에서 운영 라우터는 ${fmt(R.RouterNoGender.ndcg_active)}(활성 ${num(nAct)}명)이다.`],
      ["알고리즘 간 미세한 성능 편차를 축소한다", "부분", `절대 차이는 ${fmt(1 / ratio, 3)}배로 줄지만 순위는 항상 같고, 유의성 판정도 이번 실행에서 모든 방법이 같았다. 그런데 집단 비교에서는 결론이 바뀌었다(학습활동 집단에서 가장 높은 집단이 바뀜, 아래 표). 1차본 6.5절의 해석이 실제로 틀렸으므로 이 부분의 지적은 처음 판단보다 더 정확했다.`],
      ["A/B 테스트의 효과 크기 추정마저 오도한다", "오류", "A/B 표본 크기는 퀴즈 통과율(22% → 24%)로 계산하며 오프라인 NDCG를 쓰지 않는다. 비판 3절도 그 계산을 ‘무결’로 확인했다."],
    ],
    prev: "1차본 3.2절: ‘정답 없는 사용자도 NDCG 0으로 평균에 넣어(노트북 규칙) 보수적으로 추정하고 그 수를 감사 기록에 남김’. 6.1절: ‘… 노트북의 규칙을 그대로 따르므로 절대 수치는 보수적이며 …’. 6.5절: ‘학습활동이 많은 집단이 가장 높은 것은 기록이 많을수록 개인화가 잘 되는 자연스러운 결과다’.",
    why: "노트북 기록과 소수점 5자리까지 맞추는 재현을 최우선에 두어 노트북 규칙의 값만 보고했다. 다른 연구와 비교하려면 다른 관례의 값이 필요하다는 점, 그리고 집단마다 정답 있는 사용자의 비율이 달라 집단 비교가 활동량과 섞인다는 점을 계산해 보지 않았다. ‘보수적’이라는 한 단어로 설명을 대신했다.",
    wrong: ["한 가지 관례의 값만 보고하고 다른 관례의 값을 병기하지 않았다.", "‘보수적’은 방법 간 비교에서만 맞는 표현이었다. 집단 비교에서는 보수적인 것이 아니라 활성 비율과 섞인 값이었다.", "그 결과 1차본 6.5절의 학습활동 집단 해석은 정답 없는 사용자 처리 방식이 만든 착시였다."],
    reject: "‘확립된 표준’(관례가 갈림), ‘노이즈 희석’(상수 배율), ‘A/B 효과 크기 오도’(무관)는 근거와 함께 정정하고 보완 대상에서 제외했다. 지표 정의(IDCG = 0이면 0)는 노트북 재현을 위해 그대로 두고 활성 기준을 함께 계산한다.",
    fix: ["etfrec/pipeline.py: 방법별 결과에 ndcg_active·hit_active·active_users·difference_vs_global_active·ci_low/high_active 열을 추가했다.",
      "집단별 결과(group_results.csv)에 활성 사용자 수·활성 비율·활성 기준 NDCG와 95% 구간을 추가했다.",
      `QA: ndcg_active_identity(활성 × 활성 인원 = 전체 × 전체 인원), active_users_identical_across_methods, active_rank_preserved. 감사 기록에 다음 주 통과 기록이 있는 사용자(${num(M.test.raw_positive_users)}명)와 후보 안에 정답이 있는 활성 사용자(${num(nAct)}명)를 구분해 남긴다.`,
      "평가 화면(10단계), README, 중간보고서 6.1·6.3·6.5·7.1절에 두 기준을 병기하고 그림 9(방법별)와 그림 11(집단별)을 두 기준으로 다시 그렸다."],
    change: `방법별 NDCG@5(전체 / 활성): 규칙 ${fmt(R.RULE.ndcg)} / ${fmt(R.RULE.ndcg_active)}, 운영 라우터 ${fmt(R.RouterNoGender.ndcg)} / ${fmt(R.RouterNoGender.ndcg_active)}, 인기 ${fmt(R.POP.ndcg)} / ${fmt(R.POP.ndcg_active)}, 무작위 ${fmt(R.Random.ndcg)} / ${fmt(R.Random.ndcg_active)}. 순위는 같다. 학습활동 집단은 두 기준에서 가장 높은 집단이 바뀐다(전체 ${ctTopAll}, 활성 ${ctTopAct}).`,
    extra: () => table(["학습활동", "사용자", "활성 비율", "NDCG@5 전체", "NDCG@5 활성"], CT.map(x => [CT_LAB[+x.group], num(x.users), pct(x.active_share, 1), fmt(x.ndcg, 3), fmt(x.ndcg_active, 3)]),
      [2.6, 1.8, 1.8, 2.4, 2.4], { caption: `학습활동 집단별 NDCG@5(운영 라우터): 가장 높은 집단이 전체 기준 ${ctTopAll}, 활성 기준 ${ctTopAct}`, size: 17, zebra: true, numCols: [1, 2, 3, 4] }) },

  { id: "2.2", sec: "2.2절", short: "MLP는 관측 시도만 학습했다(미관측 0 가정 아님). 미관측 음성 BPR이 v1 MLP를 약 두 배로 올렸고, v2는 공통 학습 사용자에서 차이 없음(전체는 쌍 없는 사용자 대체 점수로 악화). ‘목표 불일치’ 단정 정정", title: "BCE 손실의 한계와 BPR 부재 → 딥러닝 결과 무효", verdict: "부분 수용(요구는 전면 반영: BPR 기준선 추가, 효과는 v1에서만 확인)",
    quote: "MF·MLP의 성능(각각 0.0698, 0.0734)이 인기(0.0951)나 무작위(0.0430) 수준에 머문 원인을 ‘학습 목표와 평가 목표의 불일치’로 단순히 치부했다 … 근본 원인은 BCE라는 점별 손실을 암묵적 피드백에 기계적으로 적용한 데 있다 … BCE는 관측되지 않은 모든 항목을 절대적 0으로 가정하고, 밀도 10.2%에서 예측값을 0으로 붕괴시킨다 … BPR이 표준이며, BPR로 재학습하지 않는 이상 딥러닝 평가 결과는 학술적으로 전혀 유효하지 않다.",
    units: [
      ["MF와 MLP의 성능은 각각 0.0698, 0.0734다", "부분", `0.0698은 관측 MF(관측된 행만 MSE)이고, 미관측을 표본 0으로 쓰는 표본 MF는 ${jo(fmt(PREV.MF), "이었다/였다")}. 둘 다 BCE가 아니다(표본 MF는 신뢰도 가중 MSE).`],
      ["MF·MLP가 인기나 무작위 수준에 머물렀다", "부분", `인기보다는 낮았지만 v2에서 무작위보다는 확실히 높았다(MLP − 무작위 ${ci(PR2["MLP-Random"])}). 노트북 세계(v1)에서는 MLP가 무작위보다 낮았다(${ci(PR1["MLP-Random"])}).`],
      ["원인을 ‘목표 불일치’로 단순히 치부했다", "사실", "1차본은 실험 없이 ‘모델 결함이 아니라 목표 불일치’라고 단정했다(아래 인용)."],
      ["근본 원인은 점별 BCE를 암묵적 피드백에 기계적으로 적용한 데 있다", "부분", `노트북 세계에서는 맞다. 비판이 처방한 BPR(미관측 음성)을 쓰면 v1에서 MLP 점수(${fmt(V1.MLP.ndcg, 5)} → ${fmt(V1.MLP_BPRU ? V1.MLP_BPRU.ndcg : null, 5)})가 ${effS(PR1["MLP_BPRU-MLP"])}고, 네 MLP가 모두 학습한 사용자(${NNG1 ? num(NNG1.common) : "–"}명)로 좁혀도 ${effS(CG(NNG1, "MLP_BPRU-MLP"))}다. BPR MF는 표본 MF보다 ${two(PR1["MF_BPR-MF"], PR2["MF_BPR-MF"])}. 그러나 v2에서는 네 MLP가 모두 학습한 사용자(${NNG ? num(NNG.common) : "–"}명)로 좁히면 MLP와 ${effS(CG(NNG, "MLP_BPRU-MLP"))}고, 전체 사용자로는 ${effS(PR2["MLP_BPRU-MLP"])}다. 전체의 차이는 학습 주에 통과가 없어 쌍이 없는 사용자(${NNG ? num(NNG.history_no_pairs) : "–"}명)에게서 나온다. 이들은 점별 MLP에서는 미통과 행으로 학습되지만 쌍별 모델에서는 콘텐츠 대체 점수를 받는다. 두 세계에서 일관되게 효과를 낸 것은 음성 정의였다. 학습 범위가 같은 두 쌍별 모델에서 음성을 미통과 시도에서 미관측 단원으로 바꾸면 ${two(PR1["MLP_BPRU-MLP_BPR"], PR2["MLP_BPRU-MLP_BPR"])}.`],
      ["암묵적 피드백에서 관측되지 않은 것은 부정이 아니다", "사실", "일반론으로 맞다."],
      ["BCE는 관측되지 않은 모든 항목을 0(거절)으로 가정한다", "오류", "우리 MLP에는 해당하지 않는다. MLP는 관측된 시도 행만 학습했다(양성 = 통과, 음성 = 시도했지만 미통과). 미관측 단원은 0으로 둔 것이 아니라 아예 학습에 쓰지 않았다. 문제는 오히려 이것이었다(아래 해석)."],
      ["밀도 10.2%에서 예측값이 0으로 붕괴하는 클래스 불균형·과적합에 빠진다", "부분", `‘0으로 붕괴’와 ‘극단적 불균형’은 데이터와 다르다. 학습 행의 통과 비율은 ${pct(mlpPos)}이고, 마지막 학습 손실 ${mlpAud ? jo(fmt(mlpAud.loss_last, 3), "은/는") : "–"} 통과율만 맞히는 상수 예측의 손실 ${bce0 ? fmt(bce0, 3) : "–"}보다 낮으며, MLP 추천 목록의 Diversity@5는 ${jo(fmt(R.MLP.diversity, 3), "이다/다")}. ‘과적합’은 검증 손실 기록이 없어 산출물로 판단할 수 없다. 다만 v2에서 MLP의 테스트 NDCG가 무작위보다 높아 학습한 패턴이 다음 주에도 일부 통한다.`],
      ["추천의 목표는 순위이며 BPR 같은 쌍별 손실이 표준이다", "사실", "널리 쓰이는 기준선이다(Rendle 외 2009). 1차본에 이 기준선이 없었던 것은 결함이다."],
      ["MLP가 규칙에 참패한 것은 아키텍처 설계의 치명적 오류다", "부분", `손실을 바꿔도 신경망 최고치(v1 ${fmt(nnBest1)}, v2 ${fmt(nnBest2)})는 규칙(v1 ${fmt(V1.RULE.ndcg)}, v2 ${fmt(R.RULE.ndcg)})에 미치지 못했다. 생성기가 관심 주제·수준·목적으로 행동을 만드는 영향도 크다.`],
      ["BPR로 재학습하지 않는 이상 딥러닝 결과는 학술적으로 전혀 유효하지 않다", "부분", "‘전혀 무효’는 과하다. 1차본 결과는 같은 후보·정답·후처리에서 수업 레시피의 성능으로는 유효하다. 그러나 ‘신경망이 이 문제에서 할 수 있는 것’의 증거로는 불완전했으므로 BPR 계열 4개를 추가해 보완했다."],
    ],
    prev: "1차본 3.1절 기법 표: ‘사용자·단원 특징 → 은닉층 → 통과 확률(BCEWithLogitsLoss)’. 6.3절: ‘MF·MLP가 무작위와 비슷하거나 그보다 조금 높은 수준에 머문 것은 학습 목표(시도한 단원의 통과 여부)와 평가 목표(다음 주에 어떤 단원을 골라 통과하는지)가 어긋나기 때문이며 …’. 6.7절: ‘MF·MLP의 낮은 성능은 모델 결함이 아니라 목표 불일치이며, 랭킹 손실(BPR 등)로 … 변형을 다음 단계에서 비교한다’.",
    why: "수업 레시피(BCE·MSE)를 같은 조건에서 비교하는 데 집중했고, 낮은 성능의 원인을 실험 없이 단정했다. 기법 표에 학습 행과 음성의 정의를 쓰지 않아 ‘BCE = 미관측 0’으로 읽힐 여지를 남겼고, BPR 구현 비용을 과대평가해 ‘다음 단계’로 미뤘다. 보완 과정에서도 처음에는 관측 음성 쌍별 MLP 하나만 비교하고 같은 결론을 되풀이했는데, 그 변형은 비판이 말한 BPR(미관측 음성)이 아니었다. 음성 정의를 분리한 실험을 하고 나서야 정정할 수 있었다. 그다음에는 모델마다 누가 학습되고 누가 대체 점수를 받는지(학습 사용자 범위)를 점검하지 않았다. 점별 MLP에서 맞는 ‘관측 행이 있으면 학습된 사용자’ 규칙을 쌍별 MLP에도 그대로 써서, 쌍에 한 번도 나오지 않은 사용자를 학습된 사용자로 표시했다. 최종 검토가 이 결함을 찾았고, 고친 뒤 v2의 전체 사용자 결론은 ‘차이 없음’에서 ‘유의하게 나빠짐’으로 바뀌었다.",
    wrong: ["근거 없는 인과 주장(‘모델 결함이 아니라 목표 불일치’)을 결론처럼 쓰고, 랭킹 손실(BPR) 비교를 다음 단계로 미뤘다.", "순위 학습의 표준 기준선(BPR)이 없었다.", "기법별 학습 목표(어떤 행에 어떤 손실)를 문서에 적지 않았다.",
      `보완 1·2회차의 쌍별 MLP는 학습 사용자 표시(user_seen)를 전체 관측 행으로 계산해, 쌍이 없는 사용자(v2 테스트 ${NNG ? num(NNG.history_no_pairs) : "–"}명)가 학습되지 않은 임베딩으로 점수를 받았다(코드 결함). 감사 기록의 쌍 사용자 수도 실제 수가 아니었다.`,
      "점별·쌍별·목표 정렬 MLP는 학습 사용자 범위가 달라 ‘한 가지씩만 바꾼 비교’가 아니었는데 그렇게 썼고, 범위를 맞춘 비교(공통 학습 사용자)를 보고하지 않았다.",
      `관측 음성 쌍별 MLP도 미통과 시도가 없는 사용자는 미관측 단원을 음성으로 쓰는데(v2 테스트 스냅샷 쌍의 ${OBSNEG != null ? pct(OBSNEG) : "–"}), ‘음성 = 시도했지만 미통과’라고만 적었다.`],
    reject: `‘BCE가 미관측을 0으로 가정한다’(우리 MLP에는 해당 없음), ‘예측값이 0으로 붕괴’(데이터로 반박), ‘결과가 전혀 무효’(과장)는 정정했다. 요구(BPR 재학습)는 모두 수행했다. 그러나 비판의 핵심 주장인 ‘BCE가 근본 원인이고 BPR로 바꾸면 해결된다’는 노트북 세계(v1)에서만 확인되었다. 비판이 평가한 1차본 세계(생성기 v2)에서는 BPR 변형이 점별 MLP를 넘지 못했고(전체 사용자 ${ci(PR2["MLP_BPRU-MLP"])}, 공통 학습 사용자 ${ci(CG(NNG, "MLP_BPRU-MLP"))}), 신경망 최고치도 ${KO[NN2_BEST] || NN2_BEST} ${jo(fmt(R[NN2_BEST].ndcg), "이다/다")}. 그래서 판정은 ‘부분 수용’이다(1회차 검토 뒤 ‘대부분 수용’으로 올렸다가 최종 검토에서 되돌림, 5절).`,
    fix: ["etfrec/neural.py: train_mf_bpr(미관측 음성, 에폭마다 다시 추출, 설정 6개), fit_observed_model의 mlp9_bpr(관측 음성)·mlp9_bpru(미관측 음성 = 비판의 처방)·mlp9_next(주 w에 처음 통과한 단원 vs 그 주까지 통과하지 않은 단원).",
      "etfrec/signals.py next_week_pairs(기준 주 이전 로그만 사용), etfrec/zoo.py 기법군 MF_BPR·MLP_BPR·MLP_BPRU·MLP_NEXT, etfrec/pipeline.py 선택 대상과 QA(두 기준 주에서 각각 학습되었는지).",
      "노트북 재현(v1) 14개 수치는 새 기법군을 더해도 소수점 5자리까지 그대로다(scripts/regression_check.py). 이 문서의 ‘노트북 MLP’에 대한 서술은 노트북을 그 정도로 재현한 etfrec 구현을 근거로 한다.",
      "학습 사용자 범위(최종 검토 반영): 쌍별 MLP(관측·미관측 음성)도 쌍을 만든 뒤 학습 사용자·단원을 쌍 기준으로 다시 정한다. 쌍이 없는 사용자는 목표 정렬 MLP와 같이 콘텐츠 유사도 대체 점수를 받는다. 감사 기록에 쌍 사용자 수·쌍이 있는 단원 수를 남기고, QA pairwise_models_score_only_pair_users(학습 사용자 수 = 쌍 사용자 수)를 추가했다.",
      "학습 행이 상한(train_max_rows)을 넘어 부분표본을 쓸 때도 쌍과 ‘미관측’ 음성 풀은 전체 행으로 만든다(etfrec/signals.py). 현재 번들은 상한보다 작아 영향이 없던 잠재 결함이다.",
      "보고 범위: 각 쌍 비교를 전체 사용자와 네 MLP가 모두 학습한 사용자로 나눠 계산하고, 사용자군(공통 학습, 기록은 있지만 통과 없음, 기록 없음)별 차이를 함께 보고한다.",
      "범위 한정: 새 신경망 변형은 하이브리드의 구성 신호로는 넣지 않았다. 단독 설정은 전역·인구통계 미사용·라우터 선택의 후보였지만 검증 점수가 낮아 선택되지 않았고, v1 재현은 그 결과로 유지된다(구조적 보장은 아니다. 기본 테스트는 커밋된 v1 결과 파일이 노트북 값과 같은지만 확인하고, 코드로 다시 학습해 확인하는 것은 ETFREC_FULL=1 전체 재현 테스트와 scripts/regression_check.py다). BPR MF 설정은 6개(잠재요인 8·16·32 × 정규화 2)다.",
      "중간보고서 3.1절에 기법별 손실·학습 행·음성 정의와 학습 사용자 범위를 적고, 6.3절에 전체·공통 학습 사용자 쌍 비교 표, 사용자군 분해, 해석을 넣었다."],
    change: `아래 표(같은 테스트 사용자에 대한 사용자 단위 쌍 부트스트랩 95% 구간). ‘공통’은 네 MLP가 모두 학습한 사용자(v1 ${NNG1 ? num(NNG1.common) : "–"}명, v2 ${NNG ? num(NNG.common) : "–"}명)이며, 한 가지만 바꾼 비교는 이 열이다.`,
    extra: () => table(["비교(A − B)", "바꾼 것", "v1 전체", "v1 공통", "v2 전체", "v2 공통"], [
      ["BPR MF − 표본 MF", "손실(가중 MSE → BPR)", ci(PR1["MF_BPR-MF"]), ci(CG(NNG1, "MF_BPR-MF")), ci(PR2["MF_BPR-MF"]), ci(CG(NNG, "MF_BPR-MF"))],
      ["MLP 쌍별(관측 음성) − MLP", "손실 형태(학습 범위도 다름)", ci(PR1["MLP_BPR-MLP"]), ci(CG(NNG1, "MLP_BPR-MLP")), ci(PR2["MLP_BPR-MLP"]), ci(CG(NNG, "MLP_BPR-MLP"))],
      ["MLP 쌍별(미관측 음성) − MLP 쌍별(관측 음성)", "음성 정의만(학습 범위 같음)", ci(PR1["MLP_BPRU-MLP_BPR"]), ci(CG(NNG1, "MLP_BPRU-MLP_BPR")), ci(PR2["MLP_BPRU-MLP_BPR"]), ci(CG(NNG, "MLP_BPRU-MLP_BPR"))],
      ["MLP 쌍별(미관측 음성) − MLP", "비판이 처방한 BPR 전체", ci(PR1["MLP_BPRU-MLP"]), ci(CG(NNG1, "MLP_BPRU-MLP")), ci(PR2["MLP_BPRU-MLP"]), ci(CG(NNG, "MLP_BPRU-MLP"))],
      ["MLP 목표 정렬 − MLP", "레이블을 평가 목표로", ci(PR1["MLP_NEXT-MLP"]), ci(CG(NNG1, "MLP_NEXT-MLP")), ci(PR2["MLP_NEXT-MLP"]), ci(CG(NNG, "MLP_NEXT-MLP"))],
      [`쌍 없는 사용자에서 MLP 쌍별(미관측 음성) − MLP`, "콘텐츠 대체 vs 학습 임베딩", `${ci(HG(NNG1, "MLP_BPRU-MLP"))} (${NNG1 ? num(NNG1.history_no_pairs) : "–"}명)`, "–", `${ci(HG(NNG, "MLP_BPRU-MLP"))} (${NNG ? num(NNG.history_no_pairs) : "–"}명)`, "–"],
    ], [3.0, 2.4, 1.8, 1.8, 1.8, 1.8], { caption: "신경망 변형의 쌍 비교(테스트 NDCG@5 차이; ‘공통’ = 네 MLP가 모두 학습한 사용자)", size: 15, zebra: true }) },

  { id: "2.3", sec: "2.3절", short: "정의는 타당(단원 2개 이상). 다양성 상승은 같은 주제의 선수 사슬 때문(꽉 찬 5개 목록에서도 상승)", title: "Diversity@5(주제가 다른 단원 쌍의 비율)의 타당성", verdict: "긍정 평가(해석 보완)",
    quote: "이 정의는 Ziegler 등(2005)이 제안한 리스트 내 유사도(ILS)를 역산한 리스트 내 다양성(ILD)의 철학적 개념과 정확히 일치한다 … 범주형 불일치를 거리로 차용한 것은 합리적이다 … 선수 가드레일이 같은 주제 심화 추천을 억제해 Diversity@5가 0.997로 치솟는 기계적 현상을 정확하게 포착하므로 다양성 평가 체계는 신뢰할 수 있다.",
    units: [
      ["Diversity@5는 ILD의 철학적 개념과 정확히 일치한다", "사실", "개념(목록 안 단원 쌍의 비유사도 평균)이 같다. 정의만 보충한다. 단원이 2개 미만이면 ILD 식의 분모가 0이라 정의되지 않는데 코드는 0을 준다. 비판이 2.1절에서 문제 삼은 ‘정의되지 않는 값을 0으로’와 같은 관례다(현재 번들의 최소 목록 길이는 3이라 해당 행은 없다). 2차본 6.1절에 정의를 명시했다."],
      ["주제의 범주형 불일치를 거리로 쓰는 것은 합리적이다", "사실", `주제는 ${D.catalog.n_topics}개로 서로 겹치지 않는다.`],
      ["가드레일이 같은 주제 심화를 억제해 다양성이 0.997로 오른다", "사실", `데이터로 확인했다. 꽉 찬 5개 목록만 봐도 ${fmt(DIVR.by_len && DIVR.by_len["5"] ? DIVR.by_len["5"].div : null, 3)} → ${fmt(DIVG.by_len && DIVG.by_len["5"] ? DIVG.by_len["5"].div : null, 3)}이고, 같은 주제 쌍이 있는 목록이 ${pct(DIVR.by_len && DIVR.by_len["5"] ? DIVR.by_len["5"].same_topic_rows : null)} → ${pct(DIVG.by_len && DIVG.by_len["5"] ? DIVG.by_len["5"].same_topic_rows : null)}로 줄었다(짧은 목록까지 합한 전체로는 ${pct(DIVR.same_topic_rows)} → ${pct(DIVG.same_topic_rows)}). 같은 주제에서는 수준 n−1이 항상 선수 단원이라 가드레일 아래에서는 주제마다 후보가 사실상 하나만 남는다. 1차본은 이 원인을 설명하지 않았다.`],
      ["다양성 평가 체계는 신뢰할 수 있다", "부분", `정의는 타당하다. 다만 모든 방법이 ${fmt(Math.min(...D.results.map(r => r.diversity)), 2)}~${jo(fmt(Math.max(...D.results.map(r => r.diversity)), 2), "으로/로")} 높아 변별력이 낮고, 주제 중복만 재며 수준 다양성은 재지 않는다.`],
    ],
    prev: "1차본 6.6절: ‘선수 가드레일을 켜면 위반이 0이 되고 다양성이 0.997으로 오르지만 …’ (원인 설명 없음).",
    why: "다양성 상승을 결과로만 적고 원인을 분석하지 않았다. 대응서 초안에서는 상승의 일부를 ‘짧은 목록 효과’로 설명했는데, 지표는 표시된 단원 쌍만으로 계산하므로 목록이 짧다고 다양성이 오르지 않는다. 독립 검토가 목록 길이별로 다시 계산해 이 설명이 틀렸음을 보였고(짧은 목록 몫은 상승분의 약 3% 이하), 비판의 설명이 맞았다.",
    wrong: ["다양성 상승의 원인을 설명하지 않았고, 초안의 설명(짧은 목록)은 틀렸다.", "목록이 2개 미만일 때의 정의와 지표의 천장 효과를 적지 않았다."],
    reject: "없음(긍정 평가). 단원 2개 미만일 때의 정의(0)를 보충하고, 비판이 2.1절과 같은 관례(정의되지 않는 값을 0으로)를 여기서는 받아들인다는 점을 함께 적었다.",
    fix: ["중간보고서 6.1절에 정의(2개 미만이면 0)를, 6.6절에 다양성 상승의 구조적 원인(같은 주제의 선수 사슬)과 지표의 한계를 넣었다.", "보고서 데이터에 목록 길이별 다양성(diversity_by_len)을 추가해 수치로 확인할 수 있게 했다."],
    change: `가드레일 다양성 ${fmt(DIVR.mean, 3)} → ${fmt(DIVG.mean, 3)}(5개 목록 ${fmt(DIVR.by_len && DIVR.by_len["5"] ? DIVR.by_len["5"].div : null, 3)} → ${fmt(DIVG.by_len && DIVG.by_len["5"] ? DIVG.by_len["5"].div : null, 3)}).` },

  { id: "3", sec: "3절", short: "표본 공식은 맞다. 단측 우월성은 비열등성이 아니고, 외생 충격은 편향이 아니라 분산 문제. 7.3절 재작성", title: "온라인 A/B 테스트의 검정력과 현실적 한계", verdict: "수용(통계 표현 정정)",
    quote: "군당 6,949 ≈ 7,000명 산출은 무결하다 … (표) MDE 2.0%p: 이보다 작은 개선 효과는 80% 확률로 탐지 불가 / 유의수준 5%: 우연히 2%p 차이가 발생했다고 오판할 확률 / 3개 군 운영 시 총 20,850명 … 3개 군을 동시에 운영하면 약 21,000명이 필요하고 유입이 느리면 수개월로 장기화되어 외생 변수가 유의성을 심각하게 교란한다 … MDE를 3%p로 타협하거나, 나빠지지 않음만 증명해도 된다면 양측 대신 단측 검정(Z0.05 ≈ 1.64)으로 전환해야 한다.",
    units: [
      ["군당 6,949 ≈ 7,000명 산출은 무결하다", "사실", `정밀한 분위수로 계산하면 6,949.004명이라 올림하면 ${num(AB2)}명이다(1차본 ‘약 7,000명’).`],
      ["MDE 2%p(상대 9.1%)를 80% 확률로 검출한다", "사실", "공식의 의미 그대로다."],
      ["MDE보다 작은 개선 효과는 80% 확률로 탐지하지 못한다", "오류", `MDE보다 작은 효과는 검정력이 80%보다 낮아질 뿐, ‘80% 확률로 놓치는’ 것이 아니다. 군당 ${num(AB2)}명이면 참 효과 1.5%p의 검정력은 ${pct(POW15, 1)}(놓칠 확률 ${pct(1 - POW15, 1)}), 1%p는 ${pct(POW10, 1)}다. 7.3절 설계를 읽는 데 쓰이는 문장이라 정정한다.`],
      ["유의수준 5%는 우연히 2%p 차이가 났다고 오판할 확률이다", "오류", "α는 참 차이가 0일 때 관측 차이의 크기와 무관하게 ‘유의하다’고 판정할 확률이다. 2%p라는 특정 크기와는 관계가 없다(2%p는 검정력 계산에 쓰는 MDE다)."],
      ["3개 군 동시 운영에 약 21,000명이 필요하다", "사실", `비판 자신의 표(군당 6,950명 × 3 = 20,850명)와 같은 계산이다(보정 없이 ${num(3 * AB2)}명). 덧붙이면 대조군 대비 두 비교를 다중성 보정할 때(비교마다 α=2.5%) 군당 ${num(AB2dun)}명, 합계 ${num(3 * AB2dun)}명으로 더 많아진다.`],
      ["유입이 느리면 테스트가 수개월로 길어진다", "사실", "타당한 실행 위험이다. 1차본은 ‘가입 속도에 따라 4~8주’라고만 적고 필요한 하루 유입을 계산하지 않았다."],
      ["장기화하면 외생 변수가 유의성을 심각하게 교란한다", "부분", "동시 무작위 배정에서는 시장 충격이 두 군에 같이 작용하므로 효과 추정이 편향되지 않는다. 실제 문제는 분산 증가, 처치×시기 상호작용, 외적 타당성이다. 대책(코호트 층화·블록 분석)은 그대로 유효하다."],
      ["MDE를 3%p로 타협해 표본을 줄인다", "사실", `군당 ${num(AB3)}명으로 준다. 다만 참 효과가 2%p라면 검정력이 ${pct(POW3, 0)}로 떨어진다는 대가를 함께 적어야 한다.`],
      ["나빠지지 않음만 증명하면 되므로 단측 검정으로 바꿔 표본을 줄인다", "오류", `단측 우월성 검정(군당 ${num(AB2one)}명)은 ‘B가 A보다 낫다’만 검정한다. ‘나빠지지 않음’은 비열등성 검정이며 사전에 정한 마진이 필요하다. 참 차이 0을 가정하면 마진 1%p일 때 군당 ${num(niSize(0.22, 0.01))}명으로 오히려 늘고, 2%p일 때 ${num(niSize(0.22, 0.02))}명이다.`],
    ],
    prev: "1차본 7.3절: ‘통과율 22% → 24%(+2%p) 검출, 유의수준 5%, 검정력 80% 기준 군당 약 7,000명. 가입 속도에 따라 4~8주’.",
    why: "표본 크기 공식에 집중하고 실행 가능성(필요 유입·기간·다중 비교·검정 방향)을 평가 계획의 일부로 보지 않았다. 2차본 초안에서도 비판의 ‘단측 검정 = 나빠지지 않음 확인’ 표현을 그대로 옮겼고, 대응서 초안에는 서로 다른 공식(연속성 보정 유무)으로 계산한 수치(3%p 약 3,200명, 4%p 약 1,850명)를 섞어 적었다. 독립 검토에서 발견해 같은 공식으로 다시 계산했다.",
    wrong: ["실행 계획(유입·기간·순서·중단과 판정 보류 규칙)이 없었다.", "주 지표가 사용자별 이진 결과인지 정의하지 않아 두 비율 Z-검정의 전제가 불분명했다.", "2차본 초안의 검정 방향 설명과 대응서 초안의 수치가 틀렸다."],
    reject: "‘외생 변수가 유의성을 심각하게 교란’과 ‘단측 = 나빠지지 않음’은 정정했다. 실행 위험에 대한 지적의 본질은 모두 수용했다.",
    fix: ["주 지표를 ‘노출 후 7일 안에 퀴즈를 1개 이상 통과한 사용자 비율’(사용자별 이진 결과)로 정의했다.",
      `MDE 2·3·4%p × 양측·단측·비교 2개 보정의 군당 표본 표(${num(AB2)}·${num(AB3)}·${num(AB4)}명 등)와 MDE 3%p의 검정력 대가를 넣었다.`,
      "고정 순서 검정: 1단계 A vs B를 α=5%로 검정해 귀무가설을 기각했을 때만 2단계 B vs C로 넘어간다(두 단계 전체의 1종 오류 5%). 2단계는 B·C에 신규 사용자를 새로 배정하고, 총 유입이 3군 동시 운영보다 많아진다는 대가를 명시했다. 1단계에서 효과가 없을 때 C를 시험하려면 새로 사전 등록하고 별도 α로 보고하는 독립 실험으로 하며, 이 실험은 위 5% 보장 범위 밖이다(최종 검토 반영: 처음에는 같은 표에 ‘2단계 생략’과 ‘C를 별도 실험으로 시험’을 함께 적고 구분하지 않았다).",
      `비열등성 검정과 마진, 단측 검정의 사전 등록 조건, 단계별 기간 상한 8주와 필요한 하루 유입(7일 결과까지 들어오도록 등록 ${ENROLL_DAYS}일 기준 2%p 약 ${num(Math.ceil(2 * AB2 / ENROLL_DAYS))}명, 3%p 약 ${num(Math.ceil(2 * AB3 / ENROLL_DAYS))}명), 상한 도달 시 ‘판정 보류’ 규칙, 1단계 대비를 고른 근거를 적었다.`],
    change: `군당 표본(양측): 2%p ${num(AB2)} · 3%p ${num(AB3)} · 4%p ${num(AB4)}명. 단측 2%p ${num(AB2one)}명. 비열등성(마진 1%p) ${num(niSize(0.22, 0.01))}명.` },

  { id: "4.1", sec: "4.1절", short: "1차본은 ‘증권사 확인’만 적어 실질적 누락. 단일종목 현금 3,000만원(7/31)·교육 3시간과 모의거래 5시간(8/19)까지 반영", title: "레버리지·인버스 ETP 기본예탁금 누락", verdict: "수용",
    quote: "KIFIN 사전교육 수강료 4,000원·약 1시간·이수증 등록은 현행과 정확히 일치한다 … 그러나 기본예탁금 제도를 완벽히 누락했다 … 최소 1,000만원(증권사 규정에 따라 1,500만원 이상) 예탁 자산(현금 및 대용증권)이 있어야 주문이 활성화된다 … 100만원으로 매수하면 즉시 거절된다 … ‘최초 거래 시 최소 1,000만원 이상의 기본예탁금 유지 의무’ 문구가 병기되어야 한다.",
    units: [
      ["KIFIN 4,000원·약 1시간·이수번호 등록은 현행과 일치한다", "사실", "일반 레버리지 ETP 과정 기준으로 맞다. 단일종목 레버리지·인버스는 2026년 8월 19일부터 사전교육 총 3시간과 신규 투자자 모의거래 5시간이 더해졌다(비판 시점에 이미 시행 중이던 단일종목형 요건을 비판은 다루지 않았다)."],
      ["기본예탁금 제도를 완벽히 누락했다", "부분", "1차본 카드에는 ‘기본예탁금 요건은 거래 증권사 안내 확인’이라는 문구가 있었다. 그러나 금액과 ‘미달 시 주문이 들어가지 않는다’는 결과를 적지 않았으므로 실질적 누락이라는 지적은 맞다."],
      ["최소 1,000만원을 예탁해야 한다", "사실", "2020년 도입된 기본예탁금 1,000만원이다."],
      ["증권사 규정에 따라 1,500만원 이상으로 상향되기도 한다", "부분", "해외 상장 레버리지 ETP는 등급별 금액이 증권사마다 다르다는 안내를 확인했지만(부록 A), 구체 금액은 확인하지 못했다. 국내 일반 규정의 상향 여부는 증권사 기준 확인으로 안내한다."],
      ["예탁 자산에 현금과 대용증권을 인정한다", "부분", "단일종목 레버리지·인버스는 2026년 7월 31일부터 현금만 인정한다(대용증권 불인정, 신규·추가 매수 모두, 매도대금은 결제 후 인정). 일반 규정의 인정 자산은 증권사 기준 확인으로 안내한다."],
      ["교육만 마치고 100만원으로 매수하면 거절되는 UX 실패다", "사실", "그대로 수용했다."],
      ["‘최초 거래 시 1,000만원 유지 의무’ 문구를 병기해야 한다", "요구 수용", "더 정확한 조건으로 반영했다(아래)."],
    ],
    prev: "1차본 유형 카드: ‘금융투자교육원(KIFIN) 레버리지 ETP 사전교육 이수(약 1시간, 평생 1회) 후 증권사에 이수번호 등록. 기본예탁금 요건은 거래 증권사 안내 확인. 단일종목 레버리지는 심화교육 추가.’",
    why: "사전교육은 금융투자교육원 자료로 확인했지만 예탁금은 확인하지 못한 채 ‘증권사 확인’으로 넘겼다. 확인하지 못한 사실을 비워 둘 것이 아니라 교육 흐름의 관문으로 명시했어야 했다. 2차본 초안에서도 단일종목형의 시행일(‘8월’, 실제 7월 31일 조기 시행)과 교육 시간(‘총 2시간’, 8월 이후 3시간 + 모의거래 5시간)을 낡은 정보로 적었다. 독립 검토가 지적했고 다시 검색해 확인했다.",
    wrong: ["레버리지 유형의 진입 조건 설명이 불완전했다(교육만 있고 자본 요건이 없음).", "2차본 초안의 단일종목형 시행일·교육 시간·인정 자산 설명이 틀리거나 낡았다.", "진단 퀴즈의 기본예탁금 문항(q20)이 변동성 위험 단원에 연결되어, 소거법으로 쉽게 맞히면 위험 교육 단원이 ‘진단 통과’로 빠지는 역효과가 있었다.", "진단 퀴즈의 정답이 두 번째 보기에 몰려 있었다(1차본 16문항 중 13문항, 2차본 초안 20문항 중 17문항)."],
    reject: "없음. 비판의 ‘1,500만원’·‘대용증권’ 서술은 범위를 나눠 정정했다.",
    fix: ["etfrec/taxonomy.py LEVERAGE_RULES(기준일 2026-10-13): ① 사전교육과 이수번호 등록, ② 기본예탁금 1,000만원, ③ 단일종목형 현금 3,000만원·사전교육 총 3시간·신규 투자자 모의거래 5시간, ④ 해외 상장 레버리지 ETP 사전교육(2025-12-15)·기본예탁금(2026-05-22), ‘요건 미달 시 매수 주문이 들어가지 않음’. 카드 주의 사항 4개.",
      "레버리지 수준 3 단원 제목을 ‘변동성 장세의 레버리지 위험과 거래 요건(사전교육·기본예탁금)’으로 보강하고 학습 요점 본문을 붙였다(etfrec/lessons.py).",
      "q20은 규제 상식 문항이라 수준 판정에만 쓰고 단원을 통과 처리하지 않는다. 한 단원에 문항이 둘이면 둘 다 답하고 맞혀야 통과로 기록하고(하나를 건너뛰면 판정 보류), 수준별 최소 응답 수(수준 1은 5문항, 수준 2·3은 3문항)를 채우지 않은 수준은 판정하지 않는다. 정답 위치는 보기 네 자리에 다섯 개씩 나눴다. 테스트: 한 위치만 골라 찍으면 수준 1이 되는지, q20이 위험 단원을 건너뛰게 하지 않는지, 한 문항을 건너뛰면 단원이 통과되지 않는지, 몇 문항만 골라 답해 높은 수준이 나오지 않는지 확인.",
      "출처 등록부(금융투자교육원)·README·중간보고서 2.2·2.4·5.4절·부록 B·C·F에 반영했다."],
    change: "유형 카드 규제 문구 1줄(‘증권사 확인’) → 요건 4개와 기준일, 주의 사항 4개. 진단 퀴즈는 한 위치만 골라도 수준 1(1차본은 두 번째 보기만 골라도 대부분 정답)." },

  { id: "4.2", sec: "4.2절", short: "ISA·IRP 70% 누락은 사실. ‘400만원 전면 비과세’는 서민형 기준, ‘유일한 대안’은 오류", title: "ISA 계좌 누락과 IRP 위험자산 70% 한도 누락", verdict: "수용(수치 정정, 단원 배치 범위 조정)",
    quote: "연금저축·IRP의 세액공제(연 900만원 한도)와 연금소득세(3.3~5.5%)를 다룬 것은 적절하다 … 그러나 ISA에 대한 언급과 연결 논리가 카탈로그 전체에서 누락되었다 … 순서는 ‘연금저축 → IRP → ISA’ 또는 ‘ISA 선납 후 연금 전환’ … ISA는 최대 400만원까지 전면 비과세, 초과분 9.9% 분리과세로 금융소득종합과세를 회피할 수 있는 유일한 대안 … 만기 자금을 연금계좌로 옮기면 10%(최대 300만원) 추가 세액공제 … ‘ISA와 연금계좌의 시너지’ 단원을 기초·핵심 로드맵에 편입해야 한다 … 시스템이 주식형 중심의 포트폴리오를 IRP에 편입하도록 유도하면서 70% 한도를 설명하지 않으면 사용자는 주문 거부 현상을 맞닥뜨리게 된다.",
    units: [
      ["연금저축·IRP의 세액공제(연 900만원 한도)와 연금소득세(3.3~5.5%)를 다룬 것은 적절하다", "부분", "혜택(세액공제·연금소득세)을 다룬 것은 맞다. 다만 비판이 괄호로 덧붙인 숫자는 1차본에 없었다. 1차본에는 ‘한도 내 세액공제’, ‘연금소득세’라는 표현만 있었다. 2차본에서 숫자와 조건을 넣었다(연금저축 600만원·IRP 합산 900만원, 사적연금 연 1,500만원 이하 3.3~5.5%, 초과 시 종합과세 또는 16.5% 분리과세 선택)."],
      ["ISA가 카탈로그 전체에서 누락되었다", "사실", "1차본 21개 주제에 ISA 단원이 없었다."],
      ["절세 순서는 ‘연금저축 → IRP → ISA’ 또는 ‘ISA 선납 후 연금 전환’이다", "사실", "실무에서 쓰는 순서이며 제도가 정한 순서는 아니다. 비판 안에서도 ‘ISA를 가장 우선 채워야 한다’는 문장과 순서 제시가 엇갈린다. 학습 요점에는 두 방식을 소득·유동성에 따른 선택으로 적었다."],
      ["ISA는 최대 400만원까지 전면 비과세다", "부분", "정정: 일반형 200만원, 서민형·농어민형 400만원이다."],
      ["초과분은 9.9% 분리과세다", "사실", "그대로 반영했다."],
      ["금융소득종합과세를 회피할 수 있는 유일한 대안이다", "오류", "연금저축·IRP도 과세이연 후 연금 수령 때 연금소득세로 과세되므로 ‘유일한’ 대안이 아니다."],
      ["만기 자금을 연금계좌로 옮기면 10%(최대 300만원) 추가 세액공제를 받는다", "사실", "만기 후 60일 안에 옮길 때다."],
      ["‘ISA와 연금계좌의 시너지’ 단원을 기초·핵심 로드맵에 편입해야 한다", "요구 부분 수용", "ISA 기초 단원은 연금·노후(목적별 핵심 2·심화 1), 장기 지수(목적별 핵심 1), 배당·인컴(목적별 핵심 1·심화 1), 분산·안정(심화 1)에 넣었다. 시너지(만기 자금의 연금계좌 전환) 단원은 연금계좌 3을 선수로 두므로 연금·노후의 심화에만 두고, 모든 목적의 필수 기초에는 넣지 않았다. 단기 매매 목적 템플릿에는 ISA를 넣지 않았다(몇 달 안에 쓸 돈이 많아 의무가입 3년과 맞지 않음). 다른 목적이라도 투자 기간이 1년 미만이면 ISA 단원에 의무가입 기간 주의를 붙인다(최종 검토 반영: 처음에는 기간이 아니라 목적으로만 걸렀다)."],
      ["시스템이 주식형 중심 포트폴리오를 IRP에 편입하도록 유도하면서 70% 한도를 설명하지 않으면 주문이 거부된다", "부분", "한도 안내가 빠진 것은 사실이라 수용했다. IRP는 위험자산 총투자한도 70%(계좌 평가액 기준)이고, 한도를 넘으면 위험자산 추가 매수가 제한된다. 카드 문구와 학습 요점에 넣었다. 다만 ‘유도’ 전제는 사실과 다르다. 이 시스템은 계좌별 자산 비중이나 상품을 권하지 않고, 모든 추천 응답에 매수·매도 비권유 고지를 붙인다."],
    ],
    prev: "1차본: 유형 카드 10종의 ‘세금·연금계좌·규제 요약’ 칸에 반복된 연금 문구 ‘연금저축·IRP 편입 가능(국내 상장), 과세이연 후 연금 수령 시 연금소득세’, 용어집 ‘납입액은 한도 내 세액공제’. ISA와 70% 한도는 어디에도 없었다.",
    why: "카탈로그를 수업 노트북의 20개 주제에서 물려받고 커버드콜 주제만 더했다. 세제를 ‘연금계좌’ 한 주제로 묶어 두고 절세 계좌 체계 전체(ISA·연금저축·IRP)의 커버리지를 점검하지 않았다. 2차본 초안에서도 배당·인컴 목적에 ISA 기초 단원을 ‘심화’ 단계에 두었고, 70% 한도의 ‘주문 거부’ 결과는 용어집에만 있고 카드에는 없었다(독립 검토로 발견).",
    wrong: ["절세 계좌 교육의 커버리지와 IRP 투자 한도 설명이 빠졌다.", "2차본 초안의 ISA 배치와 카드 문구가 불완전했다.", "ISA 2(유형·납입 한도) 단원의 선수 단원을 연금계좌로 둔 근거가 약했다(연금 지식은 ISA 3 전환 단원에만 필요)."],
    reject: "‘400만원 전면 비과세’와 ‘유일한 대안’은 정정했다. ISA 단원 배치는 목적별 핵심·심화로 범위를 조정했고(시너지 단원은 연금 심화), IRP 70% 요구는 모두 반영했다. ‘유도’ 전제는 바로잡았다.",
    fix: [`카탈로그 v2에 주제 ‘절세 계좌’ 3단원(ISA 계좌란: 비과세 한도와 분리과세 / ISA 유형·납입 한도·의무가입 기간 / ISA 만기 자금의 연금계좌 전환과 절세 순서)과 선수 관계(분배금 1 → ISA 1 → 2 → 3, ISA 3 ← 연금계좌 3), 출처·개념 태그를 넣었다. 단원 ${PREV.catalog} → ${D.catalog.n_items}개.`,
      "로드맵 템플릿과 목적 친화도에 ISA를 넣고(위 배치), 유형 카드의 연금계좌 문구에 70% 한도·초과 시 매수 제한·연금저축펀드 무제한·세액공제·연금소득세 조건을, 국내주식형 카드에 ‘ISA의 절세 효과는 주로 분배금에서 나온다(손익 통산 취급은 원문 확인)’를 적었다.",
      "학습 요점 본문 4개(ISA 3단원, IRP 70%)와 진단 퀴즈 q17(ISA)·q19(IRP 70%), 자연어 파서의 ISA 키워드, 출처 등록부 주제를 추가했다."],
    change: `카탈로그 ${PREV.catalog} → ${D.catalog.n_items}단원(${D.catalog.n_topics}주제), 선수 관계 ${D.catalog.n_prereq_edges}개, 진단 퀴즈 ${PREV.quiz} → ${D.questions.length}문항(${QUNITS}개 단원), 연금 로드맵 ${D.roadmaps.pension.units_total}단원·약 ${D.roadmaps.pension.minutes_total}분.` },

  { id: "4.3", sec: "4.3절", short: "1차본은 ‘보유기간 과세’ 용어만 있었다. 작은 금액 과세와 비대칭을 본문·카드·퀴즈·단기 매매 로드맵에 반영", title: "국내 상장 해외 ETF 과세의 ‘과표기준가’ 메커니즘 부재", verdict: "수용",
    quote: "국내 상장 해외주식형 ETF의 세금을 ‘매매차익·분배금 배당소득세 15.4%, 금융소득종합과세 대상’으로 정리한 것은 대원칙과 부합하고, 해외 직상장 ETF가 ‘연 250만원 기본공제 후 22% 양도소득세(분리과세)’를 적용받는다는 분류도 올바르다 … 그러나 과표기준가 메커니즘이 누락되었다: 국내 상장 해외/파생형 ETF를 매도할 때 … ‘실제 매매차익’과 ‘과표기준가의 상승분’ 중 더 작은 금액을 기준으로 15.4%가 부과되는 보유기간과세 … 단기 매매자에게 결정적이므로 ‘과표기준가와 매매차익의 딜레마’ 텍스트 콘텐츠를 신설해야 한다.",
    units: [
      ["15.4%·종합과세 서술은 대원칙과 부합한다", "사실", "1차본 서술 그대로다."],
      ["1차본이 해외 직상장 ETF를 ‘연 250만원 공제 후 22% 분리과세’로 분류했다", "부분", "1차본에는 ‘해외 상장 ETF는 양도소득세 22%’만 있었고 250만원 공제·손익통산·분리과세는 없었다. 2차본에서 퀴즈 해설·해외 주식형 카드·학습 요점에 넣었다."],
      ["과표기준가 메커니즘이 누락되었다", "사실", "‘보유기간 과세’라는 용어만 있고 계산 기준이 없었다."],
      ["국내 상장 해외/파생형 ETF는 실제 차익과 과표기준가 상승분 중 작은 금액에 15.4%가 붙는다", "부분", "해외주식형·채권·원자재 같은 기타 ETF에는 맞고, 그대로 반영했다. 그러나 ‘파생형’ 전체에 일괄 적용한 것은 틀렸다. 국내 레버리지·인버스는 상품 구성(장외 스와프 여부 등)에 따라 매매차익 과세 여부가 달라 상품별로 확인해야 한다(2차본 초안도 같은 일반화를 했다가 정정함, 아래). 실제 이익이 있어도 과표기준가가 내렸으면 과세되지 않고, 계좌 밖에서는 손실을 다른 이익과 통산하지 못한다는 비대칭도 함께 적었다."],
      ["단기 매매 투자자에게 결정적이다", "사실", "단기 매매 템플릿의 심화 단계에 해외 ETF 세금 단원을 넣었다."],
      ["‘과표기준가와 매매차익의 딜레마’ 텍스트 콘텐츠를 신설해야 한다", "요구 수용", "학습 요점 본문(딜레마 ①·②, 계산 예시, 해외 직상장과의 차이)을 신설했다."],
    ],
    prev: "1차본 유형 카드: ‘매매차익·분배금 배당소득세 15.4%(보유기간 과세), 연 금융소득 2,000만원 초과 시 종합과세’. 퀴즈 해설: ‘국내 상장 해외주식형·채권·원자재 ETF의 매매차익은 배당소득으로 15.4% 과세된다. 해외 상장 ETF는 양도소득세 22%다.’",
    why: "세금 설명을 대부분의 요약 자료 수준(세율)에서 멈추고 과세 기준의 계산까지 내려가지 않았다. 2차본 초안은 단원 제목·퀴즈·카드 문구만 고쳐 ‘콘텐츠 신설’ 요구를 다 채우지 못했고, 단기 매매 템플릿에 넣지 않았으며, 국내 상장 ‘파생형’ 전체에 같은 규칙을 일괄 적용했다. 국내 레버리지·인버스는 상품 구성(장외 스와프 여부 등)에 따라 과세 여부가 달라 상품별 확인이 필요하다(독립 검토로 발견, 다시 검색해 정정).",
    wrong: ["과세 기준(두 값 중 작은 금액) 설명이 빠졌다.", "2차본 초안의 반영 범위가 요구보다 좁았고 ‘파생형’ 일반화는 근거가 없었다."],
    reject: "없음.",
    fix: ["카탈로그 v2 단원 제목 ‘해외 ETF 세금: 과표기준가·보유기간과세와 양도소득세’와 v2 전용 개념 태그(v1 재현용 태그는 그대로).",
      "유형 카드 세금 문구(TAX_OTHER)에 계산 기준과 비대칭을, 레버리지·인버스 카드에 ‘상품 구성에 따라 과세 여부가 다르니 과세유형 공시 확인’을, 해외 주식형 카드에 해외 직상장 ETF의 양도소득세 체계를 적었다.",
      "학습 요점 본문(etfrec/lessons.py), 진단 퀴즈 q18 신설·q13 해설 보강, 단기 매매 템플릿 심화 단계에 해외 ETF 3 편입, 용어집."],
    change: "세금 단원 1개 보강과 본문 신설, 퀴즈 +1(같은 단원 두 문항은 둘 다 답하고 맞혀야 통과), 카드 문구 3종 보강." },

  { id: "5.1", sec: "5.1절", short: "비공식 호출을 삭제했다. 약관 조항·횟수는 미검증. 기본정보는 공공데이터포털에 있는지 확인되지 않아 수동 파일 경로 유지", title: "KRX 정보데이터시스템 비공식 엔드포인트 호출(크롤링)", verdict: "수용(약관 조항 번호 미검증, 처방은 부분 수용)",
    quote: "본 중간보고서의 아키텍처는 한국거래소 약관을 명백히 위반하는 불법적 요소를 내재하고 있으며 … 4.3절은 비공식 화면용 JSON 엔드포인트(getJsonData.cmd, bld=MDC/STAT/…)를 직접 호출해 파싱한다고 당당히 기술한다 … 법적 분쟁을 야기할 수 있는 치명적 설계 오류다 … 이용약관 제6조·제7조의 크롤링·스크래핑 금지, ‘API 인증키의 담보 사용 및 일 10,000회 초과 호출’ 금지 … IP 차단을 유발한다 … 공공데이터포털 API(15094806, 15094775)가 합법적 통로이므로 KRX 직접 크롤링 모듈을 즉시 삭제하고 공공데이터포털 API 중심 ETL로 전면 이관해야 한다.",
    units: [
      ["비공식 엔드포인트를 직접 호출한다고 기술했다", "사실", "1차본 4.3절의 문장이다(아래 인용)."],
      ["이용약관 제6조·제7조, ‘일 10,000회 초과 호출 금지’", "미검증", "약관 원문을 확인하지 못해 조항 번호와 횟수를 인용하지 않는다. 일 호출 한도는 인증키가 있는 Open API 쪽 조건일 가능성이 있어, 코드에 실행당 호출 상한과 호출 간격을 두고 키의 일 한도는 이용 조건으로 확인하도록 적었다."],
      ["자동 주기 호출은 크롤링으로 간주되어 IP 차단을 유발한다", "부분", "약관·서버 부하 측면의 위험 판단은 타당하다. ‘즉각적인 IP 차단’은 확인하지 못했다."],
      ["공공데이터포털 API가 합법적 통로다", "사실", "서비스키 기반 공식 API다."],
      ["KRX 직접 크롤링 모듈을 즉시 삭제해야 한다", "요구 수용", "삭제했고 테스트로 부재를 확인한다."],
      ["한국거래소 약관을 명백히 위반하는 불법적 요소이며 법적 분쟁을 야기할 치명적 설계 오류다", "미검증", "비공식 화면 엔드포인트의 자동 호출은 약관·서버 부하 측면에서 위반 소지가 크다고 보고 삭제했다(아래). 다만 약관 조항 원문을 확인하지 못해 ‘명백한 위반·불법’이라는 단정은 판정하지 않는다."],
      ["공공데이터포털 API 중심 ETL로 전면 이관해야 한다", "요구 부분 수용", "시세는 공공데이터포털과 KRX Open API(인증키)로 받고 상장종목정보로 종목 코드를 교차 확인한다. 총보수·과세유형 같은 기본정보는 공공데이터포털에 있는지 확인하지 못해 사람이 직접 내려받은 파일을 정규화하는 경로를 유지했다."],
    ],
    prev: "1차본 4.3절: ‘KRX 정보데이터시스템 ETF 전종목 기본정보: 화면이 쓰는 JSON 엔드포인트(getJsonData.cmd, bld=MDC/STAT/standard/MDCSTAT04601)로 전종목 목록을 받아 …’. 4.5절: ‘KRX 데이터의 자동 수집은 개인 학습·연구 범위로 제한하고 대량 수집 전 이용 약관을 확인한다.’",
    why: "자동 수집의 편의를 약관 준수보다 앞에 두었고, 개발 환경에서 한국 기관 사이트에 접근할 수 없어 약관을 읽지 못한 채 ‘비공식’ 표시와 ‘대량 수집 전 약관 확인’이라는 유예 문장으로 넘어갔다. 2차본 초안에서도 Open API 응답을 정규화하면 종목명이 비어 레버리지 ETF가 시장대표형으로 분류되는 결함, ‘일 한도 준수’·‘Excel 지원’·‘괴리율 예시’처럼 코드가 뒷받침하지 않는 문구, 빈 결과를 ‘ok’로 기록하고 옛 파일을 오늘 날짜로 표시하는 문제가 있었다(독립 검토로 발견). 그 뒤 최종 검토에서도 수집 경로의 견고성 결함이 더 나왔다. 쓰는 도중 실패하면 스냅샷이 손상되는데도 ‘기존 파일 유지’로 기록했고, 키 끝의 줄바꿈 때문에 인증키 원문이 기록에 남는 경로가 있었으며, 형식 검사가 없어 다른 화면의 파일이 정상 스냅샷을 덮을 수 있었다(5절 [최종·데이터 수집]). 실패 경로(쓰기 실패·중단·잘못된 입력)를 시험하지 않고 정상 경로만 테스트했기 때문이다.",
    wrong: ["비공식 화면 엔드포인트의 자동 호출을 기본 수집 경로로 설계했다.", "약관 확인을 미룬 채 ‘개인 학습·연구 범위’라는 문장으로 위험을 덮었다.", "2차본 초안의 공식 API 경로에도 정규화 결함과 과장된 문구가 있었다.", "공식 경로도 비상업 이용 조건이라는 점(상용화 시 별도 이용 계약 필요)을 적지 않았다.", "‘기존 스냅샷은 지우지 않는다’는 약속이 쓰기 도중 실패에는 지켜지지 않았고, 인증키와 로컬 경로가 기록·API로 새는 경로가 있었다(최종 검토로 발견)."],
    reject: "약관 조항 번호와 ‘일 10,000회’는 검증하지 못해 인용하지 않았다. 처방 가운데 ‘전면 이관’은 위 이유로 부분 수용했다.",
    fix: FIX9,
    change: CHANGE9 },

  { id: "5.2", sec: "5.2절", short: `준식별자 결합 위험은 사실. 10% 특례는 시행 중이나 요건이 다르고 조문은 미검증. 원시 연령·연소득·시각 미보관, 공개 산출물 k≥5(저장 조합의 ${pct(QSH)}는 k 미만)`, title: "가명정보 처리 가이드라인 위반 위험(k-익명성·망 분리 부재)", verdict: "수용(법령 요건 정정, k-익명화 범위 조정)",
    quote: "4.5절은 ‘성별을 수집하되 운영 라우터에서 제외하며 가명 처리된 사용자 번호만 쓴다’며 개인정보 이슈가 해결된 것처럼 주장한다 … 2026년 3월 전면 개정된 금융위원회 및 개인정보보호위원회의 가명정보 처리 가이드라인에 비추어 단순 속성 삭제는 기준 미달이다 … 나이·소득분위·투자 목적·접속 시간대·테마 ETF 조회 로그가 결합되면 모자이크 효과로 재식별된다 … 2026년 개정된 가이드라인과 개인정보 보호법 특례에 따라, 재식별 가능성을 인지하고도 안전조치를 취하지 않거나 특정 개인을 알아볼 목적으로 데이터를 처리한 경우 전체 매출액의 최대 10%에 달하는 징벌적 과징금을 부과하는 조항(제64조의2 제1항 제6호)이 시행 중이다 … k-익명성을 로그 전처리에 필수로 넣어 일반화하고, 가명처리 부서와 모델 학습 부서의 망 분리와 개인정보 이노베이션 존에 준하는 접근 통제를 설계 문서에 명문화해야 한다.",
    units: [
      ["1차본 4.5절이 가명 번호·성별 제외로 해결된 것처럼 썼다", "사실", "1차본 문장 그대로다(아래 인용)."],
      ["2026년 3월 금융위원회와 개인정보보호위원회가 가이드라인을 전면 개정했다", "부분", "2026년 3월 31일 위험도 기반으로 전면 개정된 것은 개인정보보호위원회의 가명정보 처리 가이드라인으로 확인했다. 금융위원회와의 공동 개정 여부는 확인하지 못했다."],
      ["단순 속성 삭제는 기준 미달이며 준식별자 결합으로 재식별될 수 있다(모자이크 효과)", "사실", "핵심 지적을 그대로 수용했다."],
      ["특례에 따라 (재식별 가능성 인지 후 안전조치 미흡 등의 경우) 전체 매출액의 최대 10% 징벌적 과징금이 시행 중이다", "부분", `10% 특례가 시행 중인 것은 맞다(2026년 3월 10일 공포·9월 11일 시행, 비판은 그 뒤에 쓰였다). 다만 비판이 든 요건은 검색으로 확인한 특례 요건(고의·중과실 3년 안 반복, 1천만 명 이상 피해 등)과 다르다. 일반 상한은 전체 매출액의 3%(2023년 9월 시행)다.`],
      ["근거 조문은 제64조의2 제1항 제6호다", "미검증", "조문 번호를 원문으로 확인하지 못해 인용하지 않는다."],
      ["k-익명성을 로그 전처리에 필수로 넣어 일반화해야 한다", "요구 부분 수용", `범위를 나눠 반영했다. 공개·공유되는 산출물에는 일반화·억제로 k를 맞추는 비식별 내보내기와 학습 QA를 두었다. 번들·API에서는 원시 연령·연소득과 일·분 단위 시각을 저장하지 않지만, 나머지 준식별자 6개(성별·경험·성향·기기·목적·기간)는 원값 그대로라 저장 조합의 ${pct(QSH)}가 k 미만(5명 미만) 셀에 있다. 그래서 학습 환경 밖으로는 export-deid 결과만 반출한다. 모델 학습 입력 자체를 일반화하는 것은 정확도와 맞바꾸는 결정이라 하지 않았고, 대신 가명정보를 접근 통제 환경에서만 처리한다는 원칙과 근거를 적었다.`],
      ["망 분리·권한 분리와 개인정보 이노베이션 존에 준하는 접근 통제를 명문화해야 한다", "요구 수용", "코드로 강제할 수 없는 부분은 ‘조직 정책’으로 구분해 문서화했다(권한·망 분리, 반출 심사, 접근 기록 감사, 외부 결합·공유 때 이노베이션 존 수준 통제, 보관·삭제, 재식별 금지)."],
    ],
    prev: "1차본 4.5절: ‘학습 로그는 가명 처리된 사용자 번호만 쓰고, 성별은 수집하더라도 운영 라우터·운영 설정에서 제외하며 뒤집기 검사로 영향이 없음을 확인한다.’",
    why: "가명 번호와 성별 제외를 개인정보 대응의 전부로 보고, 준식별자 결합이라는 재식별 경로를 설계에서 다루지 않았다. 2차본 초안에서도 점검 대상과 실제 저장 대상이 달랐다. 감사는 구간화한 열을 재는데 번들·API·화면은 원시 연령·연소득과 분 단위 시각을 저장하고 보여 주었고, ‘라우팅 k=20 충족’은 실제 라우터 잎과 다른 조합의 결과였으며, 정책 문장을 ‘현재 번들’의 사실처럼 썼다(독립 검토로 발견). 최종 검토에서도 통제를 우회하는 경로가 나왔다. 운영 로그의 스키마 밖 열(외부 회원 ID·분 단위 시각·IP)이 번들에 그대로 남았고, 반출 표의 행 순서가 가명 번호와 같아 행 번호로 다시 결합되었으며, API로 작은 세그먼트 설정을 골라 특정인의 통과 단원을 알아낼 수 있었고, 숨긴 노드·셀은 함께 공개한 값의 차분으로 복원되었다(5절 [최종·개인정보]). 저장된 값만 점검하고 ‘내보낸 값들을 서로 조합하면 무엇이 나오는가’는 시험하지 않았기 때문이다.",
    wrong: ["개인정보 설계가 정책 문장에 머물고 측정·강제가 없었다.", "2차본 초안의 점검 대상이 실제 저장·노출 대상과 달랐고, 정책을 사실처럼 서술했다.", "현재는 모의 데이터라 개인정보 처리가 없다는 점, 서비스 제공(동의·계약 근거 처리)과 가명정보 특례(통계·연구 재이용·결합·제공)의 구분을 적지 않았다.",
      "‘저장 최소화’·‘k-익명 반출’·‘작은 셀 비공개’가 각각 스키마 밖 로그 열·반출 행 순서·차분 때문에 실제로는 우회될 수 있었고, 인증 없는 학습자 조회 API와 임의 설정 번호 선택이 학습자 단위 정보를 내보냈다(최종 검토로 발견)."],
    reject: "10% 특례의 요건(비판이 든 요건은 확인한 요건과 다름)은 정정하고, 조문 번호와 금융위원회 공동 개정 여부는 확인하지 못해 인용하지 않았다. 로그 전처리 단계에서 k-익명성으로 일반화하라는 요구는 공개·공유 산출물(반출 표·공개 집단표)로 범위를 좁혀 반영했고, 모델 학습 입력은 일반화하지 않았다(위 표 #6, 정확도와 맞바꾸는 결정). 망 분리·접근 통제 요구는 코드가 강제할 수 없어 조직 정책으로 문서화했다.",
    fix: FIX10,
    change: CHANGE10 },

  { id: "서론·결론", sec: "서론·결론", short: "배포 불가라는 판단에는 동의한다. 통계 항목을 ‘모순·왜곡’으로 규정한 부분에만 동의하지 않는다", title: "‘실제 서비스 배포에 치명적 결함’이라는 총평", verdict: "부분 수용",
    quote: "통계적·알고리즘적·금융 도메인적·법률적 오류를 규명했다 … KRX 불법 크롤링 및 가명정보 처리 가이드라인 위반이라는 치명적 법적 리스크를 간과하고 있다 … 네 가지 핵심 도메인(모의 로그 이벤트의 상호 배타성 정규화, BPR 손실과 활성 사용자 기준 NDCG, 세금·규제 콘텐츠 보강, k-익명성과 합법적 API)을 수정·내재화할 것을 강력히 권고한다.",
    units: [
      ["프로젝트는 시의적절하고 학술·실무적으로 타당하다", "긍정", "감사히 받는다."],
      ["실제 서비스로 배포하기에는 결함이 다수 있다", "사실", "우리도 같은 입장이다. 중간보고서 6.7절에 실서비스 전 필요 조건(실제 로그 재평가, 원문 대조와 전문가 검수, 개인정보 법률 검토, 데이터 이용 조건의 상용 범위 확인)을 적었다."],
      ["기술 통계에 산술적 모순이 있다", "오류", "1절 참조(불수용)."],
      ["NDCG 산출이 기준선을 심각하게 왜곡한다", "부분", "2.1절 참조. 방법 간 결론은 그대로였지만 집단 결론은 바뀌었다."],
      ["손실 함수 선택 오류로 비교의 공정성이 훼손되었다", "부분", "2.2절 참조. 같은 프로토콜이라 ‘공정성 훼손’은 아니지만 표준 기준선 부재와 근거 없는 인과 주장은 결함이었다."],
      ["기본예탁금·ISA를 누락했다", "사실", "4.1·4.2절 참조(수용)."],
      ["KRX 불법 크롤링과 가명정보 처리 가이드라인 위반이라는 치명적 법적 위험을 간과했다", "부분", "법적 위험을 간과한 것은 사실이라 수용했다(5.1·5.2절). 다만 ‘불법’·‘위반’ 단정은 약관·법령 원문을 확인하지 못해 판정하지 않는다(미검증)."],
      ["네 가지 권고를 수정·내재화해야 한다", "요구 부분 수용", "BPR·활성 NDCG, 세금·규제 보강, 합법 API와 개인정보 보완은 반영했다. 이벤트 정규화는 생성기에 결함이 없어 생성기는 고치지 않고, 실제 로그와 화면 입력 경로에 정규화를 넣었다."],
    ],
    prev: "1차본 6.7절: ‘모의 데이터의 결과이므로 절대 수치는 실제 학습자 성과가 아니다.’ 4.1절: ‘학습 로그는 실제 서비스 로그가 생기기 전까지 규칙을 공개한 모의 데이터로 대체하고 …’.",
    why: "",
    wrong: ["대응서 초안은 ‘실서비스 효과 검증이 아니다’를 1차본 문구처럼 인용했는데, 이는 화면 고지문이었다. 1차본의 실제 문장으로 바로잡았다.", "초안은 1·2.1·2.2절을 ‘전제 오류’로 한데 묶었는데, 2.1절은 전제가 맞고 추론 일부만 틀렸다.", "초안은 ‘도메인·법률 지적을 모두 반영했다’고 썼지만 당시에는 k-익명성이 점검 수준이었고 2차본에 옛 위험 문구가 남아 있었다."],
    reject: "동의하지 않는 부분은 배포 불가라는 판단이 아니라, 통계 항목을 ‘모순·왜곡’으로 규정한 부분이다.",
    fix: ["이 문서와 중간보고서 2차본(1절 요약, 6.7절 실서비스 전 필요 조건, 부록 E)."],
    change: "—" },
];

// ---------- 문서 ----------
const body = [];
const add = (...xs) => xs.flat().forEach(x => body.push(x));
const count = (k) => CLAIMS.filter(c => c.verdict.split("(")[0].trim() === k).length;
const TALLY = ["수용", "대부분 수용", "부분 수용", "불수용", "긍정 평가"].filter(k => count(k)).map(k => `${k} ${count(k)}건`).join(", ");
add(spacer(1500),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run("ETF 교육 콘텐츠 개인화 추천 시스템", { size: 24, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [run("중간보고서 비판 검토 및 보완 보고서", { size: 42, bold: true, color: GREEN })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [run("지적 11건의 문장 단위 분석 · 사실 확인 · 판정 · 간과 이유 · 잘못된 점 · 보완 내역 · 수치 변화", { size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("작성일: 2026년 10월 19일 (검토 대상: 중간보고서 1차본, 비판 문서 ‘심층 검증 및 비판적 분석 보고서’)", { size: 21 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("작성자: (이름 · 학번 기입)", { size: 21 })] }),
  spacer(1000),
  note([{ t: "결론. ", bold: true }, `11건 중 ${TALLY}이다. 가장 뼈아픈 지적은 금융 도메인(기본예탁금·ISA·IRP 70%·과표기준가), 데이터 접근 방식(비공식 엔드포인트), 개인정보 설계였고, 공통 원인은 ‘확인하지 못한 사실을 비워 두거나 완곡한 문장으로 넘긴 것’이었다. 통계 지적 가운데 ‘산술 모순’은 사실과 달라 불수용했지만, 정답 없는 사용자 처리는 집단 결론을 실제로 바꾸었다(1차본 해석 정정). 손실 함수 지적은 노트북 세계(v1)에서는 맞았지만(미관측 음성 BPR이 MLP 점수를 약 두 배로 올림), 비판이 평가한 1차본 세계(v2)에서는 확인되지 않아 요구한 BPR 기준선은 모두 추가하되 판정은 부분 수용으로 했다. 수용한 항목은 코드·데이터·문서에 반영하고 다시 학습·검증했다(학습 QA ${M.qa}건, 자동화 테스트 ${TESTS}건 중 기본 실행 ${TESTS - 1}건 통과, 노트북 재현 14개 수치 일치). 판정과 보완은 독립 검토를 거쳐 고쳤다(5절).`]),
  pageBreak(),
  new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { after: 160 }, children: [new TextRun({ text: "목차", font: FONT })] }),
  new TableOfContents("목차", { hyperlink: true, headingStyleRange: "1-2" }),
  p("※ Word에서 열면 목차 필드 갱신을 묻는 창이 뜹니다. ‘예’를 누르면 페이지 번호가 채워집니다.", { size: 18, color: GREY }),
  pageBreak(),
);

add(h1("1. 요약표"),
  ...table(["#", "지적(비판 문서 절)", "판정", "핵심 근거", "보완"], CLAIMS.map(c => [c.id, c.title, [vrun(c.verdict, 15)],
    trunc(c.short || c.units.find(u => ["오류", "부분", "사실"].includes(u[1]))[2], 150), trunc(c.fix[0] || "", 110)]),
    [0.8, 2.8, 1.8, 3.9, 3.2], { caption: "지적별 판정 요약", size: 15, zebra: true }),
  p("판정 기준: ‘수용’ = 지적이 사실이고 결과물에 결함이 있어 고쳤다. ‘부분 수용’ = 요구는 반영했으나 지적의 전제나 결론 일부가 사실과 달라 정정한다. ‘불수용’ = 지적의 사실관계가 틀렸다(오해를 부른 표현과 관련 장치는 보완). ‘긍정 평가’ = 비판이 타당성을 인정한 항목. 판정 괄호 안에는 요구를 어디까지 반영했는지를 적는다(예: 요구는 전면 반영했지만 핵심 주장이 실험으로 확인되지 않으면 ‘부분 수용’). 3절의 문장 단위 표에서는 비판의 각 문장을 사실·부분·오류·미검증·이미 충족·요구 수용으로 판정했다."),
);

add(h1("2. 검토 방법"),
  bullet([{ t: "문장 단위 분해: ", bold: true }, "비판 문서를 절로 나누고, 각 절의 문장을 (a) 사실 주장, (b) 결과물에 대한 평가, (c) 요구 사항으로 분리했다. 한 절에 요구가 여럿이면(예: 4.2절의 ISA와 IRP 70%) 모두 따로 판정했다."]),
  bullet([{ t: "1차본 대조: ", bold: true }, "비판이 인용하거나 평가한 1차본 문장을 원문에서 찾아 그대로 옮겼다. 비판이 1차본에 없는 내용을 1차본의 것으로 평가한 경우(4.2절 세액공제 숫자, 4.3절 250만원 공제)도 표시했다."]),
  bullet([{ t: "코드·데이터 대조: ", bold: true }, "주장이 가리키는 코드(파일·함수)를 직접 읽고, 필요한 수치는 학습 번들로 다시 계산했다. 예: 이벤트 생성 규칙(etfrec/synth.py), MLP 학습 행(etfrec/signals.py), NDCG 정의(etfrec/evaluation.py), 목록 길이별 다양성, KRX 수집(etfrec/sources/)."]),
  bullet([{ t: "외부 사실 확인: ", bold: true }, "금융·세제·법령 주장은 2026년 10월 13~14일 웹 검색(보도·기관 안내 요약)으로 확인했고(부록 A), 확인하지 못한 세부(KRX 약관 조항 번호·일 호출 한도, 개인정보보호법 조문 번호와 과징금 특례 요건, 가이드라인 공동 개정 여부)는 단정하지 않았다. 개발 환경에서 한국 기관 사이트 본문을 직접 열 수 없어 검색 요약에 의존한 한계가 있으므로, 원문 대조를 11월 2주 일정에 넣었다(중간보고서 8절)."]),
  bullet([{ t: "보완과 재검증: ", bold: true }, `수용 항목을 코드와 문서에 반영한 뒤 전체를 다시 학습했다(모의 데이터 v2, 설정 ${num(M.configurations)}개, QA ${M.qa}건 통과). 노트북 원본 세계(v1)는 새 기법군을 더해도 14개 수치가 소수점 5자리까지 일치한다. 자동화 테스트는 ${TESTS}건을 모으며 기본 실행에서 ${TESTS - 1}건이 통과한다(노트북 전체 재현 1건은 ETFREC_FULL=1일 때만 실행). 같은 seed로 v1·v2를 다시 학습하면 결과 파일과 모델 상태 해시가 같다(시간 열 제외).`]),
  bullet([{ t: "독립 검토: ", bold: true }, "판정의 편향을 줄이려고 별도 검토자가 각 판정을 비판 문서·코드·데이터에 대조했다. 검토는 판정 검증(1회차 1~2.2절, 2회차 2.3~결론)과 최종 코드·문서 검토(모델·도메인·데이터 수집·개인정보·보고서 수치·화면과 문서·적대적 점검·대응서 판정과 사실)로 나눴다. 검토에서 나온 지적과 처리 결과는 5절에 정리했다."]),
);

add(pageBreak(), h1("3. 항목별 분석"));
CLAIMS.forEach((c, k) => {
  add(h2(`3.${k + 1} ${c.title} (비판 ${c.sec})`),
    p([{ t: "판정: ", bold: true }, vrun(c.verdict), { t: `   (비판 문서 ${c.sec})`, color: GREY, size: 18 }]),
    h3("비판 요지"), quote(c.quote),
    h3("문장 단위 분석"), ...unitTable(c.units, `비판 ${c.sec} 지적의 문장 단위 판정`));
  if (c.prev) add(h3("1차본은 어떻게 썼나"), p(c.prev, { size: 20 }));
  if (c.why) add(h3("왜 간과했는가"), p(c.why));
  if (c.wrong && c.wrong.length) add(h3("무엇이 잘못되었나"), ...c.wrong.map(w => bullet(w)));
  if (c.reject) add(h3("불수용·정정하고 보완에서 제외한 부분"), p(c.reject));
  add(h3("보완 내용"), ...c.fix.map(f => bullet(f)), h3("결과 변화"), p(c.change));
  if (c.extra) add(...c.extra());
});

add(pageBreak(), h1("4. 불수용·정정 항목의 근거 정리"),
  ...table(["비판의 주장", "판단", "근거"], [
    ["이벤트 합(134,041) > 시도(108,777)는 산술 모순이며 생성기 난수 로직 결함", "불수용", `열은 한 시도의 다중 플래그. 차이 ${num(PREV_EXCESS)} = 통과 ${num(PREV.quiz_pass)} + 저장 ${num(PREV.save)} − 미완료·비이탈 ${num(PREV_NCND)}. 모순 행 0건을 QA로 상시 검증`],
    ["이탈과 완료·통과가 동시에 성립하는 행이 있을 개연성", "불수용", `이탈∧완료 ${DS.drop_and_complete}건, 통과∧¬퀴즈 ${DS.pass_without_quiz}건(v1·v2 모두 0)`],
    ["10.2%의 고정된 희소성 제약", "불수용", "밀도는 생성 결과로 계산한 값이며 생성기의 목표가 아님"],
    ["마르코프 체인 전이 확률 수정·세션 ID 기준 1NF 정규화 필요", "불수용(이미 충족)", "생성 규칙이 곧 상태 전이이고 로그는 시도 단위 한 행. 실데이터 경로에는 세션 단위 시도 묶기(events_to_attempts)와 플래그 정규화를 추가"],
    ["정답 없는 사용자 배제가 확립된 표준", "정정", "scikit-learn·TorchMetrics 기본 설정은 0점으로 포함. 관례가 갈리므로 두 기준을 병기"],
    ["0점 산입이 노이즈로 신호를 희석", "정정", "정답 없는 사용자는 모든 방법에서 0이라 상수 배율이며 쌍 비교 차이는 0"],
    ["0점 산입이 A/B 효과 크기 추정을 오도", "불수용", "A/B 표본 크기는 퀴즈 통과율로 계산하며 NDCG와 무관"],
    ["MLP가 미관측 항목을 0(거절)으로 가정", "불수용(표본 MF에는 해당)", "MLP는 관측 시도 행만 학습(음성 = 시도했지만 미통과). 표본 MF는 미관측 표본 0의 가중 MSE"],
    ["밀도 10.2%에서 예측값이 0으로 붕괴", "불수용", `학습 행 통과 비율 ${pct(mlpPos)}, 학습 손실 ${mlpAud ? fmt(mlpAud.loss_last, 3) : "–"} < 상수 예측 ${bce0 ? fmt(bce0, 3) : "–"}`],
    ["BPR 없이는 딥러닝 결과가 학술적으로 전혀 무효", "정정(BPR은 추가)", "같은 프로토콜의 수업 레시피 성능으로는 유효. BPR 계열 4개를 추가해 범위를 넓힘"],
    ["외생 변수가 A/B 유의성을 심각하게 교란", "정정", "동시 무작위 배정이면 효과 추정은 편향되지 않음. 문제는 분산·처치×시기 상호작용"],
    ["MDE보다 작은 효과는 80% 확률로 탐지 불가", "정정", `검정력이 80%보다 낮아질 뿐이다(군당 ${num(AB2)}명이면 1.5%p ${pct(POW15, 0)}, 1%p ${pct(POW10, 0)})`],
    ["유의수준 5% = 우연히 2%p 차이가 났다고 오판할 확률", "정정", "참 차이가 0일 때 유의로 판정할 확률이며 차이의 크기와 무관"],
    ["나빠지지 않음만 증명하면 되므로 단측 검정", "정정", `단측 우월성 ≠ 비열등성. 비열등성은 마진 필요(1%p면 군당 ${num(niSize(0.22, 0.01))}명)`],
    ["1차본이 세액공제(연 900만원)·연금소득세(3.3~5.5%)를 다룸", "부분 정정", "혜택은 다뤘으나 숫자는 없었음(2차본에서 추가)"],
    ["ISA 최대 400만원 전면 비과세", "정정", "일반형 200만원, 서민형·농어민형 400만원"],
    ["ISA가 금융소득종합과세를 회피할 유일한 대안", "정정", "연금저축·IRP도 과세이연 후 연금소득세"],
    ["시스템이 주식형 중심 포트폴리오를 IRP에 편입하도록 유도", "정정", "계좌별 비중·상품을 권하지 않고 모든 추천 응답에 비권유 고지. 70% 한도 안내 누락은 수용"],
    ["국내 상장 해외/파생형 ETF 매도 시 작은 금액에 15.4%(보유기간과세)", "부분 정정", "해외주식형·채권·원자재에는 맞음. 국내 레버리지·인버스(파생형)는 상품 구성에 따라 과세 여부가 달라 일괄 적용은 틀림"],
    ["1차본이 해외 직상장 ETF를 250만원 공제 후 22%로 분류", "정정", "1차본은 ‘양도소득세 22%’만 적음(2차본에서 공제·통산·분리과세 추가)"],
    ["KRX 약관 제6조·제7조, 일 10,000회 초과 호출 금지", "미검증(조치는 수용)", "원문 미확인으로 인용하지 않음. 비공식 호출 제거와 실행당 호출 상한은 실행"],
    ["한국거래소 약관을 명백히 위반하는 불법적 요소", "미검증(위반 소지는 인정)", "자동 호출의 위반 소지가 커서 삭제했지만 약관 조항 원문은 확인하지 못해 ‘명백한 위반·불법’ 단정은 판정하지 않음"],
    ["가이드라인을 금융위원회와 개인정보보호위원회가 개정", "미검증", "2026-03-31 위험도 기반 전면 개정은 개인정보보호위원회 가이드라인으로 확인. 금융위원회와의 공동 개정 여부는 확인하지 못함"],
    ["특례에 따라 전체 매출액 최대 10% 과징금이 시행 중(제64조의2 제1항 제6호)", "부분(요건 상이)·조문 미검증", "10% 특례는 2026-03-10 공포·09-11 시행으로 시행 중이 맞음. 비판이 든 요건은 확인한 요건(고의·중과실 3년 안 반복, 1천만 명 이상 피해 등)과 다름. 일반 상한은 3%. 조문 번호는 미확인"],
  ], [4.4, 1.9, 6.2], { caption: "불수용·정정 항목", size: 16, zebra: true }),
);

const REVIEW_ROWS = [
  ["[1회차·1절] 판정은 타당하나 비판의 수치만으로 모순이 아님을 보이는 산술 분해, ‘고정 희소성’ 반박, 점수 규칙(최댓값)과 반복 시도 합산 공개, 운영 로그·화면 입력 경로의 보장 범위가 빠졌다", "모두 3.1절과 중간보고서 4.4절에 넣었다. 화면 입력 경로의 이탈∧완료 결함과 운영 로그 정규화 부재는 코드로 고쳤다."],
  ["[1회차·2.1절] ‘편차 축소’는 절댓값 기준으로 사실이며, 신뢰구간 동일은 항등식이 아닌 경험적 확인이다. 집단 비교에서는 결론이 뒤집힌다(학습활동). 활성의 정의(후보 안 정답)가 비판의 정의와 다르다. ‘확립된 표준’은 과장이다", "판정 문구를 고치고, 집단별 활성 열과 6.5절 정정, 활성 정의와 인원 차이(통과 기록 기준 vs 후보 기준) 공개, 구현 관례(scikit-learn·TorchMetrics) 근거를 넣었다."],
  ["[1회차·2.2절] 표본 MF는 BCE가 아니라 가중 MSE이고 0.0698은 관측 MF의 수치다. 관측 음성 쌍별 MLP는 비판의 BPR이 아니다. 목표 정렬 학습이 구현되지 않았다. 붕괴 주장 미대응. 신경망 변형이 하이브리드에 들어가지 않는 범위 한정", "미관측 음성 BPR MLP와 목표 정렬 MLP를 구현해 쌍 비교했고, 그 결과로 판정을 한때 ‘대부분 수용’으로 올렸다(최종 검토에서 v2 결과로는 확인되지 않아 ‘부분 수용’으로 되돌림, 아래 [최종·대응서 판정과 사실] 행). 손실·학습 행 정의를 문서화하고 범위 한정을 적었다."],
  ["[2회차·2.3절] 다양성 상승을 ‘짧은 목록 효과’로 설명한 대응서 초안이 틀렸고, 2차본에 해석이 들어가지 않았다", "목록 길이별로 다시 계산해 구조적 원인(같은 주제의 선수 사슬)으로 고쳤다. 정의(2개 미만 0)와 천장 효과도 적었다."],
  ["[2회차·3절] 대응서 초안의 수치(3,200·1,850)가 다른 공식에서 왔고, ‘단측 = 나빠지지 않음’ 혼동, 단계 배정의 진입 조건·총 유입, 다중 비교, 주 지표 정의, 검정력 대가, 외생 변수 전제가 빠졌다", "같은 공식으로 다시 계산하고 7.3절을 다시 썼다(고정 순서 검정, 비열등성·마진, 유입·기간·판정 보류, 1단계 대비의 근거)."],
  ["[2회차·4.1절] 단일종목 3,000만원 시행일(7월 31일)·교육 시간(총 3시간+모의거래 5시간)·현금만 인정·해외 레버리지 ETP 예탁금 시점(5월 22일)이 틀리거나 낡았다. q20이 위험 단원을 건너뛰게 한다. 정답 위치가 몰려 있다", "다시 검색해 문구를 고치고 기준일을 달았다. q20은 수준 판정 전용으로 바꾸고, 정답 위치 균형·단원 단위 채점과 테스트를 넣었다."],
  ["[2회차·4.2절] ISA 배치(배당·인컴에서 기초 단원이 심화), 같은 단원 두 문항의 중복 집계, 보고서의 낡은 숫자(63단원·16문항), 연금소득세 조건, 자연어 파서·출처 등록부 누락, ISA 2의 선수 관계, ‘유일한 대안’ 미정정", "배치와 선수 관계를 고치고, 중복 집계를 없애고, 숫자를 데이터에서 읽게 바꾸고, 조건과 키워드·등록부를 보강하고, 정정표에 넣었다."],
  ["[2회차·4.3절] ‘딜레마’ 텍스트 콘텐츠가 신설되지 않았고, 단기 매매 템플릿에 없으며, ‘파생형’ 전체에 같은 규칙을 일반화했다. 수준 3 판정 문턱이 같은 단원 두 문항으로 낮아졌다", "학습 요점 본문을 신설하고, 단기 매매 템플릿에 넣고, 레버리지 과세를 상품별 확인으로 고치고, 수준 3 조건을 ‘서로 다른 주제 2개 이상 + 정답률 60%’로 바꿨다."],
  ["[2회차·5.1절] Open API 응답 정규화에서 종목명이 비어 분류가 틀린다. ‘일 한도 준수’·‘Excel’·‘괴리율 예시’ 문구를 코드가 뒷받침하지 않는다. 빈 결과를 ok로 기록하고 옛 파일을 오늘 날짜로 표시한다. 상용 범위가 빠졌다. 보고서에 옛 위험 문구가 남았다", "5.1절 보완 내용의 코드 변경으로 고쳤다. 별도로 계획한 구현 검증은 실행되지 못했고, 그 역할은 최종 검토의 데이터 수집 점검이 맡았다(아래 [최종·데이터 수집] 행)."],
  ["[2회차·5.2절] 감사는 구간 열을 재는데 번들·API·화면은 원시 연령·연소득·분 단위 시각을 저장·노출한다. ‘라우팅 k=20 충족’은 실제 라우터 잎과 다른 조합이다. 일반화가 적용되지 않고 QA에 개인정보 검사가 없다. 정책을 사실처럼 썼다", "5.2절 보완 내용의 코드 변경으로 고쳤다. 구현 검증의 역할은 최종 검토의 개인정보 점검이 맡았다(아래 [최종·개인정보] 행)."],
  ["[2회차·결론] 대응서 초안이 화면 고지문을 1차본 문구로 인용했고, 2.1절을 ‘전제 오류’로 묶었고, ‘모두 반영’을 과장했다", "1차본 원문으로 바꾸고 판정 근거를 나눠 적었다."],
];
// 최종 검토(모델·도메인·데이터 수집·개인정보) 지적과 처리. 수치는 재학습한 번들에서 읽는다
const NSRC = (D.tests_per_file || {})["tests/test_sources.py"];
const UTX0 = ((D.privacy_summary || {}).users_table || {}).quasi_extended || null;
const FINAL_ROWS = [
  ["[최종·모델] 쌍별 MLP가 쌍에 나오지 않은 사용자(학습 주에 통과가 없는 사용자)를 학습된 사용자로 표시해, 학습되지 않은 임베딩으로 점수를 매겼다. 그래서 점별·쌍별 MLP 비교는 한 가지만 바꾼 비교가 아니었고, v2의 ‘차이 없음’ 결론과 목표 정렬 MLP 해석이 이 처리에 좌우되었다",
    `학습 사용자를 쌍 기준으로 다시 정하고(쌍이 없는 사용자는 콘텐츠 대체 점수) QA를 추가한 뒤 v1·v2를 다시 학습했다. v2 전체 결론은 ‘유의하게 나빠짐’(${ci(PR2["MLP_BPRU-MLP"])})으로 바뀌었고, 공통 학습 사용자 비교(${ci(CG(NNG, "MLP_BPRU-MLP"))})와 사용자군 분해를 두 보고서에 넣었다. v1 결론은 그대로다(${ci(PR1["MLP_BPRU-MLP"])}).`],
  ["[최종·모델] 표 13이 QA에 없는 누수 검사·재현성 해시 비교·오프라인/온라인 일치를 QA 항목처럼 적었다. 학습 행을 부분표본할 때 ‘미관측’ 음성 풀이 부분표본 기준이라 실제로 시도한 단원이 음성으로 뽑힐 수 있었다(잠재 결함). 이벤트 정규화의 ‘고친 행 수’가 플래그 수정 건수의 합이었고, 한 행만 고쳐도 입력 점수 전체를 다시 계산했다",
    `QA에 누수 검사(기준 주 이후 행의 모든 열을 섞고 더한 로그·이후 행을 지운 로그로 만든 특징 저장소가 모든 필드에서 같음)와 쌍별 모델의 학습 범위 검사를 넣고(QA ${M.qa}건), 표 13을 실제 QA 분류로 고쳤다. 재현성은 같은 seed로 v1·v2를 다시 학습해 결과 파일과 상태 해시가 같음을 확인했다. 쌍과 음성 풀은 전체 행으로 만들고, 고친 행은 행 단위로 세며 고친 행만 다시 채점한다.`],
  ["[최종·모델] 민감도 실험의 ‘역전 확인’은 95% 구간이 0을 포함해 확인된 결과가 아니었고, 표의 ‘주당 퀴즈 통과’는 4주 합계였다. 표 4의 기법 설명(인기 점수, 세그먼트 인기 λ 격자, 규칙 부분, CF 격자, 검증 1위의 목적 일치 포함, 잎 최소 20명)과 6.1절의 학습 기간(테스트용 모델은 0~2주로 다시 학습)이 코드·선택 결과와 달랐다",
    "‘점 추정치는 역전되었지만 95% 구간이 0을 포함한다’로 고치고 열 이름을 바꿨다. 표 4·13과 6.1절을 설정 격자, 선택된 설정 이름, 실제 학습 기간에 맞췄다."],
  ["[최종·모델] 이 문서의 테스트 수(수집 수를 통과 수처럼 씀), 1차본 표본 MF 값(0.0687 → 0.0686), 그림 번호(그림 4·7 → 9·11)가 틀렸다. 중간보고서 6.5절의 목적 집단 1위는 전체 기준에서만 맞았다. ‘신경망 변형은 라우터 후보가 아님’은 사실과 달랐다(후보였지만 선택되지 않음)",
    "모두 고쳤다. 테스트 수는 수집·통과·옵션을 나눠 적고, 목적 집단은 두 기준의 1위를 함께 적었다. 기본 테스트에 커밋된 v1 결과 파일이 노트북 값과 같은지 보는 검사를 넣었다(코드로 다시 학습해 확인하는 것은 ETFREC_FULL=1 전체 재현과 scripts/regression_check.py)."],
  ["[최종·도메인] ‘레버리지 일일 복리’를 모든 목적의 필수 기초 개념이라고 썼지만 공통 필수 기초에는 ‘레버리지·인버스 ETF란’만 있었다(1차본부터). 페르소나 표의 로드맵 서술과 규모가 페르소나 설정이 아닌 공통 설정으로 계산되어 실제와 달랐다",
    `공통 필수 기초에 ‘일일 수익률 복리와 음의 복리 효과’를 넣고 다시 학습했다. 페르소나 표는 페르소나마다 목적·성향·기간·진단 답안으로 다시 계산했다(예: 페르소나 A ${D.personas && D.personas.A ? D.personas.A.units_total : "–"}단원).`],
  ["[최종·도메인] 진단 퀴즈가 두 문항 단원에서 한 문항만 답해도 통과로 기록했고(과표기준가·IRP 70% 문항을 건너뛰어도 통과), 답한 문항 수에 하한이 없어 네 문항만 맞혀도 수준 3이 나왔다. 화면 배지와 로드맵 메모는 정답 수를 전체 20문항으로 나눠 다른 표시와 분모가 달랐다",
    "단원 문항을 모두 답하고 맞혀야 통과(아니면 판정 보류), 수준별 최소 응답 수(5·3·3)를 넣고, 표시를 ‘정답/답한 문항(전체 20문항)’으로 통일했다. 각 경우를 테스트로 고정했다."],
  ["[최종·도메인] 유형 카드의 ‘적합 목적’과 ‘이 목적에 권장’·로드맵 연결이 서로 다른 목록에서 나와 4개 유형에서 어긋났고, 안정 성향 학습자에게도 위험 5 유형(레버리지·인버스)에 ‘권장’이 붙었다",
    "적합 목적을 로드맵 템플릿에서 파생해 한 원천으로 만들고, 안정 성향이면 위험 5 유형을 ‘학습용(권장 아님)’으로 표시한다. 일치 여부를 테스트한다."],
  ["[최종·도메인] 자연어 파서가 ‘투자 경험 1~3년’을 3년 이상으로 읽고 경험 문구로 투자 기간까지 바꿨다(화면 예시 9개 중 4개, 그림 4 포함). 커버드콜 키워드가 없었고, ‘연금 ETF’가 ‘금 ETF’로, ‘6개월’이 요청 개수 6으로, ‘보수적’이 비용 주제로 읽혔다. 따옴표 뒤 다음 절의 ‘통과’까지 읽었고 ‘5,000만원’ 소득을 읽지 못했다",
    "경험과 기간 표현을 분리하고 긴 표현을 먼저 찾게 했으며, 커버드콜 키워드·단어 경계·‘개월’ 제외·절 경계·쉼표 소득을 고쳤다. 예시 9개의 기대값 전체와 각 오탐을 테스트로 고정하고 그림 4를 다시 캡처했다."],
  ["[최종·도메인] 용어집이 보유기간과세를 파생형 전체에 일괄 적용했고, ‘ISA 효과는 분배금에 한정’을 단정했으며, 확인 사실에 없는 수치(사전교육 ‘평생 1회’·‘과정별 4,000원’, 적격 TDF 한도 예외, 총보수 0.01~0.6%대)를 단정형으로 썼다. q20 해설과 학습 요점이 단일종목형의 날짜(7월 31일 현금 요건, 8월 19일 교육·모의거래)를 섞었고 해외 레버리지 ETP 예탁금의 ‘기존 거래자 제외’를 뺐다",
    "용어집을 ‘해외주식형·채권·원자재(레버리지·인버스는 상품별 확인)’로 고치고, ISA 문구는 ‘주로 분배금’으로 낮추고 손익 통산 적용 여부를 원문 대조 목록에 넣었다. 출처 없는 수치는 지우거나 ‘금융사·기관 안내 확인’으로 낮췄고, 날짜를 나누고 빠진 조건을 넣었다."],
  ["[최종·도메인] 원자재 키워드 ‘금’이 ‘금융’ ETF를 원자재로 분류했다. 투자 기간이 짧은 학습자에게 ISA 의무가입 기간 주의가 없었다(목적으로만 거름). 카탈로그 CSV의 선수 단원 ‘-1’이 마지막 단원을 가리켰고 순환 검사가 없었다",
    "‘금현물·금선물·골드’ 같은 구체 키워드로 바꾸고 분류 테스트를 넣었다. 기간이 1년 미만이면 ISA 단원에 주의를 붙인다. 선수 단원은 범위 안의 다른 단원만 받고 순환을 검사한다."],
  ["[최종·데이터 수집] 스냅샷을 바로 덮어써서, 쓰는 도중 실패하면(디스크 가득 참·인코딩 오류) 기존 파일이 손상되는데도 ‘기존 파일 유지’로 기록했다. 데이터 파일과 provenance.json을 따로 저장해 중단되면 새 파일이 옛 기준일로 표시되었고, 다시 쓰지 않은 파일의 ‘일부만 받음’ 표시가 사라졌다. 형식 검사가 없어 다른 화면의 파일이나 필드 이름이 바뀐 응답이 정상 스냅샷을 덮었다",
    "임시 파일에 다 쓴 뒤 교체하고, 파일마다 내용 해시를 기록하며 바꾼 직후 기록을 저장한다(끊기면 complete: false, 해시가 다르면 ‘기록 불일치’ 표시). 일부만 받음 표시를 승계하고, 형식 검사를 통과하지 못하면 fail(schema)로 기록하고 기존 파일을 지키며, 읽지 못하는 스냅샷은 샘플로 내려간다."],
  ["[최종·데이터 수집] 키 끝의 줄바꿈 때문에 KRX 인증키 원문이 오류 문구로 provenance.json과 터미널에 남는 경로가 있었고, 키를 명령줄 인자로도 받았다. API 응답에 로컬 절대 경로와 원시 오류 문구가 실렸다. 공공데이터포털의 오류 응답을 ‘0행·휴장일’로 기록했고, 짧은 쪽에서 멈추면서 멈춘 이유를 늘 ‘페이지 상한’으로 적었다",
    "키는 앞뒤 공백을 지우고 형식을 검사하며 오류 문구에서 가린다. 키는 환경변수로만 받는다. API에는 라벨·기준일·상태 같은 필요한 필드만 보낸다. 응답 봉투를 검사하고, totalCount를 알면 짧은 쪽에서도 계속 받으며 멈춘 이유와 진행 상황을 기록한다."],
  ["[최종·데이터 수집] 샘플 CSV가 패키지 데이터에 빠져 설치본에서는 서버가 뜨지 않았다. CLI와 서버의 스냅샷 폴더 기본값이 달랐고 날짜 인자를 검사하지 않았다. ‘엔드포인트를 설정으로 바꿀 수 있다’는 사실이 아니었고, README 한계 절은 Excel 지원과 어긋났다. 이 문서의 5.1·5.2 행은 있지도 않은 ‘구현 검증 행’을 가리켰다",
    `샘플을 패키지 데이터에 넣고 휠로 확인했다. 폴더 규칙을 하나로 맞추고(serve --sources-dir) 날짜는 실제 날짜만 받는다. 엔드포인트는 환경변수로 바꿀 수 있게 했고, README와 이 표의 참조를 고쳤다. 수집 테스트는 ${NSRC != null ? NSRC : "–"}건이다.`],
  ["[최종·개인정보] 운영 로그를 train --data로 읽으면 외부 회원 ID·분 단위 시각·IP 같은 학습 스키마 밖 열이 번들 로그에 그대로 남았다(QA는 day·minute 이름만 봤고 감사는 프로필 열만 봤다). export-deid 표의 행 순서가 가명 번호와 같아(i행 = 학습자 i) 매핑표·학습자 표와 행 번호로 다시 결합되었다",
    "학습 입력을 읽을 때 스키마 밖 열을 버리고 이름을 데이터 요약에 남기며, 번들 로그는 허용 열만 남기고 QA가 ‘로그 열 ⊆ 허용 목록’을 확인한다. 감사는 로그 열과 서빙 학습자 표의 열까지 분류한다. 반출 표는 반출 값으로 정렬해 원래 순서를 지운다."],
  [`[최종·개인정보] API가 설정 ${num(M.configurations)}개 중 아무 번호나 받아, 5변수 세그먼트 인기처럼 한 명뿐인 칸으로 계산되는 설정과 세그먼트 덮어쓰기로 특정인의 통과 단원을 그대로 얻을 수 있었다(검토자 재현 9명 중 9명). 인증 없는 학습자 조회 API가 기준 학습자 전원의 학습자 단위 표를 내보냈다`,
    `API로 고를 수 있는 기법을 화면의 기법 목록(기법군 1위·라우터)으로 제한하고 임의 설정 번호는 개발 모드·CLI에서만 받는다. 학습자 조회 API는 로컬 실행에서만 기본으로 켜고(다른 주소는 --expose-learners), 감사에 학습자 표의 확장 조합(준식별자 8개 + 학습 시간대 + 관심 주제) k를 기록하며${UTX0 ? `(5명 미만 칸 ${pct(UTX0.share_below_k)})` : ""}, 서빙 API 접근 통제를 조직 정책에 넣었다.`],
  ["[최종·개인정보] 추천 경로의 정확한 n·원시 평균, 공개 집단표와 방법별 합계의 차분으로 숨긴 노드·셀을 복원할 수 있었다. 저장 설계 가림이 설계 이름·목록 안 문장·‘45세 이상’·‘연소득은 7000만원’·‘1억 2천만원’·이벤트의 일·시·분을 놓쳤다. 매핑표 경로 검사가 심볼릭 링크로 우회되었고, 문서의 키 입력 예가 셸 기록에 키를 남겼다. 이 문서의 5.2절은 로그 k-익명화를 범위 조정했는데도 ‘요구는 모두 반영’이라고 썼다",
    "경로 출력은 크기 구간만 보이고 원시 평균을 내보내지 않으며, 집단표는 한 변수에서 하나만 숨기면 하나를 더 숨긴다(보완 억제, QA 확인). 가림을 설계 이름·모든 문자열·여러 표기·이벤트 시각으로 넓혔다. 매핑표 경로는 실제 경로로 비교한다. 키 입력 예를 read -rs로 바꿨다. 5.2절 판정을 ‘수용(범위 조정)’으로 고치고 범위를 적었다."],
  ["[최종·보고서 수치] 중간보고서 7.3절은 A/B 대조군 A를 ‘세그먼트 인기’로 정의해 놓고 1단계 대비 근거에는 전역 인기 값을 써서, 가드레일을 켠 운영 라우터(B)가 대조군보다 높은 것처럼 읽혔다. 실제 세그먼트 인기 설정은 테스트 주차에서 B보다 유의하게 높다",
    `대조군 A(성별을 쓰지 않는 세그먼트 인기 설정 중 검증 1위)를 평가 전용 행으로 학습 결과에 넣고(서빙 기법 목록에는 넣지 않음, QA ${M.qa}건) v1·v2를 다시 학습했다. 기존 결과는 모두 그대로다. 근거는 ‘오프라인 C > A > B, B − A ${ci(PR2["RouterNoGender+prereq-ABControl"])}’로 고치고, 그래도 B를 먼저 시험하는 이유(선수 효과는 기록 재생으로 잴 수 없음)와 양측 검정을 주 비교로 두는 이유를 적었다.`],
  ["[최종·보고서 수치] 중간보고서가 1차본을 ‘손실 함수가 아니라 목표 불일치’라고 인용했지만 1차본 원문은 ‘모델 결함이 아니라 목표 불일치’다. 생성기의 단원 선택 효용에 없는 ‘선수 미이수’ 항을 적었다. 그 밖에 그림 2의 ‘16문항·단원 21개’(1차본 값), 그림 12의 ‘후보 5개 미만’ 라벨(실제는 목록 5개 미만 비율), 표 번호 참조(표 19 → 표 20), 콜드스타트의 사용자 CF 점수, 후보 정의에 섞인 목록 후처리 규칙, 로드맵 우선순위(다음 단계가 아니라 이후 단계 0.7), 모든 라우터에 단조 증가로 쓴 λ 곡선, 일정표의 원인 분석 범위와 점별 점수 혼합 비교 누락, 두 표의 퀴즈 확장 목표 불일치, 다양성의 꽉 찬 목록 값, 페르소나 표의 단원 목록 누락, 누수 검사 범위, 2차본 표지 날짜가 틀렸다",
    "모두 고쳤다. 인용은 원문으로 바꾸고, 그림 문구·페르소나 단원 목록·퀴즈 확장 목표는 데이터에서 생성하며, 표 번호를 실제 표에 맞췄다. 2차본 표지는 제출일 2026년 10월 19일(1차본 10월 13일)로 고쳤다."],
  ["[최종·화면과 문서] 샘플 종목 CSV가 .gitignore의 ‘data/’ 규칙(모든 깊이의 data 폴더)에 걸려 한 번도 커밋되지 않았다. 작업 폴더에만 파일이 있어 테스트가 통과했지만, 깨끗한 체크아웃에서는 서버가 뜨지 않고 테스트 28개가 실패했다. 화면은 학습자 조회 403과 시뮬레이션·비교 요청 실패를 표시하지 않고 ‘계산 중…’에 멈췄고, 6단계 안내문은 수준 가드레일까지 ‘+prereq’ 행으로 따로 쟀다고 적었다. API는 guardrail을 생략하면 화면 기본과 다른 가드레일을 썼고, 범위 밖 통과 가정 번호에 500을 냈다(음수는 마지막 단원을 통과로 처리). README·CLI 도움말의 카탈로그 단원 수(63), 로드맵 표, UI 점검 명령, 보고서 빌드 방법이 실제와 달랐고, 보고서 빌드 스크립트가 이 세션의 경로에 묶여 있었다",
    "규칙을 저장소 루트의 data/로 좁히고 샘플을 커밋했으며, 파일이 git에 실제로 있는지 테스트한다(샘플이 없어도 서버는 빈 표와 이유를 보이며 뜬다). 화면은 오류 문구를 그 자리에 표시하고, guardrail 생략은 화면 기본과 같게, 통과 가정은 범위 밖이면 422로 했다. 문서를 실제 동작에 맞추고, 보고서 빌드는 저장소 기준 경로와 docs/report/build/build.sh 한 번으로 돌게 했다. 그림 크기는 이미지 헤더에서 읽는다(직전 빌드에서 그림 10이 세로로 약 4% 눌려 있던 것도 바로잡혔다)."],
  ["[최종·적대적 점검] 학습자 조회를 끈 서버에서도 추천·비교·로드맵·유형 API가 learner_id를 받아 학습자 프로필과 통과 단원을 돌려줘, 번호를 바꿔 가며 학습자 표를 열거할 수 있었다. 저장 설계 가림이 키워드 없는 금액에서 ‘1억 2천만원’의 ‘1억’을 남기고 나머지를 다른 분위로 표기했다. 진단 퀴즈가 최소 응답 수 미달로 판정을 보류한 수준을, 같은 결과의 진단 통과 이벤트가 수준 갱신 규칙으로 다시 올렸다(수준 2 문항 하나만 맞혀도 추천 수준 2). 학습 로그의 understood 열이 0/1 정수면 학습이 멈췄다. 자연어 파서가 ‘통과하지 못했어’·‘미완료’를 통과·완료로 읽고, 다음 문장의 기간 표현을 경험으로 읽었다. 누수 검사가 일부 열만 섞고 일부 필드만 비교해 개수·시간대로 새는 누수를 놓쳤다. train --data의 폴더 경로(OS 사용자 이름 포함)가 번들과 API에 남았고, 선수가 하나뿐인 카탈로그 CSV를 읽지 못했다",
    `모두 고치고 각 경우를 테스트로 고정했다. learner_id는 학습자 조회와 같은 스위치로 막고(꺼져 있으면 403), 금액은 통째로 구간 이름으로 바꾸며, 진단 통과 행은 통과 단원에만 쓰고 수준 갱신에서는 뺀다. understood는 0/1·문자열을 불리언으로 맞추고, 파서는 부정·실패 표현과 문장 경계를 본다(금액 가림·진단 행의 화면 경로·파서의 회귀는 아래 [최종·적대적 점검 2차]에서 다시 고침). 누수 검사는 미래 행의 모든 열을 섞고 행을 더한 로그와 미래 행을 지운 로그로 저장소를 만들어 모든 필드를 비교하며, 개수·시간대·정답 주 누수를 실제로 잡는지 시험한다. 데이터 출처는 ‘csv’로만 기록하고, 선수 열은 문자열로 읽는다. v1·v2를 다시 학습했고 결과는 그대로다(테스트 ${TESTS}건).`],
  ["[최종·보고서 수치 2차] 비교·로드맵 API 응답에 비권유 고지가 없는데도 ‘모든 API 응답에 고지’로 충족 판정했다. ‘--effect 0 위약 세계로 확인한다’(1차본부터)는 실행한 기록이 없었고 그 세계는 위약도 아니었다. A/B 기간 상한 8주의 하루 유입이 주 지표의 7일 관찰 기간을 빼고 계산되었다. 재현 명령(부록 D)이 v1 번들을 저장하지 않았고 그림 패키지가 설치 목록에 없었으며 전체 재현 테스트 선택자가 세 건을 골랐다. /api/meta의 ‘가드레일 기본값’은 평가용 값이었다. 성별 뒤집기 결과는 보고 번들이 아닌 테스트용 작은 세계 값이었고, 정확도 수용 기준은 서비스 기본(가드레일 켬)이 아닌 가드레일을 끈 수치로 판정했다. 상태 해시는 일부 모델에만 있었고, 아이템 CF·CF 신뢰도 게이트 설명이 실제와 달랐다",
    `비교·로드맵 응답에 고지를 넣고(로드맵에는 유형 고지까지) 테스트로 확인했다. 인구통계 열을 섞은 위약 세계를 실제로 학습해 결과를 실었다(${D.placebo ? `검증 1위가 인구통계를 쓰지 않는 설정, 인구통계 라우터의 이점 없음` : "–"}). 유입은 등록 49일 기준으로 다시 계산했다. 재현 명령·설치 안내·테스트 선택자·Python 버전(3.11 이상)을 고치고, /api/meta는 생략 시 기본과 평가 기본을 나눠 돌려준다. 성별 뒤집기는 번들 v2 테스트 사용자 전원${D.gender_flip ? `(${num(D.gender_flip.invariant)}/${num(D.gender_flip.users)}명 불변)` : ""}으로 다시 쟀고, 정확도 기준은 서비스 기본과 가드레일 끔을 함께 판정한다. 모든 학습 모델에 상태 해시를 기록하고, 기법 표 설명을 코드에 맞췄다.`],
  [`[최종·대응서 판정과 사실] 2.2절 ‘대부분 수용’은 1회차 결과로 올린 판정을 v2 결론이 바뀐 뒤에 다시 따지지 않은 것이었다(비판이 평가한 v2 세계에서는 BPR 변형이 점별 MLP를 넘지 못함). 1차본은 자기 표 17에서도 소득분위 심화 노출 격차가 ${jo(fmt(PREV.exp_hi - PREV.exp_lo, 3), "이었는데/였는데")} ‘약 4%p로 충족’으로 판정했고, 이 문서는 이를 ‘재학습 후 새로 드러난 점’으로 적었다. ‘이벤트 스트림을 시도 단위로 모으는 규칙을 추가했다’는 서술과 달리 그 코드가 없었다. 과징금 10% 특례는 시행 중인데 비판 문장을 ‘기본 상한처럼 쓴 서술’로 바꿔 정정했고, 확인하지 못한 공동 개정을 정정표에 ‘정정’으로 적었다. ‘원시 준식별자 미보관’은 연령·연소득·시각에만 맞았다. ISA 시너지 단원(연금 심화에만 둠)을 ‘요구 수용’으로 판정했고, IRP ‘유도’ 전제·‘명백한 약관 위반’ 단정·보유기간과세의 파생형 일반화·MDE와 α 설명은 판정 없이 지나쳤다. 그 밖에 인용 위치(7절 → 6.7절)와 있지 않은 ‘연금계좌 카드’, 짧은 목록이 섞인 다양성 값, 부록 B의 변경 파일 누락, 근거 없는 금액(1,500만원·3,000만원), 기본 테스트의 v1 확인 범위, 평가 화면의 ‘보수적’, 고정 순서 검정 밖의 C 실험, 생성기 효용 항 누락, 2절과 5절의 검토 목록, 원문 대조 일정이 서로 어긋났다`,
    `2.2절을 ‘부분 수용(요구는 전면 반영, 효과는 v1에서만 확인)’으로 낮추고 총계를 ‘${TALLY}’으로 고쳤다(중간보고서 1절·부록 E 포함). 노출 격차는 1차본 판정 정정으로 바꾸고, 세션 ID로 이벤트를 시도로 묶는 events_to_attempts를 구현해 테스트했다. 과징금·공동 개정·준식별자·ISA·IRP·약관·보유기간과세 판정을 고치고 MDE·α 두 문장을 표에 더했으며(군당 ${num(AB2)}명이면 1.5%p 검정력 ${pct(POW15, 0)}, 1%p ${pct(POW10, 0)}), 문장 단위 라벨 4건(5.2 #6, 3절 #3, 4.2 #1, 2.3 #1)과 비판 인용을 원문 표현으로 바로잡았다. 부록 B는 작업 트리와 새 파일까지 센다. 화면 문구, 7.3절의 별도 α, 생성기 효용 설명, 검토 목록, 11월 2주 원문 대조(KRX 약관·개인정보보호법 조문)를 두 보고서에 맞췄다.`],
  ["[최종·적대적 점검 2차] 화면이 서버로 보내는 이벤트에서 source를 빼, ‘진단 통과는 수준 갱신에서 뺀다’는 수정이 화면에서는 작동하지 않았다(수준 2 문항 하나만 맞혀도 추천 수준 2와 수준 3 단원). 파서의 새 부정 처리가 ‘처음엔 떨어졌는데 재시험에서 통과’·‘통과는 전에 했어’·‘1.5배속으로 끝까지 봤어’를 조회로 떨어뜨리고, ‘통과 안됐어’·‘통과하지는 못했어’·‘끝까지 보지 못했어’는 여전히 통과·완료로 읽었다. 저장 설계 가림이 ‘1억 2000만원’을 둘로 쪼개 표기하고 소수 억·‘연봉 6천’·원 단위·단위 없는 숫자·출생 연도를 놓쳤으며 월급을 연소득으로 봤다. 키워드 없는 금액 규칙은 ISA 한도·인원 같은 수치를 거짓 소득 분위로 바꿨고, 함께 저장되는 추천·로드맵 결과(학습자 프로필·통과 단원·학습 카드)는 학습자 조회를 끈 서버에서도 내려갔다. 학습자 없는 /api/types는 범위 밖 통과 가정 번호를 받았고, 자연어 파서는 ‘연소득 1억 2천만원’을 2,000만원으로 읽었다. 이미 가린 ‘[60세 이상]’·‘[29세 이하]’는 불러올 때마다 다시 가려져 표기가 겹쳤다",
    `화면 요청에 source를 싣고 브라우저로 확인했다(같은 조작에서 수준 1, 수준 3 단원 없음). UI 점검 스크립트가 7단계 요청의 source를 확인한다. 파서는 마지막 실패어 뒤의 통과만 인정하고, 부정 목록·‘전’·‘중’의 경계·소수점 문장 경계를 고쳐 문장 28개를 테스트로 고정했다. 금액은 억 뒤 아라비아 숫자·소수 억·만 생략·원 단위·단위 없는 숫자를 합산하고 월급은 12배로 환산하며, 출생 연도는 연령대로 바꾼다. 소득 키워드가 없는 금액은 ‘원’이 붙은 것만 중립 표기 [금액]으로 가리고, 키워드가 다른 낱말(연금소득·소득공제)의 일부면 소득으로 보지 않는다. 저장 설계는 서버 출력을 저장하지 않고, 학습자 조회를 켠 서버에서 저장한 설계는 꺼진 서버가 내려보내지 않으며, 이미 가린 표기는 다시 가리지 않는다. types는 학습자 없이도 범위를 검사하고, 파서는 저장 설계 가림과 같은 소득 규칙(키워드가 붙은 금액만)을 쓴다. 테스트 ${TESTS}건.`],
].concat(D.final_privacy_rows || []);
REVIEW_ROWS.push(...FINAL_ROWS, ...(D.review_rows || []));
add(h1("5. 독립 검토 결과의 반영"),
  p("판정과 보완 내용을 별도 검토자가 비판 문서·코드·데이터에 대조했다. 검토는 처음 판정이 틀렸거나 보완이 과장된 곳을 여러 군데 찾아냈고, 모두 고친 뒤 이 문서와 중간보고서에 반영했다. 아래 표는 검토 지적과 처리 결과다. [1회차]·[2회차]는 판정 검증, [최종]은 보완을 마친 뒤의 코드·문서 검토(모델·도메인·데이터 수집·개인정보·보고서 수치·화면과 문서·적대적 점검·대응서 판정과 사실)다. 최종 검토에서 가장 큰 지적은 쌍별 MLP의 학습 사용자 범위 결함이었고, 고친 뒤 v2의 신경망 결론(2.2절)이 바뀌었다. 마지막 대응서 판정 검토에서는 그 결론 변화에 맞춰 2.2절 판정을 ‘부분 수용’으로 낮췄다."),
  ...(REVIEW_ROWS.length ? table(["검토 지적", "처리"], REVIEW_ROWS, [6.2, 6.3], { caption: "독립 검토 지적과 처리", size: 15, zebra: true }) : [p("(검토 결과로 채움)", { color: GREY })]),
);

add(h1("6. 보완 전후 비교"),
  ...table(["항목", "1차본(10월 13일)", "2차본(현재)", "비고"], [
    ["카탈로그", `${PREV.catalog}단원(21주제)`, `${D.catalog.n_items}단원(${D.catalog.n_topics}주제), 선수 관계 ${D.catalog.n_prereq_edges}개`, "절세 계좌(ISA) 3단원 신설, 세제·규제 단원 3개 제목 보강"],
    ["학습 콘텐츠", "단원 제목·출처 링크", "세제·규제 6단원 학습 요점 본문(기준일·예시·출처)", "ISA 3, 과표기준가, IRP 70%, 레버리지 거래 요건"],
    ["진단 퀴즈", `${PREV.quiz}문항, 정답 13개가 두 번째 보기`, `${D.questions.length}문항(${QUNITS}개 단원), 정답 위치 균형, 단원 단위 채점(단원 문항을 모두 답하고 맞혀야 통과), 수준별 최소 응답 수`, "규제 상식 문항은 수준 판정에만 사용"],
    ["설정 풀", `${num(PREV.configs)}개`, `${num(M.configurations)}개`, "BPR MF 6 + 신경망 변형 3"],
    ["오프라인 지표", "NDCG@5(전체 기준)만", "전체·활성 기준 병기 + 항등식·순위 QA, 집단별 두 기준", `활성 ${num(nAct)}명 / 전체 ${num(nAll)}명`],
    ["운영 설정", "규칙[관심 주제+수준 일치+투자 목적 일치]", D.operational_name, "카탈로그가 바뀌어 검증 1위가 달라짐"],
    ["운영 라우터 NDCG@5", `${fmt(PREV.RouterNoGender)}(전체)`, `${fmt(R.RouterNoGender.ndcg)}(전체) / ${fmt(R.RouterNoGender.ndcg_active)}(활성)`, "세계가 달라 직접 비교 불가"],
    ["선수 가드레일 비용", `NDCG ${fmt(PREV.RouterNoGender - PREV.prereq, 3)} 감소, 짧은 목록 ${pct(PREV.short)}`, `NDCG ${fmt(R.RouterNoGender.ndcg - R["RouterNoGender+prereq"].ndcg, 3)} 감소, 짧은 목록 ${pct(R["RouterNoGender+prereq"].short_list_rate)}`, `선수 위반 ${pct(PREV.viol, 0)} → ${pct(R.RouterNoGender.prereq_violation_rate, 0)}(가드레일 끔)`],
    ["신경망 최고(v2)", `${fmt(Math.max(PREV.MF, PREV.MF_OBS, PREV.MLP))}`, `${fmt(nnBest2)}`, `v1에서는 미관측 음성 BPR로 MLP ${fmt(V1.MLP.ndcg, 5)} → ${fmt(V1.MLP_BPRU ? V1.MLP_BPRU.ndcg : null, 5)}`],
    ["KRX 수집", "화면용 비공식 JSON 자동 호출", "사람이 내려받은 파일 정규화 + KRX Open API(인증키) + 공공데이터포털", "provenance 정책·해시 기록, 원자적 교체·형식 검사·키 가림, 비상업 범위 명시"],
    ["개인정보", "가명 번호·성별 제외 정책 문장", D.priv_after || "원시 준식별자 미보관, k-익명성 점검·비식별 내보내기, 조직 정책 구분", "5.2절"],
    ["유형 카드 규제 문구", "사전교육 + 기본예탁금은 ‘증권사 안내 확인’으로만(금액·미달 시 결과 없음)", "사전교육 + 기본예탁금(1,000만/단일종목 현금 3,000만) + 교육 3시간·모의거래 + 해외 레버리지 ETP", "기준일 표기"],
    ["A/B 계획", "군당 약 7,000명, 4~8주", "MDE·검정 방향 표, 고정 순서 검정, 유입·기간·판정 보류 규칙", "단측·비열등성 구분"],
    ["QA · 테스트", `QA ${PREV.qa}건, 테스트 ${PREV.tests}건`, `QA ${M.qa}건, 테스트 ${TESTS}건(기본 실행 ${TESTS - 1}건 통과, 전체 재현 1건 옵션)`, "이벤트 논리·항등식·신경망 학습 범위·누수·도메인 규칙·수집 정책·개인정보 검사 추가"],
    ["집단 진단(1차본 판정 정정)", `심화 노출 격차를 ‘약 4%p로 충족’으로 판정. 그러나 1차본 표 17의 소득분위 격차가 이미 ${fmt(PREV.exp_hi - PREV.exp_lo, 3)}(${fmt(PREV.exp_lo, 3)}~${fmt(PREV.exp_hi, 3)})로 오판. 목적별 구간 겹침`, `같은 변수 안 심화 노출 격차 최대 ${EXPG.v} ${fmt(EXPG.gap, 3)}${EXPG.gap > 0.05 ? "(기준 5%p 초과)" : ""}`, "비판의 지적은 아니다. 재학습이 드러낸 문제가 아니라 1차본 판정이 처음부터 틀렸으므로 정정하고 11월 과제로 넣음(중간보고서 6.5·7.5절)"],
  ], [2.2, 3.2, 4.2, 3.2], { caption: "보완 전후 비교", size: 16, zebra: true }),
  p("주의: 카탈로그가 63단원에서 66단원으로 바뀌고 생성기가 새 단원과 선수 관계를 포함해 세계를 다시 만들었으므로, 1차본과 2차본의 절대 수치는 같은 세계의 비교가 아니다. 방법 간 큰 순서(규칙 ≈ 운영 라우터 > 인구통계 미사용 > 인기·사용자 CF > 신경망·아이템 CF·콘텐츠 > 무작위)는 두 번들에서 같다."),
);

add(h1("7. 남은 한계와 후속 계획"),
  bullet("세제·규제 문구와 학습 요점은 검색으로 확인한 범위다. 최종 보고서 전에 법령·기관 공지 원문(금융위원회 보도자료, 국세청 안내, 금융투자교육원 공지, 한국거래소 공지·이용약관 조항과 호출 한도, 개인정보보호법 과징금 조문·특례 요건과 개인정보보호위원회 가명정보 가이드라인)을 직접 대조하고 전문가 검수를 받는다(11월 2주, 중간보고서 8절)."),
  bullet("KRX Open API와 공공데이터포털 API의 경로·필드명은 키 발급 후 실제 응답으로 확인한다(11월 1주). 공식 경로도 비상업 이용 조건이므로 상용 서비스로 바꿀 때는 별도 이용 계약이 필요하다."),
  bullet(`신경망은 v1에서는 BPR(미관측 음성)로 크게 좋아졌지만(${ci(PR1["MLP_BPRU-MLP"])}), v2에서는 네 MLP가 모두 학습한 사용자로 좁히면 ${effS(CG(NNG, "MLP_BPRU-MLP"))}고(${ci(CG(NNG, "MLP_BPRU-MLP"))}) 전체 사용자로는 쌍이 없는 사용자의 대체 점수 때문에 ${effS(PR2["MLP_BPRU-MLP"])}다(${ci(PR2["MLP_BPRU-MLP"])}). 쌍이 없는 사용자에게 점별 점수를 섞는 처리, 공통 학습 사용자에서 차이가 없던 원인(규칙 신호와의 정보 중복 가설), 목적·로드맵 특징을 입력으로 넣은 모델을 11월 3주에 비교한다.`),
  bullet("k-익명성은 공개·공유 산출물에 적용하고 학습 입력에는 적용하지 않았다. 실제 로그에서는 접속 시간대·조회 주제까지 준식별자에 넣어 다시 평가하고, 고차원 행동 로그는 k-익명성만으로 다루기 어렵다는 한계(l-다양성 등)를 위험도 평가 절차에 반영한다."),
  bullet(`학습 요점 본문은 세제·규제 6단원에만 있다. 나머지 단원은 교육 자료 링크로 연결하고, 본문 확장과 문항 확장(진단 단원 ${QUNITS}개 × 단원당 2문항 = ${2 * QUNITS}문항)은 11월에 한다.`),
  bullet("선수 가드레일의 짧은 목록 비율이 수용 기준(20% 이하)을 넘는다. 실제 로그로 선수 페널티를 보정한 뒤 완화 규칙을 정한다."),
  bullet(`집단 진단에 기준을 넘는 노출 격차가 있다. 1차본은 자기 표 17에서도 소득분위 격차가 ${jo(fmt(PREV.exp_hi - PREV.exp_lo, 3), "이었는데/였는데")} ‘최대 격차 약 4%p로 충족’이라고 잘못 판정했다(재학습이 드러낸 문제가 아니다). 2차본에서도 심화·레버리지 노출 비율이 ${EXPG.v}에 따라 최대 ${fmt(EXPG.gap, 3)} 차이 나고, 투자 목적 가운데 ${GOAL_LO ? (D.goals[GOAL_LO.group] || GOAL_LO.group) : "–"} 집단의 정확도가 가장 낮다(전체 기준 ${GOAL_LO ? fmt(GOAL_LO.ndcg, 3) : "–"}). 비판의 지적 사항은 아니지만 판정을 정정해 중간보고서 6.5·7.5절에 보고했으며, 원인 분석과 노출 상한 정책을 11월 4주에 다룬다.`),
);

add(pageBreak(), h1("부록 A. 사실 확인 출처"),
  ...table(["항목", "확인한 사실", "출처(2026-10-13~14 검색)"], D.facts.map(f => [f.key, f.fact, f.sources.join(" ; ")]), [1.4, 6.2, 5.2], { caption: "사실 확인 목록", size: 14, zebra: true }),
  p("출처는 검색 결과 요약으로 확인했으며 기관 사이트 본문은 개발 환경의 네트워크 제한으로 직접 열지 못했다. 언론·블로그 출처는 공식 자료로 다시 확인해야 한다.", { size: 18, color: GREY }),
);

const CHG = D.changed_since_v1 || [];
const CHG_GROUPS = [
  ["모델·평가·특징", /^etfrec\/(neural|signals|zoo|pipeline|evaluation|router|features)\.py$/, "쌍별·목표 정렬 신경망과 학습 범위, 활성 사용자 지표, A/B 대조군 평가 행, 이벤트 논리·항등식·누수·개인정보 QA, 경로 크기 구간, 진단 행을 뺀 수준 갱신"],
  ["데이터·카탈로그", /^etfrec\/(data|catalog|config|__init__)\.py$/, "이벤트 정규화, 세션 단위 시도 묶기, 스키마 밖 열 제거, 형 정규화, 출처 라벨, 절세 계좌 주제, 선수 관계 검사"],
  ["교육 설계", /^etfrec\/(taxonomy|roadmap|quiz|lessons)\.py$/, "공통 기초, 유형 목적, 세제·규제 문구, 진단 채점 규칙, 학습 요점"],
  ["개인정보", /^etfrec\/privacy\.py$/, "저장 최소화, 감사, k-익명 반출, 저장 설계 가림(서버 출력 제외, 금액·출생 연도), 자연어 소득 읽기 규칙"],
  ["공개 데이터", /^etfrec\/sources\//, "공식 API·파일 정규화, 원자적 스냅샷, 키 처리, 샘플 종목 CSV"],
  ["서빙·화면", /^etfrec\/(service|api|cli|nlparse)\.py$|^etfrec\/ui\//, "학습자 조회 스위치, 기법 제한, 입력 검사, 오류 표시, 파서 규칙"],
  ["테스트·스크립트·보고서 빌드", /^(tests|scripts|docs\/report\/build)\//, "회귀·개인정보·수집·파서 테스트, 결과 표·화면 점검 스크립트, 보고서 생성"],
];
const chgList = re => CHG.filter(f => re.test(f)).map(f => f.replace(/^etfrec\//, "")).join(", ");
const chgOther = CHG.filter(f => !CHG_GROUPS.some(g => g[1].test(f)));
add(h1("부록 B. 변경 파일 요약"),
  p(`1차본 커밋(${D.v1_commit || "9322f6e"}) 이후 바뀐 파일 ${CHG.length}개(작업 트리 기준 git diff --name-only와 새 파일, etfrec·scripts·tests·docs/report/build 범위).`),
  ...CHG_GROUPS.filter(g => CHG.some(f => g[1].test(f))).map(g => bullet([{ t: `${g[0]}: `, bold: true }, `${chgList(g[1])} — ${g[2]}`])),
  ...(chgOther.length ? [bullet([{ t: "기타: ", bold: true }, chgOther.join(", ")])] : []),
);


const doc = new Document({
  creator: "etfrec project", title: "중간보고서 비판 검토 및 보완 보고서", features: { updateFields: true },
  styles: { default: { document: { run: { font: FONT, size: 21 }, paragraph: { spacing: { line: 312, lineRule: LineRuleType.AUTO } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 32, bold: true, color: GREEN, font: FONT }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 25, bold: true, color: "1C211C", font: FONT }, paragraph: { spacing: { before: 260, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 21, bold: true, color: GREY, font: FONT }, paragraph: { spacing: { before: 160, after: 60 }, outlineLevel: 2 } } ] },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] }] },
  sections: [{ properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: 1300, bottom: 1250, left: MARGIN, right: MARGIN } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 4 } }, children: [run("중간보고서 비판 검토 및 보완 보고서", { size: 16, color: GREY })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 17, color: GREY })] })] }) },
    children: body }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("written", OUT, buf.length, "bytes; tables", tabNo); });
