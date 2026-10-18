/* 학습 설계 스튜디오 — 프런트엔드(의존성 없음). 모든 계산은 /api 로 서버에 맡긴다. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const STEP_NAMES = ["아이디어 스케치", "기본 정보·목적", "진단", "학습 기록", "학습 로드맵", "추천 설정", "추천 미리보기", "시뮬레이션", "ETF 유형 연결", "비교·평가", "저장·내보내기"];
  const N_STEPS = STEP_NAMES.length;
  const LEVEL_NAME = { 1: "기초", 2: "구조·계산", 3: "심화·위험" };
  const RISK_NAME = ["안정", "중립", "적극"];
  const STATUS_KO = { passed: "통과", available: "학습 가능", locked: "잠김" };
  const DEFAULT_LEARNER = { label: "", age: null, gender: 0, income: null, exp: 0, risk: 1, mobile: 1, interests: [], placement: 1, hour: 4, goal: "long_term", horizon: "mid", diagnosis: null, events: [] };
  const DEFAULT_SETTINGS = { k: 5, algorithm: "", block_gap: 2, plus_one_max: 1, exclude_passed: true, prereq_block: true, topic_cap: "" };

  const state = {
    step: 1, source: "new", learnerId: null, learnerInfo: null,
    learner: { ...DEFAULT_LEARNER },
    nl: { text: "", parsed: null },
    quiz: { answers: {}, result: null },
    settings: { ...DEFAULT_SETTINGS },
    sim: { assume: [], gender: false, income_q: "", age_band: "", level: "" },
    types: { includeAssume: true },
    result: null, simResult: null, compare: null, roadmap: null, typesResult: null,
    touched: { placement: false, goal: false }, memo: "", zoom: 100,
  };
  let META = null, CATALOG = null, EXAMPLES = [], EVAL = null, QUIZ = null, SOURCES = null;
  const VOLATILE = { result: null, simResult: null, compare: null, roadmap: null, typesResult: null, learnerInfo: null };

  // ---------- 유틸 ----------
  async function api(path, body, method) {
    const opt = { method: method || (body ? "POST" : "GET"), headers: { "Content-Type": "application/json" } };
    if (body) opt.body = JSON.stringify(body);
    const r = await fetch(path, opt);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
    return data;
  }
  function toast(msg, ms = 2600) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(t._t); t._t = setTimeout(() => (t.hidden = true), ms); }
  function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function save() { try { localStorage.setItem("etfrec-draft", JSON.stringify({ ...state, ...VOLATILE })); } catch (e) { } }
  function load() { try { const d = JSON.parse(localStorage.getItem("etfrec-draft") || "null"); if (d) Object.assign(state, d); } catch (e) { } migrate(); }
  function migrate() {   // 이전 버전의 초안에 없는 항목을 기본값으로 채운다
    state.learner = { ...DEFAULT_LEARNER, ...(state.learner || {}) };
    state.settings = { ...DEFAULT_SETTINGS, ...(state.settings || {}) };
    state.quiz = { answers: {}, result: null, ...(state.quiz || {}) };
    state.types = { includeAssume: true, ...(state.types || {}) };
    state.touched = { placement: false, goal: false, ...(state.touched || {}) };
    if (!state.sim) state.sim = { assume: [], gender: false, income_q: "", age_band: "", level: "" };
    Object.assign(state, VOLATILE);
    state.step = Math.max(1, Math.min(N_STEPS, +state.step || 1));
  }
  function invalidate() { state.result = null; state.simResult = null; state.compare = null; state.roadmap = null; state.typesResult = null; }
  function download(name, text, type = "application/json") {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); a.remove();
  }
  function item(i) { return CATALOG.items[i]; }
  function fmt(x, d = 4) { return x == null ? "–" : Number(x).toFixed(d); }
  function pct(x) { return Math.round((x || 0) * 100) + "%"; }
  function riskDots(r) { return "●".repeat(r) + "○".repeat(Math.max(0, 5 - r)); }
  function sourceLinks(list) {
    return (list || []).map(s => s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener" title="${esc(s.menu || "")}">${esc(s.name)}</a>` : esc(s.name)).join(" · ");
  }
  function isExisting() { return state.source === "existing" && state.learnerId != null; }
  function learnerRef() {
    const L = state.learner;
    if (isExisting()) return { learner_id: state.learnerId };
    const events = L.events.map(e => ({ item: e.item, week: e.week || 0, complete: !!e.complete, quiz: !!e.quiz, quiz_pass: !!e.quiz_pass, save: !!e.save, drop: !!e.drop, replay: !!e.replay }));
    return { learner: { label: L.label || "새 학습자", age: L.age ?? 35, gender: L.gender, income: L.income, exp: L.exp, risk: L.risk, mobile: L.mobile, interests: L.interests, placement: L.placement, hour: L.hour, goal: L.goal, horizon: L.horizon, diagnosis: L.diagnosis, events } };
  }
  function buildRequest(extra = {}) {
    const S = state.settings;
    return { k: S.k, algorithm: S.algorithm || null, guardrail: { block_gap: S.block_gap, plus_one_max: S.plus_one_max, exclude_passed: S.exclude_passed, prereq_block: S.prereq_block }, topic_cap: S.topic_cap ? +S.topic_cap : null, ...learnerRef(), ...extra };
  }

  // ---------- 체크리스트·스테퍼 ----------
  function checklistItems() {
    const L = state.learner, ex = isExisting();
    return [
      ["학습자 출처 지정", true],
      ["투자 목적·기간 지정", ex || state.touched.goal],
      ["기본 정보 입력", ex || L.age != null],
      ["관심 주제 1~2개", ex || L.interests.length > 0],
      ["진단 수준(퀴즈 또는 직접)", ex || state.touched.placement],
      ["학습 기록(선택)", ex || L.events.length > 0],
      ["로드맵 확인", !!state.roadmap],
      ["추천 계산 완료", !!state.result],
      ["ETF 유형 연결 확인", !!state.typesResult],
    ];
  }
  function renderChecklist() {
    const items = checklistItems(); const done = items.filter(x => x[1]).length;
    $("#checklist-summary").textContent = `${done}/${items.length} 완료 · ${$("#checklist-items").hidden ? "항목 펼쳐 보기" : "접기"}`;
    $("#checklist-items").innerHTML = items.map(([n, ok]) => `<li class="${ok ? "done" : ""}"><span class="dot">${ok ? "✓" : ""}</span>${n}</li>`).join("");
  }
  function renderStepper() {
    $("#stepper").innerHTML = STEP_NAMES.map((n, i) => `<li data-step="${i + 1}" class="${i + 1 === state.step ? "active" : ""} ${i + 1 < state.step ? "done" : ""}"><span class="num">${i + 1}</span><span class="name">${n}</span></li>`).join("");
    $$("#stepper li").forEach(li => li.onclick = () => goStep(+li.dataset.step));
    $("#nav-indicator").textContent = `${state.step}/${N_STEPS} · ${STEP_NAMES[state.step - 1]}`;
    $("#nav-prev").disabled = state.step === 1; $("#nav-next").textContent = state.step === N_STEPS ? "처음으로" : "다음 →";
  }
  async function goStep(n) {
    state.step = Math.max(1, Math.min(N_STEPS, n));
    $$(".step").forEach(s => s.hidden = +s.dataset.step !== state.step);
    renderStepper(); renderChecklist(); save();
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (state.step >= 2 && state.step <= 10) await ensureLearnerInfo();
    if (state.step === 2) renderBasic();
    if (state.step === 3) { renderTopics(); renderQuiz().catch(e => toast(e.message)); }
    if (state.step === 4) renderEvents();
    if (state.step === 5) loadRoadmap().catch(() => { });
    if (state.step === 6) renderSettings();
    if (state.step === 7 && !state.result) runRecommend().catch(() => { });
    if (state.step === 8) renderSimControls();
    if (state.step === 9) loadTypes().catch(() => { });
    if (state.step === 10) { renderCompare(); if (!EVAL) loadEvaluation(); }
    if (state.step === 11) { listDesigns(); $("#design-memo").value = state.memo; }
  }

  // ---------- 1단계 ----------
  function renderExamples() {
    $("#example-grid").innerHTML = EXAMPLES.map((e, i) => `<div class="example"><h4>${esc(e.title)}</h4><p>${esc(e.text)}</p><div><button class="btn small" data-ex="${i}">입력창에 넣기</button></div></div>`).join("");
    $$("[data-ex]").forEach(b => b.onclick = () => { $("#nl-text").value = EXAMPLES[+b.dataset.ex].text; state.nl.text = $("#nl-text").value; $("#nl-text").focus(); });
  }
  async function parseNL() {
    const text = $("#nl-text").value.trim(); if (!text) return toast("문장을 먼저 적어 주세요");
    const p = await api("/api/parse", { text });
    state.nl = { text, parsed: p };
    const f = p.fields; const L = state.learner;
    if (f.interests) L.interests = f.interests.slice(0, 2);
    for (const k of ["placement", "exp", "risk", "mobile", "hour", "gender", "age", "income", "goal", "horizon"]) if (f[k] != null) L[k] = f[k];
    if (f.placement != null) state.touched.placement = true;
    if (f.goal != null || f.horizon != null) state.touched.goal = true;
    if (f.events) L.events = f.events;
    if (f.k) state.settings.k = f.k;
    state.source = "new"; $$("input[name=source]").forEach(r => r.checked = r.value === "new"); $("#existing-picker").hidden = true;
    const names = { interests: "관심 주제", placement: "진단 수준", exp: "투자 경험", risk: "위험성향", mobile: "기기", hour: "학습 시간대", gender: "성별", age: "연령", income: "연소득(만원)", k: "추천 개수", events: "학습 기록", goal: "투자 목적", horizon: "투자 기간" };
    const show = (e) => e.field === "goal" ? (META.goals[e.value] || e.value) : e.field === "horizon" ? (META.horizons[e.value] || e.value) : Array.isArray(e.value) ? e.value.join(", ") : e.value;
    $("#nl-table").innerHTML = `<tr><th>항목</th><th>읽어 낸 값</th><th>근거가 된 표현</th></tr>` + p.evidence.map(e => `<tr><td>${names[e.field] || e.field}</td><td>${esc(show(e))}</td><td class="muted">${esc(e.matched)}</td></tr>`).join("");
    $("#nl-warnings").textContent = p.warnings.join(" ");
    $("#nl-result").hidden = false; invalidate(); renderChecklist(); save();
    toast(`${p.evidence.length}개 조건을 읽었습니다. 2단계에서 확인하세요`);
  }
  let searchSeq = 0;
  async function searchLearners() {
    const q = $("#learner-query").value.trim(); const seq = ++searchSeq;
    const r = await api(`/api/learners?q=${encodeURIComponent(q)}&limit=12`);
    if (seq !== searchSeq) return;   // 더 늦게 보낸 검색 결과가 이미 그려졌으면 이전 응답은 버린다
    $("#learner-results").innerHTML = (r.items.length ? "" : `<div class="muted small">검색 결과가 없습니다</div>`) + r.items.map(u =>
      `<div class="learner-card ${u["학습자"] === state.learnerId ? "selected" : ""}" data-uid="${u["학습자"]}"><span>#${u["학습자"]} · ${esc(u["성별"])} ${esc(u["연령대"] ?? "")} · ${esc(u["소득분위"] ?? "")} · ${esc(u["투자 목적"] || "")} · ${esc(u["투자 경험"])}/${esc(u["위험성향"])}/${esc(u["기기"])} · 관심 ${esc(u["관심 주제"])} · 조회 ${u["조회 수"]} · 수준 ${u["추정 수준"]}</span><button class="btn small">선택</button></div>`).join("");
    $("#learner-results").insertAdjacentHTML("afterbegin", `<div class="muted small">${r.total}명 중 ${r.items.length}명 표시</div>`);
    $$("#learner-results .learner-card button").forEach(b => b.onclick = () => selectLearner(+b.parentElement.dataset.uid));
  }
  async function selectLearner(uid) {
    state.learnerId = uid; state.source = "existing"; invalidate(); state.learnerInfo = null;
    await ensureLearnerInfo();
    $$(".learner-card").forEach(c => c.classList.toggle("selected", +c.dataset.uid === uid));
    renderChecklist(); save(); toast(`학습자 #${uid}를 불러왔습니다`);
  }
  async function ensureLearnerInfo() {
    if (isExisting() && (!state.learnerInfo || state.learnerInfo.user !== state.learnerId)) {
      try { state.learnerInfo = await api(`/api/learners/${state.learnerId}`); } catch (e) { state.learnerId = null; state.learnerInfo = null; toast(e.message); }
    }
    return state.learnerInfo;
  }

  // ---------- 2단계 ----------
  function goalNote() {
    const L = state.learner; const tpl = (META.templates || {})[L.goal];
    const types = tpl ? tpl.types.map(k => META.type_names[k] || k).join(", ") : "";
    return `<b>${esc(META.goals[L.goal])}</b> · ${esc(META.horizons[L.horizon])} · ${RISK_NAME[L.risk]} 성향 → 로드맵 '목적별 핵심 개념' 단계가 이 목적에 맞게 구성되고, 마지막 단계에서 <b>${esc(types)}</b> 유형으로 연결됩니다.`;
  }
  function renderBasic() {
    const L = state.learner, ex = isExisting() && state.learnerInfo;
    $("#existing-profile").hidden = !ex; $("#basic-form").hidden = !!ex;
    if (ex) {
      const p = state.learnerInfo.profile; const seg = state.learnerInfo.segment;
      $("#existing-profile").innerHTML = `<h3>학습자 #${state.learnerId} 프로필 (스냅샷 ${state.learnerInfo.snapshot_week}주차 기준)</h3><div class="kv">` +
        ["투자 목적", "투자 기간", "위험성향", "성별", "연령대", "소득분위", "투자 경험", "기기", "학습 시간대", "관심 주제", "조회 수", "퀴즈 통과율", "완료율", "이탈률", "추정 수준", "선호 1위 주제", "통과 단원 수"].map(k => `<div><span class="muted">${k}</span><b>${esc(p[k] ?? "–")}</b></div>`).join("") +
        `</div><p class="small muted">세그먼트: ${Object.values(seg).map(s => esc(s.label)).join(" · ")}</p><button class="btn small" id="copy-as-new">이 프로필을 새 학습자로 복사</button>`;
      $("#copy-as-new").onclick = () => {
        const ev = state.learnerInfo.history.map(h => ({ item: h.item, week: h.week, complete: h.complete, quiz: h.quiz, quiz_pass: h.quiz_pass, save: h.save, drop: h.drop, replay: h.replay }));
        const B = state.learnerInfo.bands || {}; const BA = B.age_band || {}, BI = B.income_q || {};   // 번들에는 원값이 없다: 구간 대표값으로 채운다
        Object.assign(L, { label: `#${state.learnerId} 복사본`, age: BA.representative ?? null, gender: p["성별"] === "여성" ? 1 : 0, income: BI.representative ?? null, exp: ["없음", "1~3년", "3년 이상"].indexOf(p["투자 경험"]), risk: RISK_NAME.indexOf(p["위험성향"]), mobile: p["기기"] === "모바일" ? 1 : 0, interests: state.learnerInfo.interest_ids.filter(x => x >= 0), placement: state.learnerInfo.placement, goal: state.learnerInfo.goal || "long_term", horizon: state.learnerInfo.horizon || "mid", diagnosis: null, events: ev });
        state.source = "new"; state.touched.placement = true; state.touched.goal = true; invalidate(); $$("input[name=source]").forEach(r => r.checked = r.value === "new"); renderBasic();
        const bandNote = `연령 ${BA.representative ?? "–"}세·연소득 ${BI.representative != null ? Number(BI.representative).toLocaleString("ko-KR") + "만원" : "–"}은 학습자 #${state.learnerId}의 원값이 아니라 구간 대표값입니다(${esc(BA.label || "연령대 미상")} · ${esc(BI.label || "소득분위 미상")}). 번들은 원시 연령·연소득을 보관하지 않습니다.`;
        $("#band-rep-note")?.remove(); $("#basic-form").insertAdjacentHTML("afterbegin", `<p class="note small" id="band-rep-note">${bandNote}</p>`);
        toast("새 학습자로 복사했습니다. 연령·소득은 구간 대표값입니다. 수정 후 추천을 계산하세요", 5000);
      };
      return;
    }
    $("#f-goal").innerHTML = Object.entries(META.goals).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
    $("#f-horizon").innerHTML = Object.entries(META.horizons).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
    $("#f-goal").value = L.goal; $("#f-horizon").value = L.horizon;
    $("#f-label").value = L.label || ""; $("#f-age").value = L.age ?? ""; $("#f-gender").value = L.gender; $("#f-income").value = L.income ?? "";
    $("#f-exp").value = L.exp; $("#f-risk").value = L.risk; $("#f-mobile").value = L.mobile; $("#f-hour").value = L.hour;
    $("#goal-note").innerHTML = goalNote();
  }
  function bindBasic() {
    const L = state.learner;
    $("#f-label").oninput = e => { L.label = e.target.value; save(); };
    $("#f-age").onchange = e => { L.age = e.target.value === "" ? null : +e.target.value; invalidate(); save(); renderChecklist(); };
    $("#f-income").onchange = e => { L.income = e.target.value === "" ? null : +e.target.value; invalidate(); save(); };
    for (const k of ["gender", "exp", "mobile", "hour"]) $(`#f-${k}`).onchange = e => { L[k] = +e.target.value; invalidate(); save(); };
    $("#f-risk").onchange = e => { L.risk = +e.target.value; invalidate(); save(); $("#goal-note").innerHTML = goalNote(); };
    for (const k of ["goal", "horizon"]) $(`#f-${k}`).onchange = e => { L[k] = e.target.value; state.touched.goal = true; invalidate(); save(); renderChecklist(); $("#goal-note").innerHTML = goalNote(); };
  }

  // ---------- 3단계 ----------
  function renderTopics() {
    const L = state.learner; const groups = CATALOG.groups;
    $("#topic-chips").innerHTML = groups.map((g, gi) => `<div class="topic-group"><h4>${esc(g)}</h4><div class="chip-list">` +
      CATALOG.topics.map((t, ti) => CATALOG.topic_group[ti] === gi ? `<button class="chip ${L.interests.includes(ti) ? "on" : ""}" data-topic="${ti}">${esc(t)}</button>` : "").join("") + `</div></div>`).join("");
    $$("[data-topic]").forEach(b => b.onclick = () => {
      const t = +b.dataset.topic; const i = L.interests.indexOf(t);
      if (i >= 0) L.interests.splice(i, 1); else { if (L.interests.length >= 2) L.interests.shift(); L.interests.push(t); }
      invalidate(); renderTopics(); renderChecklist(); save();
    });
    $$("input[name=placement]").forEach(r => { r.checked = +r.value === L.placement; r.onchange = () => { L.placement = +r.value; state.touched.placement = true; invalidate(); save(); renderChecklist(); }; });
  }
  async function renderQuiz() {
    if (!QUIZ) QUIZ = await api("/api/quiz");
    const ex = isExisting();
    $("#quiz-count").textContent = `${QUIZ.length}문항 · ${new Set(QUIZ.map(q => q.topic + "·" + q.level)).size}개 단원`;
    $("#quiz-note").textContent = ex ? "기존 학습자는 스냅샷 기록으로 수준을 추정합니다. 진단을 적용하려면 2단계에서 '이 프로필을 새 학습자로 복사'하세요."
      : (state.learner.diagnosis ? `적용된 진단: ${state.learner.diagnosis.summary}` : "정답률은 답한 문항으로 계산합니다. 수준 2는 수준1 문항 5개·수준2 문항 3개 이상을 답하고 수준1 60%·수준2 50% 이상 맞혔을 때, 수준 3은 여기에 수준3 문항 3개 이상을 답하고 수준2 75% 이상, 서로 다른 주제의 수준3 문항 2개 이상 정답, 수준3 정답률 60% 이상일 때 부여합니다(최소 응답 수를 못 채우면 판정 보류). 한 단원에 문항이 둘이면 둘 다 답하고 맞혀야 통과로 기록하고, 규제 상식 문항(표시)은 수준 판정에만 씁니다.");
    const A = state.quiz.answers;
    $("#quiz-list").innerHTML = QUIZ.map((q, i) => `<div class="qcard" id="qc-${q.id}"><div class="qhead"><span class="qnum">Q${i + 1}</span><span class="muted small">${esc(q.topic)} · 수준 ${q.level}${q.diagnostic_only ? " · 규제 상식(수준 판정용)" : ""}</span></div><div class="qtext">${esc(q.text)}</div><div class="qopts">` +
      q.options.map((o, j) => `<label><input type="radio" name="quiz-${q.id}" value="${j}" ${A[q.id] === j ? "checked" : ""}> ${esc(o)}</label>`).join("") + `</div><div class="qresult" id="qr-${q.id}"></div></div>`).join("");
    $$("#quiz-list input[type=radio]").forEach(r => r.onchange = () => { A[r.name.slice(5)] = +r.value; save(); });
    renderQuizResult();
  }
  function renderQuizResult() {
    const R = state.quiz.result; const box = $("#quiz-result");
    if (!R) { box.hidden = true; $$(".qresult").forEach(el => { el.className = "qresult"; el.innerHTML = ""; }); return; }
    box.hidden = false;
    $("#quiz-summary").innerHTML = `<span class="badge ok">진단 수준 ${R.level} · ${LEVEL_NAME[R.level]}</span><span class="badge">정답 ${R.correct}/${R.answered} (전체 ${R.total}문항)</span>` +
      [1, 2, 3].map(l => `<span class="badge">수준${l} 문항 ${R.by_level[l].correct}/${R.by_level[l].total}</span>`).join("") + `<span class="badge">진단 통과 단원 ${R.mastered.length}개</span>`;
    R.results.forEach(r => {
      const el = $(`#qr-${r.id}`); if (!el) return;
      el.className = "qresult " + (r.answered ? (r.correct ? "ok" : "bad") : "skip");
      el.innerHTML = r.answered ? `${r.correct ? "✓ 정답" : "✕ 오답 · 정답: " + esc(r.correct_option)} <span class="muted">${esc(r.explain)}</span>` : `<span class="muted">답하지 않음 · 정답: ${esc(r.correct_option)}</span>`;
    });
  }
  async function scoreQuiz() {
    const A = state.quiz.answers; if (!Object.keys(A).length) return toast("문항에 먼저 답해 주세요");
    state.quiz.result = await api("/api/quiz/score", { answers: A }); renderQuizResult(); save();
    toast(state.quiz.result.summary, 4000);
  }
  function applyQuiz() {
    const R = state.quiz.result; if (!R) return toast("먼저 채점하세요");
    if (isExisting()) return toast("기존 학습자에는 적용할 수 없습니다. 2단계에서 새 학습자로 복사하세요");
    const L = state.learner;
    L.placement = R.level; state.touched.placement = true;
    L.diagnosis = { level: R.level, correct: R.correct, answered: R.answered, total: R.total, summary: R.summary };
    L.events = L.events.filter(e => e.source !== "diagnosis").concat(R.events.map(e => ({ ...e, source: "diagnosis" })));
    invalidate(); renderTopics(); renderQuiz(); renderChecklist(); save();
    toast(`진단 적용: 수준 ${R.level}, 진단 통과 ${R.events.length}개 단원을 학습 기록에 추가했습니다`, 3500);
  }

  // ---------- 4단계 ----------
  function renderEvents() {
    const ex = isExisting() && state.learnerInfo;
    $("#existing-history").hidden = !ex; $("#event-editor").hidden = !!ex;
    if (ex) {
      const h = state.learnerInfo.history;
      $("#existing-history").innerHTML = `<p class="small muted">${h.length}건의 학습 시도 (서빙 스냅샷 이전). 통과 단원 ${state.learnerInfo.passed_items.length}개는 후보에서 제외됩니다.</p>` +
        `<div class="table-wrap"><table class="table"><tr><th>주차</th><th>단원</th><th>수준</th><th>완료</th><th>퀴즈 통과</th><th>저장</th><th>이탈</th><th>점수</th></tr>` +
        h.map(r => `<tr><td>${r.week}</td><td>${esc(r.title)}</td><td>${r.level}</td><td>${r.complete ? "✓" : ""}</td><td>${r.quiz_pass ? "✓" : ""}</td><td>${r.save ? "✓" : ""}</td><td>${r.drop ? "✓" : ""}</td><td class="num">${r.score}</td></tr>`).join("") + `</table></div>`;
      return;
    }
    const sel = $("#ev-item");
    if (!sel.options.length) sel.innerHTML = CATALOG.items.map(it => `<option value="${it.item}">${esc(it.topic)} · 수준 ${it.level} · ${esc(it.title)}</option>`).join("");
    const ev = state.learner.events;
    $("#event-table").innerHTML = (ev.length ? `<tr><th>단원</th><th>출처</th><th>완료</th><th>퀴즈 통과</th><th>저장</th><th>이탈</th><th></th></tr>` : `<tr><td class="muted">학습 기록이 없습니다. 첫 방문 학습자로 처리됩니다.</td></tr>`) +
      ev.map((e, i) => { const it = item(e.item); return `<tr><td>${esc(it.title)} <span class="muted small">(${esc(it.topic)} · 수준 ${it.level})</span></td><td>${e.source === "diagnosis" ? '<span class="tag">진단</span>' : "입력"}</td><td>${e.complete ? "✓" : ""}</td><td>${e.quiz_pass ? "✓" : ""}</td><td>${e.save ? "✓" : ""}</td><td>${e.drop ? "✓" : ""}</td><td><button class="btn small ghost" data-del="${i}">삭제</button></td></tr>`; }).join("");
    $$("[data-del]").forEach(b => b.onclick = () => { ev.splice(+b.dataset.del, 1); invalidate(); renderEvents(); renderChecklist(); save(); });
  }
  function addEvent() {
    const pass = $("#ev-pass").checked;
    state.learner.events.push({ item: +$("#ev-item").value, week: 0, complete: $("#ev-complete").checked || pass, quiz: pass, quiz_pass: pass, save: $("#ev-save").checked, drop: $("#ev-drop").checked && !pass, replay: false });
    invalidate(); renderEvents(); renderChecklist(); save();
  }
  async function parseLog(text) {
    const r = await api("/api/parse-log", { csv_text: text });
    state.learner.events.push(...r.events.map(e => ({ week: 0, complete: false, quiz: false, quiz_pass: false, save: false, drop: false, replay: false, ...e, quiz: e.quiz || e.quiz_pass || false })));
    $("#log-warnings").textContent = r.warnings.join(" "); invalidate(); renderEvents(); renderChecklist(); save(); toast(`${r.events.length}건을 읽었습니다`);
  }

  // ---------- 5단계: 로드맵 ----------
  function stageName(key) { const s = state.roadmap && state.roadmap.stages.find(x => x.key === key); return s ? s.name : key; }
  async function loadRoadmap(force) {
    if (state.roadmap && !force) { renderRoadmap(); return; }
    $("#roadmap-status").textContent = "로드맵 계산 중…";
    try { state.roadmap = await api("/api/roadmap", { ...learnerRef() }); renderRoadmap(); renderChecklist(); save(); }
    catch (e) { $("#roadmap-status").textContent = "오류: " + e.message; $("#roadmap-view").hidden = true; throw e; }
  }
  function unitRow(u, nextItem) {
    const mark = u.status === "passed" ? "✓" : u.status === "locked" ? "○" : "▶";
    return `<li class="unit ${u.status} ${u.item === nextItem ? "next" : ""}"><span class="ustat">${mark}</span><div>` +
      `<div class="utitle">${esc(u.title)} ${u.item === nextItem ? '<span class="tag">다음 단원</span>' : ""}</div>` +
      `<div class="meta"><span>${esc(u.topic)}</span><span>수준 ${u.level}</span><span>약 ${u.minutes}분</span><span>${STATUS_KO[u.status]}</span>${u.concepts && u.concepts.length ? `<span>개념: ${esc(u.concepts.join(", "))}</span>` : ""}</div>` +
      (u.missing_prereqs.length ? `<div class="small warn-text">선수 단원 미이수: ${esc(u.missing_prereqs.join(", "))}</div>` : "") +
      (u.caution ? `<div class="small warn-text">주의: ${esc(u.caution)}</div>` : "") +
      (u.sources && u.sources.length ? `<div class="small muted">자료: ${sourceLinks(u.sources)}</div>` : "") + lessonBlock(u.lesson) + `</div></li>`;
  }
  function lessonBlock(L) {
    if (!L) return "";
    return `<details class="lesson"><summary>학습 요점 (기준일 ${esc(L.asof)})</summary><ul>${L.points.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` +
      (L.example ? `<div class="small"><b>예시</b> ${esc(L.example)}</div>` : "") + `</details>`;
  }
  function renderRoadmap() {
    const rm = state.roadmap; if (!rm) return;
    $("#roadmap-status").textContent = `${rm.learner.label} · 목적 ${rm.goal_label} · 기간 ${rm.horizon_label} · 단원 ${rm.units_total}개`;
    $("#roadmap-view").hidden = false;
    $("#rm-badges").innerHTML = `<span class="badge ok">진행률 ${pct(rm.progress)} (${rm.units_passed}/${rm.units_total} 단원)</span><span class="badge">남은 학습 약 ${rm.minutes_left}분 / 전체 ${rm.minutes_total}분</span><span class="badge">추정 수준 ${rm.level} · ${LEVEL_NAME[rm.level]}</span><span class="badge">위험성향 ${RISK_NAME[rm.risk]}</span><span class="badge">현재 단계: ${esc(stageName(rm.current_stage))}</span>`;
    $("#rm-flow").innerHTML = rm.stages.map((s, i) => `<div class="rm-stage ${s.key === rm.current_stage ? "current" : ""} ${s.done ? "done" : ""}"><div class="rm-stage-num">${i + 1}</div><div class="rm-stage-name">${esc(s.name)}</div><div class="rm-stage-meta">${s.key === "diagnosis" ? esc(s.note) : s.key === "connect" ? `유형 ${s.total}개` : `${s.passed}/${s.total} 통과 · ${s.minutes_left}분 남음`}</div></div>`).join("");
    const next = rm.next_unit;
    $("#rm-next").innerHTML = next ? `<b>다음 학습 단원</b> ${esc(next.title)} <span class="muted small">(${esc(next.topic)} · 수준 ${next.level} · 약 ${next.minutes}분${next.concepts && next.concepts.length ? " · 개념: " + esc(next.concepts.join(", ")) : ""})</span>` : `<b>로드맵의 모든 단원을 통과했습니다.</b> 9단계 ETF 유형 연결로 넘어가세요.`;
    $("#rm-stages").innerHTML = rm.stages.filter(s => (s.units && s.units.length) || s.key === "connect").map(s => {
      if (s.key === "connect") return `<div class="rm-block"><h3>${esc(s.name)} <span class="muted small">${esc(s.note)}</span></h3><div class="chip-list">` +
        s.types.map(t => `<span class="chip ${t.concepts_passed === t.concepts_total ? "on" : ""}" title="위험 ${t.risk}/5">${esc(t.name)} · 개념 ${t.concepts_passed}/${t.concepts_total} · ${riskDots(t.risk)}</span>`).join("") + `</div></div>`;
      return `<div class="rm-block ${s.key === rm.current_stage ? "current" : ""} ${s.done ? "done" : ""}"><h3>${esc(s.name)} <span class="muted small">${s.passed}/${s.total} 통과 · 약 ${s.minutes_left}분 남음${s.key === rm.current_stage ? " · 현재 단계" : s.done ? " · 완료" : ""}</span></h3><ol class="unit-list">` +
        s.units.map(u => unitRow(u, next && next.item)).join("") + `</ol></div>`;
    }).join("");
  }

  // ---------- 6단계 ----------
  function renderSettings() {
    const S = state.settings; const sel = $("#s-algorithm");
    sel.innerHTML = `<option value="">운영 라우터 (${META.operational_router === "RouterNoGender" ? "성별 제외" : META.operational_router}) · 기본</option>` +
      META.methods.map(m => `<option value="${esc(m.key)}">${esc(m.label)}${META.test_ndcg[m.key] != null ? ` · 테스트 NDCG ${fmt(META.test_ndcg[m.key], 3)}` : ""}</option>`).join("");
    sel.value = S.algorithm; $("#s-k").value = S.k; $("#s-block").value = S.block_gap; $("#s-plus").value = S.plus_one_max; $("#s-exclude").value = S.exclude_passed ? "1" : "0"; $("#s-cap").value = S.topic_cap; $("#s-prereq").value = S.prereq_block ? "1" : "0";
    const op = META.operational_algorithm;
    $("#algo-note").innerHTML = `<b>운영 설정</b> #${op.aid} ${esc(op.name)}<br><span class="muted small">${esc(op.formula)}</span><br><span class="small">검증 ${(META.configurations || 0).toLocaleString()}개 설정 중 1위(세그먼트 라우터 λ 교차 선택). 선수 단원 차단·두 단계 위 차단·한 단계 위 1개 상한은 수업의 교육 처방이 아니라 이 프로젝트의 시연용 정책이며, 오프라인 평가에는 '운영 라우터+prereq' 행으로 효과를 따로 기록했습니다.</span>`;
  }
  function bindSettings() {
    const S = state.settings;
    $("#s-k").onchange = e => { S.k = Math.max(1, Math.min(20, +e.target.value || 5)); e.target.value = S.k; state.result = null; save(); };
    $("#s-algorithm").onchange = e => { S.algorithm = e.target.value; state.result = null; save(); };
    $("#s-block").onchange = e => { S.block_gap = +e.target.value; state.result = null; save(); };
    $("#s-plus").onchange = e => { S.plus_one_max = Math.max(0, Math.min(5, +e.target.value || 0)); e.target.value = S.plus_one_max; state.result = null; save(); };
    $("#s-exclude").onchange = e => { S.exclude_passed = e.target.value === "1"; state.result = null; save(); };
    $("#s-prereq").onchange = e => { S.prereq_block = e.target.value === "1"; state.result = null; save(); };
    $("#s-cap").onchange = e => { S.topic_cap = e.target.value; state.result = null; save(); };
  }

  // ---------- 7단계 ----------
  async function runRecommend() {
    $("#rec-status").textContent = "계산 중…";
    try {
      state.result = await api("/api/recommend", buildRequest()); state.simResult = null; state.compare = null;
      renderResult(); renderChecklist(); save();
    } catch (e) { $("#rec-status").textContent = "오류: " + e.message; $("#rec-view").hidden = true; throw e; }
  }
  function renderResult() {
    const r = state.result; if (!r) return;
    $("#rec-status").textContent = `${r.learner.label} · ${r.learner.goal_label || ""} · ${r.latency_ms ?? "–"} ms · 스냅샷 ${r.snapshot_week}주차`;
    $("#rec-view").hidden = false;
    const allOk = r.checks.every(c => c.passed); const rm = r.roadmap || {};
    $("#rec-badges").innerHTML = `<span class="badge ${allOk ? "ok" : "bad"}">${allOk ? "가드레일 검사 통과" : "검사 실패 있음"}</span><span class="badge">후보 ${r.candidates ?? 0}개</span><span class="badge">추정 수준 ${r.level} · ${LEVEL_NAME[r.level]}</span><span class="badge">${r.router ? "라우터 " + r.router : "설정 강제"}</span><span class="badge">#${r.algorithm_id} ${esc(r.family_label)}</span>` +
      (rm.current_stage_name ? `<span class="badge">로드맵 ${esc(rm.current_stage_name)} · ${pct(rm.progress)}</span>` : "") + (r.shortfall ? `<span class="badge warn">${(r.candidates ?? 0) < r.k ? `가드레일 통과 후보 ${r.candidates}개뿐 · ` : ""}${r.shortfall}개 부족</span>` : "");
    $("#rec-roadmap").innerHTML = rm.next_unit ? `<b>로드맵</b> ${esc(rm.goal_label)} · 현재 단계 <b>${esc(rm.current_stage_name)}</b> · 진행률 ${pct(rm.progress)} (${rm.units_passed}/${rm.units_total}) · 남은 학습 약 ${rm.minutes_left}분 · 다음 단원: ${esc(rm.next_unit.title)}<span class="muted small"> · 연결 유형: ${(rm.types || []).map(k => esc(META.type_names[k] || k)).join(", ")}</span>`
      : `<b>로드맵</b> ${esc(rm.goal_label || "")} · 로드맵 단원을 모두 통과했습니다. 연결 유형: ${(rm.types || []).map(k => esc(META.type_names[k] || k)).join(", ")}`;
    renderMap(r.topic_map, "#topic-map");
    $("#map-legend").innerHTML = `<span class="l-rec">추천</span><span class="l-passed">통과한 단원</span><span>후보</span><span class="l-plus">한 단계 위(상한 ${r.guardrail.plus_one_max})</span><span class="l-blocked">가드레일 차단(수준·선수 단원)</span>`;
    const maxScore = Math.max(...r.items.map(i => i.score), 1e-9);
    $("#rec-list").innerHTML = r.items.length ? r.items.map(it => {
      const pos = it.contributions.filter(c => c.contribution > 0); const tot = pos.reduce((s, c) => s + c.contribution, 0) || 1;
      return `<li class="rec-item"><div class="rank">${it.rank}</div><div><div class="title">${esc(it.title)} ${it.in_current_stage ? '<span class="tag">현재 단계</span>' : ""}</div><div class="meta"><span>${esc(it.topic)}</span><span>수준 ${it.level} · ${LEVEL_NAME[it.level]}</span>${it.short ? "<span>짧은 콘텐츠</span>" : ""}<span>약 ${it.minutes}분</span><span>점수 ${fmt(it.score, 3)}</span>${it.level_gap === 1 ? '<span style="color:var(--plus)">한 단계 위</span>' : ""}</div>` +
        `<div class="bar"><i style="width:${(100 * it.score / maxScore).toFixed(1)}%;background:var(--accent)"></i></div><div class="reason">${esc(it.reason)}</div>` +
        (it.missing_prereqs && it.missing_prereqs.length ? `<div class="small warn-text">선수 단원 미이수: ${esc(it.missing_prereqs.join(", "))}</div>` : "") +
        `<div class="contrib">${pos.slice(0, 4).map(c => `<div><span class="muted" title="${esc(c.label)}">${esc(c.label)}</span><div class="cbar"><i style="width:${(100 * c.contribution / tot).toFixed(1)}%"></i></div><span class="num">${fmt(c.contribution, 2)}</span></div>`).join("")}</div>` +
        (it.sources && it.sources.length ? `<div class="small muted" style="margin-top:4px">자료: ${sourceLinks(it.sources)}</div>` : "") + `</div></li>`;
    }).join("") : `<li class="muted">${esc(r.reason || "추천할 단원이 없습니다")}</li>`;
    $("#rec-checks").innerHTML = r.checks.map(c => `<li class="${c.passed ? "" : "fail"}">${esc(c.name)}<span class="muted small">${esc(c.detail)}</span></li>`).join("");
    $("#rec-route").innerHTML = r.route_path.length ? r.route_path.map((p, i) => `<div class="node ${i === r.route_path.length - 1 ? "leaf" : ""}"><span class="muted">${esc(p.var_label)}${p.var ? " = " + esc(r.segment[p.var].label) : ""}</span><span>${p.n != null ? "n=" + p.n : esc(p.n_label || "20명 미만")} · #${p.champ} ${esc(p.champion_family)} · 추정 NDCG ${fmt(p.est, 4)}</span></div>`).join("") : `<div class="muted small">설정을 강제로 골라 라우터를 쓰지 않았습니다.</div>`;
    $("#rec-formula").textContent = r.formula;
  }
  function renderMap(map, sel) {
    const el = $(sel); const groups = CATALOG.groups; const topicsByGroup = groups.map((g, gi) => CATALOG.topics.map((t, ti) => ti).filter(ti => CATALOG.topic_group[ti] === gi));
    const order = topicsByGroup.flat(); const byItem = {}; map.forEach(m => byItem[m.item] = m);
    let html = `<div class="corner"></div>` + groups.map((g, gi) => `<div class="grouplab g${gi}" style="grid-column: span ${topicsByGroup[gi].length}">${esc(g)}</div>`).join("");
    html += `<div class="corner"></div>` + order.map(ti => `<div class="collab" title="${esc(CATALOG.topics[ti])}">${esc(CATALOG.topics[ti])}</div>`).join("");
    for (const lv of [1, 2, 3]) {
      html += `<div class="rowlab">수준 ${lv}<br><span class="small">${LEVEL_NAME[lv]}</span></div>`;
      for (const ti of order) {
        const it = CATALOG.items.find(x => x.topic_id === ti && x.level === lv);
        if (!it) { html += `<div class="cell none"></div>`; continue; }
        const m = byItem[it.item] || { status: "eligible" };
        const label = m.status === "recommended" ? m.rank : m.status === "passed" ? "✓" : "";
        html += `<div class="cell ${m.status} ${m.rank ? "recommended" : ""}" title="${esc(it.title)} · ${{ passed: "통과", recommended: "추천 " + m.rank + "위", plus_one: "한 단계 위 후보", eligible: "후보", blocked: "가드레일 차단" }[m.status]}">${label}</div>`;
      }
    }
    el.innerHTML = html; el.style.gridTemplateColumns = `92px repeat(${order.length}, var(--cell, 36px))`;
    el.style.setProperty("--cell", (36 * state.zoom / 100).toFixed(0) + "px"); $("#zoom-val").textContent = state.zoom + "%";
    $("#map-caption").textContent = `주제 × 수준 배치도 · 열 = 주제 ${order.length}개, 행 = 수준 3단계`;
  }

  // ---------- 8단계 ----------
  function renderSimControls() {
    const r = state.result; const labels = META.labels;
    $("#w-income").innerHTML = `<option value="">그대로</option>` + labels.income_q.map((l, i) => `<option value="${i}">${esc(l)}</option>`).join("");
    $("#w-age").innerHTML = `<option value="">그대로</option>` + labels.age_band.map((l, i) => `<option value="${i}">${esc(l)}</option>`).join("");
    $("#w-income").value = state.sim.income_q; $("#w-age").value = state.sim.age_band; $("#w-level").value = state.sim.level; $("#w-gender").checked = state.sim.gender;
    if (!r) { $("#sim-pass").innerHTML = `<span class="muted small">7단계에서 추천을 먼저 계산하세요.</span>`; return; }
    const cands = r.topic_map.filter(m => m.status === "recommended" || m.status === "eligible" || m.status === "plus_one").sort((a, b) => (a.rank || 99) - (b.rank || 99));
    $("#sim-pass").innerHTML = cands.slice(0, 24).map(m => `<button class="chip ${state.sim.assume.includes(m.item) ? "on" : ""}" data-pass="${m.item}">${m.rank ? m.rank + "위 · " : ""}${esc(item(m.item).title)}</button>`).join("");
    $$("[data-pass]").forEach(b => b.onclick = () => { const i = +b.dataset.pass; const k = state.sim.assume.indexOf(i); if (k >= 0) state.sim.assume.splice(k, 1); else state.sim.assume.push(i); state.typesResult = null; renderSimControls(); save(); });
  }
  async function runSim() {
    if (!state.result) return toast("7단계에서 추천을 먼저 계산하세요");
    const sim = state.sim; sim.gender = $("#w-gender").checked; sim.income_q = $("#w-income").value; sim.age_band = $("#w-age").value; sim.level = $("#w-level").value;
    const overrides = {};
    if (sim.gender) overrides.gender = 1 - state.result.segment.gender.code;
    if (sim.income_q !== "") overrides.income_q = +sim.income_q; if (sim.age_band !== "") overrides.age_band = +sim.age_band; if (sim.level !== "") overrides.level = +sim.level;
    $("#sim-status").textContent = "계산 중…";
    state.simResult = await api("/api/recommend", buildRequest({ assume_passed: sim.assume, overrides }));
    const base = state.result.items.map(i => i.item_id), now = state.simResult.items.map(i => i.item_id);
    const same = base.join() === now.join();
    let genderBadge = "";
    if (sim.gender) {   // 성별만 뒤집은 별도 요청으로 입력 불변성을 따로 확인한다(통과 가정·다른 what-if와 섞지 않음)
      const only = await api("/api/recommend", buildRequest({ overrides: { gender: 1 - state.result.segment.gender.code } }));
      const inv = only.items.map(i => i.item_id).join() === base.join();
      genderBadge = `<span class="badge ${inv ? "ok" : "warn"}">성별만 뒤집기: ${inv ? "추천 불변 (코드 수준 점검)" : "추천 변화 — 이 설정은 성별을 씀"}</span>`;
    }
    const rm0 = state.result.roadmap || {}, rm1 = state.simResult.roadmap || {};
    $("#sim-status").textContent = `${state.simResult.latency_ms} ms`; $("#sim-view").hidden = false;
    $("#sim-badges").innerHTML = `<span class="badge ${same ? "ok" : ""}">${same ? "추천 목록 동일" : "추천 목록 변화"}</span>` + genderBadge +
      (sim.assume.length ? `<span class="badge">통과 가정 ${sim.assume.length}개</span>` : "") + `<span class="badge">추정 수준 ${state.result.level} → ${state.simResult.level}</span>` +
      (rm0.progress != null ? `<span class="badge">로드맵 진행 ${pct(rm0.progress)} → ${pct(rm1.progress)} · ${esc(rm1.current_stage_name || "")}</span>` : "") + `<span class="badge">#${state.simResult.algorithm_id}</span>`;
    $("#sim-base").innerHTML = state.result.items.map(i => `<li class="${now.includes(i.item_id) ? "" : "gone"}">${esc(i.title)} <span class="muted small">수준 ${i.level}</span></li>`).join("");
    $("#sim-new").innerHTML = state.simResult.items.map(i => `<li class="${base.includes(i.item_id) ? "" : "new"}">${esc(i.title)} <span class="muted small">수준 ${i.level}</span></li>`).join("");
    state.typesResult = null; save();
  }

  // ---------- 9단계: ETF 유형 연결 ----------
  async function loadTypes(force) {
    if (state.typesResult && !force) { renderTypes(); return; }
    $("#types-status").textContent = "유형 카드 계산 중…";
    const body = { ...learnerRef(), assume_passed: state.types.includeAssume ? state.sim.assume : [] };
    try {
      const [t, s] = await Promise.all([api("/api/types", body), SOURCES ? Promise.resolve(SOURCES) : api("/api/sources")]);
      state.typesResult = t; SOURCES = s; renderTypes(); renderChecklist(); save();
    } catch (e) { $("#types-status").textContent = "오류: " + e.message; $("#types-view").hidden = true; throw e; }
  }
  function renderTypes() {
    const T = state.typesResult; if (!T) return;
    const uni = T.universe || {}; const sample = uni.kind !== "snapshot"; const px = uni.prices || null;   // px: 결합된 시세 스냅샷(없으면 null)
    $("#types-status").textContent = `목적 ${T.goal_label} · 위험성향 ${RISK_NAME[T.risk]} · 유형 ${T.cards.length}개 (권장 ${T.cards.filter(c => c.recommended_for_goal).length}개)`;
    $("#types-view").hidden = false;
    $("#types-badges").innerHTML = `<span class="badge ${sample || uni.stale ? "warn" : "ok"}">${sample ? "유형 통계: 샘플 데이터(가상 종목)" : "유형 통계: KRX 스냅샷 " + esc(uni.as_of || (uni.synced_at || "").slice(0, 10)) + (uni.stale ? ` · ${uni.age_days}일 지남` : "")}</span>` +
      (px ? `<span class="badge ${px.stale ? "warn" : ""}">시세 ${esc(px.as_of)} · ${esc(px.source_name)} · ${px.matched}종목 결합</span>` : "") + `<span class="badge">종목 ${T.universe_rows}개</span><span class="badge">열린 유형 ${T.cards.filter(c => c.unlocked).length}/${T.cards.length}</span>` +
      (state.types.includeAssume && state.sim.assume.length ? `<span class="badge">통과 가정 ${state.sim.assume.length}개 반영</span>` : "");
    $("#types-grid").innerHTML = T.cards.map(c => {
      const st = c.stats || {};
      return `<article class="type-card ${c.recommended_for_goal ? "rec" : ""} ${c.unlocked ? "unlocked" : ""}">
        <header><div><h3>${esc(c.name)}</h3><div class="muted small">위험 ${riskDots(c.risk)} · 적합 목적: ${esc(c.goals.join(", "))}</div></div>
        <div class="tags">${c.recommended_for_goal ? '<span class="tag">이 목적에 권장</span>' : ""}${c.learn_only ? '<span class="tag lock">안정 성향: 학습용(권장 아님)</span>' : ""}<span class="tag ${c.unlocked ? "ok" : "lock"}">${c.unlocked ? "개념 모두 통과 · 열림" : `개념 ${c.concepts_passed}/${c.concepts_total} · 잠김`}</span></div></header>
        <p>${esc(c.description)}</p>
        <div class="concepts">${c.concepts.map(k => `<span class="chip ${k.passed ? "passed" : ""}" title="${esc(k.topic)} · 수준 ${k.level}">${k.passed ? "✓ " : ""}${esc(k.title)}</span>`).join("")}</div>
        <dl class="kvl"><dt>세금</dt><dd>${esc(c.tax)}</dd><dt>연금계좌</dt><dd>${esc(c.pension)}</dd>${c.regulation ? `<dt>규제·사전교육</dt><dd class="warn-text">${esc(c.regulation)}</dd>` : ""}<dt>주의</dt><dd>${c.cautions.map(x => esc(x)).join(" / ")}</dd></dl>
        <div class="stats"><span class="muted">${sample ? "샘플" : "KRX"} 통계</span> 종목 ${st.count ?? 0}개 · 환헤지(H) ${st.hedged ?? 0}개 · 총보수 중앙값 ${st.fee_median != null ? st.fee_median + "%" : "–"}${st.fee_min != null ? ` (${st.fee_min}~${st.fee_max}%)` : ""}${px && (st.premium_abs_median != null || st.volume_median != null) ? ` · <span class="muted">시세 ${esc(px.as_of)}</span>${st.premium_abs_median != null ? ` 괴리율 절댓값 중앙값 ${(st.premium_abs_median * 100).toFixed(2)}% (${st.priced}/${st.count}종목)` : ""}${st.volume_median != null ? ` · 거래량 중앙값 ${Number(st.volume_median).toLocaleString("ko-KR")}주` : ""}` : ""}${st.examples && st.examples.length ? ` · 예: ${esc(st.examples.join(", "))}` : ""}</div>
        <div class="small muted">자료: ${sourceLinks(c.sources)}</div>
      </article>`;
    }).join("");
    renderSources();
  }
  function renderSources() {
    if (!SOURCES) return;
    $("#sources-table").innerHTML = `<tr><th>출처</th><th>종류 · 접근</th><th>쓰임</th><th>이용 조건</th><th>확인</th></tr>` + SOURCES.sources.map(s =>
      `<tr><td><b>${esc(s.name)}</b><br><span class="muted small">${esc(s.publisher)}${s.menu ? " · " + esc(s.menu) : ""}</span>${s.url ? `<br><a class="small" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a>` : ""}</td><td class="small">${esc(s.kind)}<br><span class="muted">${esc(s.access)}</span></td><td class="small">${esc(s.use)}</td><td class="small muted">${esc(s.license)}</td><td class="small">${esc(s.verified)}</td></tr>`).join("");
    $("#sources-stats").innerHTML = `<p class="muted small">${esc(SOURCES.universe.label)} · 종목 ${SOURCES.universe_rows}개. 실제 목록으로 바꾸려면 KRX 정보데이터시스템에서 전종목 기본정보 파일을 내려받아 <code>python -m etfrec sources sync --krx-csv 파일</code>을, 괴리율·거래량 통계까지 보려면 <code>--krx-key</code>(KRX Open API) 또는 <code>--datagokr-key</code>(공공데이터포털 serviceKey)를 함께 실행하세요. 비상업 수업 프로젝트 범위의 이용입니다.</p>` +
      `<div class="table-wrap"><table class="table"><tr><th>유형</th><th>종목 수</th><th>환헤지</th><th>선물형</th><th>총보수 중앙값(%)</th><th>운용사 수</th><th>예시</th></tr>` +
      SOURCES.type_stats.map(t => `<tr><td>${esc(t.name)}</td><td class="num">${t.count}</td><td class="num">${t.hedged}</td><td class="num">${t.futures}</td><td class="num">${t.fee_median ?? "–"}</td><td class="num">${t.issuers}</td><td class="small">${esc(t.examples.join(", "))}</td></tr>`).join("") + `</table></div>`;
  }

  // ---------- 10단계 ----------
  async function renderCompare(force) {
    if (!state.result) { $("#compare-view").innerHTML = `<p class="muted small">7단계에서 추천을 먼저 계산하세요.</p>`; return; }
    if (!state.compare || force) {
      $("#compare-view").innerHTML = `<p class="muted small">계산 중…</p>`;
      state.compare = await api("/api/compare", buildRequest({ methods: ["RouterNoGender", "Global", "RULE", "UCF", "ICF", "POP", "CONTENT", "MF", "MF_BPR", "MF_OBS", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT", "NoDemographics"].filter(m => META.methods.some(x => x.key === m)) }));
    }
    const c = state.compare; const opIds = (c.methods[0] ? c.methods[0].items : []).map(i => i.item_id);
    $("#compare-view").innerHTML = `<table class="table"><tr><th>설정</th><th>테스트 NDCG@5</th><th>Top-${state.settings.k}</th><th>운영과 겹침</th></tr>` + c.methods.map(m => {
      const ids = m.items.map(i => i.item_id); const ov = ids.filter(i => opIds.includes(i)).length;
      return `<tr><td>${esc(META.methods.find(x => x.key === m.key)?.label || m.key)}<br><span class="muted small">#${m.algorithm_id} ${esc(m.family_label)}</span></td><td class="num">${fmt(m.test_ndcg, 4)}</td><td>${m.items.map(i => `<span title="${esc(i.title)}">${i.item_id}<sub>${i.level}</sub></span>`).join(" · ")}</td><td class="num">${ov}/${ids.length}</td></tr>`;
    }).join("") + `</table><p class="muted small">후보 ${c.candidates}개 · 같은 가드레일 · 아이템 번호 옆 작은 숫자는 수준</p>`;
  }
  function groupLabel(variable, group) {
    if (variable === "goal") return META.goals[group] || group;
    const l = META.labels[variable]; return l ? l[group] : group;
  }
  async function loadEvaluation() {
    EVAL = await api("/api/evaluation");
    const ds = EVAL.dataset; const res = EVAL.results; const maxN = Math.max(...res.map(r => r.ndcg));
    const opName = META.operational_router; const hasPre = res.some(r => r.prereq_violation_rate != null);
    let html = `<div class="kv"><div><span class="muted">학습자</span><b>${ds.users.toLocaleString()}</b></div><div><span class="muted">학습 시도</span><b>${ds.study_attempts.toLocaleString()}</b></div><div><span class="muted">단원</span><b>${ds.items}</b></div><div><span class="muted">설정 수</span><b>${EVAL.configurations.toLocaleString()}</b></div><div><span class="muted">신호 수</span><b>${EVAL.signal_count}</b></div><div><span class="muted">테스트 사용자</span><b>${EVAL.test_audit.rows.toLocaleString()}</b></div><div><span class="muted">정답 없는 사용자</span><b>${EVAL.test_audit.zero_observed_target.toLocaleString()}</b></div><div><span class="muted">QA 검사</span><b>${EVAL.qa.filter(q => q.passed).length}/${EVAL.qa.length}</b></div><div><span class="muted">MF·MLP 학습</span><b>${EVAL.neural_enabled ? "포함" : "제외"}</b></div></div>`;
    if (ds.goals) html += `<p class="muted small">투자 목적 분포: ${Object.entries(ds.goals).map(([g, n]) => `${esc(META.goals[g] || g)} ${Number(n).toLocaleString()}`).join(" · ")}</p>`;
    if (EVAL.privacy && EVAL.privacy.quasi) { const P = EVAL.privacy, q = P.quasi, lf = (P.router_leaves || {})[EVAL.selection.operational], rl = P.release || {};   // 측정한 것만 표시(충족 여부를 꾸미지 않는다)
      html += `<p class="muted small">개인정보 점검: 저장 준식별자 ${q.columns.length}개 조합(k=${q.k}) ${q.groups.toLocaleString()}개 셀 중 k 미만 ${q.groups_below_k.toLocaleString()}개(${q.users_below_k.toLocaleString()}명)${q.satisfied ? "" : " → 학습자 단위 표는 export-deid로 일반화·억제한 것만 반출"}${rl.satisfied ? `(k=${q.k} 표 ${rl.rows_out.toLocaleString()}/${rl.rows_in.toLocaleString()}행)` : ""}` +
        (lf ? ` · 운영 라우터 잎 ${lf.leaves}개 중 ${lf.threshold}명 미만 ${lf.leaves_below}개(${lf.users_in_small_leaves.toLocaleString()}명), 최소 ${lf.min_leaf}명 — 잎 크기는 보장되지 않으며 ${lf.min_users_param}명 미만 노드는 상위 노드 추정으로 챔피언을 정함` : "") + `</p>`; }
    html += `<h4>방법별 NDCG@5 (사용자 평균, 테스트 ${EVAL.test_audit.week}주차)</h4>` + res.map(r => `<div class="evbar ${r.method === opName ? "op" : ""}"><span title="${esc(r.method)}">${esc(r.method)}</span><div class="ebar"><i style="width:${(100 * r.ndcg / maxN).toFixed(1)}%"></i></div><span class="num">${fmt(r.ndcg, 4)}</span></div>`).join("");
    const hasAct = res.some(r => r.ndcg_active != null);
    html += `<div class="table-wrap"><table class="table"><tr><th>방법</th><th>NDCG@5 (전체)</th>${hasAct ? "<th>NDCG@5 (활성 사용자)</th>" : ""}<th>Diversity@5</th><th>Hit@5</th>${hasAct ? "<th>Hit@5 (활성)</th>" : ""}${hasPre ? "<th>선수 미이수 비율</th>" : ""}<th>전역 1위 대비 차이 [95% 구간]</th></tr>` + res.map(r => `<tr><td>${esc(r.method)}</td><td class="num">${fmt(r.ndcg)}</td>${hasAct ? `<td class="num">${fmt(r.ndcg_active)}</td>` : ""}<td class="num">${fmt(r.diversity, 3)}</td><td class="num">${fmt(r.hit_diagnostic, 3)}</td>${hasAct ? `<td class="num">${fmt(r.hit_active, 3)}</td>` : ""}${hasPre ? `<td class="num">${r.prereq_violation_rate != null ? fmt(r.prereq_violation_rate, 3) : "–"}</td>` : ""}<td class="num">${fmt(r.difference_vs_global)} [${fmt(r.ci_low)}, ${fmt(r.ci_high)}]</td></tr>`).join("") + `</table></div>`;
    if (hasAct) html += `<p class="muted small">전체 = 다음 주 정답이 없는 사용자도 NDCG 0으로 평균에 포함(노트북 규칙, 보수적). 활성 사용자 = 후보 안에 정답이 1개 이상인 사용자만 평균(추천 시스템 평가에서 흔한 관행, ${(res[0] && res[0].active_users) ? res[0].active_users.toLocaleString() : "–"}명). 모든 방법이 같은 활성 집합으로 평가되므로 두 값의 비가 같고 방법 순위도 같습니다(학습 QA에서 확인). 절대 차이는 활성 기준에서 그 비만큼 커집니다.</p>`;
    if (hasPre) html += `<p class="muted small">선수 미이수 비율 = Top-5 중 선수 단원을 아직 통과하지 않은 단원의 비율. '+prereq' 행은 같은 운영 라우터에 선수 단원 가드레일을 켠 결과입니다.</p>`;
    const g = EVAL.group_results.filter(x => x.method === "Global");
    const vars = { gender: "성별", age_band: "연령대", income_q: "소득분위", click_tier: "학습활동", goal: "투자 목적" };
    const gAct = g.some(x => x.ndcg_active != null);
    html += `<h4>전역 1위 설정의 집단별 NDCG@5 (진단용, 동등 대우의 증거가 아님)</h4><div class="table-wrap"><table class="table"><tr><th>변수</th><th>집단</th><th>사용자</th><th>NDCG@5 전체</th><th>95% 구간</th>${gAct ? "<th>활성 비율</th><th>NDCG@5 활성</th><th>95% 구간</th>" : ""}</tr>` + g.map(x => `<tr><td>${vars[x.variable] || esc(x.variable)}</td><td>${esc(groupLabel(x.variable, x.group))}</td><td class="num">${x.users.toLocaleString()}</td><td class="num">${fmt(x.ndcg)}</td><td class="num">[${fmt(x.ci_low)}, ${fmt(x.ci_high)}]</td>${gAct ? `<td class="num">${fmt(x.active_share, 2)}</td><td class="num">${fmt(x.ndcg_active)}</td><td class="num">[${fmt(x.ci_low_active)}, ${fmt(x.ci_high_active)}]</td>` : ""}</tr>`).join("") + `</table></div>`;
    if (gAct) html += `<p class="muted small">활성 비율(다음 주 정답이 있는 사용자 비율)이 집단마다 다르면 전체 기준과 활성 기준의 집단 순서가 달라질 수 있습니다. 예: 학습활동이 적은 집단은 활성 비율이 낮아 전체 기준에서 불리하게 보입니다.</p>`;
    const ex = EVAL.exposure.filter(x => x.method === "RouterNoGender");
    if (ex.length) html += `<h4>심화·레버리지 콘텐츠 노출 비율 (운영 라우터, 집단별)</h4><div class="table-wrap"><table class="table"><tr><th>변수</th><th>집단</th><th>사용자</th><th>Top-5 중 심화·레버리지 비율</th></tr>` + ex.map(x => `<tr><td>${vars[x.variable] || esc(x.variable)}</td><td>${esc(groupLabel(x.variable, x.group))}</td><td class="num">${x.users.toLocaleString()}</td><td class="num">${fmt(x.advanced_share, 3)}</td></tr>`).join("") + `</table></div>`;
    html += `<h4>검증 상위 설정 (${EVAL.validation_audit.week}주차)</h4><div class="table-wrap"><table class="table"><tr><th>#</th><th>기법군</th><th>설정</th><th>검증 NDCG@5</th><th>Diversity</th></tr>` + EVAL.validation_top.slice(0, 10).map(j => `<tr><td>${j.job_id}</td><td>${esc(j.family)}</td><td>${esc(j.name)}</td><td class="num">${fmt(j.ndcg)}</td><td class="num">${fmt(j.diversity, 3)}</td></tr>`).join("") + `</table></div>`;
    html += `<p class="muted small">번들 생성 ${esc(EVAL.created_at)} · 운영 라우터 ${esc(EVAL.selection.operational)} · λ ${JSON.stringify(EVAL.selection.router_lambdas)} · 모의 데이터이므로 수치는 실제 학습자 성과가 아닙니다.</p>`;
    $("#eval-view").innerHTML = html;
  }

  // ---------- 11단계 ----------
  function designPayload() { return { saved_from: "학습 설계 스튜디오", version: META.version, summary: `${isExisting() ? "#" + state.learnerId : state.learner.label || "새 학습자"} · ${META.goals[state.learner.goal] || ""} · k=${state.settings.k} · ${state.settings.algorithm || "운영 라우터"}`, state: { ...state, ...VOLATILE }, memo: state.memo, result: state.result, roadmap: state.roadmap }; }
  async function saveDesign() {
    const name = $("#design-name").value.trim(); if (!name) return toast("설계 이름을 적어 주세요");
    state.memo = $("#design-memo").value; const r = await api("/api/designs", { name, payload: designPayload() });
    $("#design-status").textContent = `저장됨: ${r.saved} (${r.saved_at})`; listDesigns(); save();
  }
  async function listDesigns() {
    const ds = await api("/api/designs");
    $("#design-list").innerHTML = ds.length ? ds.map(d => `<li><span><b>${esc(d.name)}</b><br><span class="muted small">${esc(d.saved_at)} · ${esc(d.summary)}</span></span><span><button class="btn small" data-load="${esc(d.name)}">불러오기</button> <button class="btn small ghost" data-rm="${esc(d.name)}">삭제</button></span></li>`).join("") : `<li class="muted">저장된 설계가 없습니다.</li>`;
    $$("[data-load]").forEach(b => b.onclick = async () => { const d = await api(`/api/designs/${encodeURIComponent(b.dataset.load)}`); applyDesign(d.payload); const br = ((d.payload || {}).state || {}).learner?.band_representative; toast(`'${d.name}'을 불러왔습니다` + (br && br.length ? " · 연령·소득은 저장 때 구간 코드로만 남아 구간 대표값으로 채웠습니다(원값 아님)" : ""), br && br.length ? 5000 : undefined); });
    $$("[data-rm]").forEach(b => b.onclick = async () => { await api(`/api/designs/${encodeURIComponent(b.dataset.rm)}`, null, "DELETE"); listDesigns(); });
  }
  function applyDesign(p) {
    if (!p || !p.state) return toast("설계 파일 형식이 아닙니다");
    const s = p.state; Object.assign(state, { ...s, ...VOLATILE, memo: p.memo || "" }); migrate();
    if (isExisting()) api(`/api/learners/${state.learnerId}`).then(i => { state.learnerInfo = i; });
    $("#nl-text").value = state.nl.text || ""; $$("input[name=source]").forEach(r => r.checked = r.value === state.source); $("#existing-picker").hidden = state.source !== "existing";
    save(); goStep(2);
  }
  function exportCSV() {
    if (!state.result) return toast("추천을 먼저 계산하세요");
    const rows = [["rank", "item_id", "title", "topic", "level", "score", "in_current_stage", "missing_prereqs", "reason"]].concat(state.result.items.map(i => [i.rank, i.item_id, i.title, i.topic, i.level, i.score.toFixed(4), i.in_current_stage ? 1 : 0, (i.missing_prereqs || []).join("; "), i.reason]));
    download("recommendation.csv", "﻿" + rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n"), "text/csv");
  }

  // ---------- 바인딩·시작 ----------
  function bind() {
    $("#nav-prev").onclick = () => goStep(state.step - 1);
    $("#nav-next").onclick = () => goStep(state.step === N_STEPS ? 1 : state.step + 1);
    $("#checklist-toggle").onclick = () => { $("#checklist-items").hidden = !$("#checklist-items").hidden; renderChecklist(); };
    $("#btn-new").onclick = () => { try { localStorage.removeItem("etfrec-draft"); } catch (e) { } location.reload(); };
    $("#btn-saved").onclick = () => goStep(N_STEPS);
    $("#btn-file").onclick = () => { $("#file-menu").hidden = !$("#file-menu").hidden; };
    document.addEventListener("click", e => { if (!e.target.closest(".menu")) $("#file-menu").hidden = true; });
    $$("#file-menu button").forEach(b => b.onclick = () => {
      const a = b.dataset.act; $("#file-menu").hidden = true;
      if (a === "export-json") download("design.json", JSON.stringify(designPayload(), null, 2));
      if (a === "import-json") $("#import-file").click();
      if (a === "export-csv") exportCSV();
      if (a === "export-rec-json") { if (!state.result) return toast("추천을 먼저 계산하세요"); download("recommendation.json", JSON.stringify(state.result, null, 2)); }
      if (a === "export-roadmap") { if (!state.roadmap) return toast("5단계에서 로드맵을 먼저 계산하세요"); download("roadmap.json", JSON.stringify(state.roadmap, null, 2)); }
    });
    $("#import-file").onchange = e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => applyDesign(JSON.parse(t))).catch(() => toast("JSON을 읽지 못했습니다")); e.target.value = ""; };
    $$("input[name=source]").forEach(r => r.onchange = () => { state.source = r.value; $("#existing-picker").hidden = r.value !== "existing"; invalidate(); renderChecklist(); save(); if (r.value === "existing" && !$("#learner-results").innerHTML) searchLearners(); });
    $("#learner-search").onclick = searchLearners; $("#learner-query").onkeydown = e => { if (e.key === "Enter") searchLearners(); };
    $("#nl-parse").onclick = () => parseNL().catch(e => toast(e.message)); $("#nl-text").oninput = e => { state.nl.text = e.target.value; };
    $("#skip-to-direct").onclick = () => goStep(2);
    bindBasic(); bindSettings();
    $("#quiz-score").onclick = () => scoreQuiz().catch(e => toast(e.message));
    $("#quiz-apply").onclick = applyQuiz;
    $("#quiz-reset").onclick = () => { state.quiz = { answers: {}, result: null }; renderQuiz(); save(); };
    $("#ev-add").onclick = addEvent;
    $("#log-parse").onclick = () => parseLog($("#log-text").value).catch(e => toast(e.message));
    $("#log-file").onchange = e => { const f = e.target.files[0]; if (f) f.text().then(t => parseLog(t)).catch(e => toast(e.message)); };
    $("#rm-refresh").onclick = () => loadRoadmap(true).catch(e => toast(e.message));
    $("#run-recommend").onclick = () => runRecommend().catch(e => toast(e.message));
    $("#zoom-in").onclick = () => { state.zoom = Math.min(160, state.zoom + 20); if (state.result) renderMap(state.result.topic_map, "#topic-map"); };
    $("#zoom-out").onclick = () => { state.zoom = Math.max(60, state.zoom - 20); if (state.result) renderMap(state.result.topic_map, "#topic-map"); };
    $("#run-sim").onclick = () => runSim().catch(e => toast(e.message));
    $("#types-refresh").onclick = () => loadTypes(true).catch(e => toast(e.message));
    $("#types-assume").onchange = e => { state.types.includeAssume = e.target.checked; loadTypes(true).catch(err => toast(err.message)); };
    $("#run-compare").onclick = () => renderCompare(true).catch(e => toast(e.message));
    $("#design-save").onclick = () => saveDesign().catch(e => toast(e.message));
    $("#design-export").onclick = () => { state.memo = $("#design-memo").value; download("design.json", JSON.stringify(designPayload(), null, 2)); };
    $("#rec-export").onclick = exportCSV;
    $("#design-memo").oninput = e => { state.memo = e.target.value; };
  }
  async function boot() {
    load();
    [META, CATALOG, EXAMPLES] = await Promise.all([api("/api/meta"), api("/api/catalog"), api("/api/examples")]);
    META.type_names = META.type_names || {};
    $("#bundle-info").textContent = `번들 ${META.created_at} · 학습자 ${META.n_users.toLocaleString()}명 · 단원 ${META.n_items}개(카탈로그 v${META.catalog_version}) · 운영 설정 #${META.operational_algorithm.aid}`;
    $("#notice").textContent = META.notice + " 모의 데이터로 실행한 수업용 추천이며 실서비스 효과 검증이 아닙니다.";
    renderExamples(); bind(); $("#nl-text").value = state.nl.text || "";
    $("#types-assume").checked = state.types.includeAssume;
    $$("input[name=source]").forEach(r => r.checked = r.value === state.source); $("#existing-picker").hidden = state.source !== "existing";
    if (isExisting()) { try { state.learnerInfo = await api(`/api/learners/${state.learnerId}`); } catch (e) { state.learnerId = null; } }
    goStep(state.step || 1);
  }
  boot().catch(e => { $("#rec-status").textContent = e.message; document.body.insertAdjacentHTML("afterbegin", `<div class="warn">서버에 연결하지 못했습니다: ${esc(e.message)}</div>`); });
})();
