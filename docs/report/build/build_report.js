// 중간보고서 .docx 생성 (docx-js). 실행: node build_report.js out.docx
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, ImageRun, PageBreak, Footer, Header, PageNumber, TableOfContents, LevelFormat, TabStopType, VerticalAlign, LineRuleType,
} = require("docx");

const HERE = __dirname;
const D = JSON.parse(fs.readFileSync(path.join(HERE, "report_data.json"), "utf8"));
const DIMS = JSON.parse(fs.readFileSync(path.join(HERE, "fig_dims.json"), "utf8"));
const FIG = path.join(HERE, "fig");
const OUT = process.argv[2] || path.join(HERE, "중간보고서.docx");

// ---------- 서식 ----------
const FONT = "맑은 고딕";
const PAGE_W = 11906, MARGIN = 1247, CONTENT_W = PAGE_W - 2 * MARGIN;   // A4, 좌우 2.2cm
const CONTENT_PX = 620;                                                // 이미지 최대 폭(px, 96dpi)
const GREEN = "1F6F55", SOFT = "DCEFE6", GOLD = "9A6A00", SOFT2 = "F4F5F2", GREY = "5D665D";
let figNo = 0, tabNo = 0;

const run = (text, opt = {}) => new TextRun({ text, font: FONT, size: opt.size || 21, bold: opt.bold, italics: opt.italics, color: opt.color, superScript: opt.sup });
const p = (text, opt = {}) => new Paragraph({
  alignment: opt.align || AlignmentType.JUSTIFIED, spacing: { after: opt.after ?? 120, line: opt.line || 312, lineRule: LineRuleType.AUTO },
  indent: opt.indent, keepNext: opt.keepNext,
  children: Array.isArray(text) ? text : [run(text, opt)],
});
const rich = (parts, opt = {}) => p(parts.map(x => typeof x === "string" ? run(x, opt) : run(x.t, { ...opt, ...x })), opt);
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 }, children: [new TextRun({ text: t, font: FONT })] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 120 }, children: [new TextRun({ text: t, font: FONT })] });
const h3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 80 }, children: [new TextRun({ text: t, font: FONT })] });
const bullet = (text, level = 0) => new Paragraph({ numbering: { reference: "bullets", level }, spacing: { after: 60, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED,
  children: Array.isArray(text) ? text.map(x => typeof x === "string" ? run(x) : run(x.t, x)) : [run(text)] });
const numbered = (text, ref = "numbers") => new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED,
  children: Array.isArray(text) ? text.map(x => typeof x === "string" ? run(x) : run(x.t, x)) : [run(text)] });
const note = (text) => new Paragraph({ spacing: { after: 120, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED, indent: { left: 240 },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: GREEN, space: 8 } }, shading: { type: ShadingType.CLEAR, fill: SOFT2, color: "auto" },
  children: (Array.isArray(text) ? text : [text]).map(x => typeof x === "string" ? run(x, { size: 20 }) : run(x.t, { size: 20, ...x })) });
const caption = (t) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 }, children: [run(t, { size: 18, color: GREY, italics: false })] });
const spacer = (n = 120) => new Paragraph({ spacing: { after: n }, children: [] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });
const fmt = (x, d = 4) => (x == null || Number.isNaN(+x)) ? "–" : (+x).toFixed(d);
const pct = (x, d = 1) => (x == null) ? "–" : (100 * x).toFixed(d) + "%";
const num = (x) => Number(x).toLocaleString("ko-KR");

function img(name, cap, widthPx = CONTENT_PX, maxH = 760) {
  const [w, h] = DIMS[name]; let W = widthPx, H = Math.round(widthPx * h / w);
  if (H > maxH) { H = maxH; W = Math.round(maxH * w / h); }
  const data = fs.readFileSync(path.join(FIG, name));
  const type = name.endsWith(".png") ? "png" : "jpg";
  figNo += 1;
  return [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40, line: 240, lineRule: LineRuleType.AUTO }, keepNext: true,
    children: [new ImageRun({ type, data, transformation: { width: W, height: H } })] }), caption(`그림 ${figNo}. ${cap}`)];
}

function cell(text, opt = {}) {
  const children = (Array.isArray(text) ? text : [text]).map(t => new Paragraph({ alignment: opt.align || AlignmentType.LEFT, spacing: { after: 20, line: 264, lineRule: LineRuleType.AUTO },
    children: (Array.isArray(t) ? t : [t]).map(x => typeof x === "string" ? run(x, { size: opt.size || 18, bold: opt.bold, color: opt.color }) : run(x.t, { size: opt.size || 18, ...x })) }));
  return new TableCell({ width: { size: opt.width, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
    shading: opt.fill ? { type: ShadingType.CLEAR, fill: opt.fill, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 80, right: 80 }, children });
}
function table(headers, rows, widthsRel, opt = {}) {
  const total = widthsRel.reduce((a, b) => a + b, 0);
  const widths = widthsRel.map(w => Math.round(CONTENT_W * w / total));
  widths[widths.length - 1] += CONTENT_W - widths.reduce((a, b) => a + b, 0);
  const size = opt.size || 18;
  const head = new TableRow({ tableHeader: true, children: headers.map((hh, i) => cell(hh, { width: widths[i], fill: SOFT, bold: true, size })) });
  const body = rows.map((r, ri) => new TableRow({ children: r.map((c, i) => cell(c, { width: widths[i], size, fill: (opt.zebra && ri % 2 === 1) ? SOFT2 : undefined,
    align: (opt.numCols || []).includes(i) ? AlignmentType.RIGHT : AlignmentType.LEFT })) }));
  const out = [new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows: [head, ...body],
    borders: { top: { style: BorderStyle.SINGLE, size: 6, color: "BBBBBB" }, bottom: { style: BorderStyle.SINGLE, size: 6, color: "BBBBBB" },
      left: { style: BorderStyle.NONE, size: 0 }, right: { style: BorderStyle.NONE, size: 0 },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: "DDDDDD" }, insideVertical: { style: BorderStyle.NONE, size: 0 } } })];
  if (opt.caption) { tabNo += 1; out.unshift(new Paragraph({ spacing: { before: 160, after: 60 }, keepNext: true, children: [run(`표 ${tabNo}. ${opt.caption}`, { size: 19, bold: true, color: GREEN })] })); }
  out.push(spacer(100));
  return out;
}

// ---------- 데이터 가공 ----------
const KO = { RULE: "규칙(검증 1위)", Global: "전역 1위", RouterNoGender: "라우터(성별 제외) = 운영", RouterFull: "라우터(성별 포함)", RouterNoGenderIncome: "라우터(성별·소득 제외)",
  NoDemographics: "인구통계 미사용 1위", UCF: "사용자 CF", "RouterNoGender+prereq": "운영 라우터 + 선수 가드레일", POP: "인기", ICF: "아이템 CF", CONTENT: "콘텐츠 기반",
  MLP: "MLP(9주차, BCE)", MF_OBS: "관측 MF", MF: "표본 MF", Random: "무작위", MF_BPR: "BPR MF(미관측 음성)", MLP_BPR: "MLP 쌍별(관측 음성)",
  MLP_BPRU: "MLP 쌍별(미관측 음성)", MLP_NEXT: "MLP 목표 정렬(다음 주 통과)" };
const NEW_FAMS = ["MF_BPR", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"];
const GOAL_KO = D.goals, HOR_KO = D.horizons;
const resBy = Object.fromEntries(D.results.map(r => [r.method, r]));
const v1By = Object.fromEntries(D.v1_results.map(r => [r.method, r]));
const NB = { RULE: 0.17123, Global: 0.17123, RouterNoGender: 0.17119, RouterFull: 0.17116, RouterNoGenderIncome: 0.15702, NoDemographics: 0.15355, UCF: 0.14268,
  POP: 0.11875, ICF: 0.11112, CONTENT: 0.09957, MF: 0.09264, MF_OBS: 0.07099, Random: 0.05993, MLP: 0.05325 };
const M = D.manifest, DS = M.dataset;
const sens = D.sensitivity;
const PRIV = M.privacy || {};
const nActive = resBy.RULE.active_users, nAll = resBy.RULE.users;
const dBPR = (resBy.MF_BPR ? resBy.MF_BPR.ndcg - resBy.MF.ndcg : null), dMLP = (resBy.MLP_BPR ? resBy.MLP_BPR.ndcg - resBy.MLP.ndcg : null);
const sensRev = sens.filter(x => x["RouterNoGender+prereq"].ndcg > x.RouterNoGender.ndcg).map(x => x.prereq_penalty);
const ZQ = { a2: 1.959963985, a1: 1.644853627, a2_dunnett: 2.241402728, a2_bonf3: 2.393979902, b80: 0.841621234 };   // 표준정규 분위수
function abSize(p1, p2, alpha2 = true, za = null) {   // 두 비율 Z-검정 표본 크기(군당, 검정력 80%, 연속성 보정 없음)
  const z = za ?? (alpha2 ? ZQ.a2 : ZQ.a1), pb = (p1 + p2) / 2;
  return Math.ceil(Math.pow(z * Math.sqrt(2 * pb * (1 - pb)) + ZQ.b80 * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)), 2) / Math.pow(p2 - p1, 2));
}
const niSize = (p, margin) => Math.ceil(Math.pow(ZQ.a1 + ZQ.b80, 2) * 2 * p * (1 - p) / (margin * margin));   // 비열등성(참 차이 0, 단측 5%)
function Phi(x) { const t = 1 / (1 + 0.2316419 * Math.abs(x)); const d = 0.3989423 * Math.exp(-x * x / 2); const q = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - q : q; }
const abPower = (p1, p2, n) => { const pb = (p1 + p2) / 2; return Phi((Math.abs(p2 - p1) * Math.sqrt(n) - ZQ.a2 * Math.sqrt(2 * pb * (1 - pb))) / Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))); };
const AB_ROWS = [0.02, 0.03, 0.04].map(d => [`${(d * 100).toFixed(0)}%p (22% → ${((0.22 + d) * 100).toFixed(0)}%)`, num(abSize(0.22, 0.22 + d, true)), num(abSize(0.22, 0.22 + d, false)),
  num(abSize(0.22, 0.22 + d, true, ZQ.a2_dunnett)), num(2 * abSize(0.22, 0.22 + d, true)), num(3 * abSize(0.22, 0.22 + d, true, ZQ.a2_dunnett))]);
const AB2 = abSize(0.22, 0.24, true), AB3 = abSize(0.22, 0.25, true), POW3 = abPower(0.22, 0.24, AB3);
const INFLOW2 = Math.ceil(2 * AB2 / 56), INFLOW3 = Math.ceil(2 * AB3 / 56);
// 쌍 비교(사용자 단위 쌍 부트스트랩 95% 구간), 집단별 활성 기준, 다양성, 기타 사실
const PR2 = Object.fromEntries((D.paired || []).map(x => [`${x.a}-${x.b}`, x])), PR1 = Object.fromEntries((D.paired_v1 || []).map(x => [`${x.a}-${x.b}`, x]));
const sgn = (x, d = 4) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d);
const ci = (x, d = 4) => x ? `${sgn(x.diff, d)} [${sgn(x.ci_low, d)}, ${sgn(x.ci_high, d)}]` : "–";
const sig = (x) => !x ? "–" : (x.ci_low > 0 ? "유의하게 높음" : (x.ci_high < 0 ? "유의하게 낮음" : "차이 없음"));
const ratioAct = nActive / nAll;
const eff = (x) => !x ? "–" : (x.ci_low > 0 ? "개선" : (x.ci_high < 0 ? "악화" : "유의한 차이 없음"));
const BPRU2 = PR2["MLP_BPRU-MLP"], BPRU1 = PR1["MLP_BPRU-MLP"], NEXT2 = PR2["MLP_NEXT-MLP"], NEXT1 = PR1["MLP_NEXT-MLP"], MFB2 = PR2["MF_BPR-MF"], MFB1 = PR1["MF_BPR-MF"];
const OBS2 = PR2["MLP_BPR-MLP"], OBS1 = PR1["MLP_BPR-MLP"], NEG2 = PR2["MLP_BPRU-MLP_BPR"], NEG1 = PR1["MLP_BPRU-MLP_BPR"];
const nnBest2 = Math.max(...["MF", "MF_OBS", "MF_BPR", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"].filter(k => resBy[k]).map(k => resBy[k].ndcg));
const nnBest1 = Math.max(...["MF", "MF_OBS", "MF_BPR", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"].filter(k => v1By[k]).map(k => v1By[k].ndcg));
const CT = D.click_tier || [];
const ctTopAll = CT.length ? CT.reduce((a, b) => (b.ndcg > a.ndcg ? b : a)) : null, ctTopAct = CT.length ? CT.reduce((a, b) => (b.ndcg_active > a.ndcg_active ? b : a)) : null;
const DIVL = D.diversity_by_len || {};
const DIVG = DIVL["RouterNoGender+prereq"] || {}, DIVR = DIVL.RouterNoGender || {};
const TESTS = D.tests_collected, SCREENS = D.screens, ROOTS = D.n_root_units;
const QUNITS = new Set(D.questions.map(q => q.topic + "|" + q.level)).size;
const QL = (l) => D.questions.filter(q => q.level === l).length;
const mlpAud = ((D.training_audit || {}).mlp9 || []).slice(-1)[0] || null;
const mlpPos = mlpAud ? mlpAud.positive / mlpAud.training_rows : null;
const bce0 = mlpPos ? -(mlpPos * Math.log(mlpPos) + (1 - mlpPos) * Math.log(1 - mlpPos)) : null;
const valTop = D.validation_top || [];
const valTopRoad = valTop.filter(j => j.name.includes("로드맵")).length, valTopGoal = valTop.filter(j => j.name.includes("투자 목적")).length;
const opHas = (k) => D.operational_name.includes(k);
const EV = (() => { const sum4 = DS.complete + DS.quiz_pass + DS.save + DS.drop, ncnd = DS.not_complete - DS.drop; return { sum4, excess: sum4 - DS.study_attempts, ncnd }; })();
if (EV.excess !== DS.quiz_pass + DS.save - EV.ncnd) throw new Error("이벤트 합 분해 검산 실패");
const goalRows = D.group_results.filter(x => x.method === "RouterNoGender" && x.variable === "goal");
const goalMin = Math.min(...goalRows.map(x => x.ndcg)), goalMax = Math.max(...goalRows.map(x => x.ndcg));
const expRows = D.exposure.filter(x => x.method === "RouterNoGender");
const expTop = expRows.reduce((a, b) => (b.advanced_share > a.advanced_share ? b : a), expRows[0]);
const expGap = Math.max(...expRows.map(x => x.advanced_share)) - Math.min(...expRows.map(x => x.advanced_share));
const ageRows = D.group_results.filter(x => x.method === "RouterNoGender" && x.variable === "age_band");
const oldAge = ageRows.find(x => +x.group === 4) || ageRows[ageRows.length - 1];
const LAB = { gender: ["남성", "여성"], age_band: ["29세 이하", "30대", "40대", "50대", "60세 이상"], income_q: ["소득 1분위", "2분위", "3분위", "4분위", "5분위"],
  click_tier: ["신규(조회 0)", "보통(1~9)", "많음(10+)"], goal: GOAL_KO };
const glab = (v, g) => v === "goal" ? GOAL_KO[g] : LAB[v][+g];
const VAR_KO = { goal: "투자 목적", age_band: "연령대", income_q: "소득분위", gender: "성별", click_tier: "학습활동" };

// ---------- 문서 본문 ----------
const body = [];
const add = (...xs) => xs.flat().forEach(x => body.push(x));

// 표지
add(
  spacer(1800),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run("추천 시스템 프로젝트 · 중간보고서", { size: 24, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [run("ETF 교육 콘텐츠 개인화 추천 시스템", { size: 44, bold: true, color: GREEN })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [run("진단 → 필수 기초 개념 → 목적별 핵심 → ETF 유형 연결의 단계별 로드맵 설계와 구현", { size: 26 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("제출일: 2026년 10월 13일", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("작성자: (이름 · 학번 기입)", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("소스 코드: github.com/kyounghob/forclaudekyoungho (브랜치 claude/pensive-goldberg-dzposy)", { size: 20, color: GREY })] }),
  spacer(1400),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("2차본(중간 점검 지적 반영): 활성 사용자 기준 NDCG 병기, BPR·목표 정렬 신경망 비교, ISA·기본예탁금·IRP 70%·과표기준가 콘텐츠 보강, 공식 API 전용 수집, k-익명성 점검, A/B 설계 정정", { size: 18, color: GOLD })] }),
  note([{ t: "한 줄 요약. ", bold: true }, "학습자의 투자 목적·성향·지식 수준을 진단한 뒤, 총보수·괴리율·환헤지·레버리지 복리 효과 같은 필수 기초 개념부터 목적별 핵심·심화 개념까지의 학습 로드맵을 만들고, 지금 공부할 단원 5개를 추천하며, 마지막 단계에서 적합한 ETF 유형으로 연결하는 교육용 추천 시스템이다. 수업에서 배운 추천 기법 9종을 같은 조건에서 비교하는 파이프라인, 공개 데이터 커넥터, REST API와 11단계 웹 UI까지 실행 가능한 형태로 구현했다. " + `모의 데이터 기준 ${num(M.configurations)}개 설정 중 검증 1위는 ‘${D.operational_name.replace(/\(base=.*\)/, "")}’였고, 선수 단원 가드레일은 교육 순서 위반을 0으로 만드는 대신 정확도 비용이 있음을 확인해 다음 단계의 보정 과제로 정리했다.`]),
  pageBreak(),
  new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { after: 160 }, children: [new TextRun({ text: "목차", font: FONT })] }),
  new TableOfContents("목차", { hyperlink: true, headingStyleRange: "1-2" }),
  p("※ Word에서 열면 목차 필드 갱신을 묻는 창이 뜹니다. ‘예’를 누르면 페이지 번호가 채워집니다.", { size: 18, color: GREY }),
  pageBreak(),
);

// 1. 요약
add(h1("1. 요약"),
  p("이 보고서는 ETF 교육 콘텐츠 개인화 추천 시스템의 중간 결과를 정리한다. 제안서 단계에서 ‘B안(ETF 교육)’으로 정한 주제를 (1) 투자 목적과 지식 수준을 진단해 (2) 필수 기초 개념을 먼저 학습시키고 (3) 적합한 ETF 유형으로 연결하는 단계별 로드맵 형태로 확장했고, 실제 접근 가능한 공개 데이터·교육 자료에 연결되도록 데이터 계층을 다시 설계했다. 현재 상태는 다음과 같다."),
  bullet([{ t: "문제·시나리오: ", bold: true }, "2025년 말 국내 상장 ETF 1,058종목·순자산 297조 원 규모로 상품이 급증했지만, 총보수·괴리율·환헤지(H)·파생형 복리 효과 같은 구조적 비용과 위험은 상품명에 드러나지 않는다. 연금·배당·단기 매매 등 투자 목적과 현재 지식 수준에 맞춘 학습 경로가 없다는 점을 문제로 정의하고, 세 가지 페르소나 시나리오로 구체화했다(2절)."]),
  bullet([{ t: "추천 기법: ", bold: true }, "인기·세그먼트 인기·규칙·콘텐츠 기반·사용자 CF·아이템 CF·행렬분해(표본/관측)·MLP·하이브리드·세그먼트 라우터를 같은 후보·같은 정답·같은 후처리로 비교하는 구조를 구현했다. 각 기법의 한계(콜드스타트, 희소성, 인기 편향, 학습 목표 불일치, 교육 순서 무시)를 로드맵 신호·선수 가드레일·진단 퀴즈로 보완했다(3절)."]),
  bullet([{ t: "데이터: ", bold: true }, "학습 로그 스키마(profiles·study_log·catalog + 목적·기간·선수 관계), 공개 데이터 출처 12건(전국투자자교육협의회 스쿨, 금융투자교육원 사전교육, KRX ETF 정보·정보데이터시스템, 공공데이터포털 시세 API, 운용사 가이드북)을 등록부로 정리하고, KRX 전종목 기본정보·공공데이터포털 시세 커넥터와 스냅샷·출처 기록, 샘플 폴백을 구현했다(4절)."]),
  bullet([{ t: "구현: ", bold: true }, `파이썬 패키지 etfrec, 카탈로그 v2(단원 ${D.catalog.n_items}개·선수 관계 ${D.catalog.n_prereq_edges}개), 진단 퀴즈 ${D.questions.length}문항(${QUNITS}개 단원), 세제·규제 단원 학습 요점, 로드맵 엔진, ETF 유형 분류 10종, 학습 파이프라인(설정 ${num(M.configurations)}개, 신호 ${M.signal_count}개, QA ${M.qa_passed}/${M.qa}건), FastAPI 서버와 11단계 웹 UI ‘학습 설계 스튜디오’, 자동화 테스트 ${TESTS}건과 Playwright UI 점검 스크립트(5절).`]),
  bullet([{ t: "결과: ", bold: true }, `모의 데이터 v2(학습자 ${num(DS.users)}명, 학습 시도 ${num(DS.study_attempts)}건)에서 검증 1위는 ‘${D.operational_name}’(검증 NDCG@5 ${fmt(M.selection.validation_best)}), 테스트 NDCG@5(전체 / 활성 사용자)는 규칙 ${fmt(resBy.RULE.ndcg)} / ${fmt(resBy.RULE.ndcg_active)}, 운영 라우터 ${fmt(resBy.RouterNoGender.ndcg)} / ${fmt(resBy.RouterNoGender.ndcg_active)}, 인기 ${fmt(resBy.POP.ndcg)} / ${fmt(resBy.POP.ndcg_active)}, 무작위 ${fmt(resBy.Random.ndcg)} / ${fmt(resBy.Random.ndcg_active)}였다. 노트북 B의 원본 세계(v1)는 소수점 5자리까지 재현했다. 선수 단원 가드레일은 선수 미이수 추천을 ${pct(resBy.RouterNoGender.prereq_violation_rate, 0)}에서 0으로 줄이는 대신 NDCG를 ${fmt(resBy.RouterNoGender.ndcg - resBy["RouterNoGender+prereq"].ndcg, 3)} 낮췄는데, 선수 효과가 강한 세계에서는 오히려 역전됨을 민감도 실험으로 확인했다(6절).`]),
  bullet([{ t: "평가 계획: ", bold: true }, "오프라인 정확도(전체·활성 사용자 기준)·다양성·교육 순서 준수 지표, 집단별 점검(두 기준), 온라인 A/B(MDE별 표본 크기, 고정 순서 검정, 기간 상한과 필요 유입) 설계, 사용성·전문가 검토 계획을 세웠다(7절). 남은 일정은 실제 공개 데이터 수집 실행, 교육 자료 연동, 사용자 테스트, 최종 보고서다(8절)."]),
  bullet([{ t: "중간 점검 지적 반영: ", bold: true }, `별도 문서 ‘비판 검토 및 보완 보고서’에서 지적 11건을 문장 단위로 판정했다. 수용 6건(A/B 설계, 기본예탁금, ISA·IRP 70%, 과표기준가, KRX 비공식 호출 제거, 가명정보·k-익명성), 대부분 수용 1건(손실 함수·BPR), 부분 수용 2건(정답 없는 사용자의 NDCG 처리, 총평), 불수용 1건(모의 로그의 ‘산술 모순’: 이벤트 열은 한 시도의 다중 플래그이며 합계 초과분은 통과·저장 플래그와 미완료·비이탈 시도로 정확히 분해된다), 긍정 평가 1건(다양성 지표). 가장 큰 정정은 손실 함수다. 1차본은 MF·MLP의 낮은 성능을 ‘손실 함수가 아니라 목표 불일치’라고 실험 없이 단정했다. 같은 실행에서 비교하니 미관측 단원을 음성으로 쓰는 쌍별 손실이 노트북 세계(v1)에서 MLP를 ${fmt(v1By.MLP.ndcg, 4)} → ${v1By.MLP_BPRU ? fmt(v1By.MLP_BPRU.ndcg, 4) : "–"}로 올렸고, BPR MF는 두 세계 모두 표본 MF보다 높았다. v2에서는 MLP 개선이 없었고(${ci(PR2["MLP_BPRU-MLP"])}), 어느 신경망도 규칙을 넘지 못했다(6.3절, 부록 E).`]),
  ...table(["항목", "제안서(9월)", "현재(10월 중간)"], [
    ["문제 정의", "ETF 교육 콘텐츠 다음 단원 추천", "투자 목적·수준 진단 → 로드맵 → 단원 추천 → ETF 유형 연결"],
    ["카탈로그", "주제 20 × 수준 3 = 60단원", `주제 ${D.catalog.n_topics} × 수준 3 = ${D.catalog.n_items}단원, 선수 관계 ${D.catalog.n_prereq_edges}개, 단원별 출처·개념 태그`],
    ["학습자 입력", "관심 주제·수준·기기·시간대·인구통계", "+ 투자 목적(5종)·투자 기간(3종)·진단 퀴즈 결과(20문항)"],
    ["추천 신호", "규칙 6개 + 인기·CF·MF·MLP", `+ 투자 목적 일치, 로드맵 단계 우선순위, BPR MF·쌍별 MLP·목표 정렬 MLP (신호 ${M.signal_count}개, 설정 ${num(M.configurations)}개)`],
    ["가드레일", "수준(두 단계 위 차단, 한 단계 위 1개), 통과 단원 제외", "+ 선수 단원 미이수 차단(평가에 별도 행으로 기록)"],
    ["데이터", "모의 데이터(노트북 생성기)", `모의 데이터 v2 + 공식 API 커넥터(KRX Open API·공공데이터포털)·수동 내려받기 정규화 + 출처 등록부 ${D.sources.length}건 + k-익명성 점검`],
    ["산출물", "노트북", "패키지·CLI·REST API·11단계 UI·테스트·스크린샷·재현 스크립트"],
  ], [2, 4, 6], { caption: "제안서 대비 중간 시점의 변화", zebra: true }),
);

// 2. 문제 정의
add(pageBreak(), h1("2. 문제 정의와 시나리오"),
  h2("2.1 배경: 상품은 급증했지만 학습 경로는 없다"),
  p("한국거래소 집계로 국내 상장 ETF는 2025년 7월 1,000종목을 넘었고, 2025년 ETF·ETN 시장 결산 기준 상장 종목 1,058개, 순자산총액 297조 2천억 원으로 1년 사이 71% 성장했다. 같은 기초지수를 따르는 상품이 운용사별로 여럿 상장되고, 커버드콜·월배당·레버리지·환헤지(H)·합성·액티브 같은 구조 변형이 더해지면서 초보 투자자가 상품명만 보고 차이를 이해하기 어려워졌다. 투자자 교육 자료는 전국투자자교육협의회 스쿨, 금융투자교육원 사전교육, 한국거래소 정보 포털, 운용사 가이드북 등 여러 곳에 흩어져 있고, 어느 것을 어떤 순서로 봐야 하는지 알려 주는 장치가 없다."),
  h2("2.2 보이지 않는 비용과 구조적 리스크"),
  p("학습자가 가장 자주 놓치는 네 가지를 이 시스템의 ‘필수 기초 개념’으로 삼았다."),
  ...table(["개념", "무엇이 문제인가", "로드맵에서의 위치"], [
    ["총보수(수수료)", "순자산에서 매일 조금씩 차감되어 가격에 숨어 있다. 같은 지수 ETF라도 총보수가 0.01%대에서 0.6%대까지 차이 나며, 장기 복리로 수익률 격차가 커진다.", "필수 기초 ‘ETF 총보수 이해하기’(수준 1) → ‘추적오차가 생기는 이유’(수준 2)"],
    ["괴리율(시장가격 vs NAV)", "장중 가격이 순자산가치와 벌어지면 비싸게 사거나 싸게 팔게 된다. 해외·원자재·거래량이 적은 ETF에서 커진다.", "‘ETF 가격은 어떻게 정해지나: NAV와 괴리율’(수준 2), ‘괴리율이 커지는 상황 이해하기’(수준 3)"],
    ["환헤지(H) 여부", "해외 ETF의 수익률에 환율 변동이 더해지는지(환노출) 상쇄되는지(환헤지)가 상품명 끝의 (H)로만 구분되고, 헤지 비용은 금리차에 따라 달라진다.", "‘환율이 해외 ETF 수익률에 미치는 영향’(수준 1) → ‘환헤지형과 환노출형 ETF 비교’(수준 2) → ‘환헤지 비용과 금리차’(수준 3)"],
    ["파생형 상품의 복리 효과", "레버리지·인버스 ETF는 ‘일간’ 수익률의 배수를 따르므로 횡보장에서 지수가 제자리여도 손실이 누적된다(음의 복리). 연금계좌 편입이 제한되고, 사전교육과 기본예탁금(1,000만원; 단일종목형은 현금 3,000만원, 사전교육 총 3시간, 신규 투자자 모의거래 5시간)이 있다.", "‘레버리지·인버스 ETF란’(수준 1) → ‘일일 수익률 복리와 음의 복리 효과’(수준 2) → ‘변동성 장세의 레버리지 위험과 거래 요건’(수준 3, 학습 요점 포함) → 유형 카드"],
    ["세제·계좌 관문(2차본 보강)", "같은 ETF라도 어느 계좌에서 사느냐에 따라 세금이 다르다: ISA(순이익 200만원·서민형 400만원 비과세, 초과분 9.9% 분리과세), 연금저축·IRP(과세이연, IRP 위험자산 70% 한도), 국내 상장 해외·채권·원자재 ETF의 보유기간과세(실제 차익과 과표기준가 상승분 중 작은 금액에 15.4%).", "‘절세 계좌’ 주제 3단원(신설), ‘IRP·연금저축의 ETF 투자 규칙과 위험자산 70% 한도’(수준 2), ‘해외 ETF 세금: 과표기준가·보유기간과세와 양도소득세’(수준 3)"],
  ], [2.2, 6, 4.3], { caption: "학습자가 놓치기 쉬운 비용·구조 리스크·세제 관문과 로드맵 배치", zebra: true }),
  h2("2.3 개인화된 학습의 부재"),
  p("같은 ‘ETF 초보’라도 노후 대비 연금 투자자는 연금계좌 편입 규칙·세액공제·과세이연과 자산배분을, 월 현금흐름을 원하는 투자자는 분배금·커버드콜·리츠·채권 ETF의 작동 원리를, 단기 트레이딩에 관심 있는 투자자는 유동성·호가 스프레드·괴리율과 레버리지의 복리 효과를 먼저 알아야 한다. 또 현재 지식 수준이 다르면 같은 단원이라도 너무 쉽거나 어려워 이탈로 이어진다. 기존 교육 포털은 목록을 나열할 뿐 이 두 축(목적 × 수준)으로 큐레이션하지 않는다. 이 프로젝트는 ‘진단 → 기초 → 목적별 핵심 → 심화 → ETF 유형 연결’의 로드맵 안에서 추천이 일어나도록 설계해 이 공백을 메운다."),
  h2("2.4 대상 사용자와 시나리오"),
  p("웹 UI의 자연어 예시 문장으로도 쓰인 세 가지 페르소나다. 괄호 안은 실제 시스템이 계산한 로드맵 규모다."),
  ...table(["페르소나", "진단", "로드맵(실제 계산)", "추천·연결"], [
    ["A. 45세 직장인, 연금저축·IRP로 노후 준비, 안정 성향, 10년 이상, 초급",
     `진단 퀴즈 ${D.questions.length}문항 중 기초 문항 위주로 정답 → 수준 1. 맞힌 단원은 ‘진단 통과’로 기록되어 후보에서 제외.`,
     `연금·노후 대비 템플릿: 단원 ${D.roadmaps.pension.units_total}개, 약 ${D.roadmaps.pension.minutes_total}분. 필수 기초(ETF 구조·총보수·NAV와 괴리율·유동성·환헤지·레버리지) → 분배금·채권·분산투자·연금계좌 투자·ISA 비과세 한도와 유형·환헤지형 비교·주식채권 자산배분·IRP 규칙과 위험자산 70% 한도 → 채권과 금리·리밸런싱·환헤지 비용·상관관계·세액공제·ISA 만기 자금의 연금계좌 전환. 안정 성향이므로 레버리지 심화 단원 제외.`,
     `다음 단원 ‘ETF란 무엇인가’부터 시작. 연결 유형: ${D.roadmaps.pension.types.join(", ")}. 연금계좌 편입 가능 여부·IRP 위험자산 70% 한도·과세이연과 ISA 만기 자금의 연금계좌 전환(추가 세액공제) 안내.`],
    ["B. 38세 중급, 월배당으로 현금흐름, 커버드콜·리츠 관심, 중립 성향, 3년",
     "수준 2 판정. 분배금·NAV 관련 단원은 진단 통과.",
     `배당·인컴 템플릿: 단원 ${D.roadmaps.income.units_total}개, 약 ${D.roadmaps.income.minutes_total}분. 분배금 지급 구조·커버드콜·리츠·채권 ETF·분배금 과세가 핵심 단계.`,
     `연결 유형: ${D.roadmaps.income.types.join(", ")}. 커버드콜의 ‘상승 제한·분배금 원천’ 주의 사항 카드.`],
    ["C. 27세 적극 성향, 단기 매매로 레버리지 ETF 사용 희망, 경험 없음, 몇 달 단위",
     "수준 1~2. 레버리지 복리 문항 오답 시 해당 단원이 로드맵의 필수 기초에 남음.",
     `단기 매매 템플릿: 단원 ${D.roadmaps.trading.units_total}개, 약 ${D.roadmaps.trading.minutes_total}분. 유동성·호가 스프레드·괴리율·레버리지 위험이 핵심·심화 단계에 배치되고 투자 기간이 짧아 ‘ETF 거래량과 유동성’ 심화가 추가.`,
     `연결 유형에 레버리지·인버스가 포함되지만 ‘개념 통과 + 금융투자교육원 사전교육(약 1시간) + 기본예탁금 1,000만원(단일종목형은 현금 3,000만원·사전교육 총 3시간·신규 투자자 모의거래 5시간)’을 안내한 뒤에 카드가 열림. 예탁금이 없으면 교육을 마쳐도 매수 주문이 들어가지 않는다는 점을 카드 주의 사항에 명시. 심화 단계에 과표기준가 단원(해외 ETF 3)을 넣어 단기 매매자의 세금 계산을 다룸.`],
  ], [3, 3, 5, 4], { caption: "세 가지 페르소나 시나리오", zebra: true }),
  h2("2.5 추천 문제의 정의"),
  bullet([{ t: "입력: ", bold: true }, "학습자 프로필(연령·소득·투자 경험·위험성향·기기·시간대, 성별은 수집하되 운영 설정에서 제외), 투자 목적(연금·노후 / 배당·인컴 / 장기 지수 / 단기 매매 / 분산·안정), 투자 기간(1년 미만 / 1~5년 / 5년 이상), 관심 주제 2개, 진단 퀴즈 결과 또는 학습 기록(조회·완료·퀴즈 통과·저장·이탈)."]),
  bullet([{ t: "출력: ", bold: true }, "① 단계별 로드맵(단원 상태: 통과·학습 가능·잠김, 남은 학습 시간, 다음 단원), ② 지금 공부할 단원 Top-5(점수·근거·신호 기여도·출처 링크), ③ ETF 유형 안내 카드(개념 통과 여부, 세금·연금계좌·규제·주의, 유형 통계)."]),
  bullet([{ t: "정답 정의(오프라인): ", bold: true }, "기준 주 다음 주에 학습자가 퀴즈를 통과한 단원. 후보는 ‘아직 통과하지 않은 단원 ∩ 수준 가드레일(추정 수준 + 2 이상 차단, 한 단계 위 최대 1개) ∩ (선택) 선수 단원 통과’로 제한한다."]),
  bullet([{ t: "제약: ", bold: true }, "특정 ETF 상품의 매수·매도 권유 금지(화면·API 응답에 고지문 포함), 성별을 운영 라우터에서 제외, 요청 중 재학습 없음(미리 학습된 번들만 사용), 교육 자료는 링크·출처만 저장하고 본문을 복제하지 않음."]),
  bullet([{ t: "성공 기준: ", bold: true }, "오프라인 NDCG@5가 인기·무작위 기준선을 유의하게 앞서고(95% 부트스트랩 구간), 선수 단원 위반 0, 집단별 정확도 격차가 설명 가능하며, 온라인에서는 다음 주 퀴즈 통과율이 대조군(인기순)보다 높을 것(7절)."]),
);

// 3. 추천 기법
add(pageBreak(), h1("3. 추천 기법 요약과 한계"),
  p("수업에서 다룬 기법을 이 문제에 맞게 정의하고, 각 기법이 필요로 하는 데이터와 한계, 이 시스템에서의 역할을 정리했다. 모든 기법은 같은 후보 집합·같은 정답·같은 후처리(가드레일·주제 상한)를 거쳐 비교되므로 표의 수치 차이는 기법 자체의 차이다."),
  h2("3.1 기법별 요약"),
  ...table(["기법", "핵심 아이디어·수식", "필요 데이터", "장점", "한계", "이 시스템에서의 역할"], [
    ["인기(POP)", "단원별 통과·완료 점수의 합. 세그먼트 인기는 세그먼트 평균을 전역 평균으로 수축: n/(n+λ)·세그먼트 + λ/(n+λ)·전역", "학습 로그", "콜드스타트에 강함, 단순·안정", "개인화 없음, 인기 편향, 다양성 1.0에 가깝지만 교육 순서 무시", "기준선, 하이브리드의 구성 신호(λ 격자 10·20·50·100)"],
    ["규칙(지식 기반)", "기본 5 + 관심 주제 3 + 수준 일치 2 + 모바일·짧은 콘텐츠 1 + 소득 구간 주제 + 위험성향 주제 + 투자 목적 일치 2 + 로드맵 단계 우선순위 2", "프로필·목적·카탈로그", "설명 가능, 로그 없이 동작, 교육 정책을 직접 넣을 수 있음", "가중치가 사람 판단, 로그가 쌓여도 스스로 개선되지 않음", "검증 1위(목적 일치 포함). 라우터의 기본 설정"],
    ["콘텐츠 기반", "단원 특징(주제·수준 원-핫 + 제목 문자 TF-IDF)과 학습자 선호 프로필의 코사인 유사도", "카탈로그 텍스트, 학습자 이력", "신규 단원에 강함, 근거 제시 쉬움", "비슷한 것만 추천(과특화), 이력 없으면 관심 주제만 의존", "하이브리드 구성 신호, 운용사 가이드북 텍스트로 확장 예정"],
    ["사용자 CF", "코사인 유사 학습자 k명(k=20·50)의 반응 가중 평균, 인구통계 혼합 변형", "충분한 사용자×단원 반응", "집단 지성, 의외의 발견", `희소성(밀도 ${pct(DS.density, 0)})·콜드스타트, 선수 구조 무시(선수 미이수 ${fmt(resBy.UCF.prereq_violation_rate, 2)}), 계산량`, "비교 기준선, CF 신뢰도 게이트 n/(n+10) 적용"],
    ["아이템 CF", "단원 간 수축 코사인 유사도(λ=10)로 ‘함께 통과한 단원’ 점수", "반응 행렬", "안정적, 오프라인 사전 계산", "인기 단원 쏠림, 새 단원 불가", "비교 기준선, 하이브리드 구성 신호"],
    ["행렬분해(MF)", "표본 MF(6·9주차): 관측 칸은 신뢰도 1+α·log(1+점수) 가중, 미관측 칸은 표본추출해 0으로 둔 가중 MSE. 관측 MF: 관측된 행만 MSE. 둘 다 사용자·단원 잠재요인 내적, Adam", "반응 행렬(암묵 피드백)", "희소 행렬 일반화", "점수 회귀(점별 손실)라 순위를 직접 학습하지 않음, 해석 어려움", "비교 기준선(torch 학습, NumPy 추론)"],
    ["MLP(9주차)", "사용자·단원 임베딩 → 은닉층 → 통과 확률(BCEWithLogitsLoss). 관측된 시도 행만 학습(양성 = 통과, 음성 = 시도했지만 미통과). 미관측 단원은 학습에 쓰지 않음", "관측 시도 + 통과 레이블", "비선형 상호작용", `시도하지 않은 단원과 시도한 단원을 비교하는 법을 배우지 못함(다음 주 선택 예측과 어긋남). 인기 대비 v2 ${fmt(resBy.MLP.ndcg - resBy.POP.ndcg, 3)}, 무작위 대비 v1 ${fmt(v1By.MLP.ndcg - v1By.Random.ndcg, 3)}(6절)`, "비교 기준선"],
    ["쌍별·목표 정렬 확장(2차본)", "BPR MF: −ln σ(p_u·q_i − p_u·q_j), j = 미관측 단원(에폭마다 다시 추출) / MLP 쌍별(관측 음성): (통과, 미통과 시도) 쌍 / MLP 쌍별(미관측 음성): (통과, 미관측) 쌍 = 비판이 처방한 BPR / MLP 목표 정렬: (주 w에 처음 통과한 단원, 그 주까지 통과하지 않은 단원) 쌍", "반응 행렬·관측 시도·주차", "미관측을 ‘거절’이 아니라 ‘양성보다 뒤’로 보는 순위 학습, 평가 목표(다음 주 통과)와 맞춘 레이블", `세계에 따라 효과가 다름: 미관측 음성 쌍별 MLP는 v1에서 ${fmt(v1By.MLP.ndcg, 3)} → ${v1By.MLP_BPRU ? fmt(v1By.MLP_BPRU.ndcg, 3) : "–"}(${eff(BPRU1)}), v2에서는 ${eff(BPRU2)}. 신경망 최고치가 v1 ${fmt(nnBest1, 3)}·v2 ${fmt(nnBest2, 3)}로 규칙(${fmt(v1By.RULE.ndcg, 3)}·${fmt(resBy.RULE.ndcg, 3)}) 아래(6.3절)`, "같은 후보·정답·후처리로 비교(기법군 MF_BPR·MLP_BPR·MLP_BPRU·MLP_NEXT)"],
    ["하이브리드", "신호 가중합 또는 α_u 가중: α_u = n_u/(n_u+λ)로 이력이 많을수록 CF 비중 ↑", "위 모두", "콜드스타트와 개인화를 잇는 전환", `조합 수 폭발(${num(M.configurations)}개) → 검증으로 선택 필요`, "설정 풀의 대부분(HYBR 1,024개 등)"],
    ["세그먼트 라우터", "학습활동→선호군집→연령대→소득분위(→성별) 계층에서 세그먼트별 최적 설정을 전역 1위로 수축(λ 교차 선택, 잎 최소 20명)", "검증 주차 사용자별 점수", "집단마다 다른 설정 가능", "세그먼트가 작으면 과적합 → λ 커지며 전역과 동일해짐", "운영 설정(성별 제외). 이번 데이터에서 전역 1위와 유의한 차이 없음"],
  ], [1.6, 3.6, 1.8, 2, 3, 2.6], { caption: "추천 기법 요약과 한계", size: 16, zebra: true }),
  h2("3.2 한계에 대한 설계상의 대응"),
  ...table(["한계", "증상(이 프로젝트에서 관찰)", "대응"], [
    ["콜드스타트", "기록 없는 신규 학습자는 CF·MF 점수가 0", "진단 퀴즈로 수준·통과 단원을 즉시 확보, 규칙·콘텐츠·세그먼트 인기 신호, α_u 가중으로 기록이 쌓이면 CF 비중 증가"],
    ["희소성", `사용자×단원 밀도 ${pct(DS.density)}(학습 결과로 계산한 값이며 생성기의 제약이 아님), 검증 사용자 ${pct(M.validation.zero_observed_target / M.validation.rows, 0)}가 다음 주 정답 0개`, "수축(λ)·CF 신뢰도 게이트. 정답 없는 사용자를 NDCG 0으로 넣은 전체 기준(노트북 규칙)과 정답이 있는 사용자만 평균한 활성 기준을 함께 보고(6.1절)"],
    ["인기 편향·다양성 저하", "인기 신호 비중이 크면 모두 같은 단원", "Diversity@5·주제 상한 옵션, 추천 근거에 기여도 분해 표시"],
    ["학습 목표·손실의 불일치", "MF·MLP가 인기보다 낮음(v1의 MLP는 무작위보다 낮음)", `같은 실행에서 네 가지 변형을 비교했다(6.3절 표). BPR MF는 표본 MF 대비 v1 ${eff(MFB1)}·v2 ${eff(MFB2)}, 미관측 음성 쌍별 MLP는 MLP 대비 v1 ${eff(BPRU1)}·v2 ${eff(BPRU2)}, 다음 주 통과를 직접 레이블로 쓴 목표 정렬 MLP는 v1 ${eff(NEXT1)}·v2 ${eff(NEXT2)}였다. 1차본의 ‘손실 함수가 아니라 목표 불일치’라는 단정은 실험 없이 쓴 문장이라 정정한다`],
    ["교육 순서 무시", `운영 라우터 Top-5의 ${pct(resBy.RouterNoGender.prereq_violation_rate, 0)}가 선수 단원 미이수`, "로드맵 단계 우선순위 신호 + 선수 단원 가드레일, 평가에 ‘선수 미이수 비율’ 지표 추가"],
    ["공정성·민감 속성", "성별이 추천을 바꾸면 안 됨", "운영 라우터에서 성별 제외, 성별 뒤집기 불변 검사(코드 수준), 집단별 NDCG·심화 콘텐츠 노출 비율 보고"],
    ["설명가능성", "학습자가 ‘왜 이 단원인지’ 알 수 없음", "신호별 기여도·근거 문장·계산식·세그먼트 경로를 API 응답과 화면에 표시"],
  ], [2, 4, 6.5], { caption: "기법 한계와 대응", zebra: true }),
  h2("3.3 종합: 왜 ‘하이브리드 + 라우터 + 로드맵 가드레일’인가"),
  p("교육 추천은 ‘학습자가 클릭할 것’이 아니라 ‘학습자가 지금 배워야 하고 통과할 수 있는 것’을 골라야 한다. 그래서 정확도만 높이는 모델 하나보다, (1) 교육 정책을 직접 담을 수 있는 규칙과 로드맵 신호, (2) 기록이 쌓이면 자동으로 개인화되는 CF·MF 신호, (3) 둘을 검증 데이터로 섞는 하이브리드와 세그먼트 라우터, (4) 어떤 설정이 선택되든 교육 순서와 난이도를 지키는 가드레일을 층으로 쌓았다. 설정 선택은 검증 주차에서 한 번만 하고 잠근 뒤 테스트 주차에서 보고하므로, 결과 표의 수치는 선택 과정에 오염되지 않은 추정치다."),
);

// 4. 데이터
add(pageBreak(), h1("4. 데이터와 확보 계획"),
  h2("4.1 데이터 유형과 스키마"),
  p("시스템은 네 종류의 데이터를 쓴다. 학습 로그는 실제 서비스 로그가 생기기 전까지 규칙을 공개한 모의 데이터로 대체하고, 나머지는 공개 출처에서 가져온다."),
  ...table(["유형", "내용", "현재 출처", "스키마·형식"], [
    ["① 학습자 프로필·학습 로그", "온보딩 프로필, 투자 목적·기간, 진단 결과, 단원별 조회·완료·퀴즈·저장·이탈 이벤트", "모의 데이터 v2(4.5절). 실제 로그 연결 시 같은 스키마", "profiles.csv: user, gender, age, income, exp, risk, mobile, interest1, interest2, placement, goal*, horizon* / study_log.csv: user, item, week, day, hour, minute, complete, quiz, quiz_pass, save, drop, replay"],
    ["② 콘텐츠 카탈로그", `단원 ${D.catalog.n_items}개(주제 ${D.catalog.n_topics} × 수준 3), 선수 관계 ${D.catalog.n_prereq_edges}개, 단원별 개념 태그·출처 키·예상 학습 시간`, "직접 설계(교육 자료 목차 기반). 금칙어 검사 통과", "catalog.csv: item, title, topic, level, short, prereqs*(\"0;3\"), sources*(\"kcie_etf_school;krx_etf_info\")"],
    ["③ ETF 상품 메타데이터·시세", "종목명·운용사·기초지수·총보수·과세유형·복제방법·기초시장·자산 분류, 종가·NAV·거래량", "KRX 정보데이터시스템, 공공데이터포털(금융위원회) API", "커넥터가 표준 열로 정규화: name, issuer, index, total_fee, tax_type, market, asset, hedged, futures, total_return, etf_type, pension_eligible"],
    ["④ 교육 자료·용어", "스쿨 강의, 사전교육, 투자설명서·용어집, 가이드북", "전국투자자교육협의회, 금융투자교육원, 한국거래소, 운용사", "출처 등록부(이름·기관·URL·메뉴 경로·종류·접근·이용 조건·확인 상태). 본문은 저장하지 않음"],
  ], [2.2, 3.6, 2.8, 4.4], { caption: "데이터 유형(별표 * 는 선택 열)", zebra: true }),
  h2("4.2 공개 데이터·교육 자료 출처 등록부"),
  p("아래 표는 시스템 안의 출처 등록부(etfrec/sources/registry.py)를 그대로 옮긴 것이다. ‘확인’ 열은 2026년 10월 기준 검색으로 확인한 범위를 뜻하며, 기관 개편으로 세부 주소가 바뀔 수 있어 화면에서는 기관 루트와 메뉴 경로를 함께 보여 준다."),
  ...table(["출처", "종류 · 접근", "시스템에서의 쓰임", "이용 조건", "확인"],
    D.sources.map(s => [[{ t: s.name, bold: true }], [s.kind, { t: " · " + s.access, color: GREY }], s.use, s.license, s.verified]),
    [3, 3, 4, 2.8, 1.6], { caption: "공개 데이터·교육 자료 출처 등록부(12건)", size: 16, zebra: true }),
  h2("4.3 접근 설계와 커넥터"),
  bullet([{ t: "KRX 정보데이터시스템 ETF 전종목 기본정보(2차본 변경): ", bold: true }, "1차본은 화면이 쓰는 JSON 엔드포인트를 프로그램으로 호출했으나, 이용약관(자동 수집·서버 부하)과 서비스 중단 위험을 지적받아 그 코드를 삭제했다. 이제 이용자가 화면에서 직접 내려받은 CSV·Excel(종목명·운용사·기초지수·총보수·과세유형·복제방법·기초시장·기초자산)을 `python -m etfrec sources sync --krx-csv 파일`로 정규화해 쓰고, 수집 경로를 provenance에 ‘official-apis-and-manual-download-only’로 기록한다."]),
  bullet([{ t: "KRX Open API(공식): ", bold: true }, "openapi.krx.co.kr에서 인증키를 발급받고 서비스별 이용을 신청한 뒤(비상업적 이용, 재배포 금지, 출처 표기) ETF 일별매매정보(종가·NAV·거래량·기초지수 종가)를 받아 괴리율을 계산한다. 호출 간 대기를 두어 일 한도를 지킨다. 엔드포인트 경로는 활용 가이드 기준이며 설정으로 바꿀 수 있다."]),
  bullet([{ t: "공공데이터포털 증권상품시세정보(ETF): ", bold: true }, "금융위원회 오픈 API getETFPriceInfo를 serviceKey(환경변수 DATA_GO_KR_KEY 또는 --datagokr-key)로 호출해 종가·NAV·거래량·기초지수 종가를 받고 괴리율 = (종가 − NAV)/NAV를 계산한다. 무료, JSON/XML."]),
  bullet([{ t: "정규화와 분류: ", bold: true }, "종목명·기초시장·기초자산 키워드 규칙으로 ETF 유형 10종을 분류하고(레버리지·인버스 → 인컴·커버드콜 → 자산배분 → 채권 → 원자재·통화 → 리츠·인프라 → 액티브·ESG → 국내 섹터·테마 → 해외 주식형 → 국내 시장대표 순으로 우선 적용), 환헤지(H)·선물형·TR·연금계좌 편입 가능 플래그를 붙인다. 유형별 종목 수·환헤지 변형 수·총보수 중앙값·운용사 수를 교육용 통계로 보여 준다."]),
  bullet([{ t: "스냅샷과 출처 기록: ", bold: true }, "python -m etfrec sources sync가 data/sources/에 CSV 스냅샷과 provenance.json(수집 시각·행 수·엔드포인트)을 쓰고, 서버는 스냅샷이 있으면 ‘KRX 스냅샷’, 없으면 패키지에 든 가상 종목 45개 샘플을 ‘샘플 데이터’ 배지와 함께 쓴다. 수집 전후로 화면의 숫자가 어디서 왔는지 항상 표시된다."]),
  bullet([{ t: "교육 자료: ", bold: true }, "저작권이 있는 강의·가이드북은 링크·메뉴 경로·출처 키만 단원에 연결한다. 운용사 가이드북 텍스트를 콘텐츠 특징으로 쓰는 확장은 인용·요약 범위에서만 진행하고 원문 재배포는 하지 않는다."]),
  note([{ t: "현재 확인 상태. ", bold: true }, "이 개발 환경은 한국 공공·금융 도메인으로의 네트워크 접근이 차단되어 있어 커넥터는 응답 형식에 관대하게 작성했고 실제 수집은 로컬 환경에서 ‘python -m etfrec sources check / sync’로 실행할 예정이다(8절 일정). 출처 표의 메뉴 이름·이용 조건·금융투자교육원 사전교육(약 1시간, 수료 후 증권사에 이수번호 등록, 평생 1회)은 검색으로 확인했다. 공공데이터포털 API 2건은 요청 변수·무료·JSON/XML 제공을 검색 결과에서 확인했다."]),
  h2("4.4 모의 데이터 생성기 v2"),
  p("실제 로그가 없으므로 규칙을 공개한 생성기로 ‘가상 세계’를 만들고, 그 세계에서 기법을 비교한다. 노트북 B의 생성기(v1)는 난수 순서까지 그대로 보존해 재현성을 유지했고, v2는 다음을 더했다."),
  bullet("투자 목적은 연령·위험성향·소득분위·경험에 따른 분포에서 표본추출(연금은 40대 이상에서, 단기 매매는 적극 성향에서 확률이 높음)하고, 투자 기간은 목적에 따라 뽑는다."),
  bullet("목적-주제 친화도 행렬이 주제 선호 로짓에 더해진다(강도 0.8). 예: 연금 목적은 연금계좌 ETF·자산배분·채권 ETF 선호가 올라간다."),
  bullet("아직 이해하지 못한 선수 단원 수(최대 2)만큼 완료·퀴즈 통과 로짓이 0.8씩 낮아진다. 이 값이 선수 가드레일의 비용을 좌우하므로 6.6절에서 민감도를 본다."),
  bullet("이벤트는 시도 단위의 상태 전이로 생성된다: 완료 여부 → (완료일 때만) 퀴즈 시도 → (시도일 때만) 통과, 미완료일 때만 이탈, 저장은 관심 주제에 따라 독립. 따라서 ‘이탈이면서 완료’ 같은 모순 행은 구성상 생길 수 없고, QA 검사 event_logic_* 가 매 학습마다 이를 확인한다(아래 표의 논리 제약 행)."),
  bullet(`이벤트 열은 서로 배타적인 범주가 아니라 한 시도에 붙는 플래그다. 그래서 ‘완료 + 퀴즈 통과 + 저장 + 이탈’의 합(${num(EV.sum4)})은 시도 수(${num(DS.study_attempts)})보다 ${num(EV.excess)} 많고, 이 차이는 퀴즈 통과(${num(DS.quiz_pass)}, 이미 완료에 포함) + 저장(${num(DS.save)}, 독립 플래그) − 미완료이면서 이탈하지 않은 시도(${num(EV.ncnd)}, 네 열 어디에도 잡히지 않음)로 정확히 분해된다. 1차본 수치(108,777건, 합 134,041건, 차이 25,264건)도 24,187 + 12,825 − 11,748로 똑같이 분해된다.`),
  bullet("밀도(사용자×단원 고유 쌍의 비율)는 생성 결과로 계산한 값이며 생성기의 목표나 제약이 아니다. 생성기는 주마다 활동 학습자를 뽑고, 각자 1~8개 단원을 효용(관심 주제·수준 차이·인기·선수 미이수) 순위로 고른다."),
  bullet("행동 점수는 한 시도의 플래그를 max(조회 1, 완료 2, 퀴즈 통과 3, 저장 3) 하나로 줄이므로 같은 시도의 플래그가 중복 집계되지 않는다. 같은 학습자가 같은 단원을 여러 주에 걸쳐 다시 시도하면 반응 행렬에서 점수를 더한다. 반복 학습을 더 강한 신호로 보는 설계 선택이며 etfrec/features.py에 있다."),
  bullet("운영 로그(CSV)를 연결할 때는 normalize_event_flags가 같은 논리(통과 ⇒ 퀴즈 ⇒ 완료, 이탈 ⇒ 미완료)로 행을 맞추고 고친 행 수를 데이터 요약(event_repairs)에 남긴다. 화면에서 임의 학습자의 기록을 받을 때도 완료와 이탈이 함께 들어오면 이탈을 끈다(2차본에서 고친 결함). 모의 데이터는 v1·v2 모두 고친 행이 0건이다."),
  bullet("연령·소득·성별 효과는 가정값이며 ‘--effect 0’ 위약 세계에서 인구통계를 쓰는 설정의 이점이 사라지는지로 파이프라인이 없는 효과를 만들어 내지 않는지 확인한다."),
  ...table(["항목", "값"], [
    ["학습자 · 단원 · 주차", `${num(DS.users)}명 · ${DS.items}개 · ${DS.weeks}주(학습 0~1주, 검증 2주, 테스트 3주)`],
    ["학습 시도(행 수)", `${num(DS.study_attempts)}건 — 한 행이 한 번의 학습 시도이고, 아래 이벤트 열은 그 시도에 붙는 다중 플래그라 합계가 시도 수를 넘는 것이 정상이다`],
    ["  ├ 완료 / 미완료", `${num(DS.complete)} / ${num(DS.not_complete != null ? DS.not_complete : DS.study_attempts - DS.complete)}`],
    ["  │   ├ 퀴즈 시도 ⊆ 완료", `${DS.quiz_attempted != null ? num(DS.quiz_attempted) : "–"}`],
    ["  │   │   └ 퀴즈 통과 ⊆ 퀴즈 시도", `${num(DS.quiz_pass)}`],
    ["  │   └ 이탈 ⊆ 미완료(완료와 동시 불가)", `${num(DS.drop)}`],
    ["  └ 저장(독립 플래그) · 재학습", `${num(DS.save)} · ${DS.replay != null ? num(DS.replay) : "–"}`],
    ["논리 제약(QA로 검증, 모두 0이어야 함)", `이탈∧완료 ${DS.drop_and_complete ?? "–"}건 · 통과∧¬퀴즈 ${DS.pass_without_quiz ?? "–"}건 · 퀴즈∧¬완료 ${DS.quiz_without_complete ?? "–"}건`],
    ["검산: 네 열의 합 − 시도 수", `${num(EV.sum4)} − ${num(DS.study_attempts)} = ${num(EV.excess)} = 통과 ${num(DS.quiz_pass)} + 저장 ${num(DS.save)} − 미완료·비이탈 ${num(EV.ncnd)}`],
    ["사용자×단원 고유 쌍 · 밀도", `${num(DS.distinct_pairs)} · ${pct(DS.density)}`],
    ["투자 목적 분포", Object.entries(DS.goals).map(([g, n]) => `${GOAL_KO[g]} ${num(n)}`).join(" · ")],
    ["투자 기간 분포", Object.entries(DS.horizons).map(([g, n]) => `${HOR_KO[g]} ${num(n)}`).join(" · ")],
    ["검증 주차(2주) 사용자 · 정답 없는 사용자", `${num(M.validation.rows)} · ${num(M.validation.zero_observed_target)} (후보 ${M.validation.eligible_min}~${M.validation.eligible_max}개)`],
    ["테스트 주차(3주) 사용자 · 정답 없는 사용자", `${num(M.test.rows)} · ${num(M.test.zero_observed_target)} (후보 ${M.test.eligible_min}~${M.test.eligible_max}개)`],
  ], [4, 8.5], { caption: "모의 데이터 v2 요약(seed 42)", zebra: true }),
  h2("4.5 윤리·저작권·개인정보"),
  p("가명 번호만으로는 충분하지 않다는 전제로 설계한다(2차본 보강). 연령대·소득분위·성별·경험·성향·투자 목적과 접속 시간대가 결합되면 외부 자료와 교차해 재식별될 수 있으므로(모자이크 효과), 학습 파이프라인이 매 학습마다 준식별자 조합의 k-익명성을 계산해 번들에 기록하고 k 미만 셀에 대한 일반화 계획을 남긴다. 제도 근거: 개인정보보호법 과징금 상한은 전체 매출액의 3%(2023년 9월 시행)이고 2026년 3월 개정으로 반복·중대 위반에는 최대 10% 특례가 도입되었으며(9월 시행), 가명정보 처리 가이드라인은 2026년 3월 31일 위험도 기반 체계로 전면 개정되었다."),
  ...table(["점검 항목", "현재 번들(모의 데이터)", "운영 기준"], [
    ["라우팅 세그먼트(연령대×소득분위×성별) k-익명성", PRIV.routing ? `${PRIV.routing.groups}개 셀, 최소 ${PRIV.routing.min_group}명, k=${PRIV.routing.k} ${PRIV.routing.satisfied ? "충족" : "미충족"}` : "–", "잎 최소 20명(라우터 λ 수축과 동일 기준). 미달 셀은 상위 집단으로 묶음"],
    ["준식별자 6개 조합(연령대·소득분위·성별·경험·성향·목적)", PRIV.quasi ? `${PRIV.quasi.groups}개 셀, 최소 ${PRIV.quasi.min_group}명, k=${PRIV.quasi.k} 미만 ${PRIV.quasi.groups_below_k}개 셀(${num(PRIV.quasi.users_below_k)}명, ${pct(PRIV.quasi.share_below_k)})` : "–", (PRIV.generalization && PRIV.generalization.length) ? `일반화 계획: ${PRIV.generalization.map(g => g.drop).join(" → ")} 열을 순서대로 제거하면 k=${PRIV.quasi.k} 충족` : "k 충족 — 추가 일반화 불필요"],
    ["최소화·접근 통제 정책", "번들에 원시 연령·소득이 아닌 세그먼트 코드와 집계만 저장, 성별 미사용", D.policy.slice(0, 4).join(" / ")],
  ], [3.4, 4.6, 4.5], { caption: "개인정보 점검(etfrec/privacy.py, manifest.privacy)", size: 16, zebra: true }),
  bullet("학습 로그는 가명 처리된 사용자 번호만 쓰고, 성별은 수집하더라도 운영 라우터·운영 설정에서 제외하며 뒤집기 검사로 영향이 없음을 확인한다. 가명처리 담당과 모델 학습 담당의 권한·망을 분리하고 매핑표는 분리 보관한다."),
  bullet("교육 자료는 링크와 출처만 저장하고 본문을 복제하지 않는다. 운용사 자료는 인용·요약 범위에서만 쓴다. KRX 데이터의 자동 수집은 개인 학습·연구 범위로 제한하고 대량 수집 전 이용 약관을 확인한다."),
  bullet("모든 화면과 API 응답에 ‘특정 ETF의 매수·매도를 권유하지 않는다’는 고지와 ‘유형 안내는 학습 순서를 돕기 위한 분류이지 개별 상품의 적합성 판단이 아니다’라는 문구를 넣었고, 단원 제목에 금칙어(수익 보장·추천 종목 등)가 없는지 검사한다."),
);

// 5. 시스템 설계
add(pageBreak(), h1("5. 시스템 설계와 구현 현황"),
  h2("5.1 아키텍처"),
  ...img("fig1_architecture.png", "시스템 아키텍처: 데이터 계층 → 학습·선택 → 교육 설계 모듈 → 서빙"),
  p(`데이터 계층의 네 가지 입력은 특징 저장소에서 반응 행렬·추정 수준·선호·세그먼트 코드·목적으로 바뀌고, ${M.signal_count}개 신호와 ${num(M.configurations)}개 설정이 검증 주차에서 평가된 뒤 세그먼트 라우터로 잠긴다. 교육 설계 모듈(진단 퀴즈·로드맵 엔진·가드레일·유형 분류)은 학습 단계에는 신호와 후보 제한으로, 서빙 단계에는 로드맵·유형 카드 응답으로 들어간다. 서빙은 미리 학습된 번들만 읽으므로 요청 중 재학습이 없고 응답은 수십 ms다.`),
  h2("5.2 로드맵 엔진"),
  ...img("fig2_roadmap_flow.png", "로드맵 다섯 단계와 연금·노후 대비 목적의 예시 단원"),
  p(`로드맵은 다섯 단계로 구성된다. ① 진단: ${D.questions.length}문항 퀴즈 또는 학습 기록으로 수준(1~3)과 이미 아는 단원을 정한다. ② 필수 기초 개념: 모든 목적에 공통인 ETF 구조·총보수·NAV와 괴리율·유동성·환헤지·레버리지 일일 복리(선수 관계 닫힘까지 포함). ③ 목적별 핵심 개념: 목적 템플릿의 단원과 그 선수 단원. ④ 심화·리스크: 목적별 심화 단원에 투자 기간(단기 → 유동성 2, 장기 → 리밸런싱 2)과 위험성향(안정이면 레버리지 심화 제외)을 반영. ⑤ ETF 유형 연결: 목적·성향에 맞는 유형 카드로, 각 유형의 필요 개념 단원을 모두 통과해야 열린다. 각 단계의 단원은 선수 단원이 먼저 오도록 위상정렬되고 상태(통과·학습 가능·잠김)와 남은 학습 시간을 갖는다. 세제·규제 단원(ISA 3단원, 과표기준가, IRP 70% 한도, 레버리지 거래 요건)에는 기준일을 단 학습 요점·계산 예시가 붙어 로드맵 화면에서 펼쳐 볼 수 있다(부록 F).`),
  ...img("fig3_prereq_graph.png", `연금·노후 대비 로드맵 ${D.roadmaps.pension.units_total}개 단원의 선수 관계(숫자는 단원 번호)`),
  ...table(["투자 목적", "목적별 핵심 개념(템플릿)", "심화·리스크", "연결 유형", "단원 수 · 시간"], Object.entries(D.templates).map(([g, t]) => [
    GOAL_KO[g], t.core.map(x => `${x[0]} ${x[1]}`).join(", "), t.advanced.map(x => `${x[0]} ${x[1]}`).join(", "), D.roadmaps[g].types.join(", "),
    `${D.roadmaps[g].units_total}개 · 약 ${D.roadmaps[g].minutes_total}분`]), [1.8, 4.2, 3, 2.6, 1.6], { caption: "투자 목적별 로드맵 템플릿(주제 뒤 숫자는 수준)", size: 16, zebra: true }),
  p("로드맵은 추천 엔진에 두 방향으로 들어간다. 첫째, 로드맵 단계 우선순위 신호(현재 단계의 학습 가능 단원 1.0, 다음 단계 0.7, 선수 미이수 0.4, 로드맵 밖 0)와 투자 목적 일치 신호가 규칙·하이브리드 설정 풀에 추가되어 검증에서 비중이 결정된다. 둘째, 선수 단원 가드레일(prereq_block)은 선수 단원을 통과하지 않은 단원을 후보에서 제외한다. 가드레일은 수업의 교육 처방이 아니라 이 프로젝트의 정책이므로 화면에서 켜고 끌 수 있고, 오프라인 평가에는 ‘운영 라우터 + 선수 가드레일’ 행으로 효과를 따로 기록했다."),
  h2("5.3 진단 퀴즈"),
  p(`${D.questions.length}문항(수준 1 ${QL(1)}개·수준 2 ${QL(2)}개·수준 3 ${QL(3)}개, ${QUNITS}개 단원; 2차본에서 ISA·과표기준가·IRP 70% 한도·기본예탁금 문항 추가)으로 구성했고 각 문항은 카탈로그 단원 하나에 대응한다(부록 B). 해외 ETF 3과 연금계좌 ETF 2에는 문항이 둘씩 있어, 답한 문항을 모두 맞혀야 그 단원을 ‘진단 통과’로 기록하고 이벤트는 단원마다 한 번만 만든다. 레버리지 거래 요건 문항(q20)은 규제 상식이라 변동성 위험 단원 전체를 검사하지 못하므로 수준 판정에만 쓰고 단원을 통과 처리하지 않는다. 정답 위치는 보기 네 자리에 다섯 개씩 나눴다(1차본은 16문항 중 13문항이 두 번째 보기였다). 수준 판정은 답한 문항만으로 계산한다. 수준 1 정답률 60% 이상이고 수준 2 정답률 50% 이상이면 수준 2, 여기에 수준 2 정답률 75% 이상, 서로 다른 주제의 수준 3 문항 2개 이상 정답, 수준 3 정답률 60% 이상이면 수준 3이다. 틀린 문항은 기록하지 않고(진단은 배치이지 실패 기록이 아니다) 정답과 해설을 보여 준다.`),
  h2("5.4 ETF 유형 분류"),
  ...table(["유형", "위험", "필요 개념(통과해야 카드가 열림)", "적합 목적", "세금·연금계좌·규제 요약"], D.types.map(t => [
    [{ t: t.name, bold: true }], "●".repeat(t.risk) + "○".repeat(5 - t.risk), t.concepts.map(c => `${c[0]} ${c[1]}`).join(", "), t.goals.map(g => GOAL_KO[g]).join(", "),
    [t.tax, { t: " / " + t.pension, color: GREY }, ...(t.regulation ? [{ t: " / " + t.regulation, color: GOLD }] : [])]]),
    [2, 1, 3.4, 2.2, 4.4], { caption: "ETF 유형 10종과 연결 조건", size: 16, zebra: true }),
  h2("5.5 신호·설정 풀·검증·라우터"),
  ...table(["단계", "내용"], [
    ["특징 저장소", "기준 주 이전 로그로 사용자×단원 반응 행렬(시도마다 조회 1·완료 2·통과/저장 3의 최댓값, 같은 단원의 반복 시도는 합산), 통과 단원, 추정 수준, 주제 선호, 세그먼트 코드(학습활동·선호군집·연령대·소득분위·성별), 투자 목적·기간"],
    [`신호 ${M.signal_count}개`, "인기, 세그먼트 인기(변수 5 × λ 4), 개인화 인기, 콘텐츠 코사인, 사용자 CF(k·혼합), 아이템 CF, 표본 MF, BPR MF(2차본), 관측 MF, MLP, MLP 쌍별(관측 음성·미관측 음성)과 목표 정렬 MLP(2차본), 규칙 8개 부분(기본·관심 주제·수준 일치·모바일·소득 구간·위험성향·투자 목적·로드맵 단계), 맥락 신호"],
    [`설정 풀 ${num(M.configurations)}개`, Object.entries(M.family_counts).map(([k, v]) => `${k} ${v}`).join(" · ") + " (혼합 비중·세그먼트 변수·λ 격자의 조합, CF 신뢰도 게이트 n/(n+10))"],
    ["검증·선택", "검증 주차(2주) NDCG@5로 전역 1위와 기법군별 1위를 고르고, 세그먼트 라우터는 계층(학습활동→선호군집→연령대→소득분위[→성별])에서 λ ∈ {0, 20, 100, 500, 3000, ∞} 교차 선택(잎 최소 20명, 반복 2회). 선택 후 잠금."],
    ["테스트·QA", `테스트 주차(3주)에서 사용자 평균 NDCG@5·Hit@5·Diversity@5·선수 미이수 비율·짧은 목록 비율, 사용자 단위 쌍 부트스트랩 500회로 전역 1위 대비 차이의 95% 구간. QA ${M.qa}건(지표 함수 일치, 누수 없음, 가드레일, 재현성 해시, 오프라인/온라인 Top-5 일치 등) 모두 통과.`],
    ["번들", "bundle.pkl(설정·신호 메타·모델 가중치·특징 저장소), manifest.json(선택 기록·학습 감사·QA), 결과 CSV(테스트·검증·집단별·노출)"],
  ], [2.2, 10.3], { caption: "학습 파이프라인 요약", zebra: true }),
  h2("5.6 서빙: REST API와 학습 설계 스튜디오"),
  p("FastAPI 서버는 번들을 읽어 다음 엔드포인트를 제공한다(부록 A). 웹 UI ‘학습 설계 스튜디오’는 외부 라이브러리 없이 11단계 마법사로 구성했고, 모든 계산을 API에 맡긴다."),
  ...table(["단계", "화면", "하는 일"], [
    ["1", "아이디어 스케치", "예시 문장 9개 또는 자연어로 학습자를 설명 → 규칙 파서가 목적·기간·관심 주제·수준·경험·성향·기기·시간대·연령·소득·학습 이력을 읽고 근거 표현을 표시. 기존 학습자(모의 15,000명) 검색·불러오기"],
    ["2", "기본 정보·목적", "투자 목적·기간·위험성향(로드맵 구성 변수)과 인구통계 입력, 목적에 따라 연결될 유형 안내"],
    ["3", "진단", `관심 주제 2개, 수준 직접 선택 또는 ${D.questions.length}문항 진단 퀴즈 채점·적용`],
    ["4", "학습 기록", "단원별 이벤트 추가·CSV 불러오기, 진단 통과 기록 구분 표시"],
    ["5", "학습 로드맵", "단계 흐름(진행률·남은 시간·현재 단계), 단원 상태·선수 미이수·출처 링크·학습 요점, 다음 단원, 유형별 개념 통과 수"],
    ["6", "추천 설정", "k, 설정 강제(기법군별 검증 1위), 선수 단원 차단, 두 단계 위 차단, 한 단계 위 상한, 통과 제외, 주제 상한"],
    ["7", "추천 미리보기", "주제×수준 배치도(추천·통과·후보·차단), 추천 목록(점수·근거·기여도·선수 미이수·현재 단계·출처), 가드레일 검사, 세그먼트 경로, 계산식"],
    ["8", "시뮬레이션", "통과 가정·세그먼트 what-if·수준 강제 → 추천과 로드맵 진행률 변화, 성별 뒤집기 불변 검사"],
    ["9", "ETF 유형 연결·데이터 출처", "유형 카드(권장·열림 여부, 필요 개념 통과, 세금·연금·규제·주의, 유형 통계와 샘플/스냅샷 배지), 출처 등록부와 유형 통계표"],
    ["10", "비교·평가", "같은 후보·가드레일로 기법별 Top-K 비교, 번들의 오프라인 평가(방법별·집단별·노출·검증 상위 설정)"],
    ["11", "저장·내보내기", "설계 저장·불러오기, JSON/CSV 내보내기, 로드맵 JSON"],
  ], [0.8, 2.4, 9.3], { caption: "학습 설계 스튜디오 11단계", size: 17, zebra: true }),
  ...img("shot_01_idea_parsed.jpg", "1단계: 자연어 문장에서 투자 목적·기간·수준·성향·연령을 읽어 낸 결과", 470, 560),
  ...img("shot_03_diagnosis.jpg", "3단계: 진단 퀴즈 채점 결과(수준 판정, 문항별 정답·해설)", 470, 560),
  ...img("shot_05_roadmap.jpg", "5단계: 학습 로드맵(단계 흐름, 다음 단원, 단원 상태·선수 미이수·출처 링크)", 500, 620),
  ...img("shot_07_preview.jpg", "7단계: 추천 미리보기(배치도, 로드맵 요약, 추천 근거와 기여도, 가드레일 검사, 세그먼트 경로)", 500, 660),
  ...img("shot_09_types.jpg", "9단계: ETF 유형 연결 카드와 공개 데이터 출처(샘플 데이터 배지)", 470, 600),
  h2("5.7 구현 현황"),
  ...table(["구성", "상태", "비고"], [
    ["카탈로그 v2 · 선수 관계 · 출처 태그", "완료", `단원 ${D.catalog.n_items}개, 선수 관계 ${D.catalog.n_prereq_edges}개(순환 없음 검사), v1 60단원은 노트북 재현용으로 유지`],
    ["투자 목적·기간 분류, 로드맵 엔진, 우선순위 신호", "완료", "목적 5종 × 기간 3종, 단계 5개, 위상정렬, 상태·시간 계산"],
    [`진단 퀴즈 ${D.questions.length}문항·채점`, "완료", "단원 단위 채점·정답 위치 균형. 문항 확장(단원당 2~3문항)과 전문가 검수는 다음 단계"],
    ["세제·규제 단원 학습 요점(2차본)", "완료(6단원)", "ISA 3단원·과표기준가·IRP 70% 한도·레버리지 거래 요건. 나머지 단원은 교육 자료 링크, 본문 확장은 11월"],
    ["ETF 유형 10종 분류 규칙·카드", "완료", "KRX 열 매핑 테스트, 세금·연금·규제 문구는 최신 제도 확인 필요"],
    ["공개 데이터 커넥터·출처 등록부·스냅샷", "완료(코드) / 수집 미실행", "개발 환경의 네트워크 제한으로 실제 수집은 로컬에서 실행 예정"],
    ["학습 파이프라인·신호·설정 풀·라우터·평가", "완료", `v1 노트북과 5자리 일치, v2 ${num(M.configurations)}개 설정, QA ${M.qa_passed}/${M.qa}`],
    ["REST API · 11단계 UI · 자연어 파서", "완료", `Playwright 점검 스크립트로 ${SCREENS}장 화면 자동 생성, 모바일 폭 가로 스크롤 없음`],
    ["테스트", "완료", `pytest ${TESTS}건(지표 일치·가드레일·로드맵·퀴즈·도메인 규칙·KRX 분류·수집 정책·k-익명성·파서·파이프라인·API·오프라인/온라인 일치, 전체 재현 1건은 옵션)`],
    ["실제 로그·교육 자료 연동, 사용자 평가", "예정", "8절 일정"],
  ], [4, 2.2, 6.3], { caption: "구현 현황", zebra: true }),
);

// 6. 결과
add(pageBreak(), h1("6. 실험 결과"),
  h2("6.1 실험 설정"),
  p(`학습 0~1주 로그로 특징과 모델을 만들고, 검증 2주차에서 설정을 선택·잠근 뒤, 테스트 3주차에서 보고한다. 정답은 다음 주에 관측된 퀴즈 통과 단원, 후보는 아직 통과하지 않은 단원 중 수준 가드레일(두 단계 위 차단, 한 단계 위 최대 1개)을 통과한 단원이다. 지표는 사용자 평균 NDCG@5(주 지표), Hit@5, Diversity@5(Top-5 안의 단원 쌍 중 주제가 다른 쌍의 비율, 단원이 2개 미만이면 0), 선수 미이수 비율(Top-5 중 선수 단원을 통과하지 않은 단원 비율), 짧은 목록 비율(추천 목록이 5개 미만인 사용자 비율)이다. 차이의 95% 구간은 사용자 단위 쌍 부트스트랩 500회다.`),
  p(`다음 주 정답이 없는 사용자(테스트 ${num(M.test.zero_observed_target)}명)는 IDCG가 0이라 NDCG가 수학적으로 정의되지 않는다. 처리 방식은 두 가지다. 전체 기준(노트북 규칙)은 이들을 0점으로 평균에 넣고, 활성 기준은 정답이 1개 이상인 사용자만 평균한다. 널리 쓰이는 구현도 갈린다. scikit-learn의 ndcg_score와 TorchMetrics의 RetrievalNormalizedDCG(기본 설정)는 정답이 없는 질의를 0으로 넣고, 평가 데이터를 만들 때 테스트 정답이 없는 사용자를 아예 빼는 연구도 많다. 그래서 2차본부터 두 값을 함께 보고한다. 활성 사용자는 ‘후보 안의 다음 주 통과 단원’이 1개 이상인 ${num(nActive)}명이다. 다음 주 통과 기록 자체가 있는 사용자는 ${num(M.test.raw_positive_users || nActive)}명이지만, 그중 ${num((M.test.raw_positive_users || nActive) - nActive)}명은 통과 단원이 모두 후보 밖(이미 통과했거나 수준 가드레일에 걸린 단원)이라 어떤 방법도 맞힐 수 없어 활성에서 뺐다.`),
  p(`정답 없는 사용자는 모든 방법에서 0점이므로 활성 기준 × ${num(nActive)} = 전체 기준 × ${num(nAll)}이 모든 방법에 똑같이 성립한다(QA 검사 ndcg_active_identity). 따라서 방법 간 순위는 어느 기준이든 같고(QA 검사 active_rank_preserved), 전체 기준의 절대 차이는 활성 기준의 ${fmt(ratioAct, 3)}배로 줄어든다. 유의성 판정(구간이 0을 포함하는지)은 항등식으로 보장되지는 않지만 이번 실행에서는 모든 방법에서 같았다. 반면 집단 비교는 집단마다 활성 비율이 달라 결론이 바뀔 수 있다(6.5절). 1차본은 전체 기준만 보고하고 그것을 ‘보수적 추정’이라고만 적었는데, 집단 비교에서는 보수적인 것이 아니라 활동량과 섞인 값이었다.`),
  h2("6.2 노트북 B 원본 세계(v1)의 재현"),
  p("패키지로 옮기면서 결과가 바뀌지 않았는지 확인하기 위해, 카탈로그 v1(60단원)과 생성기 v1(난수 순서 동일)로 노트북과 같은 seed 42, 15,000명 세계를 다시 학습했다. 테스트 NDCG@5가 노트북 기록과 소수점 5자리까지 일치했다(scripts/regression_check.py)."),
  ...table(["방법", "노트북 기록", "패키지(bundle_v1)", "일치", "활성 사용자 기준"], Object.keys(NB).filter(k => v1By[k]).map(k => [KO[k] || k, fmt(NB[k], 5), fmt(v1By[k].ndcg, 5), Math.abs(NB[k] - v1By[k].ndcg) < 5e-5 ? "○" : "×", fmt(v1By[k].ndcg_active, 5)])
    .concat(NEW_FAMS.filter(k => v1By[k]).map(k => [KO[k] + " (2차본 추가)", "–", fmt(v1By[k].ndcg, 5), "–", fmt(v1By[k].ndcg_active, 5)])),
    [4.2, 2, 2, 1, 2.3], { caption: "v1 재현 결과(테스트 NDCG@5). 2차본에서 쌍별·목표 정렬 기법군 4개를 더해도 기존 14개 수치는 그대로다", size: 17, zebra: true, numCols: [1, 2, 4] }),
  h2("6.3 모의 데이터 v2의 결과"),
  ...img("fig4_ndcg_methods.png", "방법별 테스트 NDCG@5: 전체 기준(진한 막대)과 활성 사용자 기준(옅은 막대), 오른쪽 숫자는 선수 미이수 비율(모의 데이터 v2)"),
  ...table(["방법", "NDCG@5 전체", "NDCG@5 활성", "Diversity@5", "Hit@5", "선수 미이수", "짧은 목록", "전역 1위 대비 [95% 구간]"],
    D.results.map(r => [KO[r.method] || r.method, fmt(r.ndcg), fmt(r.ndcg_active), fmt(r.diversity, 3), fmt(r.hit_diagnostic, 3), fmt(r.prereq_violation_rate, 3), fmt(r.short_list_rate, 3),
      r.method === "RULE" || r.method === "Global" ? "기준" : `${fmt(r.difference_vs_global)} [${fmt(r.ci_low)}, ${fmt(r.ci_high)}]`]),
    [3.2, 1.3, 1.3, 1.4, 1.2, 1.4, 1.3, 3.1], { caption: `테스트 주차 결과(전체 = 테스트 사용자 ${num(nAll)}명, 활성 = 다음 주 정답이 있는 ${num(nActive)}명)`, size: 15, zebra: true, numCols: [1, 2, 3, 4, 5, 6, 7] }),
  p(`검증 1위(#${M.selection.operational_algorithm})는 ‘${D.operational_name}’다. ${opHas("로드맵") || opHas("투자 목적") ? `2차본에서 추가한 ${[opHas("투자 목적") ? "투자 목적 일치" : null, opHas("로드맵") ? "로드맵 단계 우선순위" : null].filter(Boolean).join("·")} 신호가 선택되었다. ` : ""}검증 상위 ${valTop.length}개 설정 중 ${valTop.filter(j => j.family === "RULE").length}개가 규칙 계열이고, ${valTopRoad}개가 로드맵 단계 우선순위를, ${valTopGoal}개가 투자 목적 일치를 포함한다(표 ${tabNo + 2}). 하이브리드(CF 혼합)는 밀도 ${pct(DS.density, 0)}의 희소한 세계에서 규칙을 넘지 못했고, 운영 라우터는 전역 1위와 유의한 차이가 없었다(차이 ${fmt(resBy.RouterNoGender.difference_vs_global)}, 구간 [${fmt(resBy.RouterNoGender.ci_low)}, ${fmt(resBy.RouterNoGender.ci_high)}]).`),
  h3("손실 함수와 학습 목표의 비교(2차본 추가 실험)"),
  p("중간 점검에서 ‘BCE 손실 때문에 딥러닝 결과가 무효이며 BPR로 다시 학습해야 한다’는 지적을 받아, 같은 후보·정답·후처리로 네 가지 변형을 추가했다. 아래 표는 같은 테스트 사용자에 대한 사용자 단위 쌍 부트스트랩 차이(95% 구간)이며, 각 행은 한 가지씩만 바꾼 비교가 되도록 짝을 지었다."),
  ...table(["비교(A − B)", "바꾼 것", "노트북 세계 v1", "모의 데이터 v2"], [
    ["BPR MF − 표본 MF", "손실: 가중 MSE(미관측 표본 0) → 쌍별 BPR(미관측 음성)", ci(MFB1), ci(MFB2)],
    ["MLP 쌍별(관측 음성) − MLP", "손실 형태만: 점별 BCE → 쌍별(음성은 같은 ‘시도했지만 미통과’)", ci(OBS1), ci(OBS2)],
    ["MLP 쌍별(미관측 음성) − MLP 쌍별(관측 음성)", "음성 정의만: 미통과 시도 → 미관측 단원", ci(NEG1), ci(NEG2)],
    ["MLP 쌍별(미관측 음성) − MLP", "비판이 처방한 BPR 전체(손실 + 음성 정의)", ci(BPRU1), ci(BPRU2)],
    ["MLP 목표 정렬 − MLP", "레이블을 평가 목표로: 주 w에 처음 통과한 단원 vs 그 주까지 통과하지 않은 단원", ci(NEXT1), ci(NEXT2)],
    ["MLP − 무작위", "참고", ci(PR1["MLP-Random"]), ci(PR2["MLP-Random"])],
  ], [3.4, 4.6, 2.3, 2.3], { caption: "신경망 변형의 쌍 비교(테스트 NDCG@5 차이, 사용자 단위 쌍 부트스트랩 95% 구간)", size: 16, zebra: true }),
  p(`세 가지가 보인다. 첫째, 음성을 ‘미통과 시도’에서 ‘미관측 단원’으로 바꾼 효과는 v1 ${eff(NEG1)}, v2 ${eff(NEG2)}이고, 손실 형태만 바꾼 효과는 v1 ${eff(OBS1)}, v2 ${eff(OBS2)}다. 둘째, 비판이 처방한 BPR(미관측 음성)은 v1에서 MLP를 ${fmt(v1By.MLP.ndcg)} → ${v1By.MLP_BPRU ? fmt(v1By.MLP_BPRU.ndcg) : "–"}로 바꿨고(${eff(BPRU1)}), v2에서는 ${eff(BPRU2)}다. BPR MF는 표본 MF 대비 v1 ${eff(MFB1)}, v2 ${eff(MFB2)}다. 셋째, 다음 주 통과를 직접 레이블로 쓴 목표 정렬 MLP는 v1 ${eff(NEXT1)}, v2 ${eff(NEXT2)}다. 어느 세계에서도 신경망 최고치(v1 ${fmt(nnBest1)}, v2 ${fmt(nnBest2)})는 규칙(v1 ${fmt(v1By.RULE.ndcg)}, v2 ${fmt(resBy.RULE.ndcg)})에 미치지 못했다.`),
  p(`해석. 노트북의 MLP는 미관측 단원을 0으로 본 것이 아니라 아예 학습하지 않았다. 학습 행은 관측된 시도 ${mlpAud ? num(mlpAud.training_rows) : "–"}건(통과 ${mlpPos ? pct(mlpPos) : "–"})이고, 마지막 학습 손실 ${mlpAud ? fmt(mlpAud.loss_last, 3) : "–"}은 통과율만 맞히는 상수 예측의 손실 ${bce0 ? fmt(bce0, 3) : "–"}보다 낮아 0으로 붕괴하지도 않았다. 대신 ‘시도한 단원 중 무엇을 통과할까’만 배우고 ‘무엇을 시도할까’는 배우지 못했는데, 다음 주 통과 단원 예측에는 이 부분이 필요하다. 미관측 음성 BPR은 바로 이 공백을 메우므로 v1에서 효과가 컸다. v2에서는 관심 주제·수준·목적·로드맵 규칙 신호가 같은 정보를 이미 담고 있어 신경망이 더 얻을 것이 적었을 가능성이 있다(가설, 검증은 11월). 정리하면 1차본의 ‘손실 함수가 아니라 목표 불일치가 1차 원인’이라는 문장은 실험 없이 쓴 단정이었다. 실험이 보여 준 것은 음성을 무엇으로 두느냐가 중요하고, 그 효과는 데이터 세계에 따라 다르다는 점이다. 그래서 이 문장을 정정한다.`),
  ...table(["#", "기법군", "설정", "검증 NDCG@5", "Diversity"], D.validation_top.map(j => [String(j.job_id), j.family, j.name, fmt(j.ndcg), fmt(j.diversity, 3)]),
    [0.8, 1.2, 7.5, 1.6, 1.4], { caption: "검증 상위 설정(2주차)", size: 16, zebra: true, numCols: [3, 4] }),
  h2("6.4 세그먼트 라우터의 λ 교차 선택"),
  ...img("fig6_router_lambda.png", "라우터 λ에 따른 검증 교차 NDCG@5(평균 ± 표준편차, 반복 2회)"),
  p("λ가 커질수록(세그먼트별 선택을 전역 1위 쪽으로 수축할수록) 성능이 좋아져 λ=3000이 선택되었고, 그 결과 대부분의 세그먼트에 전역 1위 설정이 배정되었다. 세그먼트별로 다른 설정을 고를 만큼의 신호가 이 데이터에는 없다는 뜻이며, 실제 로그에서 λ가 작게 선택되는지가 세그먼트 개인화의 가치를 판단하는 기준이 된다. 성별을 포함한 라우터와 제외한 라우터의 차이도 없었으므로 운영에서는 성별을 제외했다."),
  h2("6.5 집단별 결과와 심화 콘텐츠 노출"),
  ...img("fig7_groups.png", "운영 라우터의 집단별 NDCG@5(투자 목적·연령대·소득분위·성별·학습활동)"),
  p(`투자 목적별 정확도는 ${fmt(goalMin, 3)}~${fmt(goalMax, 3)}로 고르고 구간이 겹친다. ${oldAge ? `60세 이상(${num(oldAge.users)}명)의 점 추정치는 ${fmt(oldAge.ndcg, 3)}로 구간이 넓어 표본 수의 문제이고, ` : ""}학습활동이 많은 집단이 가장 높은 것은 기록이 많을수록 개인화가 잘 되는 자연스러운 결과다. 아래 표는 Top-5 중 심화·레버리지 콘텐츠의 비율로, 특정 집단에 고위험 콘텐츠가 더 많이 노출되는지 보는 진단이다. 집단 간 최대 격차는 ${fmt(expGap, 3)}이고 ${glab(expTop.variable, expTop.group)}에서 가장 높아(${fmt(expTop.advanced_share, 3)}) 실제 서비스에서는 집단별 심화 노출 상한 정책을 검토할 근거가 된다.`),
  ...table(["변수", "집단", "사용자", "Top-5 중 심화·레버리지 비율"], D.exposure.filter(x => x.method === "RouterNoGender").map(x => [VAR_KO[x.variable] || x.variable, glab(x.variable, x.group), num(x.users), fmt(x.advanced_share, 3)]),
    [2.5, 3.5, 2, 4.5], { caption: "심화·레버리지 콘텐츠 노출 비율(운영 라우터)", size: 17, zebra: true, numCols: [2, 3] }),
  h2("6.6 선수 단원 가드레일의 비용과 민감도"),
  ...img("fig5_prereq_tradeoff.png", "정확도와 교육 순서 준수의 트레이드오프"),
  p(`운영 라우터의 Top-5 중 ${pct(resBy.RouterNoGender.prereq_violation_rate, 0)}가 선수 단원을 통과하지 않은 단원이었다. 선수 가드레일을 켜면 위반이 0이 되고 다양성이 ${fmt(resBy["RouterNoGender+prereq"].diversity, 3)}으로 오르지만 NDCG@5는 ${fmt(resBy["RouterNoGender+prereq"].ndcg)}로 ${fmt(resBy.RouterNoGender.ndcg - resBy["RouterNoGender+prereq"].ndcg, 3)} 낮아진다. 원인은 두 가지다. 첫째, 선수 관계가 없는 단원이 4개뿐이어서 통과 기록이 적은 학습자는 후보가 5개 미만이 된다(테스트 사용자의 ${pct(resBy["RouterNoGender+prereq"].short_list_rate, 1)}가 짧은 목록). 둘째, 모의 세계에서는 선수 단원을 건너뛴 학습자도 상당수 통과하므로(페널티 0.8), 정답 단원이 가드레일에 걸러진다. 즉 이 비용은 ‘선수 관계가 실제로 얼마나 학습 성과를 지배하는가’에 달려 있다.`),
  ...img("fig8_sensitivity.png", "선수 페널티 강도에 따른 가드레일 비용(학습자 3,000명 모의 세계, scripts/prereq_sensitivity.py)"),
  ...table(["선수 페널티", "주당 퀴즈 통과", "운영 라우터 NDCG", "라우터 선수 미이수", "+가드레일 NDCG", "가드레일 짧은 목록", "검증 1위 설정"], sens.map(s => [
    String(s.prereq_penalty), num(s.quiz_pass), fmt(s.RouterNoGender.ndcg), fmt(s.RouterNoGender.prereq_violation_rate, 3), fmt(s["RouterNoGender+prereq"].ndcg), fmt(s["RouterNoGender+prereq"].short_list_rate, 3), s.operational]),
    [1.3, 1.5, 1.6, 1.6, 1.6, 1.6, 4.3], { caption: "선수 페널티 민감도(학습자 3,000명, 테스트 사용자 1,277명)", size: 16, zebra: true, numCols: [1, 2, 3, 4, 5] }),
  p(`${sensRev.length ? `페널티를 ${sensRev.join(", ")}으로 키운 세계(선수 단원을 모르면 통과가 훨씬 어려운 세계)에서는 가드레일을 켠 쪽이 오히려 NDCG가 높고, 검증 1위 설정에 로드맵 단계 우선순위 신호가 들어온다.` : "페널티를 키워도 이 작은 세계에서는 가드레일 쪽이 앞서지 않았다."} 따라서 실제 로그가 생기면 ‘선수 단원을 건너뛴 시도의 통과율 ÷ 선수를 갖춘 시도의 통과율’을 먼저 측정해 페널티를 보정하고, 그 값에 따라 가드레일을 강제할지 신호(가중치)로만 쓸지 정하는 것이 다음 단계의 핵심 실험이다.`),
  h2("6.7 해석과 한계"),
  bullet("모의 데이터의 결과이므로 절대 수치는 실제 학습자 성과가 아니다. 다만 파이프라인이 선택·평가를 분리하고 재현성(해시·seed)을 보장하므로, 실제 로그로 바꿔도 같은 절차로 비교할 수 있다."),
  bullet("규칙이 1위인 것은 생성기가 관심 주제·수준·목적으로 행동을 만들기 때문이기도 하다. 실제 로그에서는 CF·MF 비중이 커질 수 있으며, 그때는 α_u 가중 하이브리드가 자동으로 그 비중을 가져간다."),
  bullet("MF·MLP의 낮은 성능은 손실 함수(BCE vs BPR)의 문제가 아니라 목표 불일치와 희소성이다(6.3절에서 쌍별 손실 변형으로 확인). ‘다음 주 선택·통과’를 직접 레이블로 쓰는 학습과 특징(목적·로드맵 단계) 입력을 더한 모델은 다음 단계에서 비교한다."),
  bullet("선수 가드레일은 정확도와 교육 순서 사이의 정책 선택이고, 페널티 보정 전까지는 ‘기본 켬 + 끌 수 있음’으로 운영한다."),
);

// 7. 평가 계획
add(h1("7. 평가 계획"),
  h2("7.1 오프라인 평가(현재 시행 중)"),
  ...table(["지표", "정의", "목적", "현재 값(운영 라우터)"], [
    ["NDCG@5 전체 (주 지표, 노트북 규칙)", "다음 주 퀴즈 통과 단원을 정답으로 한 순위 품질, 정답 없는 사용자 = 0 포함 평균", "정확도(보수적)", fmt(resBy.RouterNoGender.ndcg)],
    ["NDCG@5 활성 (표준 규칙)", `정답이 1개 이상인 사용자(${num(nActive)}명)만 평균. 전체 기준과 비는 모든 방법에서 같음`, "정확도(표준)", fmt(resBy.RouterNoGender.ndcg_active)],
    ["Hit@5", "정답 단원이 Top-5에 하나라도 있는 사용자 비율", "진단", fmt(resBy.RouterNoGender.hit_diagnostic, 3)],
    ["Diversity@5", "Top-5 안의 단원 쌍 중 주제가 다른 쌍의 비율", "다양성", fmt(resBy.RouterNoGender.diversity, 3)],
    ["선수 미이수 비율", "Top-5 중 선수 단원을 통과하지 않은 단원의 비율", "교육 순서 준수", fmt(resBy.RouterNoGender.prereq_violation_rate, 3) + " (가드레일 시 0)"],
    ["짧은 목록 비율 · 커버리지", "후보가 k 미만인 사용자 비율, 추천된 단원의 카탈로그 커버리지", "콜드스타트·쏠림", fmt(resBy.RouterNoGender.short_list_rate, 3) + " · " + fmt(resBy.RouterNoGender.coverage_diagnostic, 3)],
    ["집단별 NDCG · 심화 노출 비율", "목적·연령대·소득분위·성별·학습활동별 지표와 95% 구간", "공정성 진단", "6.5절"],
    ["성별 뒤집기 불변", "성별만 바꾼 요청의 Top-5가 같은 비율(코드 수준 점검)", "민감 속성 비사용 확인", "테스트 사용자 40명 전원 불변"],
  ], [2.6, 4.6, 2, 3.3], { caption: "오프라인 지표", zebra: true }),
  p("설정 선택은 검증 주차에서만 하고 테스트 주차에서는 보고만 하는 규칙을 유지한다. 차이의 통계적 유의성은 사용자 단위 쌍 부트스트랩 95% 구간으로 판단하며, 실제 로그에서는 주차를 늘려 시간 순 롤링 평가(학습 t주 → 평가 t+1주)로 바꾼다."),
  h2("7.2 교육 효과 지표(로드맵 도입으로 추가)"),
  bullet([{ t: "로드맵 진행률·단계 통과 시간: ", bold: true }, "주별 통과 단원 수와 단계(기초→핵심→심화) 이동 시간. 추천을 따른 학습자와 그렇지 않은 학습자의 차이를 비교한다."]),
  bullet([{ t: "진단 → 재진단 수준 향상: ", bold: true }, "4주 후 같은 문항군의 재진단 점수 변화(수준 1 문항 정답률, 복리 효과·괴리율 문항 정답 여부)."]),
  bullet([{ t: "유형 카드 해금률: ", bold: true }, "목적에 권장된 유형의 필요 개념을 모두 통과한 학습자 비율과 걸린 시간."]),
  bullet([{ t: "위험 콘텐츠 선행 조건 준수: ", bold: true }, "레버리지·인버스 유형 카드가 열리기 전 사전교육 안내 노출 100%."]),
  h2("7.3 온라인 A/B 실험 설계"),
  ...table(["항목", "설계"], [
    ["대상·단위", "신규 가입 학습자, 사용자 단위 무작위 배정(진단 완료 시점)"],
    ["군", "대조군 A: 인기순(세그먼트 인기) / 처치군 B: 운영 라우터 + 선수 가드레일 / 처치군 C: 운영 라우터, 가드레일 끔(신호만)"],
    ["주 지표", "추천 노출 후 1주 안의 퀴즈 통과율(사용자당), 보조: 완료율, 이탈률, 로드맵 진행률, 세션당 학습 시간"],
    ["가드레일 지표", "선수 미이수 추천 비율, 심화·레버리지 노출 비율의 집단별 차이, 불만·신고"],
    ["표본 크기", `통과율 22% → 24%(+2%p), 유의수준 5%(양측), 검정력 80% 기준 군당 ${num(abSize(0.22, 0.24, true))}명. 아래 표처럼 MDE와 검정 방향에 따라 달라지며, 가입 속도가 느리면 MDE를 3%p로 올리거나 ‘나빠지지 않음’만 확인하는 단측 검정으로 전환한다`],
    ["단계적 배정(2차본)", "1단계: A(인기순) vs B(운영 라우터+가드레일) 두 군만 운영해 필요 유입을 2/3로 줄이고, 2단계: B가 A보다 나쁘지 않음이 확인되면 B vs C(가드레일 끔)로 가드레일의 순효과를 본다"],
    ["외생 변수 통제(2차본)", "가입 주차 코호트로 층화 배정하고, 분석 때 코호트를 블록으로 넣는다. 시장 급변(특정 테마 급등 등) 주간은 사전 등록한 규칙으로 표시해 민감도 분석에서 제외한다. 테스트 기간 상한 8주"],
    ["분석", "사전 등록한 지표와 분석 계획, 사용자 단위 부트스트랩·비율 검정, 세그먼트별 이질 효과는 탐색적으로만 보고"],
    ["중단 규칙", "처치군의 이탈률이 대조군보다 유의하게 높거나 가드레일 지표 위반 시 중단"],
  ], [2.2, 10.3], { caption: "온라인 A/B 실험 계획", zebra: true }),
  ...table(["최소 검출 효과(MDE)", "양측 검정, 군당", "단측 검정, 군당", "두 군 합계(양측)", "세 군 합계(양측)"], AB_ROWS, [3.5, 2.2, 2.2, 2.3, 2.3],
    { caption: "통과율 22% 기준 표본 크기(두 비율 Z-검정, α=5%, 검정력 80%)", size: 17, zebra: true, numCols: [1, 2, 3, 4] }),
  h2("7.4 사용성·전문가 검토"),
  bullet("사용성: 대상 페르소나별 각 3~4명(총 10명)에게 11단계 과제를 수행하게 하고 SUS 점수, 과제 완료율, ‘왜 이 단원인지 이해했는가’ 5점 척도를 측정한다."),
  bullet("콘텐츠 정확성: 금융 교육 전문가(또는 담당 교수) 검수로 퀴즈 문항·유형 카드의 세금·연금·규제 문구를 확인하고, 출처 등록부의 링크를 분기마다 점검한다."),
  bullet("안전: 화면·API 응답에서 투자 권유로 읽힐 수 있는 문구를 금칙어 검사로 차단하고, 유형 카드는 ‘교육용 분류’ 고지를 유지한다."),
  h2("7.5 수용 기준"),
  ...table(["기준", "통과 조건"], [
    ["정확도", "운영 설정의 테스트 NDCG@5가 인기·무작위보다 유의하게 높음(95% 구간이 0을 포함하지 않음) — 현재 충족"],
    ["교육 순서", "가드레일 켬 상태에서 선수 미이수 비율 0, 짧은 목록 비율 20% 이하(선수 관계 조정 또는 완화 규칙으로 달성) — 현재 52.5%로 미충족, 8절 과제"],
    ["공정성", "성별 뒤집기 불변 100%, 집단별 NDCG 격차가 표본 수로 설명되고 심화 노출 비율 격차 5%p 이내 — 현재 충족(최대 격차 약 4%p)"],
    ["재현성", "같은 seed·데이터로 재학습 시 결과 해시 일치, 노트북 v1 재현 5자리 일치 — 현재 충족"],
    ["운영", "요청당 응답 100ms 이하, 요청 중 재학습 없음, 모든 응답에 고지문 — 현재 충족(20~30ms)"],
  ], [2.2, 10.3], { caption: "수용 기준", zebra: true }),
);

// 8. 일정
add(h1("8. 남은 일정, 역할, 위험 관리"),
  ...table(["주차", "작업", "산출물"], [
    ["11월 1주", "KRX 정보데이터시스템에서 ETF 전종목 기본정보 CSV 수동 내려받기 → sources sync --krx-csv, KRX Open API 인증키·공공데이터포털 키 발급 후 시세 수집, 스냅샷 검증, 유형 분류 규칙 보정", "data/sources 스냅샷, 분류 정확도 점검표"],
    ["11월 2주", "교육 자료 링크 검수(스쿨·사전교육·KRX·가이드북), 퀴즈 문항 확장(단원당 2문항)과 전문가 검수, 세제·규제 문구(기본예탁금·ISA·IRP·과표기준가)의 법령·공지 원문 대조", "출처 등록부 v2, 문항 40개, 세제·규제 확인표"],
    ["11월 3주", "실제 로그 스키마로 파일럿 수집(수업 참여자 또는 모의 사용자 테스트), 선수 페널티 보정 실험, 랭킹 손실 MF 비교", "보정 보고, 결과 표 갱신"],
    ["11월 4주", "사용성 테스트 10명, 수용 기준 점검, 가드레일 완화 규칙(짧은 목록 대응) 확정", "SUS 결과, 정책 문서"],
    ["12월 1~2주", "최종 보고서·발표 자료, 코드 정리와 재현 문서", "최종 보고서, 발표 슬라이드"],
  ], [1.6, 7, 3.9], { caption: "남은 일정", zebra: true }),
  ...table(["위험", "영향", "대응"], [
    ["KRX 비공식 JSON 엔드포인트 변경", "자동 수집 실패", "내려받은 CSV 경로 유지, 열 매핑 관대화, 샘플 폴백과 배지로 사용자에게 상태 표시"],
    ["교육 자료 저작권·링크 변경", "자료 연결 끊김", "본문 미저장, 기관 루트+메뉴 경로 표시, 분기별 링크 점검"],
    ["모의 데이터 편향", "규칙 과대평가", "위약 세계 검사, 파일럿 로그로 선수 페널티·CF 비중 보정"],
    ["가드레일로 인한 짧은 목록", "신규 학습자 추천 4개", "입문 단원 추가(선수 없는 단원 확대) 또는 ‘다음에 열릴 단원’ 보조 표시"],
    ["제도 변경(세제·연금 편입 규정)", "유형 카드 문구 오류", "문구를 데이터(taxonomy)로 분리해 갱신, 출처·확인일 표기"],
  ], [3, 2.5, 7], { caption: "위험과 대응", zebra: true }),
  p("역할: 1인 프로젝트로 설계·구현·실험·보고를 모두 수행하며, 전문가 검수와 사용성 테스트 참여자는 11월에 섭외한다."),
);

// 9. 참고 자료
add(h1("9. 참고 자료"),
  numbered("한국거래소, ‘2025년 ETF·ETN 시장 결산’ 보도(2025.12) — 상장 종목 1,058개, 순자산총액 297조 2천억 원. 헤럴드경제(2025.07.22) ‘국내 ETF 1000개 돌파…순자산 1년 새 42% 급증’.", "refs"),
  numbered("전국투자자교육협의회(KCIE) 온라인 스쿨: ETF스쿨·연금스쿨·생애자산관리스쿨·대체투자/파생상품스쿨, https://www.kcie.or.kr", "refs"),
  numbered("금융투자교육원(KIFIN) 레버리지 ETP 사전교육(의무 이러닝, 약 1시간, 평생 1회), https://www.kifin.or.kr", "refs"),
  numbered("한국거래소 ETF/ETN 정보·지수 정보, https://www.krx.co.kr ; KRX 정보데이터시스템 ETF 전종목 기본정보, https://data.krx.co.kr", "refs"),
  numbered("공공데이터포털, 금융위원회_증권상품시세정보(ETF) https://www.data.go.kr/data/15094806/openapi.do ; 금융위원회_KRX상장종목정보 https://www.data.go.kr/data/15094775/openapi.do", "refs"),
  numbered("자산운용사 ETF 가이드북·상품 설명 자료: 삼성자산운용(KODEX), 미래에셋자산운용(TIGER), KB자산운용(RISE, 구 KBSTAR) 등 각사 홈페이지 자료실", "refs"),
  numbered("수업 자료: 추천 시스템 강의 노트북(인기·규칙·콘텐츠·CF·MF·MLP·하이브리드·세그먼트 라우터), B_ETF_Education 노트북(seed 42 결과 기록)", "refs"),
  numbered("구현: Python 3.13, NumPy, pandas, SciPy, scikit-learn, PyTorch(학습), FastAPI, Playwright(화면 점검). 저장소 github.com/kyounghob/forclaudekyoungho", "refs"),
  numbered("Rendle, S. 외 (2009). BPR: Bayesian Personalized Ranking from Implicit Feedback. UAI. / Ziegler, C.-N. 외 (2005). Improving recommendation lists through topic diversification. WWW.", "refs"),
  ...D.facts.map(f => numbered(`${f.fact}. 출처: ${f.sources.join(" ; ")}`, "refs")),
);

// 부록 A. API
add(pageBreak(), h1("부록 A. REST API 요약"),
  ...table(["메서드 · 경로", "입력", "출력"], [
    ["GET /api/health, /api/meta", "—", "번들 생성 시각, 운영 라우터, 목적·기간 사전, 유형 이름, 설정 수, 가드레일 기본값"],
    ["GET /api/catalog", "—", "단원 목록(주제·수준·선수·출처·개념), 주제·그룹"],
    ["POST /api/parse", "text", "자연어에서 읽은 필드와 근거 표현, 경고"],
    ["GET /api/learners, /api/learners/{id}", "q, limit, offset", "모의 학습자 검색, 프로필·세그먼트·통과 단원·이력"],
    ["POST /api/recommend", "learner_id 또는 learner{age, goal, horizon, risk, interests, placement, diagnosis, events…}, k, algorithm, guardrail{block_gap, plus_one_max, exclude_passed, prereq_block}, topic_cap, overrides, assume_passed", "추천 단원(점수·기여도·근거·선수 미이수·현재 단계·출처), 로드맵 요약, 검사 결과, 세그먼트 경로, 계산식, 주제×수준 배치도"],
    ["POST /api/roadmap", "learner_id 또는 learner, assume_passed, overrides", "단계별 단원(상태·분·선수 미이수·출처), 진행률, 다음 단원, 연결 유형"],
    ["POST /api/types", "learner 또는 goal, risk, assume_passed", "유형 카드(권장·열림, 개념 통과, 세금·연금·규제·주의, 통계, 출처), 유니버스 출처"],
    ["GET /api/quiz, POST /api/quiz/score", "answers{문항id: 보기}", "문항 목록(정답 제외) / 수준·정답 수·문항별 결과·진단 이벤트"],
    ["GET /api/sources", "—", "출처 등록부, 유니버스 출처(샘플/스냅샷), 유형 통계"],
    ["POST /api/compare, GET /api/evaluation", "learner, methods", "기법별 Top-K 비교 / 번들의 평가 결과·집단별·노출·검증 상위·QA"],
    ["POST /api/parse-log, /api/designs, GET/DELETE /api/designs/{name}", "csv_text / name, payload", "로그 CSV → 이벤트 / 설계 저장·목록·삭제"],
  ], [3.2, 4.3, 5], { caption: "REST API 요약", size: 16, zebra: true }),
);

// 부록 B. 퀴즈
add(h1("부록 B. 진단 퀴즈 문항"),
  ...table(["#", "단원(주제 · 수준)", "문항", "보기(정답 ★)", "해설"], D.questions.map((q, i) => [String(i + 1), `${q.topic} · ${q.level}`, q.text,
    q.options.map((o, j) => (j === q.answer ? "★ " : "") + o).join(" / "), q.explain]), [0.5, 1.8, 3.5, 4.2, 2.5], { caption: "진단 퀴즈 16문항", size: 15, zebra: true }),
);

// 부록 C. 용어집
add(h1("부록 C. 용어집"),
  ...table(["용어", "정의", "학습자에게 중요한 이유"], [
    ["총보수(TER)", "운용·판매·수탁·사무관리 보수의 합으로 순자산에서 매일 차감되는 연율 비용. 매매 수수료·호가 스프레드·기타 비용은 별도", "같은 지수라도 총보수 차이가 장기 복리로 누적된다"],
    ["NAV(순자산가치)", "ETF가 보유한 자산 가치에서 부채를 뺀 뒤 주식 수로 나눈 값. 장중에는 iNAV로 추정", "시장가격이 NAV에서 얼마나 벌어졌는지가 괴리율"],
    ["괴리율", "(시장가격 − NAV) / NAV. 양수면 순자산가치보다 비싸게 거래", "거래량이 적거나 해외 자산 시간대가 다를 때 커진다"],
    ["추적오차", "ETF 수익률과 기초지수 수익률 차이의 변동성. 괴리율(가격 vs NAV)과 다른 개념", "보수·현금 보유·배당 처리·복제 방식이 원인"],
    ["환헤지(H) / 환노출", "환율 변동을 선물 등으로 상쇄하는 상품(H)과 그대로 반영하는 상품. 헤지 비용은 양국 금리차에 비례", "같은 해외 지수라도 환율 방향에 따라 수익률이 갈린다"],
    ["레버리지·인버스의 복리 효과", "일간 수익률의 배수를 추종하므로 여러 날 누적 수익률은 지수 배수와 달라진다. 횡보장에서 손실이 누적(음의 복리)", "장기 보유에 부적합, 연금계좌 편입 제한, 사전교육 의무"],
    ["호가 스프레드 · 유동성공급자(LP)", "매수·매도 호가 차이. LP가 호가를 공급해 스프레드를 좁힌다", "스프레드는 바로 거래 비용이다"],
    ["분배금", "ETF가 보유 자산에서 받은 배당·이자 등을 투자자에게 지급하는 금액. 배당소득세 15.4%", "인컴 목적 투자자의 핵심 변수"],
    ["롤오버 · 콘탱고", "선물형 ETF가 만기 전 다음 월물로 교체하는 것. 원월물이 비싸면(콘탱고) 교체 때마다 비용", "원자재·원유 ETF의 장기 성과가 현물과 다른 이유"],
    ["과세이연 · 세액공제", "연금저축·IRP에서 운용 수익에 바로 과세하지 않고 연금 수령 시 연금소득세(3.3~5.5%)로 과세, 납입액은 연금저축 600만원·IRP 합산 900만원까지 세액공제", "연금 목적 투자자의 세제 혜택 핵심"],
    ["ISA(개인종합자산관리계좌)", "손익을 통산해 순이익 200만원(서민형·농어민형 400만원)까지 비과세, 초과분 9.9% 분리과세. 연 2,000만원·총 1억원 납입, 의무가입 3년. 만기 60일 안에 연금계좌로 옮기면 전환금액의 10%(최대 300만원) 추가 세액공제 한도", "절세 계좌의 첫 바구니. 국내 상장 해외 ETF의 배당소득세·종합과세 부담을 줄인다"],
    ["과표기준가 · 보유기간과세", "국내 상장 해외·채권·원자재·파생형 ETF의 매매차익 과세 기준. 실제 매매차익과 보유 기간의 과표기준가 상승분 중 작은 금액에 15.4%", "가격이 올라도 과표기준가가 오르지 않았으면 세금이 거의 없을 수 있다(단기 매매자에게 중요)"],
    ["IRP 위험자산 70% 한도", "퇴직연금(IRP)은 주식형 ETF 등 위험자산을 적립금의 70%까지만 담을 수 있고 30% 이상은 예금·안전자산(일부 채권형·적격 TDF 예외는 금융사 확인). 연금저축펀드에는 한도 없음", "주식형 100% 주문이 거부되는 이유"],
    ["기본예탁금(레버리지 ETP)", "레버리지·인버스 ETP를 처음 매수하려면 사전교육 이수 외에 계좌에 1,000만원 이상(단일종목형은 2026년 8월부터 3,000만원)을 예탁해야 주문이 가능", "교육을 마쳐도 예탁금이 없으면 매수가 거부된다"],
  ], [2.2, 6, 4.3], { caption: "용어집", size: 16, zebra: true }),
);

// 부록 D. 재현
add(h1("부록 D. 재현 방법과 테스트"),
  p("아래 명령으로 전체를 재현할 수 있다(Python 3.11 이상, 약 3분)."),
  ...["python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
      "python -m etfrec train --out artifacts/bundle_v2            # 모의 데이터 v2 생성 → 학습·검증·테스트 → 번들",
      "python -m etfrec serve --bundle artifacts/bundle_v2         # http://127.0.0.1:8000 (API + 학습 설계 스튜디오)",
      "python -m etfrec sources check && python -m etfrec sources sync --datagokr-key $KEY   # 공개 데이터 접근 점검·스냅샷",
      "python scripts/regression_check.py                           # 노트북 B(v1) 기록과 5자리 일치 확인",
      "python scripts/prereq_sensitivity.py docs/results/prereq_sensitivity.json   # 선수 페널티 민감도",
      "pytest -q                                                     # 자동화 테스트 23건 (약 25초)",
      "node scripts/ui_walkthrough.mjs http://127.0.0.1:8000 docs/screens          # Playwright 화면 점검·캡처"]
    .map(c => new Paragraph({ spacing: { after: 40 }, indent: { left: 240 }, shading: { type: ShadingType.CLEAR, fill: "F1F3F0", color: "auto" },
      children: [new TextRun({ text: c, font: "Consolas", size: 17 })] })),
  spacer(80),
  ...table(["테스트 파일", "확인 내용"], [
    ["tests/test_metrics.py", "NDCG@5·Hit@5·Diversity@5 벡터 구현이 강의 함수와 일치, 경계 사례"],
    ["tests/test_pipeline_service.py", "파이프라인 산출물·QA, 오프라인 평가와 서비스 Top-5 일치, 임의 학습자·가드레일(수준·선수), 로드맵·유형·퀴즈·출처 서비스, 성별 뒤집기 불변, 모든 기법군 서빙, 오류 처리, API 엔드포인트(422 검증 포함), 전체 재현(옵션)"],
    ["tests/test_roadmap_sources.py", "카탈로그 v2 선수 관계 순환 없음·v1 60단원, 로드맵 선수 순서·상태·진행률, 우선순위 행렬·위험성향 필터, 퀴즈 채점 수준·이벤트, 분류 개념 존재, KRX 열 정규화·유형 분류·샘플 유니버스·출처 등록부"],
    ["tests/test_nlparse.py", "자연어 파서: 기본 문장, 연령·소득·성별·성향, 따옴표 제목 → 이력, 예시 전부 파싱, 목적·기간, 빈 문장 경고"],
  ], [3.2, 9.3], { caption: "자동화 테스트", size: 17, zebra: true }),
);

// 부록 E. 중간 점검 지적 대응 요약
add(h1("부록 E. 중간 점검 지적 대응 요약"),
  p("자세한 분석(지적 원문 요지, 사실 확인 출처, 간과 이유, 보완 내용, 수치 변화)은 별도 문서 ‘중간보고서 비판 검토 및 보완 보고서’에 있다. 여기서는 판정만 요약한다."),
  ...table(["#", "지적", "판정", "이 보고서의 반영 위치"], [
    ["1", "모의 로그 이벤트 합계가 시도 수를 초과하는 ‘산술 모순’", "불수용(표현 보완)", "4.4절 이벤트 플래그 표·논리 제약 QA"],
    ["2.1", "정답 없는 사용자를 NDCG 0으로 산입", "부분 수용", "6.1절 두 규칙, 6.3절 활성 열, QA 항등식"],
    ["2.2", "BCE 손실·BPR 부재로 딥러닝 결과 무효", "부분 수용", "3.1절 BPR 행, 6.2·6.3절 MF_BPR·MLP_BPR"],
    ["2.3", "Diversity@5 타당", "긍정 평가", "—"],
    ["3", "A/B 표본 21,000명 비현실적", "수용", "7.3절 MDE 표·단계적 배정"],
    ["4.1", "기본예탁금 누락", "수용", "2.2·5.4절 유형 카드, 부록 B q20, 부록 C"],
    ["4.2", "ISA 누락·IRP 70% 누락", "수용(수치 정정)", "2.2절, 5.2절 로드맵 템플릿(절세 계좌 3단원), 부록 B q17·q19, 부록 C"],
    ["4.3", "과표기준가 메커니즘 부재", "수용", "2.2절, 5.4절 세금 문구, 부록 B q18, 부록 C"],
    ["5.1", "KRX 비공식 엔드포인트 호출(크롤링)", "수용(조항 번호 미검증)", "4.2·4.3절 접근 설계"],
    ["5.2", "가명정보 처리 미흡", "수용(법령 수치 정정)", "4.5절 k-익명성 표·정책"],
    ["서론·결론", "‘실제 서비스 배포 불가 수준의 치명적 결함’", "부분 수용", "1절 요약, 6.7절 한계"],
  ], [0.8, 5, 2.4, 4.3], { caption: "지적 대응 요약", size: 17, zebra: true }),
);

// ---------- 문서 조립 ----------
const doc = new Document({
  creator: "etfrec project", title: "ETF 교육 콘텐츠 개인화 추천 시스템 중간보고서", description: "진단·로드맵 기반 설계 중간보고서",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 21 }, paragraph: { spacing: { line: 312, lineRule: LineRuleType.AUTO } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 32, bold: true, color: GREEN, font: FONT }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 25, bold: true, color: "1C211C", font: FONT }, paragraph: { spacing: { before: 260, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 22, bold: true, color: GREY, font: FONT }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } } } },
                                      { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1000, hanging: 300 } } } }] },
    { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 320 } } } }] },
    { reference: "refs", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "[%1]", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 600, hanging: 420 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: 1300, bottom: 1250, left: MARGIN, right: MARGIN } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 4 } },
      children: [run("ETF 교육 콘텐츠 개인화 추천 시스템 · 중간보고서", { size: 16, color: GREY })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 17, color: GREY })] })] }) },
    children: body,
  }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("written", OUT, buf.length, "bytes; figures", figNo, "tables", tabNo); });
