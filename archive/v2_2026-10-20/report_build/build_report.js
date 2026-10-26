// 중간보고서 .docx 생성 (docx-js). 실행: node build_report.js out.docx
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, ImageRun, PageBreak, Footer, Header, PageNumber, TableOfContents, LevelFormat, TabStopType, VerticalAlign, LineRuleType,
} = require("docx");

const HERE = __dirname;
const D = JSON.parse(fs.readFileSync(path.join(HERE, "report_data.json"), "utf8"));
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
// 숫자 뒤 조사: 끝자리 읽기의 받침(0 영·3 삼·6 육 = 받침, 1 일·7 칠·8 팔 = ㄹ 받침, 2·4·5·9 = 받침 없음, % = 퍼센트)
const JONG_D = { "0": 1, "1": 2, "2": 0, "3": 1, "4": 0, "5": 0, "6": 1, "7": 2, "8": 2, "9": 0 };
function jo(v, pair) {
  const s = String(v), m = s.match(/(\d)[^\d]*$/), t = s.trim().endsWith("%") ? 0 : (m ? JONG_D[m[1]] : 1);
  const [a, b] = pair.split("/");
  if (a === "으로") return s + (t === 1 ? "으로" : "로");
  return s + (t === 0 ? b : a);
}
const fmt = (x, d = 4) => (x == null || Number.isNaN(+x)) ? "–" : (+x).toFixed(d);
const pct = (x, d = 1) => (x == null) ? "–" : (100 * x).toFixed(d) + "%";
const num = (x) => Number(x).toLocaleString("ko-KR");

function imageSize(buf) {   // PNG(IHDR)·JPEG(SOF) 헤더에서 픽셀 크기 [너비, 높이]를 읽는다(그림을 다시 만들어도 비율이 맞게)
  if (buf.readUInt32BE(0) === 0x89504e47) return [buf.readUInt32BE(16), buf.readUInt32BE(20)];
  for (let i = 2; i + 9 < buf.length;) {
    if (buf[i] !== 0xff) { i++; continue; }
    const m = buf[i + 1];
    if (m >= 0xc0 && m <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(m)) return [buf.readUInt16BE(i + 7), buf.readUInt16BE(i + 5)];
    i += 2 + buf.readUInt16BE(i + 2);
  }
  throw new Error("이미지 크기를 읽지 못했습니다");
}

function img(name, cap, widthPx = CONTENT_PX, maxH = 760) {
  const data = fs.readFileSync(path.join(FIG, name));
  const [w, h] = imageSize(data); let W = widthPx, H = Math.round(widthPx * h / w);
  if (H > maxH) { H = maxH; W = Math.round(maxH * w / h); }
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
  MLP_BPRU: "MLP 쌍별(미관측 음성)", MLP_NEXT: "MLP 목표 정렬(다음 주 통과)", ABControl: "세그먼트 인기(A/B 대조군 A)" };
const NEW_FAMS = ["MF_BPR", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"];
const GOAL_KO = D.goals, HOR_KO = D.horizons;
const resBy = Object.fromEntries(D.results.map(r => [r.method, r]));
const v1By = Object.fromEntries(D.v1_results.map(r => [r.method, r]));
const NB = { RULE: 0.17123, Global: 0.17123, RouterNoGender: 0.17119, RouterFull: 0.17116, RouterNoGenderIncome: 0.15702, NoDemographics: 0.15355, UCF: 0.14268,
  POP: 0.11875, ICF: 0.11112, CONTENT: 0.09957, MF: 0.09264, MF_OBS: 0.07099, Random: 0.05993, MLP: 0.05325 };
const M = D.manifest, DS = M.dataset;
const sens = D.sensitivity;
const PRIV = M.privacy || {};
const PS = D.privacy_summary || { quasi: {}, generalization: [], quasi_identifiers: [], qa: [], k: 5 };
const PQS = PS.quasi || {}, PQ = PS.qa || [], PR_ = PS.release && PS.release.rows_out != null ? PS.release : null;
const LF = (PS.router_leaves || {}).RouterNoGender || null, PG = (PS.published || {}).group_results || null;
const UT = PS.users_table || null, UTX = UT ? UT.quasi_extended : null;                 // 서빙 학습자 표의 확장 조합 k
const HIER_KO = { gender: "성별", mobile: "기기", exp: "경험", risk: "성향", horizon: "기간", goal: "목적", income_q: "소득분위", age_band: "연령대" };
const TPF = D.tests_per_file || {};
const LAM_OP = (M.selection.router_lambdas || {}).RouterNoGender;
const lamRows = (M.router_tuning || {}).RouterNoGender || [];
const lamRow = l => { const r = lamRows.find(x => Math.abs(x.lam - l) < 1e-6 * Math.max(1, l)); return r ? r.mean : null; };
const lamSd = lamRows.length ? lamRows.filter(x => x.lam >= 3000).reduce((a, x) => a + x.std, 0) / Math.max(1, lamRows.filter(x => x.lam >= 3000).length) : null;
const nActive = resBy.RULE.active_users, nAll = resBy.RULE.users;
const dBPR = (resBy.MF_BPR ? resBy.MF_BPR.ndcg - resBy.MF.ndcg : null), dMLP = (resBy.MLP_BPR ? resBy.MLP_BPR.ndcg - resBy.MLP.ndcg : null);
const sensRev = sens.filter(x => x["RouterNoGender+prereq"].ndcg > x.RouterNoGender.ndcg).map(x => x.prereq_penalty);
const ZQ = { a2: 1.959963985, a1: 1.644853627, a2_dunnett: 2.241402728, a2_bonf3: 2.393979902, b80: 0.841621234 };   // 표준정규 분위수
const V1_EXP = { lo: 0.099, hi: 0.237 };   // 1차본 표 17 운영 라우터 소득분위별 심화 노출(2분위·5분위): 1차본도 기준 5%p를 넘었다
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
const ENROLL_DAYS = 56 - 7;                     // 8주 상한 안에 마지막 등록자의 7일 결과까지 들어오려면 등록은 49일 안에 끝나야 한다
const INFLOW2 = Math.ceil(2 * AB2 / ENROLL_DAYS), INFLOW3 = Math.ceil(2 * AB3 / ENROLL_DAYS);
// 쌍 비교(사용자 단위 쌍 부트스트랩 95% 구간), 집단별 활성 기준, 다양성, 기타 사실
const PR2 = Object.fromEntries((D.paired || []).map(x => [`${x.a}-${x.b}`, x])), PR1 = Object.fromEntries((D.paired_v1 || []).map(x => [`${x.a}-${x.b}`, x]));
const sgn = (x, d = 4) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d);
const ci = (x, d = 4) => x ? `${sgn(x.diff, d)} [${sgn(x.ci_low, d)}, ${sgn(x.ci_high, d)}]` : "–";
const sig = (x) => !x ? "–" : (x.ci_low > 0 ? "유의하게 높음" : (x.ci_high < 0 ? "유의하게 낮음" : "차이 없음"));
const ratioAct = nActive / nAll;
const eff = (x) => !x ? "–" : (x.ci_low > 0 ? "개선" : (x.ci_high < 0 ? "악화" : "차이 없음"));
const two = (x1, x2) => (effS(x1) === effS(x2) ? `v1·v2 모두 ${effS(x1)}다` : `v1에서 ${effS(x1)}고 v2에서 ${effS(x2)}다`);
const effS = (x) => !x ? "판단할 수 없었" : (x.ci_low > 0 ? "유의하게 개선되었" : (x.ci_high < 0 ? "유의하게 나빠졌" : "유의한 차이가 없었"));   // 서술어 어간: + "고" / "다"
const BPRU2 = PR2["MLP_BPRU-MLP"], BPRU1 = PR1["MLP_BPRU-MLP"], NEXT2 = PR2["MLP_NEXT-MLP"], NEXT1 = PR1["MLP_NEXT-MLP"], MFB2 = PR2["MF_BPR-MF"], MFB1 = PR1["MF_BPR-MF"];
const OBS2 = PR2["MLP_BPR-MLP"], OBS1 = PR1["MLP_BPR-MLP"], NEG2 = PR2["MLP_BPRU-MLP_BPR"], NEG1 = PR1["MLP_BPRU-MLP_BPR"];
const nnBest2 = Math.max(...["MF", "MF_OBS", "MF_BPR", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"].filter(k => resBy[k]).map(k => resBy[k].ndcg));
const nnBest1 = Math.max(...["MF", "MF_OBS", "MF_BPR", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"].filter(k => v1By[k]).map(k => v1By[k].ndcg));
const CT = D.click_tier || [];
const ctTopAll = CT.length ? CT.reduce((a, b) => (b.ndcg > a.ndcg ? b : a)) : null, ctTopAct = CT.length ? CT.reduce((a, b) => (b.ndcg_active > a.ndcg_active ? b : a)) : null;
const ctMonoDown = CT.length > 1 && CT.every((x, i) => i === 0 || x.ndcg_active < CT[i - 1].ndcg_active);   // 활동이 많을수록 활성 기준이 낮아지는가
const DIVL = D.diversity_by_len || {};
const DIVG = DIVL["RouterNoGender+prereq"] || {}, DIVR = DIVL.RouterNoGender || {};
const TESTS = D.tests_collected, SCREENS = D.screens, ROOTS = D.n_root_units;
const QUNITS = new Set(D.questions.map(q => q.topic + "|" + q.level)).size;
const QL = (l) => D.questions.filter(q => q.level === l).length;
const mlpAud = ((D.training_audit || {}).mlp9 || []).slice(-1)[0] || null;
const mlpPos = mlpAud ? mlpAud.positive / mlpAud.training_rows : null;
const bce0 = mlpPos ? -(mlpPos * Math.log(mlpPos) + (1 - mlpPos) * Math.log(1 - mlpPos)) : null;
const NNG = D.nn_groups || null, NNG1 = D.nn_groups_v1 || null;                 // 신경망 비교의 사용자군(모든 신경망이 학습한 사용자 등)
const CG = (g, k) => (g && g.pairs[k] && g.pairs[k].common) || null, HG = (g, k) => (g && g.pairs[k] && g.pairs[k].history_no_pairs) || null;
const BPRU2c = CG(NNG, "MLP_BPRU-MLP"), BPRU1c = CG(NNG1, "MLP_BPRU-MLP"), NEXT2c = CG(NNG, "MLP_NEXT-MLP"), NEXT1c = CG(NNG1, "MLP_NEXT-MLP");
const OBS2c = CG(NNG, "MLP_BPR-MLP"), OBS1c = CG(NNG1, "MLP_BPR-MLP"), NEG2c = CG(NNG, "MLP_BPRU-MLP_BPR"), NEG1c = CG(NNG1, "MLP_BPRU-MLP_BPR");
const MFB2c = CG(NNG, "MF_BPR-MF"), MFB1c = CG(NNG1, "MF_BPR-MF"), COLD2 = HG(NNG, "MLP_BPRU-MLP"), COLD1 = HG(NNG1, "MLP_BPRU-MLP");
const PA = D.pair_audit || {}, obsNeg = PA.mlp9_bpr && PA.mlp9_bpr.pairs ? PA.mlp9_bpr.pairs_with_observed_negative / PA.mlp9_bpr.pairs : null;
const RCH = D.router_champions || {}, QC = D.qa_categories || {}, FB = D.family_best_names || {};
const lamTxt = l => (l >= 1e8 ? "∞" : String(l));
const sensRow = pen => sens.find(x => x.prereq_penalty === pen);
const sensRevSig = sensRev.filter(pen => sensRow(pen)["RouterNoGender+prereq"].ci_low > 0);
const PS_ = D.personas || {};
const GF = D.gender_flip || null, PL = D.placebo || null;
const plPair = (a, b) => PL && (PL.paired || []).find(x => x.a === a && x.b === b);
const PL_OK = !!PL && ["Global-NoDemographics", "RouterFull-RouterNoGenderIncome", "RouterNoGender-RouterNoGenderIncome"].every(k => { const x = plPair(...k.split("-")); return x && x.ci_low <= 0; });   // 인구통계를 써서 유의하게 나아지지 않음                    // 번들 v2 성별 뒤집기 점검, 위약 세계 점검(scripts/placebo_check.py)
const shortT = t => t.split(":")[0].replace(/\(.*?\)/g, "").trim();                 // 단원 제목의 짧은 형태(콜론 뒤·괄호 제거)
const stl = (P, st) => (P && P.stage_titles && P.stage_titles[st] ? P.stage_titles[st].map(shortT).join("·") : "–");
const coreSame = ["B", "C"].every(k => PS_[k] && PS_.A && JSON.stringify(PS_[k].stage_titles.core) === JSON.stringify(PS_.A.stage_titles.core));
const lamAt = (name, l) => { const r = ((M.router_tuning || {})[name] || []).find(x => Math.abs(x.lam - l) < 1e-6 * Math.max(1, l)); return r ? r.mean : null; };
const valTop = D.validation_top || [];
const valTopRoad = valTop.filter(j => j.name.includes("로드맵")).length, valTopGoal = valTop.filter(j => j.name.includes("투자 목적")).length;
const opHas = (k) => D.operational_name.includes(k);
function valSentence(t) {   // 검증 상위 설정의 구성(데이터에 따라 문장을 고른다)
  const n = valTop.length, r = valTop.filter(j => j.family === "RULE").length;
  const a = r === n ? `검증 상위 ${n}개 설정은 모두 규칙 계열이다` : `검증 상위 ${n}개 설정 중 ${r}개가 규칙 계열이다`;
  const b = valTopRoad === n ? "이들은 모두 로드맵 단계 우선순위 신호를 포함하고" : `${valTopRoad}개가 로드맵 단계 우선순위 신호를 포함하고`;
  const c = valTopGoal === 0 ? "투자 목적 일치 신호를 포함한 설정은 없다" : `${valTopGoal}개가 투자 목적 일치 신호를 포함한다`;
  return `${a}. ${b}, ${c}(표 ${t}).`;
}
const EV = (() => { const sum4 = DS.complete + DS.quiz_pass + DS.save + DS.drop, ncnd = DS.not_complete - DS.drop; return { sum4, excess: sum4 - DS.study_attempts, ncnd }; })();
if (EV.excess !== DS.quiz_pass + DS.save - EV.ncnd) throw new Error("이벤트 합 분해 검산 실패");
const goalRows = D.group_results.filter(x => x.method === "RouterNoGender" && x.variable === "goal");
const goalMin = Math.min(...goalRows.map(x => x.ndcg)), goalMax = Math.max(...goalRows.map(x => x.ndcg));
const goalLo = goalRows.reduce((a, b) => (b.ndcg < a.ndcg ? b : a)), goalHi = goalRows.reduce((a, b) => (b.ndcg > a.ndcg ? b : a));
const goalHiAct = goalRows.length ? goalRows.reduce((a, b) => (b.ndcg_active > a.ndcg_active ? b : a)) : null;
const goalOverlap = Math.max(...goalRows.map(x => x.ci_low)) <= Math.min(...goalRows.map(x => x.ci_high));
const expRows = D.exposure.filter(x => x.method === "RouterNoGender");
const expTop = expRows.reduce((a, b) => (b.advanced_share > a.advanced_share ? b : a), expRows[0]);
const expByVar = {};
expRows.forEach(x => { (expByVar[x.variable] = expByVar[x.variable] || []).push(x); });
const expGaps = Object.entries(expByVar).map(([v, rows]) => { const hi = rows.reduce((a, b) => (b.advanced_share > a.advanced_share ? b : a)), lo = rows.reduce((a, b) => (b.advanced_share < a.advanced_share ? b : a)); return { v, gap: hi.advanced_share - lo.advanced_share, hi, lo }; }).sort((a, b) => b.gap - a.gap);
const expGap = expGaps.length ? expGaps[0].gap : 0;   // 같은 변수 안의 집단 간 최대 격차
const ageRows = D.group_results.filter(x => x.method === "RouterNoGender" && x.variable === "age_band");
const oldAge = ageRows.find(x => +x.group === 4) || ageRows[ageRows.length - 1];
const ageLo = ageRows.length ? ageRows.reduce((a, b) => (b.ndcg < a.ndcg ? b : a)) : null, ageHi = ageRows.length ? ageRows.reduce((a, b) => (b.ndcg > a.ndcg ? b : a)) : null;
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
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("제출일: 2026년 10월 19일 (2차본, 1차본 제출 2026년 10월 13일)", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("작성자: (이름 · 학번 기입)", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("소스 코드: github.com/kyounghob/forclaudekyoungho (브랜치 claude/pensive-goldberg-dzposy)", { size: 20, color: GREY })] }),
  spacer(1400),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("2차본(중간 점검 지적 반영): 활성 사용자 기준 NDCG 병기, BPR·목표 정렬 신경망 비교, ISA·기본예탁금·IRP 70%·과표기준가 콘텐츠 보강, 공식 API 전용 수집, 개인정보 저장 최소화·k-익명 반출, A/B 설계 정정", { size: 18, color: GOLD })] }),
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
  bullet([{ t: "데이터: ", bold: true }, `학습 로그 스키마(profiles·study_log·catalog + 목적·기간·선수 관계), 공개 데이터 출처 ${D.sources.length}건(전국투자자교육협의회 스쿨, 금융투자교육원 사전교육, KRX ETF 정보·정보데이터시스템·Open API, 공공데이터포털 시세·상장종목 API, 운용사 가이드북)을 등록부로 정리했다. 자동 수집은 공식 API만 쓰고(실행당 호출 상한, 페이지 넘김, 빈 응답·실패의 상태 기록), ETF 전종목 기본정보는 이용자가 직접 내려받은 파일을 정규화하며, 파일별 기준일과 30일 경과 경고, 샘플 폴백을 둔다. 개인정보는 번들에 원시 연령·연소득과 일·분 단위 시각을 남기지 않고, 가명처리 도구·k-익명 반출(export-deid)·저장 전 개인정보 QA ${PQ.length}건을 구현했다(4절).`]),
  bullet([{ t: "구현: ", bold: true }, `파이썬 패키지 etfrec, 카탈로그 v2(단원 ${D.catalog.n_items}개·선수 관계 ${D.catalog.n_prereq_edges}개), 진단 퀴즈 ${D.questions.length}문항(${QUNITS}개 단원), 세제·규제 단원 학습 요점, 로드맵 엔진, ETF 유형 분류 10종, 학습 파이프라인(설정 ${num(M.configurations)}개, 신호 ${M.signal_count}개, QA ${M.qa_passed}/${M.qa}건), FastAPI 서버와 11단계 웹 UI ‘학습 설계 스튜디오’, 자동화 테스트 ${TESTS}건과 Playwright UI 점검 스크립트(5절).`]),
  bullet([{ t: "결과: ", bold: true }, `모의 데이터 v2(학습자 ${num(DS.users)}명, 학습 시도 ${num(DS.study_attempts)}건)에서 검증 1위는 ‘${D.operational_name}’(검증 NDCG@5 ${fmt(M.selection.validation_best)}), 테스트 NDCG@5(전체 / 활성 사용자)는 규칙 ${fmt(resBy.RULE.ndcg)} / ${fmt(resBy.RULE.ndcg_active)}, 운영 라우터 ${fmt(resBy.RouterNoGender.ndcg)} / ${fmt(resBy.RouterNoGender.ndcg_active)}, 인기 ${fmt(resBy.POP.ndcg)} / ${fmt(resBy.POP.ndcg_active)}, 무작위 ${fmt(resBy.Random.ndcg)} / ${jo(fmt(resBy.Random.ndcg_active), "이었다/였다")}. 노트북 B의 원본 세계(v1)는 소수점 5자리까지 재현했다. 선수 단원 가드레일은 선수 미이수 추천을 ${pct(resBy.RouterNoGender.prereq_violation_rate, 0)}에서 0으로 줄이는 대신 NDCG를 ${fmt(resBy.RouterNoGender.ndcg - resBy["RouterNoGender+prereq"].ndcg, 3)} 낮췄는데, ${sensRev.length ? `선수 효과가 강한 세계(페널티 ${sensRev.map(x => Number(x).toFixed(1)).join("·")})에서는 이 비용이 사라지고 점 추정치가 역전되었다(${sensRevSig.length ? "95% 구간도 0을 넘음" : "다만 95% 구간은 0을 포함"}; 민감도 실험, 6절).` : "선수 효과를 키운 민감도 실험에서도 비용은 남았다(6절)."}`]),
  bullet([{ t: "평가 계획: ", bold: true }, "오프라인 정확도(전체·활성 사용자 기준)·다양성·교육 순서 준수 지표, 집단별 점검(두 기준), 온라인 A/B(MDE별 표본 크기, 고정 순서 검정, 기간 상한과 필요 유입) 설계, 사용성·전문가 검토 계획을 세웠다(7절). 남은 일정은 실제 공개 데이터 수집 실행, 교육 자료 연동, 사용자 테스트, 최종 보고서다(8절)."]),
  bullet([{ t: "기대효과: ", bold: true }, "학습자는 목적·수준에 맞는 다음 단원과 올바른 학습 순서로 학습 효율과 위험 인지가 높아지고(온라인 주 지표인 7일 퀴즈 통과율 22% → 24%가 목표), 교육 서비스는 학습 완료율 향상·콘텐츠 공백 파악·규제 위험 감소를, 사회적으로는 금융 이해력 향상과 불완전판매 예방을 기대한다. 효과마다 측정 지표·목표·확인 방법을 정했다(2.6절)."]),
  bullet([{ t: "중간 점검 지적 반영: ", bold: true }, `별도 문서 ‘비판 검토 및 보완 보고서’에서 지적 11건을 문장 단위로 판정했다. 수용 6건(A/B 설계, 기본예탁금, ISA·IRP 70%, 과표기준가, KRX 비공식 호출 제거, 가명정보·k-익명성), 부분 수용 3건(손실 함수·BPR: 요구한 BPR 기준선은 모두 추가했지만 MLP 개선은 노트북 세계에서만 확인, 정답 없는 사용자의 NDCG 처리, 총평), 불수용 1건(모의 로그의 ‘산술 모순’: 이벤트 열은 한 시도의 다중 플래그이며 합계 초과분은 통과·저장 플래그와 미완료·비이탈 시도로 정확히 분해된다), 긍정 평가 1건(다양성 지표). 가장 큰 정정은 손실 함수다. 1차본은 MF·MLP의 낮은 성능을 ‘모델 결함이 아니라 목표 불일치’라고 실험 없이 단정하고 랭킹 손실(BPR) 비교를 다음 단계로 미뤘다. 같은 실행에서 비교하니 미관측 단원을 음성으로 쓰는 쌍별 손실을 쓰면 노트북 세계(v1)에서 MLP 점수(${fmt(v1By.MLP.ndcg, 5)} → ${v1By.MLP_BPRU ? fmt(v1By.MLP_BPRU.ndcg, 5) : "–"})가 ${effS(BPRU1)}고, BPR MF는 표본 MF보다 ${two(MFB1, MFB2)}. v2에서는 전체 사용자 기준으로 MLP보다 ${effS(BPRU2)}는데(${ci(BPRU2)}), 이 차이는 학습 주에 통과가 없어 쌍별 모델이 학습하지 못하고 대체 점수를 받는 사용자에게서 나온다. 모든 신경망이 학습한 사용자로 좁히면 ${effS(BPRU2c)}다(${ci(BPRU2c)}). 어느 신경망도 규칙을 넘지 못했다(6.3절, 부록 E).`]),
  ...table(["항목", "제안서(9월)", "현재(10월 중간)"], [
    ["문제 정의", "ETF 교육 콘텐츠 다음 단원 추천", "투자 목적·수준 진단 → 로드맵 → 단원 추천 → ETF 유형 연결"],
    ["카탈로그", "주제 20 × 수준 3 = 60단원", `주제 ${D.catalog.n_topics} × 수준 3 = ${D.catalog.n_items}단원, 선수 관계 ${D.catalog.n_prereq_edges}개, 단원별 출처·개념 태그`],
    ["학습자 입력", "관심 주제·수준·기기·시간대·인구통계", "+ 투자 목적(5종)·투자 기간(3종)·진단 퀴즈 결과(20문항)"],
    ["추천 신호", "규칙 6개 + 인기·CF·MF·MLP", `+ 투자 목적 일치, 로드맵 단계 우선순위, BPR MF·쌍별 MLP·목표 정렬 MLP (신호 ${M.signal_count}개, 설정 ${num(M.configurations)}개)`],
    ["가드레일", "수준(두 단계 위 차단, 한 단계 위 1개), 통과 단원 제외", "+ 선수 단원 미이수 차단(평가에 별도 행으로 기록)"],
    ["데이터", "모의 데이터(노트북 생성기)", `모의 데이터 v2 + 공식 API 커넥터(KRX Open API·공공데이터포털)·수동 내려받기 정규화 + 출처 등록부 ${D.sources.length}건 + 저장 최소화·가명처리·k-익명 반출`],
    ["산출물", "노트북", "패키지·CLI·REST API·11단계 UI·테스트·스크린샷·재현 스크립트"],
  ], [2, 4, 6], { caption: "제안서 대비 중간 시점의 변화", zebra: true }),
  ...table(["채점 항목(배점)", "필수 작성 내용", "이 보고서의 위치"], [
    ["1. 추천 기법 요약 및 한계점(30)", "인기·규칙·콘텐츠·사용자 CF·아이템 CF·행렬분해의 핵심 원리, 장점, 한계점 비교", "3.1절 표(여섯 기법과 확장 기법의 핵심 원리·필요 데이터·장점·한계·역할), 3.2절(한계별 증상과 대응)"],
    ["2. 해결하고자 하는 문제와 추천 시나리오(25)", "해결할 문제, 대상 사용자, 추천 아이템, 구체적인 사용 상황, 기대효과", "2.1~2.3절(문제), 2.4절(대상 사용자·페르소나), 2.5절 시나리오 정의 표(추천 아이템·사용 상황), 2.6절(기대효과와 측정 방법)"],
    ["3. 활용 데이터와 확보 계획(20)", "필요한 데이터 항목과 예시, 확보 방법, 사용자 반응의 해석 방법", "4.1절(데이터 항목), 4.6절(데이터 예시·확보 방법 요약·반응 해석과 평점을 쓰지 않는 이유), 4.2~4.3절(출처와 수집 경로)"],
    ["4. 적용 기법 및 비교 방법(15)", "적용할 기법, 선정 이유, 비교 기준 방법, 예상 한계와 개선 방향", "3.4절(적용 기법·선정 이유·비교 기준·예상 한계·개선 방향), 6.3절(비교 결과)"],
    ["5. 평가 계획(10)", "평가 지표 1~2개, 선택 이유, 평가 데이터와 절차", "7절 첫머리(주 지표 2개와 선택 이유, 평가 데이터·절차), 7.1~7.5절(세부 지표·온라인 실험·수용 기준)"],
  ], [2.6, 4, 5.9], { caption: "채점 기준 대응표(중간보고서 안내의 평가 항목)", size: 16, zebra: true }),
  p("읽는 순서: 채점 항목의 필수 내용은 2·3·4·7절에 있다. 5·6절과 부록은 제안한 방법이 실제로 동작하는지 보이는 구현·실험 근거로, 필수 내용은 아니지만 판단 근거로 함께 싣는다.", { size: 19, color: GREY }),
);

// 2. 문제 정의
add(pageBreak(), h1("2. 문제 정의와 시나리오"),
  h2("2.1 배경: 상품은 급증했지만 학습 경로는 없다"),
  p("한국거래소 집계로 국내 상장 ETF는 2025년 7월 1,000종목을 넘었고, 2025년 ETF·ETN 시장 결산 기준 상장 종목 1,058개, 순자산총액 297조 2천억 원으로 1년 사이 71% 성장했다. 같은 기초지수를 따르는 상품이 운용사별로 여럿 상장되고, 커버드콜·월배당·레버리지·환헤지(H)·합성·액티브 같은 구조 변형이 더해지면서 초보 투자자가 상품명만 보고 차이를 이해하기 어려워졌다. 투자자 교육 자료는 전국투자자교육협의회 스쿨, 금융투자교육원 사전교육, 한국거래소 정보 포털, 운용사 가이드북 등 여러 곳에 흩어져 있고, 어느 것을 어떤 순서로 봐야 하는지 알려 주는 장치가 없다."),
  h2("2.2 보이지 않는 비용과 구조적 리스크"),
  p("학습자가 가장 자주 놓치는 네 가지를 이 시스템의 ‘필수 기초 개념’으로 삼았다."),
  ...table(["개념", "무엇이 문제인가", "로드맵에서의 위치"], [
    ["총보수(수수료)", "순자산에서 매일 조금씩 차감되어 가격에 숨어 있다. 같은 지수를 따르는 ETF라도 운용사·상품마다 총보수가 다르고, 작은 차이도 장기 복리로 수익률 격차를 키운다(실제 분포는 KRX 전종목 기본정보의 총보수로 유형별 중앙값·범위를 계산해 유형 카드에 보여 준다).", "필수 기초 ‘ETF 총보수 이해하기’(수준 1) → ‘추적오차가 생기는 이유’(수준 2)"],
    ["괴리율(시장가격 vs NAV)", "장중 가격이 순자산가치와 벌어지면 비싸게 사거나 싸게 팔게 된다. 해외·원자재·거래량이 적은 ETF에서 커진다.", "‘ETF 가격은 어떻게 정해지나: NAV와 괴리율’(수준 2), ‘괴리율이 커지는 상황 이해하기’(수준 3)"],
    ["환헤지(H) 여부", "해외 ETF의 수익률에 환율 변동이 더해지는지(환노출) 상쇄되는지(환헤지)가 상품명 끝의 (H)로만 구분되고, 헤지 비용은 금리차에 따라 달라진다.", "‘환율이 해외 ETF 수익률에 미치는 영향’(수준 1) → ‘환헤지형과 환노출형 ETF 비교’(수준 2) → ‘환헤지 비용과 금리차’(수준 3)"],
    ["파생형 상품의 복리 효과", "레버리지·인버스 ETF는 ‘일간’ 수익률의 배수를 따르므로 횡보장에서 지수가 제자리여도 손실이 누적된다(음의 복리). 연금계좌 편입이 제한되고, 사전교육과 기본예탁금(1,000만원; 단일종목형은 현금 3,000만원, 사전교육 총 3시간, 신규 투자자 모의거래 5시간)이 있다.", "‘레버리지·인버스 ETF란’(수준 1) → ‘일일 수익률 복리와 음의 복리 효과’(수준 2) → ‘변동성 장세의 레버리지 위험과 거래 요건’(수준 3, 학습 요점 포함) → 유형 카드"],
    ["세제·계좌 관문(2차본 보강)", "같은 ETF라도 어느 계좌에서 사느냐에 따라 세금이 다르다: ISA(순이익 200만원·서민형 400만원 비과세, 초과분 9.9% 분리과세), 연금저축·IRP(과세이연, IRP 위험자산 70% 한도), 국내 상장 해외·채권·원자재 ETF의 보유기간과세(실제 차익과 과표기준가 상승분 중 작은 금액에 15.4%).", "‘절세 계좌’ 주제 3단원(신설), ‘IRP·연금저축의 ETF 투자 규칙과 위험자산 70% 한도’(수준 2), ‘해외 ETF 세금: 과표기준가·보유기간과세와 양도소득세’(수준 3)"],
  ], [2.2, 6, 4.3], { caption: "학습자가 놓치기 쉬운 비용·구조 리스크·세제 관문과 로드맵 배치", zebra: true }),
  h2("2.3 개인화된 학습의 부재"),
  p("같은 ‘ETF 초보’라도 노후 대비 연금 투자자는 연금계좌 편입 규칙·세액공제·과세이연과 자산배분을, 월 현금흐름을 원하는 투자자는 분배금·커버드콜·리츠·채권 ETF의 작동 원리를, 단기 트레이딩에 관심 있는 투자자는 유동성·호가 스프레드·괴리율과 레버리지의 복리 효과를 먼저 알아야 한다. 또 현재 지식 수준이 다르면 같은 단원이라도 너무 쉽거나 어려워 이탈로 이어진다. 기존 교육 포털은 목록을 나열할 뿐 이 두 축(목적 × 수준)으로 큐레이션하지 않는다. 이 프로젝트는 ‘진단 → 기초 → 목적별 핵심 → 심화 → ETF 유형 연결’의 로드맵 안에서 추천이 일어나도록 설계해 이 공백을 메운다."),
  h2("2.4 대상 사용자와 시나리오"),
  p("웹 UI의 자연어 예시 문장으로도 쓰인 세 가지 페르소나다. 진단 답안과 목적·성향·기간을 페르소나마다 정해 실제 로드맵 엔진으로 계산한 결과다(export 스크립트의 PERSONAS)."),
  ...table(["페르소나", "진단(실제 채점)", "로드맵(실제 계산)", "추천·연결"], [
    ["A. 45세 직장인, 연금저축·IRP로 노후 준비, 안정 성향, 10년 이상, 초급",
     PS_.A ? `${PS_.A.quiz_desc} → 진단 수준 ${PS_.A.level}(정답 ${PS_.A.correct}/${PS_.A.answered}). 맞힌 단원 ${PS_.A.mastered.length}개(${PS_.A.mastered.slice(0, 3).join("·")} 등)는 ‘진단 통과’로 기록되어 후보에서 빠진다.` : "–",
     PS_.A ? `${PS_.A.goal_label} 템플릿을 안정 성향·${PS_.A.horizon_label}으로 계산: 단원 ${PS_.A.units_total}개(진단 통과 ${PS_.A.units_passed}개), 남은 시간 약 ${PS_.A.minutes_left}분/전체 ${PS_.A.minutes_total}분. 필수 기초 ${PS_.A.stage_counts.core}개(${coreSame ? "세 페르소나 공통, " : ""}선수 단원 포함: ${stl(PS_.A, "core")}) → 목적별 핵심 ${PS_.A.stage_counts.goal}개(${stl(PS_.A, "goal")}) → 심화 ${PS_.A.stage_counts.advanced}개(${stl(PS_.A, "advanced")}). 연금 템플릿에는 레버리지 심화 단원이 없고(안정 성향이면 어느 목적에서든 레버리지 수준 3을 뺀다), 음의 복리 단원은 필수 기초라 남는다.` : "–",
     PS_.A ? `다음 단원 ‘${PS_.A.next_unit}’(필수 기초 단계). 연결 유형: ${PS_.A.types.join(", ")}. 연금계좌 편입 가능 여부·IRP 위험자산 70% 한도·과세이연과 ISA 만기 자금의 연금계좌 전환(추가 세액공제) 안내.` : "–"],
    ["B. 38세 중급, 월배당으로 현금흐름, 커버드콜·리츠 관심, 중립 성향, 3년",
     PS_.B ? `${PS_.B.quiz_desc} → 진단 수준 ${PS_.B.level}(정답 ${PS_.B.correct}/${PS_.B.answered}). 분배금·NAV와 괴리율 단원을 포함해 ${PS_.B.mastered.length}개 단원이 진단 통과(로드맵 안 ${PS_.B.units_passed}개).` : "–",
     PS_.B ? `${PS_.B.goal_label} 템플릿을 중립 성향·${PS_.B.horizon_label}으로 계산: 단원 ${PS_.B.units_total}개, 남은 시간 약 ${PS_.B.minutes_left}분/전체 ${PS_.B.minutes_total}분. 필수 기초 ${PS_.B.stage_counts.core}개${coreSame ? "(A와 같음)" : `(${stl(PS_.B, "core")})`} → 목적별 핵심 ${PS_.B.stage_counts.goal}개(${stl(PS_.B, "goal")}) → 심화 ${PS_.B.stage_counts.advanced}개(${stl(PS_.B, "advanced")}). ‘해외 ETF 거래 방법과 환전’은 템플릿 단원이 아니라 과표기준가 단원의 선수라 함께 들어온다.` : "–",
     PS_.B ? `다음 단원 ‘${PS_.B.next_unit}’(필수 기초 단계). 연결 유형: ${PS_.B.types.join(", ")}. 커버드콜의 ‘상승 제한·분배금 원천’ 주의 사항 카드.` : "–"],
    ["C. 27세 적극 성향, 단기 매매로 레버리지 ETF 사용 희망, 경험 없음, 몇 달 단위",
     PS_.C ? `${PS_.C.quiz_desc} → 진단 수준 ${PS_.C.level}(정답 ${PS_.C.correct}/${PS_.C.answered}). 레버리지 복리 문항을 틀려 ‘일일 수익률 복리와 음의 복리 효과’가 필수 기초 단계에 학습할 단원으로 남는다.` : "–",
     PS_.C ? `${PS_.C.goal_label} 템플릿을 적극 성향·${PS_.C.horizon_label}으로 계산: 단원 ${PS_.C.units_total}개, 남은 시간 약 ${PS_.C.minutes_left}분/전체 ${PS_.C.minutes_total}분. 필수 기초 ${PS_.C.stage_counts.core}개${coreSame ? "(A와 같음)" : `(${stl(PS_.C, "core")})`} → 목적별 핵심 ${PS_.C.stage_counts.goal}개(${stl(PS_.C, "goal")}) → 심화 ${PS_.C.stage_counts.advanced}개(${stl(PS_.C, "advanced")}). 심화 가운데 템플릿 단원은 레버리지 거래 요건·괴리율 확대·테마 집중 위험·선물 롤오버·콘탱고와 백워데이션·과표기준가이고, 나머지(분배금 3단원·해외 ETF 거래·원자재 기초·테마 구성 종목)는 그 선수 단원이다. 단기 기간 규칙(유동성 2 추가)은 이 단원이 이미 핵심 단계에 있어 단원 수를 바꾸지 않는다.` : "–",
     `연결 유형에 레버리지·인버스가 포함되지만 ‘개념 통과 + 금융투자교육원 사전교육(약 1시간) + 기본예탁금 1,000만원(단일종목형은 2026-07-31부터 현금 3,000만원, 2026-08-19부터 사전교육 총 3시간·신규 투자자 모의거래 5시간)’을 안내한 뒤에 카드가 열린다. 예탁금이 없으면 교육을 마쳐도 매수 주문이 들어가지 않는다는 점을 카드 주의 사항에 적었다. 안정 성향 학습자라면 같은 목적이어도 이 카드는 ‘학습용(권장 아님)’으로만 보인다.`],
  ], [3, 3, 5, 4], { caption: "세 가지 페르소나 시나리오(진단과 로드맵은 실제 계산)", zebra: true }),
  h2("2.5 추천 문제의 정의"),
  bullet([{ t: "입력: ", bold: true }, "학습자 프로필(연령·소득·투자 경험·위험성향·기기·시간대, 성별은 수집하되 운영 설정에서 제외), 투자 목적(연금·노후 / 배당·인컴 / 장기 지수 / 단기 매매 / 분산·안정), 투자 기간(1년 미만 / 1~5년 / 5년 이상), 관심 주제 2개, 진단 퀴즈 결과 또는 학습 기록(조회·완료·퀴즈 통과·저장·이탈)."]),
  bullet([{ t: "출력: ", bold: true }, "① 단계별 로드맵(단원 상태: 통과·학습 가능·잠김, 남은 학습 시간, 다음 단원), ② 지금 공부할 단원 Top-5(점수·근거·신호 기여도·출처 링크), ③ ETF 유형 안내 카드(개념 통과 여부, 세금·연금계좌·규제·주의, 유형 통계)."]),
  bullet([{ t: "정답 정의(오프라인): ", bold: true }, "기준 주 다음 주에 학습자가 퀴즈를 통과한 단원. 후보는 ‘아직 통과하지 않은 단원 ∩ 수준 가드레일(추정 수준 + 2 이상 차단) ∩ (선택) 선수 단원 통과’로 제한하고, 목록을 고를 때 한 단계 위 단원은 최대 1개만 넣는다(목록 후처리)."]),
  bullet([{ t: "제약: ", bold: true }, "특정 ETF 상품의 매수·매도 권유 금지(모든 화면과 추천을 담은 API 응답에 고지문 포함), 성별을 운영 라우터에서 제외, 요청 중 재학습 없음(미리 학습된 번들만 사용), 교육 자료는 링크·출처만 저장하고 본문을 복제하지 않음."]),
  bullet([{ t: "성공 기준: ", bold: true }, "오프라인 NDCG@5가 인기·무작위 기준선을 유의하게 앞서고(95% 부트스트랩 구간), 선수 단원 위반 0, 집단별 정확도 격차가 설명 가능하며, 온라인에서는 다음 주 퀴즈 통과율이 대조군 A(세그먼트 인기순)보다 높을 것(7절). 오프라인 NDCG에서는 가드레일을 켠 서비스 설정이 대조군보다 낮으므로 이 기준은 온라인 실험으로만 판정한다."]),
  ...table(["항목", "정의"], [
    ["해결할 문제", "국내 상장 ETF가 2025년 말 1,058종목·순자산 297조 원으로 급증했지만, 총보수·괴리율·환헤지·레버리지 복리 효과·과세 방식 같은 구조적 비용과 위험은 상품명에 드러나지 않는다. 초보 투자자는 자기 투자 목적과 지식 수준에 맞춰 ‘무엇을 어떤 순서로 배워야 하는지’ 알기 어렵고, 기존 교육 자료는 모두에게 같은 순서로 제공된다(2.1~2.3절)."],
    ["대상 사용자", "ETF 투자를 시작하려 하거나 막 시작한 개인 투자자(20~60대). 대표 시나리오는 연금저축·IRP로 노후를 준비하는 초급자(A), 월배당 현금흐름을 원하는 중급자(B), 레버리지 ETF로 단기 매매를 하려는 경험 없는 적극 성향 투자자(C)다(2.4절 표). 증권사 앱이나 금융교육 플랫폼의 학습 메뉴를 쓰는 사용자를 가정한다."],
    ["추천 아이템", `ETF 교육 콘텐츠 단원 ${D.catalog.n_items}개(주제 ${D.catalog.n_topics}개 × 수준 3단계. 예: ‘ETF 총보수 이해하기’, ‘ETF 가격은 어떻게 정해지나: NAV와 괴리율’, ‘일일 수익률 복리와 음의 복리 효과’, ‘ISA 계좌란’). 추천 단위는 지금 공부할 단원 Top-5이고, 이를 담은 단계별 로드맵과 마지막 단계의 ETF 유형 안내 카드(교육용, 특정 상품 권유 아님)를 함께 보여 준다.`],
    ["구체적인 사용 상황", "① 첫 방문: 자연어로 자기 상황을 적거나 진단 퀴즈 20문항을 풀면, 기록이 없어도(콜드스타트) 투자 목적·수준에 맞는 로드맵과 Top-5를 바로 받는다. ② 학습 중: 단원을 완료하거나 퀴즈를 통과하면 통과 단원이 후보에서 빠지고 다음 단원이 갱신된다(주 단위 재추천). 통과하지 못한 단원은 후보에 남고, 그 단원의 선수 단원을 아직 통과하지 않았으면 선수 단원이 먼저 추천된다. ③ 상품 유형으로 넘어가기 전: 로드맵 마지막 단계(ETF 유형 연결) 앞에 레버리지 거래 요건(사전교육·기본예탁금), IRP 위험자산 70% 한도 같은 관문 단원이 있고, 유형 카드는 관련 개념을 통과해야 ‘열림’으로 표시된다."],
    ["기대효과", "학습자의 학습 효율과 위험 인지 향상, 교육 서비스의 학습 완료·참여 증가와 규제 위험 감소, 사회적인 금융 이해력 향상(2.6절에서 측정 지표·목표와 함께 정의)."],
  ], [2, 10.5], { caption: "추천 시나리오 정의(해결할 문제·대상 사용자·추천 아이템·사용 상황·기대효과)", size: 17, zebra: true }),
);
add(h2("2.6 기대효과"),
  p("기대효과는 ‘이 추천이 성공하면 누구에게 무엇이 달라지는가’로 정의하고, 효과마다 측정 지표·목표·확인 방법을 함께 정했다. 목표는 기말 프로젝트에서 검증할 가설이다. 현재 근거는 모의 데이터의 오프라인 결과이고, 실제 학습자에게 나타나는 효과는 파일럿과 온라인 실험(7.3절)으로 확인한다."),
  ...table(["대상", "기대효과", "측정 지표", "목표(가설)", "현재 근거 · 확인 방법"], [
    ["학습자", "학습 효율: 자기 목적·수준에 맞는 다음 단원을 바로 찾아, 단원을 고르는 시간을 줄이고 이해(퀴즈 통과)에 이르는 비율을 높인다", "노출 후 7일 안에 퀴즈를 1개 이상 통과한 사용자 비율(온라인 주 지표), 오프라인 NDCG@5", "통과율 22% → 24%(+2%p, 대조군 A 대비)", `오프라인 NDCG@5: 운영 라우터 ${fmt(resBy.RouterNoGender.ndcg)}, 인기 ${fmt(resBy.POP.ndcg)}, 무작위 ${fmt(resBy.Random.ndcg)}(6.3절). 온라인은 A/B 1단계(7.3절)`],
    ["학습자", "올바른 학습 순서: 선수 개념을 모른 채 심화·레버리지 단원으로 건너뛰지 않는다", "Top-5 중 선수 미이수 단원의 비율", "0%(선수 가드레일 켬)", `가드레일 끔 ${pct(resBy.RouterNoGender.prereq_violation_rate, 0)} → 켬 0%. 대가는 NDCG ${fmt(resBy.RouterNoGender.ndcg - resBy["RouterNoGender+prereq"].ndcg, 3)} 감소와 짧은 목록(6.6절)`],
    ["학습자", "위험 인지: 투자하기 전에 구조적 비용(총보수·괴리율·환헤지), 레버리지 복리 효과, 거래 요건(사전교육·기본예탁금), 세제(ISA·IRP 70%·과표기준가)를 안다", "필수 기초 단원 완료율, 세제·규제 진단 문항의 사전·사후 정답률", "사후 정답률 상승(목표치는 파일럿에서 기준선을 잰 뒤 사전 등록)", "모든 목적의 로드맵 맨 앞에 필수 기초 7단원(5.2절), 진단 퀴즈 20문항(부록 B). 파일럿(11월 3주)과 사용성 테스트(7.4절)로 확인"],
    ["교육 서비스(증권사·금융교육 플랫폼)", "참여와 완료 증가, 이탈 감소: 수준에 맞는 단원을 받아 끝까지 학습하는 비율이 오른다", "완료율, 이탈률, 로드맵 진행률, 세션당 학습 시간(A/B 보조 지표)", "대조군 대비 개선(방향만 사전 등록)", "A/B 보조 지표로 확인(7.3절)"],
    ["교육 서비스", "콘텐츠 공백 파악: 진단 정답률과 단원별 통과율로 보강할 단원을 찾는다", "단원별 진단 정답률·통과율", "정답률이 낮은 단원 목록을 정기적으로 갱신", "중간 점검에서 절세 계좌(ISA) 3단원과 세제·규제 학습 요점을 새로 만든 것이 그 예다(부록 F)"],
    ["교육 서비스", "규제·평판 위험 감소: 상품 권유로 읽히지 않고, 민감 속성으로 추천이 달라지지 않으며, 개인정보를 최소로 저장한다", "비권유 고지 포함 여부, 성별 뒤집기 불변 비율, 집단별 심화 노출 격차, 개인정보 QA", "고지 100%, 불변 100%, 격차 5%p 이내", `성별 뒤집기 ${GF ? `${num(GF.invariant)}/${num(GF.users)}명 불변` : "–"}, 심화 노출 격차 ${fmt(expGap, 3)}(기준 초과, 11월 4주 과제, 6.5절), 개인정보 QA ${PQ.filter(q => q.passed).length}/${PQ.length}건 통과`],
    ["사회·시장", "금융 이해력 향상과 불완전판매 예방: ETF 시장이 빠르게 커지는 가운데 구조를 이해하고 투자하는 개인이 늘어난다", "(장기) 교육 이수자의 상품 이해도, 요건을 모른 채 낸 고위험 상품 주문의 감소", "정성 목표", "공공 교육 자료(전국투자자교육협의회·금융투자교육원)와 공식 공개 데이터(KRX·공공데이터포털)를 잇는 재현 가능한 설계라 다른 교육 기관도 재사용할 수 있다(4.2~4.3절)"],
  ], [1.7, 3.6, 2.6, 2.0, 3.6], { caption: "기대효과와 측정 방법", size: 15, zebra: true }),
  p("‘학습 효율’은 7절의 주 평가 지표(오프라인 NDCG@5, 온라인 7일 퀴즈 통과율)로, ‘올바른 학습 순서’는 선수 미이수 비율로 직접 검증한다. ‘위험 인지’와 교육 서비스 쪽 효과는 파일럿 뒤의 사전·사후 비교와 A/B 보조 지표로 확인한다."),
);

// 3. 추천 기법
add(pageBreak(), h1("3. 추천 기법 요약과 한계"),
  p("수업에서 다룬 기법을 이 문제에 맞게 정의하고, 각 기법이 필요로 하는 데이터와 한계, 이 시스템에서의 역할을 정리했다. 모든 기법은 같은 후보 집합·같은 정답·같은 후처리(가드레일·주제 상한)를 거쳐 비교되므로 표의 수치 차이는 기법 자체의 차이다."),
  h2("3.1 기법별 요약"),
  ...table(["기법", "핵심 원리·수식", "필요 데이터", "장점", "한계", "이 시스템에서의 역할"], [
    ["인기(POP)", "단원별 퀴즈 통과 건수(기준 주 이전 로그). 세그먼트 인기는 세그먼트 안 통과 비중을 전역 비중으로 수축: n/(n+λ)·세그먼트 + λ/(n+λ)·전역(세그먼트 변수 조합 31개 × λ ∈ {5, 20, 80} = 93개 신호)", "학습 로그", "콜드스타트에 강함, 단순·안정", "개인화 없음, 인기 편향, 다양성 1.0에 가깝지만 교육 순서 무시", "기준선, 규칙의 기준점수·하이브리드의 구성 신호"],
    ["규칙(지식 기반)", "기준 5 × 인기(세그먼트 없음 또는 연령대+소득분위) + 가산점: 관심 주제 3, 수준 일치 2, 연령 생애주기 주제 2, 소득 구간 주제 2, 위험성향 주제 2, 모바일·짧은 콘텐츠 1, 투자 목적 일치 2, 로드맵 단계 우선순위 2(가산점 8개의 모든 부분집합 × 기준 2종 = 512개 설정)", "프로필·목적·카탈로그", "설명 가능, 로그 없이 동작, 교육 정책을 직접 넣을 수 있음", "가중치가 사람 판단, 로그가 쌓여도 스스로 개선되지 않음", `검증 1위(${["관심 주제", "수준 일치", "연령 생애주기", "모바일·짧은 콘텐츠", "소득 구간 주제", "위험성향", "투자 목적 일치", "로드맵 단계 우선순위"].filter(k => opHas(k)).join("·")}). 라우터의 기본 설정`],
    ["콘텐츠 기반", "단원 특징(주제·수준 원-핫, 주제 이름+제목의 문자 2~3그램 TF-IDF, 또는 둘 다)과 학습자 선호 프로필의 코사인 유사도(6개 설정)", "카탈로그 텍스트, 학습자 이력", "신규 단원에 강함, 근거 제시 쉬움", "비슷한 것만 추천(과특화), 이력 없으면 관심 주제만 의존", `하이브리드 구성 신호(테스트 보고 설정: ${FB.CONTENT || "–"}), 운용사 가이드북 텍스트로 확장 예정`],
    ["사용자 CF", "코사인 유사 학습자 k명(k ∈ {20, 50, 100})의 반응 가중 평균, 인구통계 유사도 혼합(w ∈ {0.2, 0.5}) 변형(27개 설정)", "충분한 사용자×단원 반응", "집단 지성, 의외의 발견", `희소성(밀도 ${pct(DS.density, 0)})·콜드스타트, 선수 구조 무시(선수 미이수 ${fmt(resBy.UCF.prereq_violation_rate, 2)}), 계산량`, `비교 기준선(테스트 보고 설정: ${FB.UCF || "–"}). CF 항이 비CF 항과 섞인 하이브리드에서는 아이템 반응 근거 n_i/(n_i+10)로 CF 비중을 줄인다(단독 CF 설정에는 적용하지 않음)`],
    ["아이템 CF", "단원 간 수축 코사인 유사도(λ ∈ {0, 5, 10, 30}, 신뢰도 가중 여부; 8개 설정)로 ‘함께 학습(시도)한 단원’ 점수(조회만 한 시도도 함께 나온 것으로 셈)", "반응 행렬", "안정적, 오프라인 사전 계산", "인기 단원 쏠림, 새 단원 불가", `비교 기준선(테스트 보고 설정: ${FB.ICF || "–"}), 하이브리드 구성 신호`],
    ["행렬분해(MF)", "표본 MF(6·9주차): 관측 칸은 신뢰도 1+α·log(1+점수) 가중, 미관측 칸은 표본추출해 0으로 둔 가중 MSE. 관측 MF: 관측된 행만 MSE. 둘 다 사용자·단원 잠재요인 내적, Adam", "반응 행렬(암묵 피드백)", "희소 행렬 일반화", "점수 회귀(점별 손실)라 순위를 직접 학습하지 않음, 해석 어려움", "비교 기준선(torch 학습, NumPy 추론)"],
    ["MLP(9주차)", "사용자·단원 임베딩 → 은닉층 → 통과 확률(BCEWithLogitsLoss). 관측된 시도 행만 학습(양성 = 통과, 음성 = 시도했지만 미통과). 미관측 단원은 학습에 쓰지 않음. 관측 행이 있는 사용자는 통과가 없어도 학습된다", "관측 시도 + 통과 레이블", "비선형 상호작용", `시도하지 않은 단원과 시도한 단원을 비교하는 법을 배우지 못함(다음 주 선택 예측과 어긋남). 인기 대비 v2 ${fmt(resBy.MLP.ndcg - resBy.POP.ndcg, 3)}, 무작위 대비 v1 ${fmt(v1By.MLP.ndcg - v1By.Random.ndcg, 3)}(6절)`, "비교 기준선"],
    ["쌍별·목표 정렬 확장(2차본)", `BPR MF: −ln σ(p_u·q_i − p_u·q_j), j = 미관측 단원(에폭마다 다시 추출) / MLP 쌍별(관측 음성): (통과, 미통과 시도) 쌍(미통과 시도가 없는 사용자는 미관측 단원으로 대체${obsNeg != null ? `, 테스트 스냅샷 쌍의 ${pct(1 - obsNeg)}` : ""}) / MLP 쌍별(미관측 음성): (통과, 미관측) 쌍 = 비판이 처방한 BPR / MLP 목표 정렬: (주 w에 처음 통과한 단원, 그 주까지 통과하지 않은 단원) 쌍. 쌍별·목표 정렬 MLP는 쌍에 나온 사용자·단원만 학습되며, 쌍이 없는 사용자(학습 주에 통과가 없는 사용자)는 콘텐츠 유사도 대체 점수를 받는다`, "반응 행렬·관측 시도·주차", "미관측을 ‘거절’이 아니라 ‘양성보다 뒤’로 보는 순위 학습, 평가 목표(다음 주 통과)와 맞춘 레이블", `세계와 학습 범위에 따라 효과가 다름: 미관측 음성 쌍별 MLP − MLP는 v1 ${eff(BPRU1)}(공통 학습 사용자 ${eff(BPRU1c)}), v2 전체 ${eff(BPRU2)}·공통 학습 사용자 ${eff(BPRU2c)}. 신경망 최고치(v1 ${fmt(nnBest1, 3)}, v2 ${fmt(nnBest2, 3)})는 규칙(${fmt(v1By.RULE.ndcg, 3)}, ${fmt(resBy.RULE.ndcg, 3)}) 아래(6.3절)`, "같은 후보·정답·후처리로 비교(기법군 MF_BPR·MLP_BPR·MLP_BPRU·MLP_NEXT)"],
    ["하이브리드", "신호 가중합 또는 α_u 가중: α_u = n_u/(n_u+λ)로 이력이 많을수록 CF 비중 ↑", "위 모두", "콜드스타트와 개인화를 잇는 전환", `조합 수 폭발(${num(M.configurations)}개) → 검증으로 선택 필요`, "설정 풀의 대부분(HYBR 1,024개 등)"],
    ["세그먼트 라우터", "학습활동→선호군집→연령대→소득분위(→성별) 계층에서 세그먼트별 최적 설정을 전역 1위로 수축(λ 교차 선택, 표본 20명 미만 노드는 상위 추정을 그대로 씀)", "검증 주차 사용자별 점수", "집단마다 다른 설정 가능", "세그먼트가 작으면 과적합 → λ 커지며 전역과 동일해짐", LAM_OP >= 1e8 ? "운영 설정(성별 제외). 이번 데이터에서는 λ=∞가 선택되어 전역 1위와 같음" : "운영 설정(성별 제외). 이번 데이터에서 전역 1위와 유의한 차이 없음"],
  ], [1.6, 3.6, 1.8, 2, 3, 2.6], { caption: "추천 기법 요약과 한계", size: 16, zebra: true }),
  h2("3.2 한계에 대한 설계상의 대응"),
  ...table(["한계", "증상(이 프로젝트에서 관찰)", "대응"], [
    ["콜드스타트", "기록 없는 신규 학습자는 아이템 CF·MF 점수가 0이고, 사용자 CF는 인구통계 유사도로만 점수가 생긴다(행동 이웃 없음)", "진단 퀴즈로 수준·통과 단원을 즉시 확보, 규칙·콘텐츠·세그먼트 인기 신호, α_u 가중으로 기록이 쌓이면 CF 비중 증가"],
    ["희소성", `사용자×단원 밀도 ${pct(DS.density)}(학습 결과로 계산한 값이며 생성기의 제약이 아님), 검증 사용자 ${pct(M.validation.zero_observed_target / M.validation.rows, 0)}가 다음 주 정답 0개`, "수축(λ)·CF 신뢰도 게이트. 정답 없는 사용자를 NDCG 0으로 넣은 전체 기준(노트북 규칙)과 정답이 있는 사용자만 평균한 활성 기준을 함께 보고(6.1절)"],
    ["인기 편향·다양성 저하", "인기 신호 비중이 크면 모두 같은 단원", "Diversity@5·주제 상한 옵션, 추천 근거에 기여도 분해 표시"],
    ["학습 목표·손실의 불일치", "MF·MLP가 인기보다 낮음(v1의 MLP는 무작위보다 낮음)", `같은 실행에서 네 가지 변형을 비교했다(6.3절 표). BPR MF(표본 MF 대비 v1 ${eff(MFB1)}, v2 ${eff(MFB2)}), 미관측 음성 쌍별 MLP(MLP 대비 v1 ${eff(BPRU1)}, v2 ${eff(BPRU2)}; 모든 신경망이 학습한 사용자로 좁히면 v1 ${eff(BPRU1c)}, v2 ${eff(BPRU2c)}), 다음 주 통과를 직접 레이블로 쓴 목표 정렬 MLP(전체 v1 ${eff(NEXT1)}, v2 ${eff(NEXT2)}; 공통 학습 사용자 v1 ${eff(NEXT1c)}, v2 ${eff(NEXT2c)}). 1차본의 ‘모델 결함이 아니라 목표 불일치’라는 단정은 실험 없이 쓴 문장이라 정정한다`],
    ["교육 순서 무시", `운영 라우터 Top-5의 ${pct(resBy.RouterNoGender.prereq_violation_rate, 0)}가 선수 단원 미이수`, "로드맵 단계 우선순위 신호 + 선수 단원 가드레일, 평가에 ‘선수 미이수 비율’ 지표 추가"],
    ["공정성·민감 속성", "성별이 추천을 바꾸면 안 됨", "운영 라우터에서 성별 제외, 성별 뒤집기 불변 검사(코드 수준), 집단별 NDCG·심화 콘텐츠 노출 비율 보고"],
    ["설명가능성", "학습자가 ‘왜 이 단원인지’ 알 수 없음", "신호별 기여도·근거 문장·계산식·세그먼트 경로를 API 응답과 화면에 표시"],
  ], [2, 4, 6.5], { caption: "기법 한계와 대응", zebra: true }),
  h2("3.3 종합: 왜 ‘하이브리드 + 라우터 + 로드맵 가드레일’인가"),
  p("교육 추천은 ‘학습자가 클릭할 것’이 아니라 ‘학습자가 지금 배워야 하고 통과할 수 있는 것’을 골라야 한다. 그래서 정확도만 높이는 모델 하나보다, (1) 교육 정책을 직접 담을 수 있는 규칙과 로드맵 신호, (2) 기록이 쌓이면 자동으로 개인화되는 CF·MF 신호, (3) 둘을 검증 데이터로 섞는 하이브리드와 세그먼트 라우터, (4) 어떤 설정이 선택되든 교육 순서와 난이도를 지키는 가드레일을 층으로 쌓았다. 설정 선택은 검증 주차에서 한 번만 하고 잠근 뒤 테스트 주차에서 보고하므로, 결과 표의 수치는 선택 과정에 오염되지 않은 추정치다."),
);
add(h2("3.4 적용 기법과 비교 방법"),
  p("3.1절의 비교를 바탕으로 이 문제에 적용할 기법과 그 이유, 비교 기준, 예상 한계와 개선 방향을 정리했다."),
  ...table(["항목", "내용"], [
    ["적용 기법", `세그먼트 라우터(성별 제외)가 고른 규칙 기반 하이브리드 ‘${D.operational_name}’에 수준·선수 가드레일을 더한 운영 설정이다. 기록이 없는 학습자는 진단 퀴즈 결과(수준·통과 단원)와 투자 목적으로 시작한다. CF·행렬분해·신경망 신호는 같은 설정 풀(${num(M.configurations)}개)에서 경쟁하며, 기록이 쌓이면 α_u = n_u/(n_u+λ) 가중으로 비중이 커지도록 하이브리드 후보에 남겨 둔다.`],
    ["선정 이유", "① 검증 주차 NDCG@5 1위로 데이터가 고른 설정이다(검증으로 고르고 테스트에서 보고). ② 교육 정책(수준 일치·선수 순서·투자 목적·로드맵 단계)을 신호로 직접 담을 수 있다. ③ 진단 퀴즈·관심 주제·목적만으로도 추천할 수 있어 콜드스타트에 강하다. ④ 신호별 기여도로 추천 근거를 설명할 수 있다. 사용자 CF·아이템 CF·행렬분해는 밀도 약 10%의 희소한 초기 로그에서 규칙보다 낮았다."],
    ["비교 기준이 될 방법", `인기(POP)와 무작위(하한), 전역 1위 설정, 인구통계를 쓰지 않는 1위 설정, 사용자 CF·아이템 CF·콘텐츠·행렬분해·MLP(BPR 변형 포함), 온라인 실험의 대조군 A(성별을 쓰지 않는 세그먼트 인기 중 검증 1위). 모두 같은 후보·같은 정답·같은 후처리로 평가하고, 차이는 사용자 단위 쌍 부트스트랩 95% 구간으로 판단한다(현재 운영 라우터 − 인기 ${ci(PR2["RouterNoGender-POP"])}).`],
    ["예상 한계", `① 모의 데이터라 규칙이 1위인 데에는 생성기 구조의 영향이 있다. ② 선수 가드레일은 정확도와 맞바꾼다(NDCG ${fmt(resBy.RouterNoGender.ndcg - resBy["RouterNoGender+prereq"].ndcg, 3)} 감소, 짧은 목록 ${pct(resBy["RouterNoGender+prereq"].short_list_rate, 0)}). ③ 소득분위별 심화 노출 격차(${fmt(expGap, 3)})가 기준(5%p)을 넘는다. ④ 실제 로그는 더 희소하고 콜드스타트 비중이 크다. ⑤ 어떤 신경망 변형도 규칙을 넘지 못했다.`],
    ["개선 방향", "① 실제 파일럿 로그로 다시 평가하고 선수 페널티를 보정한다(11월 3주). ② 짧은 목록 완화 규칙을 정한다(11월 4주). ③ 집단별 심화 노출 상한 정책을 둔다(11월 4주). ④ 쌍이 없는 사용자에게 점별 점수를 섞는 처리와 목적·로드맵 특징을 넣은 신경망을 비교한다(11월 3주). ⑤ 온라인 A/B로 교육 효과(7일 퀴즈 통과율)를 검증한다(7.3절)."],
  ], [2, 10.5], { caption: "적용 기법·선정 이유·비교 기준·예상 한계·개선 방향", size: 16, zebra: true }),
);

// 4. 데이터
add(pageBreak(), h1("4. 데이터와 확보 계획"),
  h2("4.1 데이터 유형과 스키마"),
  p("시스템은 네 종류의 데이터를 쓴다. 학습 로그는 실제 서비스 로그가 생기기 전까지 규칙을 공개한 모의 데이터로 대체하고, 나머지는 공개 출처에서 가져온다."),
  ...table(["유형", "내용", "현재 출처", "스키마·형식"], [
    ["① 학습자 프로필·학습 로그", "온보딩 프로필, 투자 목적·기간, 진단 결과, 단원별 조회·완료·퀴즈·저장·이탈 이벤트", "모의 데이터 v2(4.4절). 실제 로그는 가명처리 도구(pseudonymize)로 같은 스키마로 바꿔 연결(4.5절)", "학습 입력 — profiles.csv: user, gender, age, income, exp, risk, mobile, interest1, interest2, placement, goal*, horizon* / study_log.csv: user, item, week, day, hour, minute, complete, quiz, quiz_pass, save, drop, replay(한 행 = 한 시도; 이벤트 스트림이면 session_id 열을 더해 시도 단위로 묶음). 번들에는 연령대·소득분위 코드와 주차·4개 시간대·주 안 순서(seq)만 저장(4.5절)"],
    ["② 콘텐츠 카탈로그", `단원 ${D.catalog.n_items}개(주제 ${D.catalog.n_topics} × 수준 3), 선수 관계 ${D.catalog.n_prereq_edges}개, 단원별 개념 태그·출처 키·예상 학습 시간`, "직접 설계(교육 자료 목차 기반). 금칙어 검사 통과", "catalog.csv: item, title, topic, level, short, prereqs*(\"0;3\"), sources*(\"kcie_etf_school;krx_etf_info\")"],
    ["③ ETF 상품 메타데이터·시세", "종목명·운용사·기초지수·총보수·과세유형·복제방법·기초시장·자산 분류, 종가·NAV·거래량", "KRX 정보데이터시스템(이용자가 직접 내려받은 파일), KRX Open API, 공공데이터포털(금융위원회) API", "커넥터가 표준 열로 정규화: code, isin, name, issuer, index_name, total_fee, tax_type, market_class, asset_class + 파생 열 hedged, futures, total_return, etf_type, pension_eligible / 시세: close, nav, volume, premium = (종가 − NAV)/NAV"],
    ["④ 교육 자료·용어", "스쿨 강의, 사전교육, 투자설명서·용어집, 가이드북", "전국투자자교육협의회, 금융투자교육원, 한국거래소, 운용사", "출처 등록부(이름·기관·URL·메뉴 경로·종류·접근·이용 조건·확인 상태). 본문은 저장하지 않음"],
  ], [2.2, 3.6, 2.8, 4.4], { caption: "데이터 유형(별표 * 는 선택 열)", zebra: true }),
  h2("4.2 공개 데이터·교육 자료 출처 등록부"),
  p("아래 표는 시스템 안의 출처 등록부(etfrec/sources/registry.py)를 그대로 옮긴 것이다. ‘확인’ 열은 2026년 10월 기준 검색으로 확인한 범위를 뜻하며, 기관 개편으로 세부 주소가 바뀔 수 있어 화면에서는 기관 루트와 메뉴 경로를 함께 보여 준다."),
  ...table(["출처", "종류 · 접근", "시스템에서의 쓰임", "이용 조건", "확인"],
    D.sources.map(s => [[{ t: s.name, bold: true }], [s.kind, { t: " · " + s.access, color: GREY }], s.use, s.license, s.verified]),
    [3, 3, 4, 2.8, 1.6], { caption: `공개 데이터·교육 자료 출처 등록부(${D.sources.length}건)`, size: 16, zebra: true }),
  h2("4.3 접근 설계와 커넥터"),
  bullet([{ t: "KRX 정보데이터시스템 ETF 전종목 기본정보(2차본 변경): ", bold: true }, "1차본은 화면이 쓰는 JSON 엔드포인트를 프로그램으로 호출했으나, 이용약관(자동 수집·서버 부하)과 서비스 중단 위험을 지적받아 그 코드를 삭제했다. 이제 이용자가 화면에서 직접 내려받은 파일을 `python -m etfrec sources sync --krx-csv 파일 [--krx-csv-date YYYYMMDD]`로 정규화한다. CSV는 UTF-8·cp949를 모두 읽고, Excel은 openpyxl(.xlsx)·xlrd(.xls)가 설치된 경우에만 읽으며 없으면 원인을 적어 ‘fail’로 기록한다(기존 스냅샷은 지우지 않음). 단축코드·종목명이 비었거나 기초지수명·총보수 열이 없는 파일(주식 전종목 기본정보처럼 다른 화면의 파일)은 형식 검사에서 ‘fail’(schema)로 기록하고 기존 스냅샷을 바꾸지 않는다. 기준일(--krx-csv-date)은 실제 날짜만 받고, 주지 않으면 파일 수정일을 ‘내려받은 날’로 기록한다."]),
  bullet([{ t: "정규화: ", bold: true }, "원천 열 이름(Open API 영문 코드, 정보데이터시스템 한글 열, 공공데이터포털 항목)을 표준 열로 바꾼다. ISU_CD는 값이 ISIN 모양(KR로 시작하는 12자)일 때만 ISIN으로, 아니면 단축코드로 보고, 숫자로 읽혀 빠진 앞자리 0과 앞에 붙은 ‘A’를 바로잡는다. 약명이 없으면 전체 이름에서 ‘증권상장지수투자신탁’ 꼬리를 떼어 이름으로 쓰고, 추적배수 열이 있으면 1이 아닌 배수를 파생형으로 분류한다."]),
  bullet([{ t: "KRX Open API(공식): ", bold: true }, "openapi.krx.co.kr에서 인증키를 발급받고 서비스별 이용을 신청한 뒤(비상업적 이용, 재배포 금지, 출처 표기) ETF 일별매매정보(종가·NAV·거래량)를 AUTH_KEY 헤더로 받는다. 인증키는 환경변수(KRX_OPEN_API_KEY)로만 받고(명령줄 인자는 ps·셸 기록에 남으므로 받지 않음), 앞뒤 줄바꿈은 지우며 안에 제어 문자가 있으면 키를 쓰지 않고 ‘인증키 형식 오류’로 기록한다. 오류 문구의 키 값은 가린 뒤 기록한다. 코드는 클라이언트마다 실행당 호출 상한(기본 30회)과 호출 간격(기본 1초)을 지키고 보낸 요청 수를 기록한다. 인증키별 일 호출 한도는 KRX 이용 조건이므로 코드가 강제하지 않는다. 기준일 기본값은 직전 평일(토·일만 건너뜀)이고, 휴장일·미공개로 응답이 0행이면 ‘empty’로 기록하며 기존 파일을 지우지 않는다. 종가·NAV가 비어 있는 응답(필드 이름이 바뀐 경우 등)은 ‘fail’(schema)로 기록하고 기존 시세 파일을 유지한다. 엔드포인트 경로는 활용 가이드 기준이며(키 발급 후 확인) 코드를 고치지 않고 환경변수(ETFREC_KRX_API_BASE·ETFREC_KRX_ETF_DAILY_PATH)로 바꿀 수 있다."]),
  bullet([{ t: "공공데이터포털(같은 serviceKey): ", bold: true }, "증권상품시세정보(ETF) getETFPriceInfo는 totalCount까지 페이지를 넘겨 받는다(최대 10쪽, 서버가 쪽 크기를 줄여 보내도 계속). 페이지 상한이나 빈 쪽 때문에 일부만 받으면 ‘partial’과 멈춘 이유를, 호출 오류가 나면 받은 쪽을 버리고 ‘fail’(기존 파일 유지)과 진행 상황을 기록한다. 응답 봉투(response·header·body)가 없으면 형식 오류로 보아 오류 응답을 ‘휴장일 0행’으로 오인하지 않는다. 키는 환경변수(DATA_GO_KR_KEY)로만 받고, 포털의 인코딩 키를 넣어도 이중 인코딩되지 않게 한 번 복호화한다. 엔드포인트는 환경변수(ETFREC_DATAGOKR_BASE·ETFREC_DATAGOKR_OPERATION·ETFREC_DATAGOKR_LISTED_URL)로 바꿀 수 있다. KRX상장종목정보 getItemInfo로는 선택적으로 전종목 기본정보의 단축코드·ISIN을 교차 확인하고 결과(일치·불일치 수)를 provenance에 기록만 한다(경로는 활용 가이드 기준, ETF 포함 여부 미확인)."]),
  bullet([{ t: "시세 결합과 유형 통계: ", bold: true }, "시세 스냅샷(KRX Open API·공공데이터포털 중 기준일이 최근인 것)을 단축코드로 결합해 괴리율 = (종가 − NAV)/NAV를 계산하고, 유형 카드에 괴리율 절댓값 중앙값·거래량 중앙값을 시세 기준일·결합 종목 수와 함께 보여 준다. 유형 분류(레버리지·인버스 → 인컴·커버드콜 → 자산배분 → 채권 → 원자재·통화 → 리츠·인프라 → 액티브·ESG → 국내 섹터·테마 → 해외 주식형 → 국내 시장대표 순의 키워드 규칙), 환헤지(H)·선물형·TR·연금계좌 편입 가능 플래그, 유형별 종목 수·총보수 중앙값·운용사 수 통계는 교육용이며 상품 추천이 아니다."]),
  bullet([{ t: "스냅샷과 출처 기록: ", bold: true }, "provenance.json에 파일마다 상태(ok, partial, empty, fail, skipped, kept, missing 중 하나), 자료 기준일(data_as_of), 저장 시각(synced_at), 내용 해시(sha256), 일부만 받음 표시(truncated), 호출 수를 남긴다. 파일과 기록은 같은 폴더의 임시 파일에 다 쓴 뒤 교체하고(쓰다가 실패하면 기존 파일 그대로), 파일을 바꾼 직후 기록도 저장한다(실행이 끊기면 complete: false). 이번 실행에서 다시 쓰지 않은 파일은 이전 기록을 그대로 두므로 화면 라벨은 그 파일 자체의 기준일을 보여 주고, 30일이 지나면 경고를 붙인다. 해시가 기록과 다르면 기록의 기준일을 믿지 않고 ‘기록 불일치’를 표시하며, 스냅샷을 읽지 못하면 샘플로 내려가 사유를 적는다. 스냅샷이 없으면 패키지에 든 가상 종목 45개 샘플을 ‘샘플 데이터’ 배지와 함께 쓴다. 스냅샷 폴더는 sources 명령과 서버가 같은 규칙(--out·serve --sources-dir, 없으면 ETFREC_SOURCES_DIR, 없으면 data/sources)으로 정하고, 서버는 시작할 때 한 번 읽는다. 화면·API에는 라벨·기준일·상태 같은 필요한 필드만 보내고 로컬 경로·오류 원문은 보내지 않는다. ‘sources check’는 출처 루트마다 HEAD 요청 1회만 보내고(리다이렉트는 따라가지 않음) User-Agent는 ‘etfrec/1.0 (non-commercial education project)’로 밝힌다."]),
  bullet([{ t: "이용 범위: ", bold: true }, "이 프로젝트는 비상업 수업 프로젝트다. KRX 자료(Open API·정보데이터시스템)는 비상업 이용·재배포 금지·출처 표기 조건이므로, 상업 서비스로 전환하려면 공공데이터포털의 이용허락 범위를 확인한 공공데이터 경로나 KRX와의 별도 데이터 이용 계약이 필요하다."]),
  bullet([{ t: "교육 자료: ", bold: true }, "저작권이 있는 강의·가이드북은 링크·메뉴 경로·출처 키만 단원에 연결한다. 운용사 가이드북 텍스트를 콘텐츠 특징으로 쓰는 확장은 인용·요약 범위에서만 진행하고 원문 재배포는 하지 않는다(현재 TF-IDF는 주제 이름과 단원 제목만 쓴다)."]),
  note([{ t: "현재 확인 상태. ", bold: true }, `이 개발 환경은 한국 공공·금융 도메인으로의 네트워크 접근이 차단되어 있어(2026-10-14 재확인) 실제 수집은 하지 못했다. 대신 요청 헤더·주소·응답 파싱·페이지 넘김·빈 응답·호출 상한·상태 기록·시세 결합을 가짜 응답으로 검사하는 테스트 ${TPF["tests/test_sources.py"] || 0}건(tests/test_sources.py)을 두었다. 실제 수집은 키를 발급받은 뒤 로컬 환경에서 실행해 엔드포인트 경로·필드명을 실제 응답으로 확인할 예정이다(8절 일정). 출처 표의 메뉴 이름·이용 조건과 금융투자교육원 사전교육(약 1시간, 수료 후 증권사에 이수번호 등록)은 검색으로 확인했고, 공공데이터포털 API 2건은 요청 변수·무료·JSON/XML 제공을 검색 결과에서 확인했다.`]),
  h2("4.4 모의 데이터 생성기 v2"),
  p("실제 로그가 없으므로 규칙을 공개한 생성기로 ‘가상 세계’를 만들고, 그 세계에서 기법을 비교한다. 노트북 B의 생성기(v1)는 난수 순서까지 그대로 보존해 재현성을 유지했고, v2는 다음을 더했다."),
  bullet("투자 목적은 연령·위험성향·소득분위·경험에 따른 분포에서 표본추출(연금은 40대 이상에서, 단기 매매는 적극 성향에서 확률이 높음)하고, 투자 기간은 목적에 따라 뽑는다."),
  bullet("목적-주제 친화도 행렬이 주제 선호 로짓에 더해진다(강도 0.8). 예: 연금 목적은 연금계좌 ETF·자산배분·채권 ETF 선호가 올라간다."),
  bullet("아직 이해하지 못한 선수 단원 수(최대 2)만큼 완료·퀴즈 통과 로짓이 0.8씩 낮아진다. 이 값이 선수 가드레일의 비용을 좌우하므로 6.6절에서 민감도를 본다."),
  bullet("이벤트는 시도 단위의 상태 전이로 생성된다: 완료 여부 → (완료일 때만) 퀴즈 시도 → (시도일 때만) 통과, 미완료일 때만 이탈, 저장은 관심 주제에 따라 독립. 따라서 ‘이탈이면서 완료’ 같은 모순 행은 구성상 생길 수 없고, QA 검사 event_logic_* 가 매 학습마다 이를 확인한다(아래 표의 논리 제약 행)."),
  bullet(`이벤트 열은 서로 배타적인 범주가 아니라 한 시도에 붙는 플래그다. 그래서 ‘완료 + 퀴즈 통과 + 저장 + 이탈’의 합(${num(EV.sum4)})은 시도 수(${num(DS.study_attempts)})보다 ${num(EV.excess)} 많고, 이 차이는 퀴즈 통과(${num(DS.quiz_pass)}, 이미 완료에 포함) + 저장(${num(DS.save)}, 독립 플래그) − 미완료이면서 이탈하지 않은 시도(${num(EV.ncnd)}, 네 열 어디에도 잡히지 않음)로 정확히 분해된다. 1차본 수치(108,777건, 합 134,041건, 차이 25,264건)도 24,187 + 12,825 − 11,748로 똑같이 분해된다.`),
  bullet("밀도(사용자×단원 고유 쌍의 비율)는 생성 결과로 계산한 값이며 생성기의 목표나 제약이 아니다. 생성기는 주마다 활동 학습자를 뽑고, 각자 1~8개 단원을 효용(주제 선호·관심 주제·수준 차이·인기·단원 매력도·연령×소득 집단과 성별의 단원 선호·모바일×짧은 콘텐츠·이미 본/통과한 단원; 주제·인기 가중치와 수준 차이 벌점은 연령·경험에 따라 다름) 순위로 고른다. 인구통계가 행동에 들어가는 경로가 여기에 있으므로 아래 위약 점검이 필요하다. 선수 미이수는 단원 선택에 들어가지 않고, 고른 뒤의 완료·통과 로짓만 미이수 선수 단원 1개당 0.8(최대 2개)씩 낮춘다."),
  bullet("행동 점수는 한 시도의 플래그를 max(조회 1, 완료 2, 퀴즈 통과 3, 저장 3) 하나로 줄이므로 같은 시도의 플래그가 중복 집계되지 않는다. 같은 학습자가 같은 단원을 여러 주에 걸쳐 다시 시도하면 반응 행렬에서 점수를 더한다. 반복 학습을 더 강한 신호로 보는 설계 선택이며 etfrec/features.py에 있다."),
  bullet("운영 로그(CSV)를 연결할 때는 normalize_event_flags가 같은 논리(통과 ⇒ 퀴즈 ⇒ 완료, 이탈 ⇒ 미완료)로 행을 맞추고 고친 행 수를 데이터 요약(event_repairs)에 남긴다. 로그가 이벤트 스트림(한 행 = 조회·완료·퀴즈 같은 이벤트 하나)이면 session_id 열로 같은 (학습자, 단원, 세션)의 행을 한 시도로 묶는다(events_to_attempts: 플래그 OR, 시각은 첫 이벤트, 묶은 수는 attempt_grouping에 기록, 세션 열은 버림). 묶지 않으면 조회 이벤트와 완료·통과 이벤트가 두 시도로 세어져 점수(1 + 3)와 조회 수가 부풀려진다. 화면에서 임의 학습자의 기록을 받을 때도 완료와 이탈이 함께 들어오면 이탈을 끈다(2차본에서 고친 결함). 모의 데이터는 v1·v2 모두 고친 행이 0건이다."),
  bullet(PL ? `연령·소득·성별 효과는 가정값이다. 파이프라인이 없는 효과를 만들어 내지 않는지는 연령·연소득·성별 열을 학습자 사이에서 열마다 섞은 위약 세계(학습자 ${num(PL.n_learners)}명, scripts/placebo_check.py)로 확인했다. 검증 1위는 ${PL.global_uses_demographics.length ? `인구통계(${PL.global_uses_demographics.join("·")})를 쓰는` : "인구통계를 쓰지 않는"} ‘${PL.global_algorithm}’였고(인구통계 미사용 1위와의 차이 ${ci(plPair("Global", "NoDemographics"))}), 성별·소득 세그먼트를 쓰는 라우터도 쓰지 않는 라우터보다 낫지 않았다(성별 포함 − 성별·소득 제외 ${ci(plPair("RouterFull", "RouterNoGenderIncome"))}, 성별 제외 − 성별·소득 제외 ${ci(plPair("RouterNoGender", "RouterNoGenderIncome"))}). ${PL_OK ? "즉 위약 세계에서는 인구통계의 거짓 이점이 나타나지 않았다." : "위약 세계에서도 인구통계 설정이 유의하게 나아 원인을 분석해야 한다."} 섞지 않은 원래 세계에서는 인구통계(연령대·소득분위)를 쓰는 설정이 검증 1위였고 인구통계 미사용 1위가 테스트에서 ${ci({ diff: resBy.NoDemographics.difference_vs_global, ci_low: resBy.NoDemographics.ci_low, ci_high: resBy.NoDemographics.ci_high })}였다. 1차본은 ‘--effect 0 위약 세계’로 확인한다고 썼지만 실행하지 않았고, 그 세계는 위약도 아니다(연령·소득이 목적·경험·성향·기기를 거쳐 행동에 남는다).` : "연령·소득·성별 효과는 가정값이다(위약 점검 결과 없음)."),
  ...table(["항목", "값"], [
    ["학습자 · 단원 · 주차", `${num(DS.users)}명 · ${DS.items}개 · ${DS.weeks}주(검증: 0~1주로 학습해 2주차에서 평가·선택, 테스트: 0~2주로 다시 학습해 3주차에서 보고)`],
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
  p("가명 번호만으로는 충분하지 않다는 전제로 설계한다(2차본 보강). 연령대·소득분위·성별·경험·성향·투자 목적·기간·기기가 결합되면 외부 자료와 교차해 재식별될 수 있으므로(모자이크 효과), 2차본은 (1) 저장 자체를 줄이고 (2) 밖으로 나가는 학습자 단위 표만 k-익명화하며 (3) 매 학습마다 감사 결과와 검사를 기록한다. 코드로 강제되는 항목과 코드가 강제하지 않는 조직 정책을 나눠 manifest.json의 privacy.policy에 함께 기록한다(etfrec/privacy.py). 제도 근거: 개인정보보호법 과징금 상한은 전체 매출액의 3%(2023년 9월 시행)이고 2026년 3월 개정으로 반복·중대 위반에는 최대 10% 특례가 도입되었으며(9월 시행), 가명정보 처리 가이드라인은 2026년 3월 31일 위험도 기반 체계로 전면 개정되었다."),
  ...table(["점검 항목", "현재 번들(모의 데이터 v2, 측정값)", "처리·기준"], [
    ["저장물", `번들 프로필 열: ${(D.bundle_profile_columns || []).join(", ")} / 번들 로그 열(허용 목록): ${(D.bundle_log_columns || []).join(", ")}(일·분 없음) / learner_profiles.csv: 연령대·소득분위 이름`, "원시 연령·연소득은 학습 중 메모리에서 소득 분위 경계 계산에만 쓰고 저장하지 않음. 학습 스키마 밖 열(외부 회원 ID·분 단위 시각·IP 등)은 읽을 때 버리고 번들 로그에는 허용 열만 남김(QA가 확인). 모델은 원래 구간 코드만 쓰므로 결과 동일(v1 14개 값 5자리 일치 재확인)"],
    [`저장 준식별자 ${PS.quasi_identifiers.length}개 조합(k=${PS.k})`, `${num(PQS.groups)}개 셀 중 k 미만 ${num(PQS.groups_below_k)}개 셀(${num(PQS.users_below_k)}명, ${pct(PQS.share_below_k)})`, `학습자 단위 표는 export-deid를 거친 것만 반출. 열 제거만으로 충족하려면 ${PS.generalization.join(" → ")} 순서로 열을 빼야 함(감사 기록)`],
    ["export-deid 반출 표", PR_ ? `일반화 ${PR_.generalized.length}단계(${PR_.generalized.map(c => HIER_KO[c] || c).join("·")}) → 국소 억제 ${num(PR_.suppressed_rows)}행 → 삭제 ${num(PR_.removed_rows)}행, ${num(PR_.rows_out)}/${num(PR_.rows_in)}행, 최소 셀 ${PR_.final_min_group}명` : "–", "모든 셀 ≥ 5를 다시 검증한 뒤에만 파일을 씀. 행은 반출 값으로 정렬해 원래 학습자 순서(가명 번호)를 지움. 가명 번호·관심 주제·진단 수준은 내보내지 않음"],
    ["운영 라우터 잎 크기", LF ? `잎 ${LF.leaves}개 중 ${LF.threshold}명 미만 ${LF.leaves_below}개(${num(LF.users_in_small_leaves)}명), 최소 ${LF.min_leaf}명. ${RCH.RouterNoGender && RCH.RouterNoGender.lam >= 1e8 ? `λ=∞라 모든 잎이 전역 1위 설정을 씀(잎 챔피언 ${RCH.RouterNoGender.distinct_leaf_champions}종)` : `챔피언을 정한 노드의 최소 표본 ${LF.decision_min_n}명`}` : "–", `잎 크기는 보장되지 않음(1차본의 ‘잎 최소 20명’ 서술 정정): ${LF ? LF.min_users_param : 20}명 미만 노드는 상위 노드 추정을 그대로 씀. 추천 경로 출력은 노드 크기를 구간(‘20명 미만’·‘20~49명’ 등)으로만 보이고 원시 평균을 내보내지 않음(부모−형제 차분으로 숨긴 노드를 복원하지 못하게)`],
    ["공개 집단표(group_results·advanced_exposure)", PG ? `5명 미만 집단 ${PG.rows_removed}행 제외, 활성 5명 미만 ${PG.active_masked}행은 활성 기준 값 비움(보완 억제 ${(PG.complementary_removed || 0) + (PG.complementary_masked || 0)}건), 최소 셀 ${PG.min_users}명` : "–", "한 변수에서 하나만 숨기면 가장 작은 집단을 하나 더 숨김(보완 억제: 함께 공개되는 합계와의 차분으로 복원되지 않게). QA published_group_cells_ge_5"],
    ["서빙 학습자 표(/api/learners, learner_profiles.csv)", UTX ? `준식별자 8개 + 학습 시간대 + 관심 주제 조합: ${num(UTX.groups)}개 셀 중 k 미만 ${num(UTX.groups_below_k)}개(${num(UTX.users_below_k)}명, ${pct(UTX.share_below_k)})` : "–", "학습자 단위 표라 k-익명 표가 아님. 학습자 조회 API와 추천·비교·로드맵·유형 API의 learner_id(기준 학습자 번호) 입력은 로컬 실행에서만 기본으로 켜고 다른 주소로 열면 --expose-learners가 있어야 켬(꺼져 있으면 403). 서빙 API로 고를 수 있는 기법은 화면의 기법 목록뿐(임의 설정 번호는 개발 모드)"],
    ["개인정보 QA", `${PQ.filter(q => q.passed).length}/${PQ.length}건 통과: ${PQ.map(q => q.test).join(", ")}`, "번들 조립 직후·저장 전에 실행. 하나라도 실패하면 학습을 멈추고 번들을 저장하지 않음"],
  ], [3, 5, 4.5], { caption: "개인정보 점검(etfrec/privacy.py, manifest.privacy)", size: 16, zebra: true }),
  ...table(["코드로 강제되는 항목", "강제·확인하는 코드와 검사"], (PS.policy_implemented || []).map(x => [x.item, x.enforced_by.join(", ")]),
    [8.5, 4], { caption: "개인정보 정책 중 코드로 강제되는 항목(manifest privacy.policy.implemented)", size: 15, zebra: true }),
  bullet([{ t: "조직 정책(코드가 강제하지 않음): ", bold: true }, (PS.policy_organizational || []).join(" / ") + ". 실제 로그를 연결하기 전에 이 항목들을 운영 절차로 문서화하고 법률 검토를 받는다."]),
  bullet("현재는 모의 데이터라 실제 개인정보를 처리하지 않는다. 실제 서비스에서 추천을 제공하는 처리는 이용자 동의나 서비스 계약 이행을 근거로 하고, 개인정보보호법의 가명정보 특례(통계 작성·과학적 연구·공익적 기록 보존 목적이면 동의 없이 처리 가능)는 모델 개선 연구나 다른 자료와의 결합처럼 수집 목적 밖의 재이용에만 쓴다. 어느 근거로 처리하는지는 실제 로그를 연결하기 전 법률 검토에서 정한다."),
  bullet("모델 학습 입력은 일반화하지 않는다(그러면 학습 결과가 바뀐다). 학습은 접근 통제된 환경에서 가명 데이터로 하고, 학습 환경 밖으로 나가는 학습자 단위 표는 export-deid를 거친다. 가명처리 결과(학습 입력)에는 소득 분위 경계 계산을 위해 원시 연령·연소득이 남는다. learner_profiles.csv와 학습자 조회 API는 내부 서빙용이며 k-익명 표가 아니다. 서빙 API에는 인증이 없으므로 학습 환경 밖에 열지 않는다(조직 정책). 저장 설계는 서버가 만든 추천·로드맵 결과(학습자 프로필·통과 단원·학습 카드)를 저장하지 않고, 설계 이름과 모든 문자열의 연령·출생 연도·소득 표현은 구간 이름으로, 키워드 없이 ‘원’을 붙여 쓴 금액은 중립 표기 [금액]으로 가린다. 학습자 조회를 켠 서버에서 저장한 설계는 꺼진 서버가 내려보내지 않고, 같은 이름으로 덮어쓰거나 지우지도 못한다. 이름·주소 같은 그 밖의 표현은 가리지 못한다."),
  bullet("교육 자료는 링크와 출처만 저장하고 본문을 복제하지 않는다. 운용사 자료는 인용·요약 범위에서만 쓴다. KRX 자료는 비상업 수업 범위에서 공식 API와 이용자가 내려받은 파일만 쓴다(4.3절)."),
  bullet("모든 화면과 추천을 담은 API 응답(추천·첫 방문 추천·비교·로드맵·유형)에 ‘특정 ETF의 매수·매도를 권유하지 않는다’는 고지를 넣고, ETF 유형이 들어가는 로드맵·유형 응답과 유형 화면에는 ‘유형 안내는 학습 순서를 돕기 위한 분류이지 개별 상품의 적합성 판단이 아니다’라는 문구를 더했으며(테스트로 확인), 단원 제목에 금칙어(수익 보장·추천 종목 등)가 없는지 검사한다."),
);
const CI = D.catalog.items, ciA = CI[0], ciB = CI.find(i => i.title.includes("총보수")) || CI[3], ciC = CI[1];
add(h2("4.6 데이터 항목 예시와 사용자 반응의 해석"),
  p("4.1절의 데이터 항목을 실제 입력 형식의 예로 보이고, 확보 방법과 각 사용자 반응을 어떻게 해석해 쓰는지 정리했다. 아래 값은 형식을 보이기 위한 예시이며 학습자 번호는 가명 번호다."),
  ...table(["파일", "예시 행", "설명"], [
    ["profiles.csv", "user=0, gender=1, age=45, income=5200, exp=0, risk=0, mobile=1, interest1=연금계좌 ETF, interest2=자산배분, placement=1, goal=pension, horizon=long", "온보딩·진단에서 받는 학습자 정보. 원시 연령·연소득(만원)은 학습 입력에만 있고 번들에는 연령대·소득분위 구간으로만 저장한다(4.5절)"],
    ["study_log.csv", `user=0, item=${ciA.item}(${ciA.title}), week=0, hour=20, complete=1, quiz=1, quiz_pass=1, save=0, drop=0, replay=0`, "한 행이 한 번의 학습 시도다. 이 행의 행동 점수는 3(퀴즈 통과)"],
    ["study_log.csv", `user=0, item=${ciB.item}(${ciB.title}), week=0, hour=21, complete=1, quiz=0, quiz_pass=0, save=1, drop=0, replay=0`, "완료하고 저장했다. 행동 점수 3(저장)"],
    ["study_log.csv", `user=0, item=${ciC.item}(${ciC.title}), week=1, hour=8, complete=0, quiz=0, quiz_pass=0, save=0, drop=1, replay=0`, "보다가 이탈했다. 행동 점수 1(조회), 이탈은 사용자 이탈률에 반영"],
    ["catalog.csv", `item=${ciC.item}, title=${ciC.title}, topic=${ciC.topic}, level=${ciC.level}, short=${ciC.short ? 1 : 0}, prereqs=${ciC.prereqs.join(";")}, sources=${ciC.sources.join(";")}`, "단원 정보와 선수 단원, 출처 등록부의 출처 키"],
  ], [1.6, 6.4, 4.5], { caption: "데이터 항목 예시(입력 형식)", size: 15, zebra: true }),
  ...table(["데이터", "확보 방법", "시점·상태"], [
    ["학습자 프로필·투자 목적·진단 결과", "서비스 온보딩 화면(자연어 입력 또는 입력란)과 진단 퀴즈 20문항. 원시 연령·연소득은 구간 코드로만 저장한다", "현재 모의 데이터 v2. 11월 3주 파일럿에서 실제 수집"],
    ["학습 로그(조회·완료·퀴즈·저장·이탈)", "서비스 이벤트 로그 → 가명처리 도구(pseudonymize: 외부 회원 ID를 HMAC 가명과 연속 번호로) → 이벤트 스트림이면 session_id로 시도 단위로 묶기 → 학습 입력", "11월 3주 파일럿(수업 참여자 또는 모의 사용자 테스트)"],
    ["교육 콘텐츠 카탈로그", "전국투자자교육협의회 ETF 스쿨·금융투자교육원 사전교육·운용사 가이드북의 링크와 출처(본문은 복제하지 않음), 세제·규제 단원은 직접 쓴 학습 요점", `출처 등록부 ${D.sources.length}건(4.2절), 11월 2주 링크 검수`],
    ["ETF 종목·시세", "KRX 정보데이터시스템에서 이용자가 내려받은 파일 정규화, KRX Open API(인증키), 공공데이터포털 API(서비스키)", "11월 1주 키 발급 뒤 실제 수집(4.3절). 비상업 수업 범위"],
  ], [3, 6, 3.5], { caption: "데이터 확보 방법 요약", size: 15, zebra: true }),
  ...table(["사용자 반응(로그 열)", "의미(해석)", "모델에서 쓰는 방법"], [
    ["조회(시도 행이 있음)", "관심을 보였지만 이해했는지는 모른다(가장 약한 신호)", "행동 점수 1, 반응 행렬과 CF의 입력"],
    ["완료(complete)", "단원을 끝까지 학습했다", "행동 점수 2, 사용자 완료율 특징"],
    ["퀴즈 시도(quiz)", "이해를 확인하려 했다", "퀴즈 통과율의 분모"],
    ["퀴즈 통과(quiz_pass)", "개념을 이해했다(가장 강한 신호이자 객관적인 신호)", "행동 점수 3. 이해 레이블이라 통과 단원은 후보에서 빼고 수준 추정에 반영한다. 오프라인 정답(다음 주 통과)도 이 열이다"],
    ["저장(save)", "나중에 다시 볼 만큼 관심이 크다(이해와는 별개)", "행동 점수 3"],
    ["이탈(drop)", "끝까지 보지 않고 떠났다. 난이도나 흥미가 맞지 않았을 수 있다", "행동 점수에는 넣지 않고 사용자 이탈률 특징으로만 쓴다. 이탈과 완료가 함께 들어오면 이탈을 끈다"],
    ["재시청(replay)", "복습이다. 이해 부족일 수도, 반복 학습일 수도 있어 뜻이 갈린다", "기록·요약만 하고 현재 점수에는 쓰지 않는다"],
    ["진단 퀴즈 통과", "학습하기 전에 이미 아는 개념이다", "통과 단원으로만 반영해 후보에서 빼고, 수준 갱신에는 쓰지 않는다(진단 수준 판정을 따름)"],
    ["같은 단원의 반복 시도", "여러 주에 걸쳐 다시 학습했다", "주차별 점수를 더해 더 강한 신호로 본다"],
  ], [2.6, 4.6, 5.3], { caption: "사용자 반응의 의미와 사용 방법", size: 15, zebra: true }),
  p("별점·좋아요 같은 명시적 평점은 수집하지도 쓰지도 않는다. 교육 콘텐츠의 평점은 재미·편의 같은 만족도를 반영해 학습 목표(이해)와 어긋날 수 있고, 남기는 사용자가 적어 희소하며, 쉬운 단원에 높은 점수가 몰리는 편향이 생기기 쉽다. 그래서 객관적인 이해 신호인 퀴즈 통과를 정답과 가장 강한 반응으로 쓰고, 조회·완료·저장은 강도가 다른 암묵 반응으로 쓴다(행동 점수 = 조회 1, 완료 2, 퀴즈 통과·저장 3 중 최댓값)."),
);

// 5. 시스템 설계
add(pageBreak(), h1("5. 시스템 설계와 구현 현황"),
  h2("5.1 아키텍처"),
  ...img("fig1_architecture.png", "시스템 아키텍처: 데이터 계층 → 학습·선택 → 교육 설계 모듈 → 서빙"),
  p(`데이터 계층의 네 가지 입력은 특징 저장소에서 반응 행렬·추정 수준·선호·세그먼트 코드·목적으로 바뀌고, ${M.signal_count}개 신호와 ${num(M.configurations)}개 설정이 검증 주차에서 평가된 뒤 세그먼트 라우터로 잠긴다. 교육 설계 모듈(진단 퀴즈·로드맵 엔진·가드레일·유형 분류)은 학습 단계에는 신호와 후보 제한으로, 서빙 단계에는 로드맵·유형 카드 응답으로 들어간다. 서빙은 미리 학습된 번들만 읽으므로 요청 중 재학습이 없고 응답은 수십 ms다.`),
  h2("5.2 로드맵 엔진"),
  ...img("fig2_roadmap_flow.png", "로드맵 다섯 단계와 연금·노후 대비 목적의 예시 단원"),
  p(`로드맵은 다섯 단계로 구성된다. ① 진단: ${D.questions.length}문항 퀴즈 또는 학습 기록으로 수준(1~3)과 이미 아는 단원을 정한다. ② 필수 기초 개념: 모든 목적에 공통인 ETF 구조·총보수·NAV와 괴리율·유동성·환헤지·레버리지 일일 복리(선수 관계 닫힘까지 포함). ③ 목적별 핵심 개념: 목적 템플릿의 단원과 그 선수 단원. ④ 심화·리스크: 목적별 심화 단원에 투자 기간(단기 → 유동성 2, 장기 → 리밸런싱 2)과 위험성향(안정이면 레버리지 심화 제외)을 반영하고, 투자 기간이 1년 미만이면 ISA(절세 계좌) 단원에 ‘의무가입 3년’ 주의를 붙인다. ⑤ ETF 유형 연결: 목적 템플릿에 연결된 유형 카드로, 각 유형의 필요 개념 단원을 모두 통과해야 열린다(안정 성향이면 위험 5 유형은 권장 목록에서 빠지고 ‘학습용(권장 아님)’으로만 보인다). 유형 카드의 ‘적합 목적’도 같은 템플릿에서 계산한다. 각 단계의 단원은 선수 단원이 먼저 오도록 위상정렬되고 상태(통과·학습 가능·잠김)와 남은 학습 시간을 갖는다. 세제·규제 단원(ISA 3단원, 과표기준가, IRP 70% 한도, 레버리지 거래 요건)에는 기준일을 단 학습 요점·계산 예시가 붙어 로드맵 화면에서 펼쳐 볼 수 있다(부록 F).`),
  ...img("fig3_prereq_graph.png", `연금·노후 대비 로드맵 ${D.roadmaps.pension.units_total}개 단원의 선수 관계(숫자는 단원 번호)`),
  ...table(["투자 목적", "목적별 핵심 개념(템플릿)", "심화·리스크", "연결 유형", "단원 수 · 시간"], Object.entries(D.templates).map(([g, t]) => [
    GOAL_KO[g], t.core.map(x => `${x[0]} ${x[1]}`).join(", "), t.advanced.map(x => `${x[0]} ${x[1]}`).join(", "), D.roadmaps[g].types.join(", "),
    `${D.roadmaps[g].units_total}개 · 약 ${D.roadmaps[g].minutes_total}분`]), [1.8, 4.2, 3, 2.6, 1.6], { caption: "투자 목적별 로드맵 템플릿(주제 뒤 숫자는 수준)", size: 16, zebra: true }),
  p("로드맵은 추천 엔진에 두 방향으로 들어간다. 첫째, 로드맵 단계 우선순위 신호(현재 단계의 학습 가능 단원 1.0, 이후 단계의 학습 가능 단원 0.7, 선수 미이수 0.4, 로드맵 밖 0)와 투자 목적 일치 신호가 규칙·하이브리드 설정 풀에 추가되어 검증에서 비중이 결정된다. 둘째, 선수 단원 가드레일(prereq_block)은 선수 단원을 통과하지 않은 단원을 후보에서 제외한다. 가드레일은 수업의 교육 처방이 아니라 이 프로젝트의 정책이므로 화면에서 켜고 끌 수 있고, 오프라인 평가에는 ‘운영 라우터 + 선수 가드레일’ 행으로 효과를 따로 기록했다."),
  h2("5.3 진단 퀴즈"),
  p(`${D.questions.length}문항(수준 1 ${QL(1)}개·수준 2 ${QL(2)}개·수준 3 ${QL(3)}개, ${QUNITS}개 단원; 2차본에서 ISA·과표기준가·IRP 70% 한도·기본예탁금 문항 추가)으로 구성했고 각 문항은 카탈로그 단원 하나에 대응한다(부록 B). 해외 ETF 3과 연금계좌 ETF 2에는 문항이 둘씩 있어, 두 문항을 모두 답하고 맞혀야 그 단원을 ‘진단 통과’로 기록하고(하나만 답하면 판정 보류) 이벤트는 단원마다 한 번만 만든다. 레버리지 거래 요건 문항(q20)은 규제 상식이라 변동성 위험 단원 전체를 검사하지 못하므로 수준 판정에만 쓰고 단원을 통과 처리하지 않는다. 정답 위치는 보기 네 자리에 다섯 개씩 나눴다(1차본은 16문항 중 13문항이 두 번째 보기였다). 정답률은 답한 문항으로 계산하되, 수준마다 최소 응답 수를 둔다(몇 문항만 골라 답해 높은 수준이 나오지 않게). 수준1 문항 5개·수준2 문항 3개 이상을 답하고 수준 1 정답률 60% 이상, 수준 2 정답률 50% 이상이면 수준 2, 여기에 수준3 문항 3개 이상을 답하고 수준 2 정답률 75% 이상, 서로 다른 주제의 수준 3 문항 2개 이상 정답, 수준 3 정답률 60% 이상이면 수준 3이다. 최소 응답 수를 못 채운 수준은 판정을 보류하고 그 아래 수준에서 시작한다. ‘진단 통과’ 이벤트는 통과 단원 표시에만 쓰고 수준 갱신 규칙(자기 수준보다 높은 단원의 퀴즈 통과 → +1)에는 넣지 않는다. 수준은 이미 퀴즈 판정에 반영되어 있어, 넣으면 보류한 수준이 다시 올라가기 때문이다. 틀린 문항은 기록하지 않고(진단은 배치이지 실패 기록이 아니다) 정답과 해설을 보여 준다.`),
  h2("5.4 ETF 유형 분류"),
  ...table(["유형", "위험", "필요 개념(통과해야 카드가 열림)", "적합 목적", "세금·연금계좌·규제 요약"], D.types.map(t => [
    [{ t: t.name, bold: true }], "●".repeat(t.risk) + "○".repeat(5 - t.risk), t.concepts.map(c => `${c[0]} ${c[1]}`).join(", "), t.goals.map(g => GOAL_KO[g]).join(", "),
    [t.tax, { t: " / " + t.pension, color: GREY }, ...(t.regulation ? [{ t: " / " + t.regulation, color: GOLD }] : [])]]),
    [2, 1, 3.4, 2.2, 4.4], { caption: "ETF 유형 10종과 연결 조건", size: 16, zebra: true }),
  h2("5.5 신호·설정 풀·검증·라우터"),
  ...table(["단계", "내용"], [
    ["특징 저장소", "기준 주 이전 로그로 사용자×단원 반응 행렬(시도마다 조회 1·완료 2·통과/저장 3의 최댓값, 같은 단원의 반복 시도는 합산), 통과 단원, 추정 수준, 주제 선호, 세그먼트 코드(학습활동·선호군집·연령대·소득분위·성별), 투자 목적·기간"],
    [`신호 ${M.signal_count}개`, "인기 1, 세그먼트 인기 93(변수 조합 31 × λ 3), 개인화 인기 1, 콘텐츠 코사인 6, 사용자 CF 27(k 3 × 인구통계 혼합 9), 아이템 CF 8, 표본 MF 6, BPR MF 6(2차본), 관측 MF 1, MLP 1, MLP 쌍별 2종·목표 정렬 MLP 1(2차본), 규칙 가산점 8(관심 주제·수준 일치·연령 생애주기·소득 구간·위험성향·모바일·투자 목적·로드맵 단계), 맥락 신호 2"],
    [`설정 풀 ${num(M.configurations)}개`, Object.entries(M.family_counts).map(([k, v]) => `${k} ${v}`).join(" · ") + " (혼합 비중·세그먼트 변수·λ 격자의 조합, CF 신뢰도 게이트 n/(n+10))"],
    ["검증·선택", "검증 주차(2주) NDCG@5로 전역 1위와 기법군별 1위를 고르고, 세그먼트 라우터는 계층(학습활동→선호군집→연령대→소득분위[→성별])에서 λ ∈ {0, 20, 100, 500, 3000, ∞} 교차 선택(반복 2회, 표본 20명 미만 노드는 상위 노드 추정을 그대로 씀 — 잎 크기를 보장하지는 않음). 선택 후 잠금."],
    ["테스트·QA", `테스트 주차(3주)에서 사용자 평균 NDCG@5·Hit@5·Diversity@5·선수 미이수 비율·짧은 목록 비율, 사용자 단위 쌍 부트스트랩 500회로 전역 1위 대비 차이의 95% 구간. 학습 QA ${M.qa}건 모두 통과: 가드레일·중복 ${QC["가드레일·중복"] || 0}, 지표 함수 일치 ${QC["지표 함수 일치"] || 0}, 신경망 학습 확인 ${QC["신경망 학습 확인"] || 0}(쌍별 모델은 쌍 사용자만 학습했는지 포함), 활성 지표 항등식·순위 ${QC["활성 지표 항등식·순위"] || 0}, 이벤트 논리 ${QC["이벤트 논리"] || 0}, Top-K 형식 ${QC["Top-K 형식"] || 0}, 누수 검사 ${QC["누수 검사"] || 0}(기준 주 이후 행의 모든 열을 섞고 행을 더한 로그와 이후 행을 지운 로그로 만든 특징 저장소가 모든 필드에서 같음), 개인정보 ${QC["개인정보"] || 0}, 기타 데이터·선택 검사 ${QC["기타 데이터·선택 검사"] || 0}. 오프라인/온라인 Top-5 일치는 자동화 테스트(test_offline_online_parity)로, 재현성은 같은 seed로 다시 학습해 결과 파일을 비교하는 방식(v1 회귀 스크립트)으로 확인한다.`],
    ["번들", "bundle.pkl(설정·신호 메타·모델 가중치·특징 저장소·일반화 프로필·축약 로그 — 원시 연령·연소득, 일·분 없음), manifest.json(선택 기록·학습 감사·QA·개인정보 감사), 결과 CSV(테스트·검증·집단별·노출, 5명 미만 집단 제외)"],
  ], [2.2, 10.3], { caption: "학습 파이프라인 요약", zebra: true }),
  h2("5.6 서빙: REST API와 학습 설계 스튜디오"),
  p("FastAPI 서버는 번들을 읽어 다음 엔드포인트를 제공한다(부록 A). 웹 UI ‘학습 설계 스튜디오’는 외부 라이브러리 없이 11단계 마법사로 구성했고, 모든 계산을 API에 맡긴다."),
  ...table(["단계", "화면", "하는 일"], [
    ["1", "아이디어 스케치", "예시 문장 9개 또는 자연어로 학습자를 설명 → 규칙 파서가 목적·기간·관심 주제·수준·경험·성향·기기·시간대·연령·소득·학습 이력을 읽고 근거 표현을 표시. 기존 학습자(모의 15,000명) 검색·불러오기(연령대·소득분위만 표시, 새 학습자로 복사하면 구간 대표값을 채우고 원값이 아님을 표시)"],
    ["2", "기본 정보·목적", "투자 목적·기간·위험성향(로드맵 구성 변수)과 인구통계 입력, 목적에 따라 연결될 유형 안내"],
    ["3", "진단", `관심 주제 2개, 수준 직접 선택 또는 ${D.questions.length}문항 진단 퀴즈 채점·적용`],
    ["4", "학습 기록", "단원별 이벤트 추가·CSV 불러오기, 진단 통과 기록 구분 표시"],
    ["5", "학습 로드맵", "단계 흐름(진행률·남은 시간·현재 단계), 단원 상태·선수 미이수·출처 링크·학습 요점, 다음 단원, 유형별 개념 통과 수"],
    ["6", "추천 설정", "k, 설정 강제(기법군별 검증 1위), 선수 단원 차단, 두 단계 위 차단, 한 단계 위 상한, 통과 제외, 주제 상한"],
    ["7", "추천 미리보기", "주제×수준 배치도(추천·통과·후보·차단), 추천 목록(점수·근거·기여도·선수 미이수·현재 단계·출처), 가드레일 검사, 세그먼트 경로, 계산식"],
    ["8", "시뮬레이션", "통과 가정·세그먼트 what-if·수준 강제 → 추천과 로드맵 진행률 변화, 성별 뒤집기 불변 검사"],
    ["9", "ETF 유형 연결·데이터 출처", "유형 카드(권장·열림 여부, 필요 개념 통과, 세금·연금·규제·주의, 유형 통계와 샘플/스냅샷 배지), 출처 등록부와 유형 통계표"],
    ["10", "비교·평가", "같은 후보·가드레일로 기법별 Top-K 비교, 번들의 오프라인 평가(방법별·집단별·노출·검증 상위 설정)"],
    ["11", "저장·내보내기", "설계 저장·불러오기(추천·로드맵 결과는 저장하지 않고, 연령·연소득 원값은 구간 코드로, 문장의 연령·소득·금액 표현은 구간 이름이나 [금액]으로 가려 저장), JSON/CSV 내보내기, 로드맵 JSON"],
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
    [`진단 퀴즈 ${D.questions.length}문항·채점`, "완료", `단원 단위 채점·정답 위치 균형. 문항 확장(진단 단원 ${QUNITS}개 × 단원당 2문항 = ${2 * QUNITS}문항)과 전문가 검수는 11월 2주`],
    ["세제·규제 단원 학습 요점(2차본)", "완료(6단원)", "ISA 3단원·과표기준가·IRP 70% 한도·레버리지 거래 요건. 나머지 단원은 교육 자료 링크, 본문 확장은 11월"],
    ["ETF 유형 10종 분류 규칙·카드", "완료", "KRX 열 매핑 테스트, 세금·연금·규제 문구는 최신 제도 확인 필요"],
    ["공개 데이터 커넥터·출처 등록부·스냅샷", "완료(코드) / 수집 미실행", `가짜 응답 테스트 ${TPF["tests/test_sources.py"] || 0}건. 개발 환경의 네트워크 제한으로 실제 수집은 키 발급 후 로컬에서 실행 예정`],
    ["개인정보(저장 최소화·가명처리·k-익명 반출·감사)", "완료(코드) / 조직 정책은 운영 전", `개인정보 QA ${PQ.length}건, 테스트 ${TPF["tests/test_privacy.py"] || 0}건. 권한 분리·반출 심사 같은 조직 정책은 코드가 강제하지 않음`],
    ["학습 파이프라인·신호·설정 풀·라우터·평가", "완료", `v1 노트북과 5자리 일치, v2 ${num(M.configurations)}개 설정, QA ${M.qa_passed}/${M.qa}`],
    ["REST API · 11단계 UI · 자연어 파서", "완료", `Playwright 점검 스크립트로 ${SCREENS}장 화면 자동 생성, 모바일 폭 가로 스크롤 없음`],
    ["테스트", "완료", `pytest ${TESTS}건(지표 일치·가드레일·로드맵·퀴즈·도메인 규칙·KRX 분류·수집 정책·개인정보·파서·파이프라인·API·오프라인/온라인 일치, 전체 재현 1건은 옵션)`],
    ["실제 로그·교육 자료 연동, 사용자 평가", "예정", "8절 일정"],
  ], [4, 2.2, 6.3], { caption: "구현 현황", zebra: true }),
);

// 6. 결과
add(pageBreak(), h1("6. 실험 결과"),
  h2("6.1 실험 설정"),
  p(`검증 단계에서는 0~1주 로그로 특징과 모델을 만들어 2주차에서 설정을 선택·잠그고, 테스트 단계에서는 잠근 설정을 0~2주 로그로 다시 만든 특징과 모델로 3주차에서 보고한다(기준 주 이후의 로그는 어느 단계에서도 입력에 쓰지 않는다. 특징 저장소는 QA 누수 검사로 확인하고, 모델 학습 행과 목표 정렬 쌍은 기준 주 이전 로그만 넘기는 호출 구조로 보장한다). 정답은 다음 주에 관측된 퀴즈 통과 단원, 후보는 아직 통과하지 않은 단원 중 수준 가드레일(두 단계 위 차단)을 통과한 단원이며, Top-5를 고를 때 한 단계 위 단원은 최대 1개로 제한한다(목록 후처리). 지표는 사용자 평균 NDCG@5(주 지표), Hit@5, Diversity@5(Top-5 안의 단원 쌍 중 주제가 다른 쌍의 비율, 단원이 2개 미만이면 0), 선수 미이수 비율(Top-5 중 선수 단원을 통과하지 않은 단원 비율), 짧은 목록 비율(추천 목록이 5개 미만인 사용자 비율)이다. 차이의 95% 구간은 사용자 단위 쌍 부트스트랩 500회다.`),
  p(`다음 주 정답이 없는 사용자(테스트 ${num(M.test.zero_observed_target)}명)는 IDCG가 0이라 NDCG가 수학적으로 정의되지 않는다. 처리 방식은 두 가지다. 전체 기준(노트북 규칙)은 이들을 0점으로 평균에 넣고, 활성 기준은 정답이 1개 이상인 사용자만 평균한다. 널리 쓰이는 구현도 갈린다. scikit-learn의 ndcg_score와 TorchMetrics의 RetrievalNormalizedDCG(기본 설정)는 정답이 없는 질의를 0으로 넣고, 평가 데이터를 만들 때 테스트 정답이 없는 사용자를 아예 빼는 연구도 많다. 그래서 2차본부터 두 값을 함께 보고한다. 활성 사용자는 ‘후보 안의 다음 주 통과 단원’이 1개 이상인 ${num(nActive)}명이다. 다음 주 통과 기록 자체가 있는 사용자는 ${num(M.test.raw_positive_users || nActive)}명이지만, 그중 ${num((M.test.raw_positive_users || nActive) - nActive)}명은 통과 단원이 모두 후보 밖(이미 통과했거나 수준 가드레일에 걸린 단원)이라 어떤 방법도 맞힐 수 없어 활성에서 뺐다.`),
  p(`정답 없는 사용자는 모든 방법에서 0점이므로 활성 기준 × ${num(nActive)} = 전체 기준 × ${jo(num(nAll), "이/가")} 모든 방법에 똑같이 성립한다(QA 검사 ndcg_active_identity). 따라서 방법 간 순위는 어느 기준이든 같고(QA 검사 active_rank_preserved), 전체 기준의 절대 차이는 활성 기준의 ${fmt(ratioAct, 3)}배로 줄어든다. 유의성 판정(구간이 0을 포함하는지)은 항등식으로 보장되지는 않지만 이번 실행에서는 모든 방법에서 같았다. 반면 집단 비교는 집단마다 활성 비율이 달라 결론이 바뀔 수 있다(6.5절). 1차본은 전체 기준만 보고하고 그것을 ‘보수적 추정’이라고만 적었는데, 집단 비교에서는 보수적인 것이 아니라 활동량과 섞인 값이었다.`),
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
  p(`검증 1위(#${M.selection.operational_algorithm})는 ‘${D.operational_name}’다. ${opHas("로드맵") || opHas("투자 목적") ? `2차본에서 추가한 ${[opHas("투자 목적") ? "투자 목적 일치" : null, opHas("로드맵") ? "로드맵 단계 우선순위" : null].filter(Boolean).join("·")} 신호가 선택되었다. ` : ""}${valSentence(tabNo + 3)} 하이브리드(CF 혼합)는 밀도 ${pct(DS.density, 0)}의 희소한 세계에서 규칙을 넘지 못했고, ${LAM_OP >= 1e8 ? `운영 라우터는 λ=∞(전역 1위로 완전 수축)를 골라 모든 세그먼트에 전역 1위 설정을 배정했으므로 테스트 결과가 전역 1위와 같다(6.4절)` : `운영 라우터는 전역 1위와 유의한 차이가 없었다(차이 ${fmt(resBy.RouterNoGender.difference_vs_global)}, 구간 [${fmt(resBy.RouterNoGender.ci_low)}, ${fmt(resBy.RouterNoGender.ci_high)}])`}.${resBy.ABControl ? ` ‘세그먼트 인기(A/B 대조군 A)’ 행은 7.3절 온라인 실험의 대조군(성별을 쓰지 않는 세그먼트 인기 설정 중 검증 1위${D.ab_control_name ? `, ‘${D.ab_control_name}’` : ""})을 같은 주차에서 잰 평가 전용 행이며, 화면의 기법 선택에는 넣지 않았다(작은 세그먼트 설정을 API로 고르지 못하게 한 개인정보 원칙, 4.5절).` : ""}`),
  h3("손실 함수와 학습 목표의 비교(2차본 추가 실험)"),
  p(`중간 점검에서 ‘BCE 손실 때문에 딥러닝 결과가 무효이며 BPR로 다시 학습해야 한다’는 지적을 받아, 같은 후보·정답·후처리로 네 가지 변형을 추가했다. 아래 표는 같은 테스트 사용자에 대한 사용자 단위 쌍 부트스트랩 차이(95% 구간)다. 각 행은 손실 형태·음성 정의·레이블 중 하나를 바꾼 짝이지만 학습 범위가 다르다. 점별 MLP는 관측 행이 있는 모든 사용자를 학습하고, 쌍별·목표 정렬 MLP는 쌍에 나온 사용자(학습 주에 통과가 있는 사용자)만 학습하며 나머지에게는 콘텐츠 유사도 대체 점수를 준다. 그래서 전체 사용자 차이와 함께 ‘모든 신경망이 학습한 사용자’(v1 ${NNG1 ? num(NNG1.common) : "–"}명, v2 ${NNG ? num(NNG.common) : "–"}명)로 좁힌 차이를 보고한다. 한 가지만 바꾼 비교는 후자다.`),
  ...table(["비교(A − B)", "바꾼 것", "v1 전체", "v1 공통 학습", "v2 전체", "v2 공통 학습"], [
    ["BPR MF − 표본 MF", "손실: 가중 MSE(미관측 표본 0) → 쌍별 BPR(미관측 음성)", ci(MFB1), ci(MFB1c), ci(MFB2), ci(MFB2c)],
    ["MLP 쌍별(관측 음성) − MLP", `손실 형태: 점별 BCE → 쌍별(음성은 같은 사용자의 미통과 시도${obsNeg != null ? `, 그런 시도가 없으면 미관측 단원(v2 쌍의 ${pct(1 - obsNeg)})` : ""})`, ci(OBS1), ci(OBS1c), ci(OBS2), ci(OBS2c)],
    ["MLP 쌍별(미관측 음성) − MLP 쌍별(관측 음성)", "음성 정의만: 미통과 시도 → 미관측 단원(두 모델의 학습 범위는 같다)", ci(NEG1), ci(NEG1c), ci(NEG2), ci(NEG2c)],
    ["MLP 쌍별(미관측 음성) − MLP", "비판이 처방한 BPR 전체(손실 + 음성 정의)", ci(BPRU1), ci(BPRU1c), ci(BPRU2), ci(BPRU2c)],
    ["MLP 목표 정렬 − MLP", "레이블을 평가 목표로: 주 w에 처음 통과한 단원 vs 그 주까지 통과하지 않은 단원", ci(NEXT1), ci(NEXT1c), ci(NEXT2), ci(NEXT2c)],
    ["MLP − 무작위", "참고", ci(PR1["MLP-Random"]), ci(CG(NNG1, "MLP-Random")), ci(PR2["MLP-Random"]), ci(CG(NNG, "MLP-Random"))],
  ], [2.9, 3.5, 1.6, 1.6, 1.6, 1.6], { caption: "신경망 변형의 쌍 비교(테스트 NDCG@5 차이, 사용자 단위 쌍 부트스트랩 95% 구간; ‘공통 학습’ = 네 신경망이 모두 학습한 사용자)", size: 15, zebra: true }),
  ...table(["사용자군(테스트)", "v1 사용자", "v2 사용자", "MLP 쌍별(미관측 음성) − MLP, v1", "같은 비교, v2", "처리 차이"], [
    ["모든 신경망이 학습(학습 주에 통과 있음)", NNG1 ? num(NNG1.common) : "–", NNG ? num(NNG.common) : "–", ci(BPRU1c), ci(BPRU2c), "네 모델 모두 학습된 임베딩 점수"],
    ["기록은 있지만 통과 없음", NNG1 ? num(NNG1.history_no_pairs) : "–", NNG ? num(NNG.history_no_pairs) : "–", ci(COLD1), ci(COLD2), "점별 MLP는 미통과 행으로 학습, 쌍별·목표 정렬 MLP는 콘텐츠 대체 점수"],
    ["학습 기록 없음", NNG1 ? num(NNG1.no_history) : "–", NNG ? num(NNG.no_history) : "–", "0", "0", "모든 신경망이 같은 콘텐츠 대체 점수"],
  ], [3.2, 1.3, 1.3, 2.4, 2.4, 3.4], { caption: "신경망 비교의 사용자군 분해(쌍 부트스트랩 95% 구간)", size: 15, zebra: true }),
  p(`세 가지가 보인다. 첫째, 학습 범위가 같은 두 쌍별 모델에서 음성을 ‘미통과 시도’에서 ‘미관측 단원’으로 바꾸면 ${two(NEG1, NEG2)}. 공통 학습 사용자에서 손실 형태만 바꾸면 ${two(OBS1c, OBS2c)}. 둘째, 비판이 처방한 BPR(미관측 음성)은 v1에서 MLP보다 ${effS(BPRU1)}고(MLP 점수 ${fmt(v1By.MLP.ndcg, 5)} → ${v1By.MLP_BPRU ? fmt(v1By.MLP_BPRU.ndcg, 5) : "–"}, 공통 학습 사용자 ${ci(BPRU1c)}), v2에서는 전체로는 ${effS(BPRU2)}지만(${ci(BPRU2)}) 공통 학습 사용자로 좁히면 ${effS(BPRU2c)}다(${ci(BPRU2c)}). v2 전체의 차이는 학습 주에 통과가 없는 ${NNG ? num(NNG.history_no_pairs) : "–"}명에게서 나온다(${ci(COLD2)}). 이들은 점별 MLP에서는 미통과 행으로 학습되지만 쌍별 모델에서는 쌍이 없어 콘텐츠 대체 점수를 받는다. BPR MF는 표본 MF보다 ${two(MFB1, MFB2)}. 셋째, 다음 주 통과를 직접 레이블로 쓴 목표 정렬 MLP는 전체로는 ${two(NEXT1, NEXT2)}. 공통 학습 사용자로 좁히면 ${two(NEXT1c, NEXT2c)}. 어느 세계에서도 신경망 최고치(v1 ${fmt(nnBest1)}, v2 ${fmt(nnBest2)})는 규칙(v1 ${fmt(v1By.RULE.ndcg)}, v2 ${fmt(resBy.RULE.ndcg)})에 미치지 못했다.`),
  p(`해석. 노트북의 MLP는 미관측 단원을 0으로 본 것이 아니라 아예 학습하지 않았다. 학습 행은 관측된 시도 ${mlpAud ? num(mlpAud.training_rows) : "–"}건(통과 ${mlpPos ? pct(mlpPos) : "–"})이고, 마지막 학습 손실 ${mlpAud ? jo(fmt(mlpAud.loss_last, 3), "은/는") : "–"} 통과율만 맞히는 상수 예측의 손실 ${bce0 ? fmt(bce0, 3) : "–"}보다 낮아 0으로 붕괴하지도 않았다. 대신 ‘시도한 단원 중 무엇을 통과할까’만 배우고 ‘무엇을 시도할까’는 배우지 못했는데, 다음 주 통과 단원 예측에는 이 부분이 필요하다. 미관측 음성 BPR은 바로 이 공백을 메우므로 v1에서 효과가 컸다. v2에서는 같은 학습 범위에서 ${effS(BPRU2c)}다. 관심 주제·수준·목적·로드맵 규칙 신호가 같은 정보를 이미 담고 있어 더 얻을 것이 적었을 가능성이 있다(가설, 검증은 11월). 또 쌍별 모델은 학습 주에 통과가 없는 사용자를 학습하지 못하므로, 실제로 쓰려면 이런 사용자에게 점별 모델 점수를 섞는 처리가 필요하다(전체 결과가 이 처리에 좌우된다). 정리하면 1차본의 ‘모델 결함이 아니라 목표 불일치’라는 문장은 실험 없이 쓴 단정이었다. 실험이 보여 준 것은 음성을 무엇으로 두느냐가 중요하고, 그 효과는 데이터 세계와 학습 범위에 따라 다르다는 점이다. 그래서 이 문장을 정정한다. (2차본 최종 검토에서 쌍별 MLP 2종이 쌍이 없는 사용자를 학습된 사용자로 표시해 대체 점수 대신 학습되지 않은 임베딩으로 점수를 매기던 결함을 찾아 고쳤고, 이 절의 수치는 고친 뒤의 값이다.)`),
  ...table(["#", "기법군", "설정", "검증 NDCG@5", "Diversity"], D.validation_top.map(j => [String(j.job_id), j.family, j.name, fmt(j.ndcg), fmt(j.diversity, 3)]),
    [0.8, 1.2, 7.5, 1.6, 1.4], { caption: "검증 상위 설정(2주차)", size: 16, zebra: true, numCols: [3, 4] }),
  h2("6.4 세그먼트 라우터의 λ 교차 선택"),
  ...img("fig6_router_lambda.png", "라우터 λ에 따른 검증 교차 NDCG@5(평균 ± 표준편차, 반복 2회)"),
  p(`세 라우터 모두 λ=0부터 3000까지는 λ가 커질수록(세그먼트별 선택을 전역 1위 쪽으로 수축할수록) 검증 교차 성능이 좋아졌고, 그 뒤는 라우터마다 다르다.${lamAt("RouterFull", 3000) != null && lamAt("RouterNoGenderIncome", 1e9) != null ? ` 성별 포함 라우터는 λ=3000(${fmt(lamAt("RouterFull", 3000), 5)})과 ∞(${fmt(lamAt("RouterFull", 1e9), 5)})가 거의 같아 3000이, 성별·소득 제외 라우터는 ∞에서 떨어져(${fmt(lamAt("RouterNoGenderIncome", 3000), 4)} → ${fmt(lamAt("RouterNoGenderIncome", 1e9), 4)}) 3000이 선택되었다.` : ""} 운영 라우터(성별 제외)는 λ=3000(${fmt(lamRow(3000), 4)})과 λ=∞(${fmt(lamRow(1e9), 4)})가 반복 간 표준편차(약 ${fmt(lamSd, 3)}) 안에서 사실상 같았고 ${LAM_OP >= 1e8 ? "∞가 근소하게 높아 선택되었다. 그 결과 잎 " + (RCH.RouterNoGender ? RCH.RouterNoGender.leaves + "개가 모두" : "모두") + " 전역 1위 설정을 쓴다(잎 챔피언 " + (RCH.RouterNoGender ? RCH.RouterNoGender.distinct_leaf_champions : 1) + "종)" : "λ=" + LAM_OP + "이 선택되어 대부분의 세그먼트에 전역 1위 설정이 배정되었다"}. 1차본(λ=3000)과 결론은 같다. 세그먼트별로 다른 설정을 고를 만큼의 신호가 이 데이터에는 없다는 뜻이며, 실제 로그에서 λ가 작게 선택되는지가 세그먼트 개인화의 가치를 판단하는 기준이 된다. ${RCH.RouterFull ? `성별을 포함한 라우터는 λ=${lamTxt(RCH.RouterFull.lam)}${RCH.RouterFull.lam >= 1e8 ? "를" : "을"} 골라 잎 챔피언이 ${RCH.RouterFull.distinct_leaf_champions}종이었지만 테스트에서 전역 1위와 ${effS({ diff: resBy.RouterFull.difference_vs_global, ci_low: resBy.RouterFull.ci_low, ci_high: resBy.RouterFull.ci_high })}다(${ci({ diff: resBy.RouterFull.difference_vs_global, ci_low: resBy.RouterFull.ci_low, ci_high: resBy.RouterFull.ci_high })}). ` : ""}성별을 써서 얻는 이득이 확인되지 않으므로 운영에서는 성별을 제외했다.`),
  h2("6.5 집단별 결과와 심화 콘텐츠 노출"),
  ...img("fig7_groups.png", "운영 라우터의 집단별 NDCG@5(위: 전체 기준, 아래: 활성 기준; 아래 막대 안 숫자는 집단의 활성 비율)"),
  p(`투자 목적별 정확도는 전체 기준 ${fmt(goalMin, 3)}~${fmt(goalMax, 3)}, 활성 기준 ${fmt(Math.min(...goalRows.map(x => x.ndcg_active)), 3)}~${fmt(Math.max(...goalRows.map(x => x.ndcg_active)), 3)}다. ${goalOverlap ? "모든 목적 집단의 구간이 겹친다." : `전체 기준에서 ${GOAL_KO[goalLo.group]} 집단이 가장 낮고 ${GOAL_KO[goalHi.group]} 집단이 가장 높으며${goalHiAct && goalHiAct.group !== goalHi.group ? `(활성 기준 1위는 ${GOAL_KO[goalHiAct.group]}로, 학습활동처럼 기준에 따라 1위가 바뀐다)` : ""}, 두 집단의 95% 구간은 전체 기준에서 겹치지 않는다(${fmt(goalLo.ci_low, 3)}~${fmt(goalLo.ci_high, 3)} vs ${fmt(goalHi.ci_low, 3)}~${fmt(goalHi.ci_high, 3)}). 원인(목적별 핵심 단원의 난이도와 선호 분포)은 집단 진단 과제로 남긴다.`} ${ageLo && ageHi ? `연령대별로는 ${LAB.age_band[+ageLo.group]} ${fmt(ageLo.ndcg, 3)}(가장 낮음)부터 ${LAB.age_band[+ageHi.group]} ${fmt(ageHi.ndcg, 3)}(가장 높음)까지이고, 두 집단의 구간은 ${ageLo.ci_high < ageHi.ci_low ? "겹치지 않는다" : "겹친다"}(${fmt(ageLo.ci_low, 3)}~${fmt(ageLo.ci_high, 3)} vs ${fmt(ageHi.ci_low, 3)}~${fmt(ageHi.ci_high, 3)}). ` : ""}${oldAge ? `60세 이상(${num(oldAge.users)}명)은 표본이 가장 작아 구간 폭이 ${fmt(oldAge.ci_high - oldAge.ci_low, 3)}로 가장 넓다. ` : ""}학습활동 집단은 두 기준에서 결론이 달라진다(아래 표).`),
  ...table(["학습활동", "사용자", "활성 비율", "NDCG@5 전체 [95% 구간]", "NDCG@5 활성 [95% 구간]"], CT.map(x => [LAB.click_tier[+x.group], num(x.users), pct(x.active_share, 1),
    `${fmt(x.ndcg, 3)} [${fmt(x.ci_low, 3)}, ${fmt(x.ci_high, 3)}]`, `${fmt(x.ndcg_active, 3)} [${fmt(x.ci_low_active, 3)}, ${fmt(x.ci_high_active, 3)}]`]),
    [2.4, 1.6, 1.6, 3.4, 3.4], { caption: "학습활동 집단별 NDCG@5: 정답 없는 사용자 처리 방식에 따라 가장 높은 집단이 바뀐다(운영 라우터)", size: 17, zebra: true, numCols: [1, 2, 3, 4] }),
  p(`1차본은 ‘학습활동이 많은 집단이 가장 높은 것은 기록이 많을수록 개인화가 잘 되는 자연스러운 결과’라고 해석했다. 전체 기준에서는 ${ctTopAll ? LAB.click_tier[+ctTopAll.group] : "–"} 집단이 가장 높지만, 활성 기준에서는 ${ctTopAct ? LAB.click_tier[+ctTopAct.group] : "–"} 집단이 가장 높다. 전체 기준에서 ${ctTopAll ? LAB.click_tier[+ctTopAll.group] : "–"} 집단이 가장 높은 것은 활동이 많을수록 다음 주 정답이 있는 사용자의 비율(활성 비율)이 높아서(${CT.length ? CT.map(x => pct(x.active_share, 0)).join(" → ") : "–"})이고, 정답이 있는 사용자만 보면 ${ctMonoDown ? "활동이 적은 집단일수록 높다" : "순서가 달라진다"}. 기록이 많은 학습자는 쉬운 단원을 이미 통과해 남은 후보가 어렵고 정답 단원도 여러 개라 순위 문제가 더 어렵기 때문으로 보인다(가설). 1차본의 해석은 정답 없는 사용자를 0점으로 넣는 방식이 만든 착시였으므로 정정한다. 2차본부터 집단별 표(group_results.csv)는 두 기준과 활성 비율을 함께 기록한다.`),
  p(`아래 표는 Top-5 중 심화·레버리지 콘텐츠의 비율로, 특정 집단에 고위험 콘텐츠가 더 많이 노출되는지 보는 진단이다. 같은 변수 안의 격차는 ${expGaps.map(g => `${VAR_KO[g.v] || g.v} ${fmt(g.gap, 3)}`).join(", ")}이다. ${expGaps.length ? `가장 큰 격차는 ${VAR_KO[expGaps[0].v] || expGaps[0].v}(${glab(expGaps[0].v, expGaps[0].lo.group)} ${fmt(expGaps[0].lo.advanced_share, 3)} → ${glab(expGaps[0].v, expGaps[0].hi.group)} ${fmt(expGaps[0].hi.advanced_share, 3)})에서 나온다. ` : ""}${expGap > 0.05 ? `이는 7.5절의 기준(5%p 이내)을 넘는다. 운영 설정의 세그먼트 기준값(연령대+소득분위)이 소득 집단별 인기 단원을 반영하는 영향으로 보인다(가설). 1차본의 ‘격차 약 4%p로 충족’ 판정은 처음부터 틀렸다. 1차본 표 17에서도 소득분위별 비율이 ${fmt(V1_EXP.lo, 3)}~${fmt(V1_EXP.hi, 3)}로 격차가 ${jo(fmt(V1_EXP.hi - V1_EXP.lo, 3), "이었다/였다")}. 재학습이 드러낸 문제가 아니라 1차본의 판정 오류이므로 정정한다. 원인 분석과 집단별 심화 노출 상한을 11월 4주 과제로 넣었다.` : "7.5절의 기준(5%p 이내) 안에 있다."}`),
  ...table(["변수", "집단", "사용자", "Top-5 중 심화·레버리지 비율"], D.exposure.filter(x => x.method === "RouterNoGender").map(x => [VAR_KO[x.variable] || x.variable, glab(x.variable, x.group), num(x.users), fmt(x.advanced_share, 3)]),
    [2.5, 3.5, 2, 4.5], { caption: "심화·레버리지 콘텐츠 노출 비율(운영 라우터)", size: 17, zebra: true, numCols: [2, 3] }),
  h2("6.6 선수 단원 가드레일의 비용과 민감도"),
  ...img("fig5_prereq_tradeoff.png", "정확도와 교육 순서 준수의 트레이드오프"),
  p(`운영 라우터의 Top-5 중 ${pct(resBy.RouterNoGender.prereq_violation_rate, 0)}가 선수 단원을 통과하지 않은 단원이었다. 선수 가드레일을 켜면 위반이 0이 되지만 NDCG@5는 ${fmt(resBy["RouterNoGender+prereq"].ndcg)}로 ${fmt(resBy.RouterNoGender.ndcg - resBy["RouterNoGender+prereq"].ndcg, 3)} 낮아진다. 원인은 두 가지다. 첫째, 선수 관계가 없는 단원이 ${ROOTS}개뿐이어서 통과 기록이 적은 학습자는 가드레일을 통과한 후보가 5개 미만이 된다(후보 5개 미만 ${pct(DIVL.prereq_candidates_below_k)}, 실제 추천 목록 5개 미만 ${pct(DIVL.prereq_shown_below_k)}; 차이는 ‘한 단계 위 단원 최대 1개’ 상한 때문이다). 둘째, 모의 세계의 학습자는 선수 여부와 무관하게 단원을 고르고(선수 미이수는 고른 뒤의 완료·통과 확률만 낮춘다), 선수 단원을 건너뛰고도 상당수 통과하므로(페널티 0.8) 정답 단원이 가드레일에 걸러진다. 즉 이 비용은 ‘선수 관계가 실제로 얼마나 학습 성과를 지배하는가’에 달려 있다.`),
  p(`가드레일을 켜면 Diversity@5도 ${fmt(DIVR.mean, 3)} → ${fmt(DIVG.mean, 3)}로 오른다. 이 상승은 목록이 짧아져서가 아니다. 꽉 찬 5개 목록만 봐도 ${fmt(DIVR.by_len && DIVR.by_len["5"] ? DIVR.by_len["5"].div : null, 3)} → ${fmt(DIVG.by_len && DIVG.by_len["5"] ? DIVG.by_len["5"].div : null, 3)}이고, 같은 주제 쌍이 있는 목록의 비율도 ${pct(DIVR.by_len && DIVR.by_len["5"] ? DIVR.by_len["5"].same_topic_rows : DIVR.same_topic_rows)} → ${pct(DIVG.by_len && DIVG.by_len["5"] ? DIVG.by_len["5"].same_topic_rows : null)}로 줄었다(짧은 목록까지 합한 전체로는 ${pct(DIVR.same_topic_rows)} → ${pct(DIVG.same_topic_rows)}). 같은 주제 안에서는 수준 n−1이 항상 선수 단원이고 통과한 단원은 후보에서 빠지므로, 가드레일 아래에서는 주제마다 후보가 사실상 하나만 남는다(중간 점검 비판의 설명과 같다). 다만 Diversity@5는 모든 방법에서 ${fmt(Math.min(...D.results.map(r => r.diversity)), 2)}~${jo(fmt(Math.max(...D.results.map(r => r.diversity)), 2), "으로/로")} 높아 방법 간 변별력이 크지 않고, 주제 중복만 재며 수준 다양성은 재지 않는다는 한계가 있다.`),
  ...img("fig8_sensitivity.png", "선수 페널티 강도에 따른 가드레일 비용(학습자 3,000명 모의 세계, scripts/prereq_sensitivity.py)"),
  ...table(["선수 페널티", "퀴즈 통과(4주 합)", "운영 라우터 NDCG", "라우터 선수 미이수", "+가드레일 NDCG", "가드레일 짧은 목록", "검증 1위 설정"], sens.map(s => [
    Number(s.prereq_penalty).toFixed(1), num(s.quiz_pass), fmt(s.RouterNoGender.ndcg), fmt(s.RouterNoGender.prereq_violation_rate, 3), fmt(s["RouterNoGender+prereq"].ndcg), fmt(s["RouterNoGender+prereq"].short_list_rate, 3), s.operational]),
    [1.3, 1.5, 1.6, 1.6, 1.6, 1.6, 4.3], { caption: `선수 페널티 민감도(학습자 3,000명, 테스트 사용자 ${num(sens[0].users)}명, 전체 기준 NDCG)`, size: 16, zebra: true, numCols: [1, 2, 3, 4, 5] }),
  p(`${sensRev.length ? `페널티를 ${sensRev.map(x => Number(x).toFixed(1)).join(", ")}으로 키운 세계(선수 단원을 모르면 통과가 훨씬 어려운 세계)에서는 가드레일을 켠 쪽의 NDCG 점 추정치가 더 높다(${sens.filter(x => sensRev.includes(x.prereq_penalty)).map(x => `${fmt(x["RouterNoGender+prereq"].ndcg)} vs ${fmt(x.RouterNoGender.ndcg)}, 차이의 95% 구간 [${sgn(x["RouterNoGender+prereq"].ci_low)}, ${sgn(x["RouterNoGender+prereq"].ci_high)}]`).join("; ")}). ${sensRevSig.length ? "구간도 0을 넘어 역전이 확인된다." : "다만 구간이 0을 포함하므로(학습자 3,000명 세계 하나, 부트스트랩 100회) 역전을 확인한 것은 아니고, 비용이 사라지는 방향을 보인 것이다."} 페널티가 클수록 라우터의 선수 미이수 비율은 줄고(${sens.map(x => fmt(x.RouterNoGender.prereq_violation_rate, 2)).join(" → ")}) 가드레일의 짧은 목록 비율은 늘어난다(${sens.map(x => fmt(x["RouterNoGender+prereq"].short_list_rate, 2)).join(" → ")}).` : "페널티를 키워도 이 작은 세계에서는 가드레일 쪽이 앞서지 않았다."} 따라서 실제 로그가 생기면 ‘선수 단원을 건너뛴 시도의 통과율 ÷ 선수를 갖춘 시도의 통과율’을 먼저 측정해 페널티를 보정하고, 그 값에 따라 가드레일을 강제할지 신호(가중치)로만 쓸지 정하는 것이 다음 단계의 핵심 실험이다.`),
  h2("6.7 해석과 한계"),
  bullet("모의 데이터의 결과이므로 절대 수치는 실제 학습자 성과가 아니다. 다만 파이프라인이 선택·평가를 분리하고 같은 seed로 다시 학습하면 같은 결과를 내므로(결과 파일 비교로 확인, 모델 상태 해시는 학습 감사에 기록), 실제 로그로 바꿔도 같은 절차로 비교할 수 있다."),
  bullet("규칙이 1위인 것은 생성기가 관심 주제·수준·목적으로 행동을 만들기 때문이기도 하다. 실제 로그에서는 CF·MF 비중이 커질 수 있으며, 그때는 α_u 가중 하이브리드가 자동으로 그 비중을 가져간다."),
  bullet(`신경망의 낮은 성능은 손실 함수·음성 정의와 학습 범위에 따라 달라진다. 미관측 음성 BPR을 쓰면 노트북 세계에서는 MLP가 ${effS(BPRU1)}고(${ci(BPRU1)}), v2에서는 전체로는 ${effS(BPRU2)}지만(${ci(BPRU2)}) 모든 신경망이 학습한 사용자로 좁히면 ${effS(BPRU2c)}다(${ci(BPRU2c)}). v2 전체의 차이는 쌍별 모델이 학습하지 못하는 사용자(학습 주에 통과 없음)의 대체 점수에서 나온다. 1차본의 ‘모델 결함이 아니라 목표 불일치’라는 단정은 정정했고, v2의 공통 학습 사용자에서 차이가 없었던 원인(규칙 신호와의 정보 중복 가설)과 목적·로드맵 특징을 입력으로 넣은 모델, 쌍이 없는 사용자에게 점별 점수를 섞는 처리는 11월에 비교한다. 새 변형은 하이브리드의 구성 신호로는 넣지 않았고, 단독 설정으로 전역·라우터 선택의 후보였지만 선택되지 않았으며, MLP 학습의 검증 손실은 기록하지 않아 과적합 여부는 산출물로 판단할 수 없다.`),
  bullet("정답 없는 사용자를 0점으로 넣는 전체 기준은 방법 간 순위에는 영향이 없지만, 활성 비율이 다른 집단의 비교에서는 결론을 바꿀 수 있다(6.5절). 집단 진단은 두 기준을 함께 보고 판단한다."),
  bullet("선수 가드레일은 정확도와 교육 순서 사이의 정책 선택이고, 페널티 보정 전까지는 ‘기본 켬 + 끌 수 있음’으로 운영한다."),
  bullet("실서비스 전 필요 조건: 실제 로그로 같은 절차의 재평가, 세제·규제 문구와 학습 요점의 법령·공지 원문 대조와 전문가 검수, 개인정보 처리의 법률 검토(가명처리·결합·반출 절차), KRX·공공데이터 이용 조건의 상용 범위 확인. 이 보고서의 결과는 그 전 단계의 프로토타입 검증이다."),
);

// 7. 평가 계획
add(h1("7. 평가 계획"),
  p("평가 지표는 오프라인과 온라인에서 하나씩, 두 개를 주 지표로 둔다. 나머지 지표는 정확도만 오르고 교육 순서나 공정성이 깨지지 않는지 감시하는 보조 지표다."),
  ...table(["구분", "지표", "선택 이유"], [
    ["주 지표 ①(오프라인)", "NDCG@5: 다음 주에 퀴즈를 통과한 단원을 정답으로 한 Top-5 순위 품질(전체 기준, 활성 기준 병기)", "시스템의 출력이 순위가 있는 Top-5 목록이고 다음 주 정답 단원이 여러 개일 수 있으므로, 정답을 위쪽에 둘수록 높아지는 순위 지표가 맞다. 수업 노트북과 같은 정의라 1차본·v1 재현과 비교할 수 있다"],
    ["주 지표 ②(온라인)", "노출 후 7일 안에 퀴즈를 1개 이상 통과한 사용자의 비율", "클릭 같은 참여가 아니라 교육 목표인 이해(퀴즈 통과)를 직접 잰다. 사용자별 이진 결과라 두 비율 검정으로 표본 크기를 계산할 수 있다(7.3절)"],
    ["보조 지표", "선수 미이수 비율, Diversity@5, 집단별 NDCG·심화 노출 비율", "교육 순서 준수, 주제 다양성, 집단 간 공정성을 감시한다(7.1·7.5절)"],
  ], [2.2, 4.8, 5.5], { caption: "주 평가 지표와 선택 이유", size: 16, zebra: true }),
  p(`평가 데이터와 절차: 오프라인 평가는 모의 데이터 v2(학습자 ${num(DS.users)}명, ${DS.weeks}주)로 한다. 0~1주 로그로 학습해 2주차에서 설정 ${num(M.configurations)}개를 평가하고 1위를 잠근 뒤(검증), 0~2주로 다시 학습해 3주차 테스트 사용자 ${num(nAll)}명(활성 ${num(nActive)}명)에게 보고한다. 정답은 다음 주에 퀴즈를 통과한 단원이고, 후보는 아직 통과하지 않은 단원 중 수준 가드레일을 통과한 단원이다. 방법 간 차이는 같은 사용자에 대한 쌍 부트스트랩 95% 구간으로 판단한다. 실제 로그가 생기면 같은 절차로 다시 평가한다. 온라인 평가는 진단을 마친 신규 학습자를 무작위로 배정해 7일 결과를 재고 고정 순서 검정으로 판정한다(7.3절).`),
  h2("7.1 오프라인 평가(현재 시행 중)"),
  ...table(["지표", "정의", "목적", "현재 값(운영 라우터)"], [
    ["NDCG@5 전체 (주 지표, 노트북 규칙)", "다음 주 퀴즈 통과 단원을 정답으로 한 순위 품질, 정답 없는 사용자 = 0 포함 평균", "정확도(노트북과 비교)", fmt(resBy.RouterNoGender.ndcg)],
    ["NDCG@5 활성 (정답 있는 사용자)", `후보 안의 정답이 1개 이상인 사용자(${num(nActive)}명)만 평균. 전체 기준과의 비(${fmt(1 / ratioAct, 3)})는 모든 방법에서 같음`, "정확도(다른 연구와 비교)", fmt(resBy.RouterNoGender.ndcg_active)],
    ["Hit@5", "정답 단원이 Top-5에 하나라도 있는 사용자 비율", "진단", fmt(resBy.RouterNoGender.hit_diagnostic, 3)],
    ["Diversity@5", "Top-5 안의 단원 쌍 중 주제가 다른 쌍의 비율", "다양성", fmt(resBy.RouterNoGender.diversity, 3)],
    ["선수 미이수 비율", "Top-5 중 선수 단원을 통과하지 않은 단원의 비율", "교육 순서 준수", fmt(resBy.RouterNoGender.prereq_violation_rate, 3) + " (가드레일 시 0)"],
    ["짧은 목록 비율 · 커버리지", "추천 목록이 k개 미만인 사용자 비율, 추천된 단원의 카탈로그 커버리지", "콜드스타트·쏠림", fmt(resBy.RouterNoGender.short_list_rate, 3) + " · " + fmt(resBy.RouterNoGender.coverage_diagnostic, 3)],
    ["집단별 NDCG · 심화 노출 비율", "목적·연령대·소득분위·성별·학습활동별 지표와 95% 구간(전체·활성 기준, 활성 비율)", "공정성 진단", "6.5절"],
    ["성별 뒤집기 불변", "성별만 바꾼 요청의 Top-5가 같은 비율(코드 수준 점검)", "민감 속성 비사용 확인", GF ? `${GF.invariant === GF.users ? `테스트 사용자 ${num(GF.users)}명 전원 불변` : `${num(GF.invariant)}/${num(GF.users)}명 불변`}(번들 v2, 서비스 기본 가드레일)` : "–"],
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
    ["주 지표", "추천 노출 후 7일 안에 퀴즈를 1개 이상 통과한 사용자의 비율(사용자별 이진 결과로 정의해 두 비율 Z-검정의 전제를 맞춘다). 보조: 통과 단원 수, 완료율, 이탈률, 로드맵 진행률, 세션당 학습 시간"],
    ["가드레일 지표", "선수 미이수 추천 비율, 심화·레버리지 노출 비율의 집단별 차이, 불만·신고"],
    ["표본 크기", `통과율 22% → 24%(+2%p), 유의수준 5% 양측, 검정력 80%면 군당 ${num(AB2)}명(아래 표). MDE를 3%p로 올리면 군당 ${num(AB3)}명으로 줄지만, 참 효과가 2%p라면 검정력이 ${pct(POW3, 0)}로 떨어진다는 대가가 있다`],
    ["검정 방향(2차본 정정)", `주 비교는 양측 우월성 검정이다. 단측 우월성 검정(군당 ${num(abSize(0.22, 0.24, false))}명)은 ‘B가 A보다 낫다’만 검정하므로 데이터를 보기 전에 사전 등록해야 하고, 악화 방향은 중단 규칙으로만 감시한다. ‘B가 A보다 나쁘지 않다’를 보이려면 비열등성 검정과 사전에 정한 마진 δ가 필요하다(참 차이 0 가정, 단측 5%: δ=1%p면 군당 ${num(niSize(0.22, 0.01))}명, δ=2%p면 ${num(niSize(0.22, 0.02))}명). ‘단측 검정 = 나빠지지 않음 확인’은 두 개념을 섞은 표현이라 쓰지 않는다`],
    ["배정 방식(2차본)", `고정 순서 검정: 1단계 A vs B를 α=5%로 검정해 귀무가설을 기각했을 때만 2단계 B vs C로 넘어간다(두 검정 전체의 1종 오류를 5%로 통제). 2단계는 시기 교란을 피하려고 B·C에 신규 사용자를 새로 배정한다. 두 질문을 모두 답하는 총 유입은 군당 표본의 4배(${num(4 * AB2)}명)로 3군 동시 운영(보정 없이 ${num(3 * AB2)}명, 비교 2개 보정 시 ${num(3 * abSize(0.22, 0.24, true, ZQ.a2_dunnett))}명)보다 많다. 대신 주 질문을 절반의 유입(${num(2 * AB2)}명)으로 먼저 답하고, 1단계에서 효과가 없으면 2단계를 생략한다. 그때 C를 시험하려면 새로 사전 등록하고 별도 α로 보고하는 독립 실험으로 하며, 이 실험은 위 5% 보장 범위 밖이다`],
    ["1단계 대비를 고른 근거", (() => { const A_ = resBy.ABControl, BA = PR2["RouterNoGender+prereq-ABControl"], CA = PR2["RouterNoGender-ABControl"];
      return `오프라인 테스트 NDCG@5는 C ${fmt(resBy.RouterNoGender.ndcg)} > A ${A_ ? fmt(A_.ndcg) : "–"} > B ${fmt(resBy["RouterNoGender+prereq"].ndcg)} 순서다(A = 성별을 쓰지 않는 세그먼트 인기 설정 중 검증 1위, 6.3절 결과 표의 ‘세그먼트 인기(A/B 대조군 A)’ 행). B는 A보다 유의하게 낮고(B − A ${ci(BA)}), C는 A보다 유의하게 높다(C − A ${ci(CA)}). 오프라인 정답은 선수와 무관하게 단원을 고른 학습자의 실제 통과라서 선수 미이수 단원을 빼는 B가 불리하고, 이 비용의 크기는 선수 효과의 세기에 달려 있다(6.6절 민감도 실험). 그래도 B를 먼저 보는 이유는 B가 교육 순서를 지키는 실제 서비스 설정이고, 선수를 마친 단원을 추천받은 학습자의 통과율이 오르는지는 기록 재생으로 잴 수 없는 질문이기 때문이다. 오프라인 근거가 B에 불리하므로 주 비교는 양측 검정으로 두고(B가 낫다는 단측 가설은 사전 등록하지 않는다), 1단계에서 효과가 없거나 B가 낮으면 C를 별도 실험(새로 사전 등록, 별도 α, 고정 순서 검정의 5% 보장 밖)으로 시험한다`; })()],
    ["기간·유입", `테스트 기간 상한은 단계별 8주. 주 지표가 노출 후 7일 결과라 등록은 앞의 ${ENROLL_DAYS}일 안에 끝나야 하므로, 8주 안에 1단계를 끝내려면 하루 진단 완료 신규 학습자가 MDE 2%p 기준 약 ${num(INFLOW2)}명, 3%p 기준 약 ${num(INFLOW3)}명 필요하다. 시작 전 2주의 실제 유입으로 MDE를 사전 등록하고, 상한에 도달하면 결과를 ‘판정 보류’로 보고한다`],
    ["외생 변수", "동시 무작위 배정이므로 시장 충격은 두 군에 같이 작용해 효과 추정을 편향시키지 않는다. 실제 문제는 분산 증가, 처치×시기 상호작용, 외적 타당성이므로 가입 주차 코호트로 층화 배정하고 분석에 블록으로 넣으며, 사전 등록한 시장 급변 주간은 민감도 분석에서 따로 본다"],
    ["분석", "사전 등록한 지표와 분석 계획, 사용자 단위 비율 검정과 부트스트랩, 세그먼트별 이질 효과는 탐색적으로만 보고"],
    ["중단 규칙", "처치군의 이탈률이 대조군보다 유의하게 높거나 가드레일 지표 위반 시 중단"],
  ], [2.2, 10.3], { caption: "온라인 A/B 실험 계획", size: 17, zebra: true }),
  ...table(["최소 검출 효과(MDE)", "양측, 군당", "단측, 군당", "양측·비교 2개 보정, 군당", "두 군 합계(양측)", "세 군 합계(보정)"], AB_ROWS, [3.1, 1.8, 1.8, 2.3, 1.9, 1.9],
    { caption: "통과율 22% 기준 표본 크기(두 비율 Z-검정, 검정력 80%, 연속성 보정 없음, 비교 2개 보정은 비교마다 α=2.5%)", size: 16, zebra: true, numCols: [1, 2, 3, 4, 5] }),
  h2("7.4 사용성·전문가 검토"),
  bullet("사용성: 대상 페르소나별 각 3~4명(총 10명)에게 11단계 과제를 수행하게 하고 SUS 점수, 과제 완료율, ‘왜 이 단원인지 이해했는가’ 5점 척도를 측정한다."),
  bullet("콘텐츠 정확성: 금융 교육 전문가(또는 담당 교수) 검수로 퀴즈 문항·유형 카드의 세금·연금·규제 문구를 확인하고, 출처 등록부의 링크를 분기마다 점검한다."),
  bullet("안전: 화면·API 응답에서 투자 권유로 읽힐 수 있는 문구를 금칙어 검사로 차단하고, 유형 카드는 ‘교육용 분류’ 고지를 유지한다."),
  h2("7.5 수용 기준"),
  ...table(["기준", "통과 조건"], [
    ["정확도", (() => { const a = PR2["RouterNoGender-POP"], b = PR2["RouterNoGender-Random"], c = PR2["RouterNoGender+prereq-POP"], e = PR2["RouterNoGender+prereq-Random"];
      const sig = x => x && x.ci_low > 0, okOff = sig(a) && sig(b), okOn = sig(c) && sig(e);
      return `운영 라우터의 테스트 NDCG@5가 인기·무작위보다 유의하게 높음(사용자 단위 쌍 부트스트랩 95% 구간이 0을 포함하지 않음). 서비스 기본(선수 가드레일 켬): ${okOn ? "충족" : "미충족"}(인기 대비 ${ci(c)}, 무작위 대비 ${ci(e)} — 인기 대비 여유가 작음). 가드레일 끔: ${okOff ? "충족" : "미충족"}(인기 대비 ${ci(a)}, 무작위 대비 ${ci(b)})`; })()],
    ["교육 순서", `가드레일 켬 상태에서 선수 미이수 비율 0, 짧은 목록 비율 20% 이하(선수 관계 조정 또는 완화 규칙으로 달성) — 현재 ${pct(resBy["RouterNoGender+prereq"].short_list_rate)}로 미충족, 8절 과제`],
    ["공정성", `성별 뒤집기 불변 100%${GF ? (GF.invariant === GF.users ? `(현재 번들 v2 테스트 사용자 ${num(GF.users)}명 전원 불변)` : `(현재 ${num(GF.invariant)}/${num(GF.users)}명 — 미충족)`) : ""}. 집단별 NDCG 격차는 전체·활성 두 기준으로 보고하고 활성 기준에서도 남는 격차는 원인을 분석한다(현재 학습활동 집단은 활성 기준 ${CT.length ? `${fmt(Math.max(...CT.map(x => x.ndcg_active)), 3)} vs ${fmt(Math.min(...CT.map(x => x.ndcg_active)), 3)}` : "–"}로 분석 과제). 같은 변수 안의 심화 노출 비율 격차 5%p 이내 — ${expGap <= 0.05 ? "현재 충족" : "현재 미충족"}(최대 ${expGaps.length ? `${VAR_KO[expGaps[0].v] || expGaps[0].v} ` : ""}${fmt(expGap, 3)}, 6.5절. 1차본의 ‘현재 충족(약 4%p)’은 1차본 표에서도 소득분위 격차 ${fmt(V1_EXP.hi - V1_EXP.lo, 3)}로 틀린 판정)`],
    ["재현성", "같은 seed·데이터로 다시 학습하면 결과 파일(테스트·검증·집단별 결과, 시간 열 제외)과 모델 상태 해시가 같음, 노트북 v1 재현 5자리 일치 — 현재 충족(v1·v2 각각 다시 학습해 비교)"],
    ["운영", "요청당 응답 100ms 이하, 요청 중 재학습 없음, 추천을 담은 모든 응답과 화면에 고지문 — 현재 충족(로컬 측정 중앙값: 기존 학습자 약 11ms, 새 학습자 약 22ms, 최대 40ms)"],
  ], [2.2, 10.3], { caption: "수용 기준", zebra: true }),
);

// 8. 일정
add(h1("8. 남은 일정, 역할, 위험 관리"),
  ...table(["주차", "작업", "산출물"], [
    ["11월 1주", "KRX 정보데이터시스템에서 ETF 전종목 기본정보 파일 수동 내려받기 → sources sync --krx-csv, KRX Open API 인증키·공공데이터포털 키 발급 후 엔드포인트 경로·필드명을 실제 응답으로 확인하고 시세 수집, 스냅샷 검증, 유형 분류 규칙 보정", "data/sources 스냅샷, 분류 정확도 점검표"],
    ["11월 2주", `교육 자료 링크 검수(스쿨·사전교육·KRX·가이드북), 퀴즈 문항 확장(진단 단원 ${QUNITS}개 × 단원당 2문항)과 전문가 검수, 세제·규제 문구와 학습 요점의 법령·공지 원문 대조(기본예탁금·ISA·IRP·과표기준가·연금소득세), KRX 이용약관 조항·호출 한도와 개인정보보호법 과징금 조문·특례 요건·가명정보 가이드라인 원문 대조(대응 보고서에서 ‘미검증’으로 남긴 항목), 나머지 단원의 학습 요점 작성`, `출처 등록부 v2, 문항 ${2 * QUNITS}개, 세제·규제·법령 확인표, 학습 요점 확대`],
    ["11월 3주", "실제 로그 스키마로 파일럿 수집(수업 참여자 또는 모의 사용자 테스트, 가명처리 도구 사용), 선수 페널티 보정 실험, 공통 학습 사용자에서 미관측 음성 쌍별 MLP가 MLP와 차이가 없었던 원인 분석, 쌍이 없는 사용자에게 점별 점수를 섞는 처리와 목적·로드맵 특징을 넣은 신경망 비교", "보정 보고, 결과 표 갱신"],
    ["11월 4주", "사용성 테스트 10명, 수용 기준 점검, 가드레일 완화 규칙(짧은 목록 대응) 확정, 집단 진단 과제(소득분위별 심화 노출 격차, 투자 목적별 정확도 차이, 학습활동 집단의 활성 기준 차이) 원인 분석과 노출 상한 정책", "SUS 결과, 정책 문서, 집단 진단 보고"],
    ["12월 1~2주", "최종 보고서·발표 자료, 코드 정리와 재현 문서", "최종 보고서, 발표 슬라이드"],
  ], [1.6, 7, 3.9], { caption: "남은 일정", zebra: true }),
  ...table(["위험", "영향", "대응"], [
    ["공식 API 경로·필드·이용 조건 차이(KRX Open API, 공공데이터포털)", "수집 실패, 이용 조건 위반", "키 발급 후 활용 가이드와 실제 응답으로 경로·필드 확인, 실행당 호출 상한, 실패·빈 결과를 상태로 기록하고 이전 스냅샷·샘플을 신선도 표시와 함께 사용, 비상업 범위 유지(상용 전환 시 별도 이용 계약)"],
    ["개인정보(실제 로그 연결 시)", "재식별, 규제 위반", "가명처리 도구(매핑표 분리), 번들·API에 원시 연령·소득·분 단위 시각과 스키마 밖 열 미보관, 공개 산출물 k≥5와 보완 억제, 반출 표 행 순서 제거, 학습자 조회 API는 로컬에서만, 외부 공유는 비식별 내보내기만, 권한 분리·반출 심사·서빙 API 접근 통제 같은 조직 통제"],
    ["교육 자료 저작권·링크 변경", "자료 연결 끊김", "본문 미저장, 기관 루트+메뉴 경로 표시, 분기별 링크 점검"],
    ["모의 데이터 편향", "규칙 과대평가", `위약 세계 점검(인구통계 열 섞기${PL ? `: ${PL_OK ? "거짓 이점 없음 확인" : "거짓 이점 발견 — 분석 중"}, 4.4절` : ""}), 파일럿 로그로 선수 페널티·CF 비중 보정`],
    ["가드레일로 인한 짧은 목록", "신규 학습자 추천 4개", "입문 단원 추가(선수 없는 단원 확대) 또는 ‘다음에 열릴 단원’ 보조 표시"],
    ["제도 변경(세제·연금 편입 규정)", "유형 카드 문구 오류", "문구를 데이터(taxonomy)로 분리해 갱신, 출처·확인일 표기"],
  ], [3, 2.5, 7], { caption: "위험과 대응", zebra: true }),
  p("역할: 1인 프로젝트로 설계·구현·실험·보고를 모두 수행하며, 전문가 검수와 사용성 테스트 참여자는 11월에 섭외한다."),
);

// 9. 참고 자료
add(h1("9. 참고 자료"),
  numbered("한국거래소, ‘2025년 ETF·ETN 시장 결산’ 보도(2025.12) — 상장 종목 1,058개, 순자산총액 297조 2천억 원. 헤럴드경제(2025.07.22) ‘국내 ETF 1000개 돌파…순자산 1년 새 42% 급증’.", "refs"),
  numbered("전국투자자교육협의회(KCIE) 온라인 스쿨: ETF스쿨·연금스쿨·생애자산관리스쿨·대체투자/파생상품스쿨, https://www.kcie.or.kr", "refs"),
  numbered("금융투자교육원(KIFIN) 레버리지 ETP 사전교육(의무 이러닝, 일반 과정 약 1시간; 단일종목 레버리지·인버스는 2026년 8월 기준 총 3시간과 한국거래소 모의거래 5시간), https://www.kifin.or.kr", "refs"),
  numbered("한국거래소 ETF/ETN 정보·지수 정보, https://www.krx.co.kr ; KRX 정보데이터시스템 ETF 전종목 기본정보, https://data.krx.co.kr", "refs"),
  numbered("공공데이터포털, 금융위원회_증권상품시세정보(ETF) https://www.data.go.kr/data/15094806/openapi.do ; 금융위원회_KRX상장종목정보 https://www.data.go.kr/data/15094775/openapi.do", "refs"),
  numbered("자산운용사 ETF 가이드북·상품 설명 자료: 삼성자산운용(KODEX), 미래에셋자산운용(TIGER), KB자산운용(RISE, 구 KBSTAR) 등 각사 홈페이지 자료실", "refs"),
  numbered("수업 자료: 추천 시스템 강의 노트북(인기·규칙·콘텐츠·CF·MF·MLP·하이브리드·세그먼트 라우터), B_ETF_Education 노트북(seed 42 결과 기록)", "refs"),
  numbered("구현: Python 3.13, NumPy, pandas, SciPy, scikit-learn, PyTorch(학습), FastAPI, Playwright(화면 점검). 저장소 github.com/kyounghob/forclaudekyoungho", "refs"),
  numbered("Rendle, S. 외 (2009). BPR: Bayesian Personalized Ranking from Implicit Feedback. UAI. / Ziegler, C.-N. 외 (2005). Improving recommendation lists through topic diversification. WWW.", "refs"),
  numbered("scikit-learn sklearn.metrics.ndcg_score 문서(정답 관련도가 모두 0인 질의는 0점으로 평균에 포함) / TorchMetrics RetrievalNormalizedDCG 문서(empty_target_action 기본값 'neg' = 정답 없는 질의를 0점 처리).", "refs"),
  numbered("Chow, S.-C., Shao, J., Wang, H. (2008). Sample Size Calculations in Clinical Research, 2판 — 두 비율 비교의 우월성·비열등성 표본 크기 공식.", "refs"),
  ...D.facts.map(f => numbered(`${f.fact}. 출처: ${f.sources.join(" ; ")}`, "refs")),
);

// 부록 A. API
add(pageBreak(), h1("부록 A. REST API 요약"),
  ...table(["메서드 · 경로", "입력", "출력"], [
    ["GET /api/health, /api/meta", "—", "번들 생성 시각, 운영 라우터, 목적·기간 사전, 유형 이름, 설정 수, 요청에서 생략할 때의 가드레일(선수 차단 켬)과 오프라인 평가 가드레일(선수 차단 끔), 학습자 조회 켜짐 여부"],
    ["GET /api/catalog", "—", "단원 목록(주제·수준·선수·출처·개념), 주제·그룹"],
    ["POST /api/parse", "text", "자연어에서 읽은 필드와 근거 표현, 경고"],
    ["GET /api/learners, /api/learners/{id}", "q, limit, offset", "모의 학습자 검색, 프로필·세그먼트·통과 단원·이력"],
    ["POST /api/recommend", "learner_id(학습자 조회가 켜진 서버에서만) 또는 learner{age, goal, horizon, risk, interests, placement, diagnosis, events…}, k, algorithm, guardrail{block_gap, plus_one_max, exclude_passed, prereq_block}(생략하면 화면 기본: 선수 단원 차단 켬), topic_cap, overrides, assume_passed(카탈로그 범위 안 단원 번호)", "추천 단원(점수·기여도·근거·선수 미이수·현재 단계·출처), 로드맵 요약, 검사 결과, 세그먼트 경로, 계산식, 주제×수준 배치도"],
    ["POST /api/roadmap", "learner_id(학습자 조회가 켜진 서버에서만) 또는 learner, assume_passed, overrides", "단계별 단원(상태·분·선수 미이수·출처), 진행률, 다음 단원, 연결 유형"],
    ["POST /api/types", "learner_id(학습자 조회가 켜진 서버에서만) 또는 learner, 또는 goal·risk, assume_passed", "유형 카드(권장·열림, 개념 통과, 세금·연금·규제·주의, 통계, 출처), 유니버스 출처"],
    ["GET /api/quiz, POST /api/quiz/score", "answers{문항id: 보기}", "문항 목록(정답 제외) / 수준·정답 수·문항별 결과·진단 이벤트"],
    ["GET /api/sources", "—", "출처 등록부, 유니버스 출처(샘플/스냅샷), 유형 통계"],
    ["POST /api/compare, GET /api/evaluation", "learner_id(학습자 조회가 켜진 서버에서만) 또는 learner, methods, guardrail(생략 시 화면 기본)", "기법별 Top-K 비교 / 번들의 평가 결과·집단별·노출·검증 상위·QA"],
    ["POST /api/parse-log, /api/designs, GET/DELETE /api/designs/{name}", "csv_text / name, payload", "로그 CSV → 이벤트 / 설계 저장·목록·삭제"],
  ], [3.2, 4.3, 5], { caption: "REST API 요약", size: 16, zebra: true }),
);

// 부록 B. 퀴즈
add(h1("부록 B. 진단 퀴즈 문항"),
  ...table(["#", "단원(주제 · 수준)", "문항", "보기(정답 ★)", "해설"], D.questions.map((q, i) => [String(i + 1), `${q.topic} · ${q.level}${q.marks_pass === false ? " (수준 판정용, 통과 처리 안 함)" : ""}`, q.text,
    q.options.map((o, j) => (j === q.answer ? "★ " : "") + o).join(" / "), q.explain]), [0.5, 1.8, 3.5, 4.2, 2.5], { caption: `진단 퀴즈 ${D.questions.length}문항(${QUNITS}개 단원, 정답 위치 균형)`, size: 15, zebra: true }),
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
    ["과세이연 · 세액공제", "연금저축·IRP에서 운용 수익에 바로 과세하지 않고 연금 수령 시 연금소득세로 과세(사적연금 연 1,500만원 이하 3.3~5.5%, 초과 시 종합과세 또는 16.5% 분리과세 선택), 납입액은 연금저축 600만원·IRP 합산 900만원까지 세액공제", "연금 목적 투자자의 세제 혜택 핵심"],
    ["ISA(개인종합자산관리계좌)", "손익을 통산해 순이익 200만원(서민형·농어민형 400만원)까지 비과세, 초과분 9.9% 분리과세. 연 2,000만원·총 1억원 납입, 의무가입 3년. 만기 60일 안에 연금계좌로 옮기면 전환금액의 10%(최대 300만원) 추가 세액공제 한도", "국내 상장 해외 ETF의 배당소득세·종합과세 부담을 줄인다. 연금계좌와의 납입 순서는 소득·유동성에 따라 다르다(제도가 정한 순서는 없음)"],
    ["과표기준가 · 보유기간과세", "국내 상장 해외주식형·채권·원자재 ETF의 매매차익 과세 기준(레버리지·인버스는 상품 구성에 따라 과세 여부가 달라 상품별 과세유형 확인). 실제 매매차익과 보유 기간의 과표기준가 상승분 중 작은 금액에 15.4%", "가격이 올라도 과표기준가가 오르지 않았으면 세금이 거의 없을 수 있다(단기 매매자에게 중요)"],
    ["IRP 위험자산 70% 한도", "퇴직연금(IRP)은 주식형 ETF 등 위험자산을 계좌 평가액의 70%까지만 담을 수 있고 30% 이상은 예금·안전자산(일부 채권혼합형·적격 TDF 예외는 금융사 확인). 연금저축펀드에는 한도 없음", "한도를 넘으면 위험자산 추가 매수가 제한되어 주식형 100% 주문이 들어가지 않는 이유"],
    ["기본예탁금(레버리지 ETP)", "레버리지·인버스 ETP를 매수하려면 사전교육 이수 외에 기본예탁금 1,000만원 이상이 필요하다. 단일종목형은 2026년 7월 31일부터 현금 3,000만원(신규·추가 매수, 대용증권 불인정), 해외 상장 레버리지 ETP는 2026년 5월 22일부터 1,000만원(기존 거래자 제외)", "교육을 마쳐도 예탁금이 없으면 매수 주문이 들어가지 않는다"],
  ], [2.2, 6, 4.3], { caption: "용어집", size: 16, zebra: true }),
);

// 부록 D. 재현
add(h1("부록 D. 재현 방법과 테스트"),
  p("아래 명령으로 전체를 재현할 수 있다(Python 3.11 이상. 걸리는 시간은 명령마다 적었다: 학습 한 번 약 3분)."),
  ...["python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
      "python -m etfrec train --out artifacts/bundle_v2            # 모의 데이터 v2 생성 → 학습·검증·테스트 → 번들",
      "python -m etfrec serve --bundle artifacts/bundle_v2         # http://127.0.0.1:8000 (API + 학습 설계 스튜디오)",
      "read -rs KRX_OPEN_API_KEY && export KRX_OPEN_API_KEY                # (선택) 키는 화면에 보이지 않게 입력(명령줄에 쓰면 셸 기록에 남음)",
      "python -m etfrec sources check && python -m etfrec sources sync --krx-csv 내려받은파일.csv   # 접근 점검·스냅샷",
      "python -m etfrec export-deid --bundle artifacts/bundle_v2 --k 5 --out deid/learners_k5.csv   # k-익명 학습자 표 반출",
      "python scripts/regression_check.py artifacts/bundle_v1     # 노트북 B(v1) 세계를 학습해 bundle_v1 저장, 기록과 5자리 일치 확인(약 2~3분)",
      "python scripts/placebo_check.py docs/results/placebo_check.json   # 위약 세계(연령·소득·성별 열 섞기) 점검(약 3분)",
      "python scripts/prereq_sensitivity.py docs/results/prereq_sensitivity.json   # 선수 페널티 민감도(약 2분)",
      `pytest -q                                                     # 자동화 테스트 ${TESTS}건 중 기본 실행 ${TESTS - 1}건 (약 30초)`,
      "ETFREC_FULL=1 pytest -q -k test_full_regression_matches_notebook   # 나머지 1건: 노트북 기록과 5자리 일치를 전체 학습으로 확인(약 2~3분)",
      "node scripts/ui_walkthrough.mjs http://127.0.0.1:8000 docs/screens          # Playwright 화면 점검·캡처(서버를 먼저 띄움)",
      "pip install matplotlib pillow && npm i docx && docs/report/build/build.sh   # 그림 → report_data.json → 두 보고서(Word). 위 두 번들이 있어야 함"]
    .map(c => new Paragraph({ spacing: { after: 40 }, indent: { left: 240 }, shading: { type: ShadingType.CLEAR, fill: "F1F3F0", color: "auto" },
      children: [new TextRun({ text: c, font: "Consolas", size: 17 })] })),
  spacer(80),
  ...table(["테스트 파일", "확인 내용"], [
    ["tests/test_metrics.py", "NDCG@5·Hit@5·Diversity@5 벡터 구현이 강의 함수와 일치, 경계 사례"],
    ["tests/test_pipeline_service.py", "파이프라인 산출물·QA, 오프라인 평가와 서비스 Top-5 일치, 임의 학습자·가드레일(수준·선수), 로드맵·유형·퀴즈·출처 서비스, 성별 뒤집기 불변, 모든 기법군 서빙, 오류 처리, API 엔드포인트(422 검증 포함, 학습자 없는 유형 API의 통과 가정 범위), 이벤트 스트림의 세션 단위 시도 묶기, 전체 재현(옵션)"],
    ["tests/test_roadmap_sources.py", "카탈로그 v2 선수 관계 순환 없음·v1 60단원, 로드맵 선수 순서·상태·진행률, 우선순위 행렬·위험성향 필터, 퀴즈 채점(답한 문항만, 단원 단위, 규제 문항 진단 전용, 찍기 방지), 도메인 규칙·학습 요점·템플릿, 분류 개념 존재, KRX 열 정규화·유형 분류·샘플 유니버스·출처 등록부, BPR 모델"],
    ["tests/test_sources.py", "KRX Open API 요청 헤더·주소·파싱, ISU_CD 규칙·전체 이름 대체, 호출 상한·간격, 키 없으면 요청 0건, cp949 CSV·Excel 엔진 없음 처리, 0행 → empty와 직전 평일 기준일, 공공데이터포털 페이지 넘김·코드 교차 확인, kept·fail 시 이전 기록 유지·30일 경고, 시세 결합 통계, HEAD 1회·User-Agent, 쓰기 실패 시 기존 스냅샷 유지·중단 시 파일과 기록 일치·해시 불일치 표시, 형식 검사(다른 화면의 파일·바뀐 필드 이름), 인증키 정리·가림, 일부만 받음 표시 승계, 응답 봉투·짧은 쪽·중간 오류, 날짜 검사, 폴더 규칙, 엔드포인트 환경변수, 패키지 데이터"],
    ["tests/test_privacy.py", "번들에 원시 연령·연소득·일·분 없음, 학습자 목록·상세의 구간 표시, 경로 출력의 작은 노드 숨김, 가명처리 결정성·키 요구·매핑표 분리(CLI 포함, 심볼릭 링크 경로 거부), k-익명화(일반화 → 억제), 누락 열·불가능 계획 보고, 라우터 잎 감사, 개인정보 QA의 실효성, 설계 저장 시 원값 제거(이름·목록 문장·이벤트 시각·여러 표기), export-deid CLI·행 순서 제거, 스키마 밖 로그 열 차단, 임의 설정 번호 거부, 학습자 조회 끄기, 경로 출력의 크기 구간, 보완 억제, 금액(억·월급·원 단위)·출생 연도 가림과 다시 가려도 같은 결과, 서버 출력 미저장과 학습자 조회를 끈 서버의 설계 숨김(덮어쓰기 409·삭제 404, 깨진 파일 무시), 가명처리의 이벤트 묶기"],
    ["tests/test_nlparse.py", "자연어 파서: 기본 문장, 연령·소득(억 단위 합산·월급 환산, 키워드 없는 금액 제외)·성별·성향, 따옴표 제목 → 이력, 통과·완료의 부정·실패·계획 표현과 문장 경계(52문장), 부사 ‘처음엔·중간에’를 수준으로 읽지 않음, 예시 전부 파싱, 목적·기간, 빈 문장 경고"],
  ].map(r => [r[0] + (TPF[r[0]] != null ? ` (${TPF[r[0]]}건)` : ""), r[1]]), [3.2, 9.3], { caption: `자동화 테스트(수집 ${TESTS}건)`, size: 17, zebra: true }),
);

// 부록 E. 중간 점검 지적 대응 요약
add(h1("부록 E. 중간 점검 지적 대응 요약"),
  p("자세한 분석(지적 원문 요지, 사실 확인 출처, 간과 이유, 보완 내용, 수치 변화)은 별도 문서 ‘중간보고서 비판 검토 및 보완 보고서’에 있다. 여기서는 판정만 요약한다."),
  ...table(["#", "지적", "판정", "이 보고서의 반영 위치"], [
    ["1", "모의 로그 이벤트 합계가 시도 수를 초과하는 ‘산술 모순’", "불수용(표 설명 보완·실데이터 정규화는 수용)", "4.4절 이벤트 플래그 표·합계 분해·논리 제약 QA"],
    ["2.1", "정답 없는 사용자를 NDCG 0으로 산입", "부분 수용(요구는 전면 반영)", "6.1절 두 기준, 6.3절 활성 열, 6.5절 집단 결론 정정, QA 항등식"],
    ["2.2", "BCE 손실·BPR 부재로 딥러닝 결과 무효", "부분 수용(요구 전면 반영, MLP 개선은 v1에서만 확인)", "3.1절 학습 목표 표, 6.3절 신경망 변형 쌍 비교, 6.7절"],
    ["2.3", "Diversity@5 타당", "긍정 평가(해석 보완)", "6.1절 정의(2개 미만 0), 6.6절 다양성 상승의 구조적 원인"],
    ["3", "A/B 표본 21,000명 비현실적", "수용(통계 표현 정정)", "7.3절 MDE·검정 방향·고정 순서 검정·유입·기간"],
    ["4.1", "기본예탁금 누락", "수용", "2.2·2.4·5.4절 유형 카드, 부록 B q20, 부록 C·F"],
    ["4.2", "ISA 누락·IRP 70% 누락", "수용(수치 정정, 단원 배치 범위 조정)", "2.2절, 5.2절 로드맵 템플릿(절세 계좌 3단원), 부록 B q17·q19, 부록 C·F"],
    ["4.3", "과표기준가 메커니즘 부재", "수용(파생형 일반화 정정)", "2.2절, 5.4절 세금 문구, 부록 B q18, 부록 C·F(학습 요점 본문)"],
    ["5.1", "KRX 비공식 엔드포인트 호출(크롤링)", "수용(조항 번호 미검증, 처방은 부분 수용)", "4.2·4.3절 접근 설계, 8절 위험"],
    ["5.2", "가명정보 처리 미흡", "수용(법령 요건 정정, k-익명화 범위 조정)", "4.5절 개인정보 점검·최소화·정책 구분, 8절 위험"],
    ["서론·결론", "‘실제 서비스 배포 불가 수준의 치명적 결함’", "부분 수용", "1절 요약, 6.7절 실서비스 전 필요 조건"],
  ], [0.8, 4.4, 3.0, 4.3], { caption: "지적 대응 요약", size: 16, zebra: true }),
);

// 부록 F. 학습 요점(세제·규제 단원)
add(h1("부록 F. 세제·규제 단원 학습 요점"),
  p(`중간 점검에서 빠졌다고 지적받은 세제·규제 단원에 붙인 본문 요점이다(etfrec/lessons.py, 로드맵 화면에서 펼쳐 볼 수 있음). 기준일 ${(D.lessons[0] || {}).asof || "–"}의 보도·기관 안내를 검색으로 확인한 범위이며, 법령·공지 원문 대조는 11월 2주에 한다. 특정 상품의 매수·매도 권유가 아니다.`),
  ...(D.lessons || []).flatMap(L => [h3(`${L.title} (${L.topic} · 수준 ${L.level})`), ...L.points.map(x => bullet(x)),
    p([run("예시 ", { bold: true }), run(L.example)]), p(`자료: ${L.sources.map(k => (D.sources.find(x => x.key === k) || { name: k }).name).join(", ")}`, { size: 18, color: GREY })]),
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
