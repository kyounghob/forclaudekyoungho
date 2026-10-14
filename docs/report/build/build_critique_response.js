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
const GREEN = "1F6F55", SOFT = "DCEFE6", GOLD = "9A6A00", SOFT2 = "F4F5F2", GREY = "5D665D", RED = "B2362D", BLUE = "3B6FB6";
let tabNo = 0;
const run = (text, opt = {}) => new TextRun({ text, font: FONT, size: opt.size || 21, bold: opt.bold, italics: opt.italics, color: opt.color });
const p = (text, opt = {}) => new Paragraph({ alignment: opt.align || AlignmentType.JUSTIFIED, spacing: { after: opt.after ?? 120, line: opt.line || 312, lineRule: LineRuleType.AUTO }, indent: opt.indent, keepNext: opt.keepNext,
  children: (Array.isArray(text) ? text : [text]).map(x => typeof x === "string" ? run(x, opt) : run(x.t, { ...opt, ...x })) });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 }, children: [new TextRun({ text: t, font: FONT })] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 120 }, children: [new TextRun({ text: t, font: FONT })] });
const h3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 80 }, children: [new TextRun({ text: t, font: FONT })] });
const bullet = (text) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED,
  children: (Array.isArray(text) ? text : [text]).map(x => typeof x === "string" ? run(x) : run(x.t, x)) });
const note = (text, color = GREEN) => new Paragraph({ spacing: { after: 120, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED, indent: { left: 240 },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color, space: 8 } }, shading: { type: ShadingType.CLEAR, fill: SOFT2, color: "auto" },
  children: (Array.isArray(text) ? text : [text]).map(x => typeof x === "string" ? run(x, { size: 20 }) : run(x.t, { size: 20, ...x })) });
const quote = (text) => new Paragraph({ spacing: { after: 100, line: 300, lineRule: LineRuleType.AUTO }, alignment: AlignmentType.JUSTIFIED, indent: { left: 400, right: 200 },
  border: { left: { style: BorderStyle.SINGLE, size: 12, color: "BBBBBB", space: 8 } }, children: [run(text, { size: 19, italics: true, color: "333333" })] });
const spacer = (n = 120) => new Paragraph({ spacing: { after: n }, children: [] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });
const fmt = (x, d = 4) => (x == null || Number.isNaN(+x)) ? "–" : (+x).toFixed(d);
const pct = (x, d = 1) => (x == null) ? "–" : (100 * x).toFixed(d) + "%";
const num = (x) => Number(x).toLocaleString("ko-KR");
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
  const body = rows.map((r, ri) => new TableRow({ children: r.map((c, i) => cell(c, { width: widths[i], size, fill: (opt.zebra && ri % 2 === 1) ? SOFT2 : undefined, align: (opt.numCols || []).includes(i) ? AlignmentType.RIGHT : AlignmentType.LEFT })) }));
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
  MLP: "MLP(BCE)", MLP_BPR: "MLP(쌍별 손실)", MF_OBS: "관측 MF", MF: "표본 MF(가중 MSE)", MF_BPR: "BPR MF(쌍별 손실)", Random: "무작위" };
const R = Object.fromEntries(D.results.map(r => [r.method, r])), V1 = Object.fromEntries(D.v1_results.map(r => [r.method, r]));
const M = D.manifest, DS = M.dataset, PRIV = M.privacy || {}, sens = D.sensitivity;
const nAll = R.RULE.users, nAct = R.RULE.active_users, ratio = nAll / nAct;
const sensRev = sens.filter(x => x["RouterNoGender+prereq"].ndcg > x.RouterNoGender.ndcg).map(x => x.prereq_penalty);
const F = Object.fromEntries(D.facts.map(f => [f.key, f]));
const PREV = { RULE: 0.1356, RouterNoGender: 0.1343, prereq: 0.1014, MF: 0.0687, MLP: 0.0734, POP: 0.0951, catalog: 63, quiz: 16, configs: 2631, viol: 0.628, short: 0.525 };   // 1차본(2026-10-13 15:12 번들) 수치
const VERDICT_COLOR = { "수용": GREEN, "부분 수용": GOLD, "불수용": RED, "긍정 평가": BLUE };
const vrun = (v) => ({ t: v, bold: true, color: VERDICT_COLOR[v.split("(")[0].trim()] || GREY });

// ---------- 지적 목록 ----------
const CLAIMS = [
  { id: "1", sec: "1절", title: "모의 데이터 기술 통계의 ‘산술적 모순’", verdict: "불수용(표현 보완은 수용)",
    quote: "완료(50,257)·퀴즈 통과(24,187)·저장(12,825)·이탈(46,772)을 합산하면 134,041건으로 총 학습 시도 108,777건을 25,264건 초과하는 수학적 모순 … 이탈과 완료/퀴즈 통과는 동시에 성립할 수 없는데 난수 생성 로직이 통제 없이 할당했을 개연성 … 마르코프 체인 상태 전이 확률 수정과 세션 ID 기준 1NF 정규화가 선행되어야",
    facts: [
      "표 8의 네 열은 ‘한 번의 학습 시도’ 한 행에 붙는 다중 플래그(완료·퀴즈 시도·퀴즈 통과·저장·이탈)이지 서로 배타적인 이벤트 건수가 아니다. 한 시도가 ‘완료이면서 퀴즈 통과이면서 저장’일 수 있으므로 플래그 합이 행 수를 넘는 것은 모순이 아니라 정의상 당연하다. 이 스키마(study_log.csv: user, item, week, …, complete, quiz, quiz_pass, save, drop, replay)는 수업 노트북의 로그 스키마 그대로다.",
      "비판이 ‘상충’이라고 본 이탈·완료는 생성기에서 구성적으로 배타적이다. etfrec/synth.py: comp = σ(…)로 완료를 먼저 정하고, quiz = comp & …, qpass = quiz & …, drop = ~comp & …. 즉 퀴즈 통과 ⊆ 퀴즈 시도 ⊆ 완료, 이탈 ⊆ 미완료가 상태 전이로 강제된다. 세션(시도) 단위로 이미 정규화된 한 행이며 별도의 1NF 정규화 대상이 없다.",
      `실제 데이터로 확인: 모의 데이터 v2 ${num(DS.study_attempts)}건 중 완료 ${num(DS.complete)} / 미완료 ${num(DS.not_complete)}, 퀴즈 시도 ${num(DS.quiz_attempted)} ⊆ 완료, 통과 ${num(DS.quiz_pass)} ⊆ 시도, 이탈 ${num(DS.drop)} ⊆ 미완료, 저장 ${num(DS.save)}(독립). 모순 행 수: 이탈∧완료 ${DS.drop_and_complete}건, 통과∧¬퀴즈 ${DS.pass_without_quiz}건, 퀴즈∧¬완료 ${DS.quiz_without_complete}건. v1 세계(노트북 원본)도 모두 0건.`,
    ],
    why: "1차본 표 8은 ‘학습 시도 · 완료 · 퀴즈 통과 · 저장 · 이탈’을 한 줄에 나열만 하고 이 열들이 플래그라는 설명을 달지 않았다. 숫자를 읽는 사람이 배타적 건수로 오해할 여지를 남긴 것은 우리의 표현 책임이다.",
    wrong: "데이터·생성기에는 오류가 없다. 잘못된 것은 보고서의 표 설명이다.",
    fix: ["데이터 요약에 quiz_attempted·not_complete·replay 와 세 가지 논리 제약 건수(drop_and_complete, pass_without_quiz, quiz_without_complete)를 추가(etfrec/data.py Dataset.summary).",
          "학습 파이프라인 QA에 event_logic_drop_excludes_complete, event_logic_quiz_pass_requires_quiz_and_complete 검사를 추가해 매 학습마다 자동 검증(etfrec/pipeline.py run_qa). 위반 시 학습이 중단된다.",
          "중간보고서 4.4절 표를 ‘시도 → 완료/미완료 → 퀴즈 시도 → 통과, 이탈 ⊆ 미완료, 저장(독립)’의 중첩 구조로 바꾸고 논리 제약 행을 넣었다."],
    change: `QA 항목 ${PREV.qa || 80} → ${M.qa}건(모두 통과). 데이터 수치는 변하지 않았다(생성기 수정 없음).` },
  { id: "2.1", sec: "2.1절", title: "Zero-positive 사용자 산입에 따른 NDCG 왜곡", verdict: "부분 수용",
    quote: "정답 아이템이 하나도 없는 사용자는 IDCG가 0이어서 0/0 … 평가 세트에서 배제하는 것이 확립된 표준 … 활성 사용자 3,489명만으로 재산출하면 0.1343이 아니라 ≈0.247 … 알고리즘 간 미세한 성능 편차를 축소시키고 A/B 테스트의 효과 크기 추정마저 오도",
    facts: [
      "표준 관행에 대한 지적은 맞다. 1차본은 수업 노트북의 규칙(정답 없는 사용자도 NDCG 0으로 평균에 포함, QA 검사 zero_positive_label_retained)을 그대로 따랐고, 표준 규칙(제외) 값을 병기하지 않았다.",
      `그러나 ‘편차 축소·결론 왜곡’은 성립하지 않는다. 정답 없는 사용자는 어떤 방법에서도 NDCG가 정확히 0이므로, 활성 사용자 평균 = 전체 평균 × N/N_active 가 모든 방법에 같은 배율(${num(nAll)}/${num(nAct)} = ${fmt(ratio, 3)})로 적용된다. 방법 간 순위, 차이의 부호, 부트스트랩 구간의 포함 여부는 어느 규칙을 쓰든 동일하다. 2차본은 이를 QA 검사 ndcg_active_identity(ndcg_active × active_users = ndcg × users)로 매 학습마다 확인한다.`,
      `비판이 제시한 0.247은 1차본 수치 0.1343 × 6,438/3,489 의 산술이며, 2차본(카탈로그 66단원) 번들에서 운영 라우터의 활성 기준 NDCG@5는 ${fmt(R.RouterNoGender.ndcg_active)}(전체 기준 ${fmt(R.RouterNoGender.ndcg)}, 활성 ${num(nAct)}명)이다.`,
      "‘A/B 효과 크기 오도’는 성립하지 않는다. 7절의 표본 크기는 퀴즈 통과율(22% → 24%)로 계산하며 오프라인 NDCG는 그 계산에 들어가지 않는다. 비판 자체도 3절에서 그 표본 크기 산출이 ‘무결하다’고 확인했다.",
    ],
    why: "노트북과의 재현 일치(소수점 5자리)를 최우선으로 두느라 노트북 규칙만 보고했고, 독자가 다른 논문·시스템의 NDCG와 비교할 때 표준 규칙 값이 필요하다는 점을 놓쳤다. 규칙의 차이를 보고서에 설명했지만 그 설명도 ‘보수적 추정’이라는 한 문장뿐이었다.",
    wrong: "지표 계산 자체는 틀리지 않았으나 보고 방식이 불완전했다. 두 규칙을 병기하고 둘의 관계(모든 방법에 같은 배율)를 명시했어야 했다.",
    fix: ["결과 표에 ndcg_active, hit_active, active_users, difference_vs_global_active, ci_low/high_active 열을 추가(etfrec/pipeline.py record()).",
          "QA 검사 ndcg_active_identity 추가. 평가 화면(10단계)과 README·보고서 6.1·6.3·7.1절에 두 기준을 병기하고 관계를 설명.",
          "지표 정의(IDCG=0이면 0)는 노트북과 같게 유지해 재현성을 지켰다."],
    change: `운영 라우터 NDCG@5: 전체 ${fmt(R.RouterNoGender.ndcg)} / 활성 ${fmt(R.RouterNoGender.ndcg_active)}; 규칙 ${fmt(R.RULE.ndcg)} / ${fmt(R.RULE.ndcg_active)}; 인기 ${fmt(R.POP.ndcg)} / ${fmt(R.POP.ndcg_active)}; 무작위 ${fmt(R.Random.ndcg)} / ${fmt(R.Random.ndcg_active)}. 순위 동일.` },
  { id: "2.2", sec: "2.2절", title: "BCE 손실의 한계와 BPR 부재 → 딥러닝 결과 전면 무효", verdict: "부분 수용",
    quote: "BCE는 관측되지 않은 모든 항목을 절대적 0(거절)으로 가정 … 희소성 10.2%에서 예측값이 0으로 붕괴 … BPR 쌍별 손실이 표준 … BPR로 재학습하지 않는 이상 딥러닝 평가 결과는 학술적으로 전혀 유효하지 않다",
    facts: [
      "비판의 전제 중 하나가 사실과 다르다. 노트북(9주차)의 MLP는 관측된 학습 시도 행만으로 학습하며(etfrec/signals.py supervised_from_log: 레이블 = 그 시도의 퀴즈 통과 여부), 음성은 ‘시도했지만 통과하지 못한 단원’이지 ‘미관측 단원’이 아니다. 따라서 ‘미관측 = 거절’ 가정은 MLP에는 해당하지 않는다. 표본 MF(6·9주차)는 미관측 단원을 표본 0으로 쓰므로 그쪽에는 비판이 맞다.",
      `BPR을 실제로 구현해 같은 프로토콜로 비교했다(etfrec/neural.py train_mf_bpr: −ln σ(p_u·q_i − p_u·q_j), j는 사용자가 관측하지 않은 단원; fit_observed_model(kind="mlp9_bpr"): 같은 MLP 구조를 (통과 단원, 미통과 시도 단원) 쌍으로 학습). 결과 — 모의 데이터 v2: 표본 MF ${fmt(R.MF.ndcg)} → BPR MF ${fmt(R.MF_BPR.ndcg)}, MLP(BCE) ${fmt(R.MLP.ndcg)} → 쌍별 MLP ${fmt(R.MLP_BPR.ndcg)}. 노트북 원본 세계(v1): 표본 MF ${fmt(V1.MF.ndcg, 5)} → BPR MF ${fmt(V1.MF_BPR.ndcg, 5)}, MLP ${fmt(V1.MLP.ndcg, 5)} → 쌍별 MLP ${fmt(V1.MLP_BPR.ndcg, 5)}.`,
      `어느 세계에서도 쌍별 손실은 두 모델을 인기(${fmt(R.POP.ndcg)})·규칙(${fmt(R.RULE.ndcg)}) 위로 끌어올리지 못했다. 손실 함수가 ‘참패의 근본 원인’이라는 주장은 데이터로 뒷받침되지 않는다. 1차 원인은 학습 목표(시도한 단원의 통과 여부)와 평가 목표(다음 주에 어떤 단원을 골라 통과하는지)의 불일치, 그리고 밀도 10%의 희소성이다.`,
      "‘학술적으로 전혀 무효’도 과하다. 같은 후보·같은 정답·같은 후처리로 수업의 레시피를 비교한 결과는 그 레시피의 성능으로서 유효하며, 2차본은 쌍별 손실 변형을 더해 비교의 범위를 넓혔다.",
    ],
    why: "BPR을 ‘다음 단계 과제’로 미룬 이유는 수업 범위(BCE·MSE 레시피)에 맞추려 한 것과 구현 비용을 과대평가한 것이다. 실제 구현은 짧았고(쌍 표본추출 + 손실 교체), 중간 점검에서 요구될 만한 표준 비교였다.",
    wrong: "원인 분석(목표 불일치)은 맞았지만 ‘손실 함수는 원인이 아니다’를 실험 없이 주장했다. 이제는 실험으로 확인했다.",
    fix: ["etfrec/neural.py: train_mf_bpr, _observed_pairs, fit_observed_model(kind='mlp9_bpr'). etfrec/signals.py: ModelStore.get_mf_bpr, 신호 mfbpr:16:0.01·mfbpr:32:0.01, mlp9_bpr. etfrec/zoo.py: 기법군 MF_BPR·MLP_BPR. etfrec/pipeline.py: 선택 대상 기법군에 추가.",
          "노트북 재현(v1) 14개 수치는 새 기법군을 더해도 소수점 5자리까지 그대로다(scripts/regression_check.py, mismatches 0).",
          "보고서 3.1·3.2·6.2·6.3·6.7절에 BPR 결과와 해석을 추가. 테스트 test_bpr_models_train_and_rank 추가."],
    change: `설정 수 ${num(PREV.configs)} → ${num(M.configurations)}개(BPR 기법군 3개 설정). MF 계열 최고 ${fmt(Math.max(R.MF.ndcg, R.MF_BPR.ndcg, R.MF_OBS.ndcg))}, MLP 계열 최고 ${fmt(Math.max(R.MLP.ndcg, R.MLP_BPR.ndcg))} — 모두 인기 ${fmt(R.POP.ndcg)} 아래.` },
  { id: "2.3", sec: "2.3절", title: "Diversity@5(주제 불일치 쌍 비율)의 타당성", verdict: "긍정 평가",
    quote: "Ziegler 등(2005)의 ILS를 역산한 ILD와 정확히 일치 … 범주형 불일치를 거리 함수로 차용한 것은 직관적이고 합리적 … 다양성 평가 체계는 신뢰할 수 있다",
    facts: [`지적대로 simple_diversity는 Top-K 안의 단원 쌍 중 주제가 다른 쌍의 비율이다(etfrec/evaluation.py). 가드레일을 켰을 때 다양성이 ${fmt(R["RouterNoGender+prereq"].diversity, 3)}으로 오르는 데는 비판이 말한 ‘같은 주제 심화 억제’ 외에, 후보가 5개 미만이 되어 짧은 목록이 되는 효과(짧은 목록 비율 ${pct(R["RouterNoGender+prereq"].short_list_rate)})도 있음을 2차본 6.6절에 적었다.`],
    why: "", wrong: "", fix: ["조치 없음. 해석 보완만."], change: "—" },
  { id: "3", sec: "3절", title: "온라인 A/B 테스트의 검정력과 현실적 한계", verdict: "수용",
    quote: "군당 6,949 ≈ 7,000명 산출은 무결 … 3개 군 21,000명은 가입 속도에 따라 장기화되어 외생 변수가 개입 … MDE를 3%p로 타협하거나 단측 검정으로 전환하는 실리적 의사결정이 수반되어야",
    facts: ["표본 크기 산출(두 비율 Z-검정, α=5% 양측, 검정력 80%, 22%→24%)은 비판도 확인했듯 맞다. 1차본은 ‘가입 속도에 따라 4~8주’라고만 적고 3개 군을 동시에 돌릴 때의 유입 요구량과 장기화 위험을 다루지 않았다."],
    why: "표본 크기 공식에 집중해 실행 가능성(트래픽·기간·외생 충격)을 평가 계획의 일부로 보지 않았다.",
    wrong: "설계가 틀린 것은 아니지만 실행 계획이 빠져 있었다.",
    fix: ["7.3절에 MDE 2/3/4%p × 양측/단측 표본 크기 표(군당·두 군·세 군 합계)를 넣었다.", "단계적 배정: 1단계 A(인기순) vs B(운영 라우터+가드레일), 2단계 B vs C(가드레일 끔). 필요 유입을 2/3로 줄인다.", "가입 주차 코호트 층화·블록 분석, 시장 급변 주간의 사전 등록 규칙, 테스트 기간 상한 8주, 중단 규칙을 명시했다."],
    change: "표본 크기(군당, 양측): 2%p 6,950 · 3%p 약 3,200 · 4%p 약 1,850; 단측은 각각 약 20% 적다(보고서 7.3절 표)." },
  { id: "4.1", sec: "4.1절", title: "레버리지·인버스 ETP 기본예탁금 누락", verdict: "수용",
    quote: "사전교육 수강료 4,000원·1시간·이수증 등록은 현행 제도와 일치 … 그러나 기본예탁금 제도를 완벽히 누락 … 최소 1,000만원 예탁 없이는 주문이 거부 … 카드에 병기되어야",
    facts: [`검색으로 확인(2026-10-13): ${F.leverage_deposit.fact}.`, `사전교육: ${F.kifin.fact}.`,
            "1차본의 유형 카드 문구는 ‘기본예탁금 요건은 거래 증권사 안내 확인’이었다. 숫자와 ‘미달 시 주문 거부’라는 결과를 적지 않았으므로 페르소나 C 시나리오(100만원으로 레버리지 매수)의 UX 실패 지적은 정당하다."],
    why: "사전교육은 금융투자교육원 자료로 확인했지만 예탁금은 확인하지 못한 채 ‘증권사 확인’으로 넘겼다. 확인하지 못한 사실을 비워 두는 대신 교육 흐름의 관문으로 명시했어야 했다.",
    wrong: "레버리지 유형의 진입 조건 설명이 불완전했다(교육만 있고 자본 요건이 없음).",
    fix: ["etfrec/taxonomy.py LEVERAGE_RULES: 사전교육(1시간·4,000원·이수번호 등록) + 기본예탁금 1,000만원, 단일종목형 3,000만원·심화교육 1시간(2026년 8월), 해외 상장 레버리지 ETP 적용(2025년 12월), ‘예탁금 미달 시 주문 거부’를 카드 규제·주의 사항에 명시.",
          "진단 퀴즈 q20(기본예탁금), 카탈로그 개념 태그(레버리지·인버스 3: 사전교육·기본예탁금), 보고서 2.2·2.4·5.4절·용어집 반영."],
    change: "유형 카드(레버리지·인버스) 규제 문구 1줄 → 4개 요건, 주의 사항 3개." },
  { id: "4.2", sec: "4.2절", title: "ISA 계좌 완전 누락과 IRP 위험자산 70% 한도 누락", verdict: "수용(수치 정정)",
    quote: "연금저축→IRP→ISA 절세 순서 … ISA는 최대 400만원까지 전면 비과세, 초과분 9.9% 분리과세 … 만기 자금을 연금계좌로 전환하면 전환 금액의 10%(최대 300만원) 추가 세액공제 … IRP 위험자산 70% 한도가 생략되어 주식형 100% 유도 시 주문 거부",
    facts: [`검색으로 확인: ${F.isa.fact}. 비판의 ‘최대 400만원 전면 비과세’는 서민형·농어민형 기준이고 일반형은 200만원이므로 두 값을 모두 적는다.`, `IRP: ${F.irp.fact}.`,
            "1차본 카탈로그(21주제)에는 ISA 단원이 없었고 연금계좌 카드에도 위험자산 한도가 없었다. 로드맵이 ‘연금·노후’ 목적에 연금저축·IRP만 연결한 것은 절세 계좌 체계의 절반만 다룬 것이다."],
    why: "카탈로그가 수업 노트북의 20개 주제를 물려받았고, 사용자 브리프에 따라 커버드콜 주제만 더했다. 세제 영역을 ‘연금계좌’ 한 주제로 묶어 두고 계좌 체계 전체(ISA·연금저축·IRP)의 커버리지를 점검하지 않았다.",
    wrong: "절세 계좌 교육의 커버리지와 IRP 투자 한도 설명이 빠졌다.",
    fix: [`카탈로그 v2에 주제 ‘절세 계좌’ 3단원 추가(ISA 계좌란: 비과세 한도와 분리과세 / ISA 유형·납입 한도·의무가입 기간 / ISA 만기 자금의 연금계좌 전환과 절세 순서), 선수 관계(분배금 1 → ISA 1 → 2 → 3, 연금계좌 ETF 1·3 연동), 출처 태그, 개념 태그. 단원 ${PREV.catalog} → ${D.catalog.n_items}개.`,
          "로드맵 템플릿: 연금·노후(핵심 2단원 + 심화 1단원), 장기 지수(핵심 1단원), 배당·인컴(심화 1단원)에 ISA 편입. 목적 친화도에 ‘절세 계좌’ 추가.",
          "‘IRP·연금저축의 ETF 투자 규칙’ 단원을 ‘…과 위험자산 70% 한도’로 보강, 연금계좌 안내 문구(PENSION_OK)에 70% 한도·연금저축펀드 무제한·세액공제 600/900만원·연금소득세 3.3~5.5% 명시, 채권형·자산배분형 카드에 안전자산 분류·적격 TDF 예외 안내.",
          "진단 퀴즈 q17(ISA), q19(IRP 70%). 보고서 2.2·2.4·5.2·5.4절·용어집 반영."],
    change: `카탈로그 ${PREV.catalog} → ${D.catalog.n_items}단원(22주제), 선수 관계 ${D.catalog.n_prereq_edges}개, 퀴즈 ${PREV.quiz} → ${D.questions.length}문항, 연금 로드맵 ${D.roadmaps.pension.units_total}단원·약 ${D.roadmaps.pension.minutes_total}분.` },
  { id: "4.3", sec: "4.3절", title: "국내 상장 해외 ETF 과세의 ‘과표기준가’ 메커니즘 부재", verdict: "수용",
    quote: "국내 상장 해외/파생형 ETF 매도 시 세금은 ‘실제 매매차익’과 ‘과표기준가 상승분’ 중 작은 금액에 15.4% … 단기 매매 투자자에게 결정적 … ‘과표기준가와 매매차익의 딜레마’ 콘텐츠 신설 요구",
    facts: [`검색으로 확인: ${F.tax_base_price.fact}.`, "1차본은 ‘매매차익·분배금 배당소득세 15.4%(보유기간 과세)’라고만 적었다. ‘보유기간 과세’라는 용어는 썼지만 그 계산 기준(두 값 중 작은 금액)을 설명하지 않아 학습자가 ‘실제 차익 전체의 15.4%’로 이해할 수 있었다."],
    why: "세금 설명을 대부분의 요약 자료 수준(세율)에서 멈추고 과세 기준의 계산 메커니즘까지 내려가지 않았다.",
    wrong: "세율은 맞지만 과세 기준 설명이 빠져 단기 매매 페르소나에게 중요한 정보가 누락됐다.",
    fix: ["카탈로그 v2 단원 제목 보강: ‘해외 ETF 세금: 과표기준가·보유기간과세와 양도소득세’(수준 3), 개념 태그(과표기준가·보유기간과세·양도소득세·손익통산). v1 제목은 재현을 위해 유지.",
          "유형 카드 세금 문구(TAX_OTHER)에 ‘실제 차익과 과표기준가 상승분 중 작은 금액에 과세’를 명시. 진단 퀴즈 q18 신설, q13 해설 보강. 용어집에 ‘과표기준가·보유기간과세’ 추가."],
    change: "세금 관련 단원 1개 보강, 퀴즈 +1, 카드 문구 보강." },
  { id: "5.1", sec: "5.1절", title: "KRX 정보데이터시스템 비공식 엔드포인트 호출(크롤링)", verdict: "수용(약관 조항 번호는 미검증)",
    quote: "비공식 화면용 JSON 엔드포인트(getJsonData.cmd)를 직접 호출 … 이용약관 제6조·제7조의 크롤링·스크래핑 금지, 일 10,000회 초과 호출 금지 … IP 차단 유발 … KRX 직접 크롤링 모듈을 즉시 삭제하고 공공데이터포털 API로 전면 이관",
    facts: [`검색으로 확인: ${F.krx_openapi.fact}. 비판이 인용한 약관 조항 번호와 ‘일 10,000회’ 문구는 원문을 확인하지 못했으므로 우리 문서에서는 단정하지 않는다.`,
            "그러나 화면이 쓰는 비공식 엔드포인트를 프로그램으로 주기 호출하는 것이 서비스 안정성과 약관 준수 면에서 부적절하다는 지적의 본질은 타당하다. 1차본도 ‘비공식, 변경 가능’이라고 썼지만 그것을 기본 자동 수집 경로로 두었다."],
    why: "자동 수집의 편의를 약관 준수보다 앞에 두었고, 개발 환경에서 한국 도메인에 접근할 수 없어 약관을 직접 읽지 못한 채 ‘비공식’ 표시만으로 넘어갔다.",
    wrong: "비공식 화면 엔드포인트의 자동 호출을 기본 경로로 설계한 것.",
    fix: ["etfrec/sources/krx.py에서 fetch_etf_list·KRX_JSON_URL·BLD 상수를 삭제. 남은 경로는 ① 이용자가 화면에서 직접 내려받은 CSV·Excel을 정규화하는 read_krx_csv(--krx-csv), ② 공식 KRX Open API 클라이언트 KrxOpenApiClient(인증키 헤더 AUTH_KEY, 비상업 이용·재배포 금지·출처 표기, 호출 간 대기), ③ 공공데이터포털 ETF 시세 API.",
          "sync_all이 provenance.json에 policy: official-apis-and-manual-download-only 를 기록. 출처 등록부에 krx_openapi 항목 추가, krx_data 항목의 접근 방식 수정. CLI에 --krx-csv, --krx-key 추가. 테스트가 비공식 호출 함수가 없음을 확인(test_sync_uses_manual_csv_and_official_apis_only).",
          "공공데이터포털 ‘KRX상장종목정보’가 ETF를 포함하는지는 활용 가이드로 확인하지 못해 총보수·과세유형 같은 기본정보는 수동 내려받기 경로를 쓴다(보고서 4.3절에 명시)."],
    change: "비공식 호출 코드 0줄. 공식 API 2개 + 수동 CSV 1개 경로." },
  { id: "5.2", sec: "5.2절", title: "가명정보 처리 가이드라인 위반 위험(k-익명성·망 분리 부재)", verdict: "수용(법령 수치 정정)",
    quote: "단순 속성 삭제는 법적 기준 미달 … 나이·소득분위·투자 목적·접속 시간대·조회 로그가 결합되면 모자이크 효과로 재식별 … 전체 매출액의 최대 10% 징벌적 과징금(제64조의2 제1항 제6호) … k-익명성을 전처리에 삽입하고 망 분리·접근 통제를 문서에 명문화",
    facts: [`검색으로 확인: ${F.privacy_law.fact}. ‘최대 10%’는 기본 상한이 아니라 2026년 개정의 반복·중대 위반 특례이며, 비판의 조문 번호는 확인하지 못해 인용하지 않는다.`,
            `본질적 지적(준식별자 결합에 의한 재식별 위험, k-익명성, 접근 통제)은 타당하다. 2차본 구현 결과 — 라우팅 세그먼트(연령대×소득분위×성별) ${PRIV.routing ? `${PRIV.routing.groups}개 셀, 최소 ${PRIV.routing.min_group}명(k=${PRIV.routing.k} ${PRIV.routing.satisfied ? "충족" : "미충족"})` : "–"}; 준식별자 6개 조합 ${PRIV.quasi ? `${PRIV.quasi.groups}개 셀, k=${PRIV.quasi.k} 미만 ${PRIV.quasi.groups_below_k}개 셀(${num(PRIV.quasi.users_below_k)}명, ${pct(PRIV.quasi.share_below_k)})` : "–"}${PRIV.generalization && PRIV.generalization.length ? `, 일반화 계획: ${PRIV.generalization.map(g => g.drop).join(" → ")} 열 제거` : ""}.`],
    why: "가명 번호 사용과 성별 제외를 개인정보 대응의 전부로 보았고, 준식별자 결합이라는 재식별 경로를 설계 문서에서 다루지 않았다.",
    wrong: "개인정보 설계가 ‘정책 문장’ 수준에 머물고 측정 가능한 점검이 없었다.",
    fix: ["etfrec/privacy.py 신설: k_anonymity(열 조합별 최소 그룹·k 미만 셀·사용자 비율), generalization_plan(k를 만족할 때까지 열 제거 제안), privacy_audit(라우팅 k=20, 준식별자 k=5), 최소화·가명처리·접근 통제·보관 정책 8항목.",
          "학습 파이프라인이 매 학습마다 privacy_audit를 실행해 번들 manifest.privacy 에 기록하고 평가 화면(10단계)에 표시. 보고서 4.5절에 점검 표와 제도 근거(3%·10% 특례·가이드라인 개정일)를 정정해 기술.",
          "운영 정책: 원시 연령·연소득은 저장하지 않고 구간만 저장, 접속 시각은 4개 시간대, 가명 매핑표 분리 보관, 가명처리·모델 학습 담당의 권한·망 분리, 보관 기간·삭제, 재식별 금지."],
    change: "개인정보 점검 자동화 0 → 2종(라우팅·준식별자), 정책 8항목 문서화." },
  { id: "서론·결론", sec: "서론·결론", title: "‘실제 서비스 배포에 치명적 결함’이라는 총평", verdict: "부분 수용",
    quote: "통계적·알고리즘적·금융 도메인적·법률적 오류 … 네 가지 핵심 도메인(이벤트 정규화, BPR·활성 NDCG, 세금·규제 보강, k-익명성·합법 API)을 수정·내재화할 것을 강력히 권고",
    facts: ["도메인·법률 지적(4.1~5.2)은 모두 수용해 코드와 문서에 반영했다. 통계·알고리즘 지적(1, 2.1, 2.2)은 전제에 사실 오류가 있어 근거와 함께 정정하되, 표현 보완·병기·추가 실험으로 비판의 취지는 반영했다.",
            "중간보고서는 모의 데이터 기반 프로토타입이며 ‘실서비스 효과 검증이 아니다’를 1차본부터 명시했다. 배포 가능성 판단은 실제 로그·법률 검토 뒤의 일이다."],
    why: "", wrong: "", fix: ["이 문서와 중간보고서 2차본."], change: "—" },
];

// ---------- 문서 ----------
const body = [];
const add = (...xs) => xs.flat().forEach(x => body.push(x));
add(spacer(1600),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run("ETF 교육 콘텐츠 개인화 추천 시스템", { size: 24, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [run("중간보고서 비판 검토 및 보완 보고서", { size: 42, bold: true, color: GREEN })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [run("지적 11건의 텍스트 단위 분석 · 사실 확인 · 판정(수용/부분 수용/불수용) · 간과 이유 · 보완 내역 · 수치 변화", { size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("작성일: 2026년 10월 13일 (검토 대상: 중간보고서 1차본, 비판 문서 ‘심층 검증 및 비판적 분석 보고서’)", { size: 21 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [run("작성자: (이름 · 학번 기입)", { size: 21 })] }),
  spacer(1200),
  note([{ t: "결론. ", bold: true }, `11건 중 수용 6건(3, 4.1, 4.2, 4.3, 5.1, 5.2), 부분 수용 3건(2.1, 2.2, 총평), 불수용 1건(1절 ‘산술 모순’ — 사실관계 오류, 표현 보완만 수용), 긍정 평가 1건(2.3). 수용한 항목은 모두 코드·데이터·문서에 반영해 재학습하고 재검증했다(자동화 테스트 26건, 학습 QA ${M.qa}건, 노트북 재현 14개 수치 일치). 가장 뼈아픈 지적은 금융 도메인(기본예탁금·ISA·IRP 70%·과표기준가)과 데이터 접근 방식(비공식 엔드포인트)으로, 공통 원인은 ‘확인하지 못한 사실을 비워 두거나 완곡하게 넘긴 것’이었다. 통계·알고리즘 지적은 활성 사용자 기준 NDCG 병기와 BPR 쌍별 손실 비교로 취지를 반영했지만, ‘모순·무효’라는 결론 자체는 데이터와 코드로 반박한다.`]),
  pageBreak(),
  new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { after: 160 }, children: [new TextRun({ text: "목차", font: FONT })] }),
  new TableOfContents("목차", { hyperlink: true, headingStyleRange: "1-2" }),
  p("※ Word에서 열면 목차 필드 갱신을 묻는 창이 뜹니다. ‘예’를 누르면 페이지 번호가 채워집니다.", { size: 18, color: GREY }),
  pageBreak(),
);

add(h1("1. 요약표"),
  ...table(["#", "지적(비판 문서 절)", "판정", "핵심 근거", "보완(코드 · 문서)"], CLAIMS.map(c => [c.id, c.title, [vrun(c.verdict)], c.facts[0].slice(0, 150) + (c.facts[0].length > 150 ? "…" : ""), c.fix[0].slice(0, 120) + (c.fix[0].length > 120 ? "…" : "")]),
    [0.8, 2.8, 1.6, 3.8, 3.5], { caption: "지적별 판정 요약", size: 15, zebra: true }),
  p("판정 기준: ‘수용’ = 지적이 사실이고 우리 결과물에 결함이 있어 고쳤다. ‘부분 수용’ = 요구는 반영했으나 지적의 전제나 결론 일부가 사실과 달라 정정한다. ‘불수용’ = 지적의 사실관계가 틀렸다(단, 오해를 부른 표현은 고친다). ‘긍정 평가’ = 비판이 타당성을 인정한 항목."),
);

add(h1("2. 검토 방법"),
  bullet([{ t: "텍스트 단위 분해: ", bold: true }, "비판 문서를 절 단위로 나누고, 각 절에서 (a) 사실 주장, (b) 우리 결과물에 대한 평가, (c) 요구 사항을 분리했다. 한 절에 여러 요구가 있으면(예: 4.2절의 ISA와 IRP 70%) 모두 따로 다뤘다."]),
  bullet([{ t: "코드 대조: ", bold: true }, "주장이 가리키는 코드(파일·함수)를 직접 읽어 확인했다. 예: 이벤트 생성 규칙(etfrec/synth.py), MLP 레이블(etfrec/signals.py supervised_from_log), NDCG 정의(etfrec/evaluation.py), KRX 수집(etfrec/sources/krx.py)."]),
  bullet([{ t: "외부 사실 확인: ", bold: true }, "금융·세제·법령 주장은 2026년 10월 13일 기준 웹 검색으로 확인했고(부록 A), 확인하지 못한 세부(약관 조항 번호, 법 조문 번호)는 우리 문서에 단정하지 않았다. 개발 환경에서 한국 기관 사이트 본문을 직접 열 수 없어 검색 결과 요약에 의존한 한계가 있으므로, 최종 보고서 전에 원문 대조를 일정에 넣었다."]),
  bullet([{ t: "보완과 재검증: ", bold: true }, `수용 항목은 코드와 문서에 반영한 뒤 전체를 다시 학습했다(모의 데이터 v2, 설정 ${num(M.configurations)}개, QA ${M.qa}건 통과). 노트북 원본 세계(v1)는 새 기법군을 더해도 14개 수치가 소수점 5자리까지 일치함을 확인했다. 자동화 테스트 26건이 통과한다.`]),
  bullet([{ t: "독립 검토: ", bold: true }, "판정의 편향을 줄이기 위해 각 판정을 비판 문서와 코드에 대조하는 독립 검토(회의적 검토자 11명 분량)와 변경 코드의 결함 검토(4개 관점)를 별도로 수행해 발견 사항을 반영했다(5절)."]),
);

add(pageBreak(), h1("3. 항목별 분석"));
CLAIMS.forEach(c => {
  add(h2(`3.${c.id} ${c.title}`),
    p([{ t: "판정: ", bold: true }, vrun(c.verdict), { t: `   (비판 문서 ${c.sec})`, color: GREY, size: 18 }]),
    h3("비판 요지"), quote(c.quote),
    h3("사실 확인"), ...c.facts.map(f => bullet(f)));
  if (c.why) add(h3("왜 간과했는가"), p(c.why));
  if (c.wrong) add(h3("무엇이 잘못되었나"), p(c.wrong));
  add(h3("보완 내용"), ...c.fix.map(f => bullet(f)), h3("결과 변화"), p(c.change));
});

add(pageBreak(), h1("4. 불수용·정정 항목의 근거 정리"),
  ...table(["비판의 주장", "우리의 판단", "근거"], [
    ["이벤트 합(134,041) > 시도(108,777)는 산술 모순이며 생성기 난수 로직 결함", "불수용", "열은 한 시도의 다중 플래그. 생성기가 완료→퀴즈→통과, 미완료→이탈의 상태 전이로 배타성을 강제. 모순 행 0건을 QA로 상시 검증"],
    ["이탈과 완료·통과가 동시에 성립하는 행이 있을 ‘개연성’", "불수용", `drop_and_complete = ${DS.drop_and_complete}건, pass_without_quiz = ${DS.pass_without_quiz}건 (v1·v2 모두 0)`],
    ["세션 ID 기준 1NF 정규화·마르코프 체인 전이 확률 수정 필요", "불수용", "로그는 이미 시도(세션) 단위 한 행이며, 생성 규칙이 곧 상태 전이 확률이다. 바꿀 결함이 없다"],
    ["정답 없는 사용자 0 산입이 방법 간 미세 편차를 축소", "불수용", `모든 방법에 같은 배율(${fmt(ratio, 3)})이 곱해지므로 순위·차이의 부호·구간 포함 여부가 불변(QA ndcg_active_identity)`],
    ["이 산입 방식이 A/B 효과 크기 추정을 오도", "불수용", "A/B 표본 크기는 퀴즈 통과율(22%→24%)로 계산하며 NDCG와 무관. 비판 3절도 그 계산을 ‘무결’로 확인"],
    ["MLP가 미관측 항목을 0(거절)으로 가정", "불수용(표본 MF에는 해당)", "supervised_from_log는 관측된 시도 행만 쓰고 음성 = 시도했지만 미통과. 표본 MF는 미관측 표본 0을 쓰므로 그쪽은 맞음"],
    ["BPR 없이는 딥러닝 결과가 학술적으로 전혀 무효", "불수용(BPR은 추가)", `BPR MF ${fmt(R.MF_BPR.ndcg)} vs 표본 MF ${fmt(R.MF.ndcg)}, 쌍별 MLP ${fmt(R.MLP_BPR.ndcg)} vs MLP ${fmt(R.MLP.ndcg)}: 손실을 바꿔도 인기 ${fmt(R.POP.ndcg)} 아래. 원인은 목표 불일치·희소성`],
    ["ISA는 최대 400만원까지 전면 비과세", "정정", "일반형 200만원, 서민형·농어민형 400만원. 초과분 9.9% 분리과세"],
    ["개인정보 과징금은 전체 매출액의 최대 10%(제64조의2 제1항 제6호)", "정정", "기본 상한 3%(2023년 시행). 10%는 2026년 3월 개정의 반복·중대 위반 특례(9월 시행). 조문 번호는 미확인"],
    ["KRX 약관 제6조·제7조, 일 10,000회 초과 호출 금지", "미검증(조치는 수용)", "원문을 확인하지 못해 인용하지 않음. 비공식 엔드포인트 자동 호출 제거는 약관 문구와 무관하게 타당하므로 실행"],
    ["금융투자교육원 사전교육이 ‘2026년 기준 현행과 일치’", "보충", "레버리지 ETP 가이드 과정 1시간·4,000원은 맞고, 2026년 신설된 단일종목 레버리지·인버스 사전교육(1시간 추가, 8월 평가 강화)을 추가 반영"],
  ], [4.2, 1.8, 6.5], { caption: "불수용·정정 항목", size: 16, zebra: true }),
);

add(h1("5. 독립 검토 결과의 반영"),
  p("판정과 코드 변경을 독립적으로 검토한 결과(회의적 검토자 11명 분량 + 코드 검토 4개 관점 + 누락 점검 1)는 부록 C에 요약했다. 검토에서 나온 발견 사항 가운데 코드 결함은 즉시 고쳤고, 문서상 보강 요구는 이 문서와 중간보고서 2차본에 반영했다. 반영하지 않은 발견은 이유를 함께 적었다."),
  p("(이 절의 상세 내용은 검토 완료 후 채워진다.)", { color: GREY, size: 18 }),
);

add(h1("6. 보완 전후 비교"),
  ...table(["항목", "1차본(10월 13일 15시 번들)", "2차본(현재)", "비고"], [
    ["카탈로그", `${PREV.catalog}단원(21주제)`, `${D.catalog.n_items}단원(${D.catalog.n_topics}주제), 선수 관계 ${D.catalog.n_prereq_edges}개`, "절세 계좌(ISA) 3단원 신설, 세제 단원 2개 제목 보강"],
    ["진단 퀴즈", `${PREV.quiz}문항`, `${D.questions.length}문항`, "ISA·과표기준가·IRP 70%·기본예탁금"],
    ["설정 풀", `${num(PREV.configs)}개`, `${num(M.configurations)}개`, "MF_BPR 2 + MLP_BPR 1"],
    ["오프라인 지표", "NDCG@5(전체 기준)만", "전체·활성 사용자 기준 병기 + 항등식 QA", `활성 ${num(nAct)}명 / 전체 ${num(nAll)}명`],
    ["운영 설정", "규칙[관심 주제+수준 일치+투자 목적 일치]", D.operational_name, "카탈로그가 바뀌어 검증 1위 설정이 달라짐"],
    ["운영 라우터 NDCG@5", `${fmt(PREV.RouterNoGender)}(전체)`, `${fmt(R.RouterNoGender.ndcg)}(전체) / ${fmt(R.RouterNoGender.ndcg_active)}(활성)`, "카탈로그·단원 수가 달라 직접 비교 불가"],
    ["선수 가드레일 비용", `NDCG ${fmt(PREV.RouterNoGender - PREV.prereq, 3)} 감소, 짧은 목록 ${pct(PREV.short)}`, `NDCG ${fmt(R.RouterNoGender.ndcg - R["RouterNoGender+prereq"].ndcg, 3)} 감소, 짧은 목록 ${pct(R["RouterNoGender+prereq"].short_list_rate)}`, `선수 위반 ${pct(PREV.viol, 0)} → ${pct(R.RouterNoGender.prereq_violation_rate, 0)}(가드레일 끔 기준)`],
    ["MF / MLP 계열 최고", `${fmt(PREV.MF)} / ${fmt(PREV.MLP)}`, `${fmt(Math.max(R.MF.ndcg, R.MF_BPR.ndcg, R.MF_OBS.ndcg))} / ${fmt(Math.max(R.MLP.ndcg, R.MLP_BPR.ndcg))}`, "쌍별 손실 추가 후에도 인기 아래"],
    ["KRX 수집", "화면용 비공식 JSON 자동 호출", "수동 내려받기 CSV + KRX Open API(인증키) + 공공데이터포털", "provenance.policy 기록"],
    ["개인정보", "가명 번호·성별 제외 정책 문장", "k-익명성 자동 점검(라우팅 k=20, 준식별자 k=5) + 정책 8항목", PRIV.quasi ? `준식별자 k 미만 셀 ${PRIV.quasi.groups_below_k}개` : "–"],
    ["유형 카드 규제 문구", "사전교육만", "사전교육 + 기본예탁금(1,000만/3,000만) + 해외 레버리지 ETP + 주문 거부 안내", ""],
    ["A/B 계획", "군당 7,000명, 4~8주", "MDE별 표본 표, 단계적 배정, 코호트 층화, 기간 상한", ""],
    ["QA · 테스트", "QA 80건, 테스트 23건", `QA ${M.qa}건, 테스트 26건`, "이벤트 논리·항등식·BPR·수집 정책·k-익명성 검사 추가"],
  ], [2.2, 3.2, 4.2, 3.2], { caption: "보완 전후 비교", size: 16, zebra: true }),
  p("주의: 카탈로그가 63단원에서 66단원으로 바뀌고 생성기가 새 단원을 포함해 세계를 다시 만들었으므로, 1차본과 2차본의 절대 수치는 같은 세계의 비교가 아니다. 방법 간 순서(규칙 ≈ 운영 라우터 > 인구통계 미사용 > 사용자 CF·인기 > MLP·CF·콘텐츠 > MF 계열 > 무작위)와 결론은 두 번들에서 같다."),
);

add(h1("7. 남은 한계와 후속 계획"),
  bullet("세제·규제 문구는 검색으로 확인한 범위이며, 최종 보고서 전에 법령·기관 공지 원문(금융위원회 보도자료, 국세청 안내, 금융투자교육원 공지, KRX 이용약관)을 직접 대조한다(11월 2주)."),
  bullet("공공데이터포털 ‘KRX상장종목정보’가 ETF를 포함하는지, KRX Open API의 ETF 일별매매정보 엔드포인트 경로가 활용 가이드와 일치하는지는 키 발급 후 실제 호출로 확인한다(11월 1주)."),
  bullet("BPR 쌍별 손실은 추가했지만 ‘다음 주 선택·통과’를 직접 레이블로 쓰는 학습, 목적·로드맵 단계를 입력 특징으로 넣는 모델은 아직 비교하지 않았다. 선수 페널티 보정 실험과 함께 11월 3주에 수행한다."),
  bullet("k-익명성 점검은 모의 데이터에서 실행한 것이다. 실제 로그에서는 접속 시간대·관심 주제까지 준식별자에 넣어 다시 계산하고, k 미만 셀의 일반화 규칙을 운영 문서로 확정한다."),
  bullet("ISA 단원은 제목·개념·출처·퀴즈까지 설계했지만 실제 강의 콘텐츠(본문)는 전국투자자교육협의회 연금스쿨·생애자산관리스쿨 자료에 연결하는 단계가 남아 있다."),
);

add(pageBreak(), h1("부록 A. 사실 확인 출처"),
  ...table(["항목", "확인한 사실", "출처(2026-10-13 검색)"], D.facts.map(f => [f.key, f.fact, f.sources.join(" ; ")]), [1.5, 6, 5.3], { caption: "사실 확인 목록", size: 15, zebra: true }),
  p("모든 출처는 검색 결과 요약으로 확인했으며 기관 사이트 본문은 개발 환경의 네트워크 제한으로 직접 열지 못했다. 블로그·언론 출처는 공식 자료로 재확인이 필요하다.", { size: 18, color: GREY }),
);

add(h1("부록 B. 변경 파일 요약"),
  p("코드 변경(2차본): etfrec/neural.py(BPR MF, 쌍별 MLP), etfrec/signals.py(BPR 신호·모델 캐시), etfrec/zoo.py(MF_BPR·MLP_BPR 기법군), etfrec/pipeline.py(활성 사용자 지표, 이벤트 논리·항등식 QA, 개인정보 점검 기록), etfrec/data.py(요약 필드), etfrec/catalog.py(절세 계좌 주제, 세제 단원 제목·개념), etfrec/taxonomy.py(기본예탁금·ISA·IRP 70%·과표기준가 문구, 템플릿·친화도), etfrec/quiz.py(q17~q20, q13), etfrec/sources/krx.py·sync.py·registry.py·cli.py(비공식 호출 제거, Open API·수동 CSV), etfrec/privacy.py(신설), etfrec/service.py·ui/app.js(활성 NDCG·개인정보 점검 표시), tests/(26건), README.md, scripts/ui_walkthrough.mjs."),
  ...(D.changes ? [new Paragraph({ spacing: { after: 40 }, indent: { left: 240 }, shading: { type: ShadingType.CLEAR, fill: "F1F3F0", color: "auto" }, children: [new TextRun({ text: D.changes.split("\n").slice(0, 60).join("\n"), font: "Consolas", size: 15 })] })] : []),
);

add(h1("부록 C. 독립 검토 요약"),
  p("(검토 완료 후 채워진다.)", { color: GREY, size: 18 }),
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
