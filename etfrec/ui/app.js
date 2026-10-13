/* 학습 설계 스튜디오 — 프런트엔드(의존성 없음). 모든 계산은 /api 로 서버에 맡긴다. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const STEP_NAMES = ["학습자 아이디어 스케치", "기본 정보", "관심 주제와 수준", "학습 기록", "추천 설정", "추천 미리보기", "시뮬레이션", "비교·평가", "저장·내보내기"];
  const LEVEL_NAME = { 1: "기초", 2: "구조·계산", 3: "심화·위험" };

  const state = {
    step: 1, source: "new", learnerId: null, learnerInfo: null,
    learner: { label: "", age: null, gender: 0, income: null, exp: 0, risk: 1, mobile: 1, interests: [], placement: 1, hour: 4, events: [] },
    nl: { text: "", parsed: null },
    settings: { k: 5, algorithm: "", block_gap: 2, plus_one_max: 1, exclude_passed: true, topic_cap: "" },
    sim: { assume: [], gender: false, income_q: "", age_band: "", level: "" },
    result: null, simResult: null, compare: null, touched: { placement: false }, memo: "", zoom: 100,
  };
  let META = null, CATALOG = null, EXAMPLES = [], EVAL = null;

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
  function save() { try { localStorage.setItem("etfrec-draft", JSON.stringify({ ...state, result: null, simResult: null, compare: null, learnerInfo: null })); } catch (e) { } }
  function load() { try { const d = JSON.parse(localStorage.getItem("etfrec-draft") || "null"); if (d) Object.assign(state, d); } catch (e) { } }
  function download(name, text, type = "application/json") {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); a.remove();
  }
  function item(i) { return CATALOG.items[i]; }
  function fmt(x, d = 4) { return x == null ? "–" : Number(x).toFixed(d); }

  // ---------- 체크리스트·스테퍼 ----------
  function checklistItems() {
    const L = state.learner, ex = state.source === "existing" && state.learnerId != null;
    return [
      ["학습자 출처 지정", true],
      ["기본 정보 입력", ex || L.age != null],
      ["관심 주제 1~2개", ex || L.interests.length > 0],
      ["진단 수준 지정", ex || state.touched.placement],
      ["학습 기록(선택)", ex || L.events.length > 0],
      ["추천 설정 확인", state.step >= 5 || !!state.result],
      ["추천 계산 완료", !!state.result],
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
    $("#nav-indicator").textContent = `${state.step}/9 · ${STEP_NAMES[state.step - 1]}`;
    $("#nav-prev").disabled = state.step === 1; $("#nav-next").textContent = state.step === 9 ? "처음으로" : "다음 →";
  }
  async function goStep(n) {
    state.step = Math.max(1, Math.min(9, n));
    $$(".step").forEach(s => s.hidden = +s.dataset.step !== state.step);
    renderStepper(); renderChecklist(); save();
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (state.step >= 2 && state.step <= 8) await ensureLearnerInfo();
    if (state.step === 2) renderBasic();
    if (state.step === 3) renderTopics();
    if (state.step === 4) renderEvents();
    if (state.step === 5) renderSettings();
    if (state.step === 6 && !state.result) runRecommend().catch(() => { });
    if (state.step === 7) renderSimControls();
    if (state.step === 8) { renderCompare(); if (!EVAL) loadEvaluation(); }
    if (state.step === 9) { listDesigns(); $("#design-memo").value = state.memo; }
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
    for (const k of ["placement", "exp", "risk", "mobile", "hour", "gender", "age", "income"]) if (f[k] != null) L[k] = f[k];
    if (f.placement != null) state.touched.placement = true;
    if (f.events) L.events = f.events;
    if (f.k) state.settings.k = f.k;
    state.source = "new"; $$("input[name=source]").forEach(r => r.checked = r.value === "new"); $("#existing-picker").hidden = true;
    const names = { interests: "관심 주제", placement: "진단 수준", exp: "투자 경험", risk: "위험성향", mobile: "기기", hour: "학습 시간대", gender: "성별", age: "연령", income: "연소득(만원)", k: "추천 개수", events: "학습 기록" };
    const show = v => Array.isArray(v) ? v.join(", ") : v;
    $("#nl-table").innerHTML = `<tr><th>항목</th><th>읽어 낸 값</th><th>근거가 된 표현</th></tr>` + p.evidence.map(e => `<tr><td>${names[e.field] || e.field}</td><td>${esc(show(e.value))}</td><td class="muted">${esc(e.matched)}</td></tr>`).join("");
    $("#nl-warnings").textContent = p.warnings.join(" ");
    $("#nl-result").hidden = false; state.result = null; renderChecklist(); save();
    toast(`${p.evidence.length}개 조건을 읽었습니다. 2단계에서 확인하세요`);
  }
  async function searchLearners() {
    const q = $("#learner-query").value.trim();
    const r = await api(`/api/learners?q=${encodeURIComponent(q)}&limit=12`);
    $("#learner-results").innerHTML = (r.items.length ? "" : `<div class="muted small">검색 결과가 없습니다</div>`) + r.items.map(u =>
      `<div class="learner-card ${u["학습자"] === state.learnerId ? "selected" : ""}" data-uid="${u["학습자"]}"><span>#${u["학습자"]} · ${esc(u["성별"])} ${u["연령"]}세 · ${esc(u["투자 경험"])}/${esc(u["위험성향"])}/${esc(u["기기"])} · 관심 ${esc(u["관심 주제"])} · 조회 ${u["조회 수"]} · 수준 ${u["추정 수준"]}</span><button class="btn small">선택</button></div>`).join("");
    $("#learner-results").insertAdjacentHTML("afterbegin", `<div class="muted small">${r.total}명 중 ${r.items.length}명 표시</div>`);
    $$("#learner-results .learner-card button").forEach(b => b.onclick = () => selectLearner(+b.parentElement.dataset.uid));
  }
  async function selectLearner(uid) {
    state.learnerId = uid; state.source = "existing"; state.result = null; state.learnerInfo = null;
    await ensureLearnerInfo();
    $$(".learner-card").forEach(c => c.classList.toggle("selected", +c.dataset.uid === uid));
    renderChecklist(); save(); toast(`학습자 #${uid}를 불러왔습니다`);
  }
  async function ensureLearnerInfo() {
    if (state.source === "existing" && state.learnerId != null && (!state.learnerInfo || state.learnerInfo.user !== state.learnerId)) {
      try { state.learnerInfo = await api(`/api/learners/${state.learnerId}`); } catch (e) { state.learnerId = null; state.learnerInfo = null; toast(e.message); }
    }
    return state.learnerInfo;
  }

  // ---------- 2단계 ----------
  function renderBasic() {
    const L = state.learner, ex = state.source === "existing" && state.learnerInfo;
    $("#existing-profile").hidden = !ex; $("#basic-form").hidden = !!ex;
    if (ex) {
      const p = state.learnerInfo.profile; const seg = state.learnerInfo.segment;
      $("#existing-profile").innerHTML = `<h3>학습자 #${state.learnerId} 프로필 (스냅샷 ${state.learnerInfo.snapshot_week}주차 기준)</h3><div class="kv">` +
        ["성별", "연령", "연소득(만원)", "투자 경험", "위험성향", "기기", "학습 시간대", "관심 주제", "조회 수", "퀴즈 통과율", "완료율", "이탈률", "추정 수준", "선호 1위 주제", "통과 단원 수"].map(k => `<div><span class="muted">${k}</span><b>${esc(p[k] ?? "–")}</b></div>`).join("") +
        `</div><p class="small muted">세그먼트: ${Object.values(seg).map(s => esc(s.label)).join(" · ")}</p><button class="btn small" id="copy-as-new">이 프로필을 새 학습자로 복사</button>`;
      $("#copy-as-new").onclick = () => {
        const ev = state.learnerInfo.history.map(h => ({ item: h.item, week: h.week, complete: h.complete, quiz: h.quiz, quiz_pass: h.quiz_pass, save: h.save, drop: h.drop, replay: h.replay }));
        Object.assign(L, { label: `#${state.learnerId} 복사본`, age: p["연령"], gender: p["성별"] === "여성" ? 1 : 0, income: p["연소득(만원)"], exp: ["없음", "1~3년", "3년 이상"].indexOf(p["투자 경험"]), risk: ["안정", "중립", "적극"].indexOf(p["위험성향"]), mobile: p["기기"] === "모바일" ? 1 : 0, interests: state.learnerInfo.interest_ids.filter(x => x >= 0), placement: state.learnerInfo.placement, events: ev });
        state.source = "new"; state.touched.placement = true; state.result = null; $$("input[name=source]").forEach(r => r.checked = r.value === "new"); renderBasic(); toast("새 학습자로 복사했습니다. 수정 후 추천을 계산하세요");
      };
      return;
    }
    $("#f-label").value = L.label || ""; $("#f-age").value = L.age ?? ""; $("#f-gender").value = L.gender; $("#f-income").value = L.income ?? "";
    $("#f-exp").value = L.exp; $("#f-risk").value = L.risk; $("#f-mobile").value = L.mobile; $("#f-hour").value = L.hour;
  }
  function bindBasic() {
    const L = state.learner;
    $("#f-label").oninput = e => { L.label = e.target.value; save(); };
    $("#f-age").onchange = e => { L.age = e.target.value === "" ? null : +e.target.value; state.result = null; save(); renderChecklist(); };
    $("#f-income").onchange = e => { L.income = e.target.value === "" ? null : +e.target.value; state.result = null; save(); };
    for (const k of ["gender", "exp", "risk", "mobile", "hour"]) $(`#f-${k}`).onchange = e => { L[k] = +e.target.value; state.result = null; save(); };
  }

  // ---------- 3단계 ----------
  function renderTopics() {
    const L = state.learner; const groups = CATALOG.groups;
    $("#topic-chips").innerHTML = groups.map((g, gi) => `<div class="topic-group"><h4>${esc(g)}</h4><div class="chip-list">` +
      CATALOG.topics.map((t, ti) => CATALOG.topic_group[ti] === gi ? `<button class="chip ${L.interests.includes(ti) ? "on" : ""}" data-topic="${ti}">${esc(t)}</button>` : "").join("") + `</div></div>`).join("");
    $$("[data-topic]").forEach(b => b.onclick = () => {
      const t = +b.dataset.topic; const i = L.interests.indexOf(t);
      if (i >= 0) L.interests.splice(i, 1); else { if (L.interests.length >= 2) L.interests.shift(); L.interests.push(t); }
      state.result = null; renderTopics(); renderChecklist(); save();
    });
    $$("input[name=placement]").forEach(r => { r.checked = +r.value === L.placement; r.onchange = () => { L.placement = +r.value; state.touched.placement = true; state.result = null; save(); renderChecklist(); }; });
  }

  // ---------- 4단계 ----------
  function renderEvents() {
    const ex = state.source === "existing" && state.learnerInfo;
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
    $("#event-table").innerHTML = (ev.length ? `<tr><th>단원</th><th>주차</th><th>완료</th><th>퀴즈 통과</th><th>저장</th><th>이탈</th><th></th></tr>` : `<tr><td class="muted">학습 기록이 없습니다. 첫 방문 학습자로 처리됩니다.</td></tr>`) +
      ev.map((e, i) => { const it = item(e.item); return `<tr><td>${esc(it.title)} <span class="muted small">(${esc(it.topic)} · 수준 ${it.level})</span></td><td>${e.week ?? 0}</td><td>${e.complete ? "✓" : ""}</td><td>${e.quiz_pass ? "✓" : ""}</td><td>${e.save ? "✓" : ""}</td><td>${e.drop ? "✓" : ""}</td><td><button class="btn small ghost" data-del="${i}">삭제</button></td></tr>`; }).join("");
    $$("[data-del]").forEach(b => b.onclick = () => { ev.splice(+b.dataset.del, 1); state.result = null; renderEvents(); renderChecklist(); save(); });
  }
  function addEvent() {
    const pass = $("#ev-pass").checked;
    state.learner.events.push({ item: +$("#ev-item").value, week: 0, complete: $("#ev-complete").checked || pass, quiz: pass, quiz_pass: pass, save: $("#ev-save").checked, drop: $("#ev-drop").checked && !pass, replay: false });
    state.result = null; renderEvents(); renderChecklist(); save();
  }
  async function parseLog(text) {
    const r = await api("/api/parse-log", { csv_text: text });
    state.learner.events.push(...r.events.map(e => ({ week: 0, complete: false, quiz: false, quiz_pass: false, save: false, drop: false, replay: false, ...e, quiz: e.quiz || e.quiz_pass || false })));
    $("#log-warnings").textContent = r.warnings.join(" "); state.result = null; renderEvents(); renderChecklist(); save(); toast(`${r.events.length}건을 읽었습니다`);
  }

  // ---------- 5단계 ----------
  function renderSettings() {
    const S = state.settings; const sel = $("#s-algorithm");
    sel.innerHTML = `<option value="">운영 라우터 (${META.operational_router === "RouterNoGender" ? "성별 제외" : META.operational_router}) · 기본</option>` +
      META.methods.map(m => `<option value="${esc(m.key)}">${esc(m.label)}${META.test_ndcg[m.key] != null ? ` · 테스트 NDCG ${fmt(META.test_ndcg[m.key], 3)}` : ""}</option>`).join("");
    sel.value = S.algorithm; $("#s-k").value = S.k; $("#s-block").value = S.block_gap; $("#s-plus").value = S.plus_one_max; $("#s-exclude").value = S.exclude_passed ? "1" : "0"; $("#s-cap").value = S.topic_cap;
    const op = META.operational_algorithm;
    $("#algo-note").innerHTML = `<b>운영 설정</b> #${op.aid} ${esc(op.name)}<br><span class="muted small">${esc(op.formula)}</span><br><span class="small">검증 1,479개 설정 중 1위. 세그먼트 라우터는 전역 1위와 차이가 없었으므로(±0.0016) 라우터가 배정하는 설정도 대부분 이 설정입니다. 두 단계 위 차단·한 단계 위 1개 상한은 수업의 교육 처방이 아니라 이 프로젝트의 시연용 정책입니다.</span>`;
  }
  function bindSettings() {
    const S = state.settings;
    $("#s-k").onchange = e => { S.k = Math.max(1, Math.min(20, +e.target.value || 5)); e.target.value = S.k; state.result = null; save(); };
    $("#s-algorithm").onchange = e => { S.algorithm = e.target.value; state.result = null; save(); };
    $("#s-block").onchange = e => { S.block_gap = +e.target.value; state.result = null; save(); };
    $("#s-plus").onchange = e => { S.plus_one_max = Math.max(0, Math.min(5, +e.target.value || 0)); e.target.value = S.plus_one_max; state.result = null; save(); };
    $("#s-exclude").onchange = e => { S.exclude_passed = e.target.value === "1"; state.result = null; save(); };
    $("#s-cap").onchange = e => { S.topic_cap = e.target.value; state.result = null; save(); };
  }
  function buildRequest(extra = {}) {
    const S = state.settings, L = state.learner;
    const body = { k: S.k, algorithm: S.algorithm || null, guardrail: { block_gap: S.block_gap, plus_one_max: S.plus_one_max, exclude_passed: S.exclude_passed }, topic_cap: S.topic_cap ? +S.topic_cap : null, ...extra };
    if (state.source === "existing" && state.learnerId != null) body.learner_id = state.learnerId;
    else body.learner = { label: L.label || "새 학습자", age: L.age ?? 35, gender: L.gender, income: L.income, exp: L.exp, risk: L.risk, mobile: L.mobile, interests: L.interests, placement: L.placement, hour: L.hour, events: L.events };
    return body;
  }

  // ---------- 6단계 ----------
  async function runRecommend() {
    $("#rec-status").textContent = "계산 중…";
    try {
      state.result = await api("/api/recommend", buildRequest()); state.simResult = null; state.compare = null;
      renderResult(); renderChecklist(); save();
    } catch (e) { $("#rec-status").textContent = "오류: " + e.message; $("#rec-view").hidden = true; throw e; }
  }
  function renderResult() {
    const r = state.result; if (!r) return;
    $("#rec-status").textContent = `${r.learner.label} · ${r.latency_ms ?? "–"} ms · 스냅샷 ${r.snapshot_week}주차`;
    $("#rec-view").hidden = false;
    const allOk = r.checks.every(c => c.passed);
    $("#rec-badges").innerHTML = `<span class="badge ${allOk ? "ok" : "bad"}">${allOk ? "가드레일 검사 통과" : "검사 실패 있음"}</span><span class="badge">후보 ${r.candidates ?? 0}개</span><span class="badge">추정 수준 ${r.level} · ${LEVEL_NAME[r.level]}</span><span class="badge">${r.router ? "라우터 " + r.router : "설정 강제"}</span><span class="badge">#${r.algorithm_id} ${esc(r.family_label)}</span>` +
      (r.shortfall ? `<span class="badge warn">${r.shortfall}개 부족</span>` : "");
    renderMap(r.topic_map, "#topic-map");
    $("#map-legend").innerHTML = `<span class="l-rec">추천</span><span class="l-passed">통과한 단원</span><span>후보</span><span class="l-plus">한 단계 위(상한 ${r.guardrail.plus_one_max})</span><span class="l-blocked">가드레일 차단</span>`;
    const maxScore = Math.max(...r.items.map(i => i.score), 1e-9);
    $("#rec-list").innerHTML = r.items.length ? r.items.map(it => {
      const pos = it.contributions.filter(c => c.contribution > 0); const tot = pos.reduce((s, c) => s + c.contribution, 0) || 1;
      return `<li class="rec-item"><div class="rank">${it.rank}</div><div><div class="title">${esc(it.title)}</div><div class="meta"><span>${esc(it.topic)}</span><span>수준 ${it.level} · ${LEVEL_NAME[it.level]}</span>${it.short ? "<span>짧은 콘텐츠</span>" : ""}<span>점수 ${fmt(it.score, 3)}</span>${it.level_gap === 1 ? '<span style="color:var(--plus)">한 단계 위</span>' : ""}</div>` +
        `<div class="bar"><i style="width:${(100 * it.score / maxScore).toFixed(1)}%;background:var(--accent)"></i></div><div class="reason">${esc(it.reason)}</div>` +
        `<div class="contrib">${pos.slice(0, 4).map(c => `<div><span class="muted" title="${esc(c.label)}">${esc(c.label)}</span><div class="cbar"><i style="width:${(100 * c.contribution / tot).toFixed(1)}%"></i></div><span class="num">${fmt(c.contribution, 2)}</span></div>`).join("")}</div></div></li>`;
    }).join("") : `<li class="muted">${esc(r.reason || "추천할 단원이 없습니다")}</li>`;
    $("#rec-checks").innerHTML = r.checks.map(c => `<li class="${c.passed ? "" : "fail"}">${esc(c.name)}<span class="muted small">${esc(c.detail)}</span></li>`).join("");
    $("#rec-route").innerHTML = r.route_path.length ? r.route_path.map((p, i) => `<div class="node ${i === r.route_path.length - 1 ? "leaf" : ""}"><span class="muted">${esc(p.var_label)}${p.var ? " = " + esc(r.segment[p.var].label) : ""}</span><span>n=${p.n} · #${p.champ} ${esc(p.champion_family)} · 추정 NDCG ${fmt(p.est, 4)}</span></div>`).join("") : `<div class="muted small">설정을 강제로 골라 라우터를 쓰지 않았습니다.</div>`;
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
        const it = CATALOG.items.find(x => x.topic_id === ti && x.level === lv); const m = byItem[it.item] || { status: "eligible" };
        const label = m.status === "recommended" ? m.rank : m.status === "passed" ? "✓" : "";
        html += `<div class="cell ${m.status} ${m.rank ? "recommended" : ""}" title="${esc(it.title)} · ${{ passed: "통과", recommended: "추천 " + m.rank + "위", plus_one: "한 단계 위 후보", eligible: "후보", blocked: "가드레일 차단" }[m.status]}">${label}</div>`;
      }
    }
    el.innerHTML = html; el.style.setProperty("--cell", (36 * state.zoom / 100).toFixed(0) + "px"); $("#zoom-val").textContent = state.zoom + "%";
  }

  // ---------- 7단계 ----------
  function renderSimControls() {
    const r = state.result; const labels = META.labels;
    $("#w-income").innerHTML = `<option value="">그대로</option>` + labels.income_q.map((l, i) => `<option value="${i}">${esc(l)}</option>`).join("");
    $("#w-age").innerHTML = `<option value="">그대로</option>` + labels.age_band.map((l, i) => `<option value="${i}">${esc(l)}</option>`).join("");
    $("#w-income").value = state.sim.income_q; $("#w-age").value = state.sim.age_band; $("#w-level").value = state.sim.level; $("#w-gender").checked = state.sim.gender;
    if (!r) { $("#sim-pass").innerHTML = `<span class="muted small">6단계에서 추천을 먼저 계산하세요.</span>`; return; }
    const cands = r.topic_map.filter(m => m.status === "recommended" || m.status === "eligible" || m.status === "plus_one").sort((a, b) => (a.rank || 99) - (b.rank || 99));
    $("#sim-pass").innerHTML = cands.slice(0, 24).map(m => `<button class="chip ${state.sim.assume.includes(m.item) ? "on" : ""}" data-pass="${m.item}">${m.rank ? m.rank + "위 · " : ""}${esc(item(m.item).title)}</button>`).join("");
    $$("[data-pass]").forEach(b => b.onclick = () => { const i = +b.dataset.pass; const k = state.sim.assume.indexOf(i); if (k >= 0) state.sim.assume.splice(k, 1); else state.sim.assume.push(i); renderSimControls(); save(); });
  }
  async function runSim() {
    if (!state.result) return toast("6단계에서 추천을 먼저 계산하세요");
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
    $("#sim-status").textContent = `${state.simResult.latency_ms} ms`; $("#sim-view").hidden = false;
    $("#sim-badges").innerHTML = `<span class="badge ${same ? "ok" : ""}">${same ? "추천 목록 동일" : "추천 목록 변화"}</span>` + genderBadge +
      (sim.assume.length ? `<span class="badge">통과 가정 ${sim.assume.length}개</span>` : "") + `<span class="badge">추정 수준 ${state.result.level} → ${state.simResult.level}</span><span class="badge">#${state.simResult.algorithm_id}</span>`;
    $("#sim-base").innerHTML = state.result.items.map(i => `<li class="${now.includes(i.item_id) ? "" : "gone"}">${esc(i.title)} <span class="muted small">수준 ${i.level}</span></li>`).join("");
    $("#sim-new").innerHTML = state.simResult.items.map(i => `<li class="${base.includes(i.item_id) ? "" : "new"}">${esc(i.title)} <span class="muted small">수준 ${i.level}</span></li>`).join("");
    save();
  }

  // ---------- 8단계 ----------
  async function renderCompare(force) {
    if (!state.result) { $("#compare-view").innerHTML = `<p class="muted small">6단계에서 추천을 먼저 계산하세요.</p>`; return; }
    if (!state.compare || force) {
      $("#compare-view").innerHTML = `<p class="muted small">계산 중…</p>`;
      state.compare = await api("/api/compare", buildRequest({ methods: ["RouterNoGender", "Global", "RULE", "UCF", "ICF", "POP", "CONTENT", "MF", "MF_OBS", "MLP", "NoDemographics"].filter(m => META.methods.some(x => x.key === m)) }));
    }
    const c = state.compare; const opIds = (c.methods[0] ? c.methods[0].items : []).map(i => i.item_id);
    $("#compare-view").innerHTML = `<table class="table"><tr><th>설정</th><th>테스트 NDCG@5</th><th>Top-${state.settings.k}</th><th>운영과 겹침</th></tr>` + c.methods.map(m => {
      const ids = m.items.map(i => i.item_id); const ov = ids.filter(i => opIds.includes(i)).length;
      return `<tr><td>${esc(META.methods.find(x => x.key === m.key)?.label || m.key)}<br><span class="muted small">#${m.algorithm_id} ${esc(m.family_label)}</span></td><td class="num">${fmt(m.test_ndcg, 4)}</td><td>${m.items.map(i => `<span title="${esc(i.title)}">${i.item_id}<sub>${i.level}</sub></span>`).join(" · ")}</td><td class="num">${ov}/${ids.length}</td></tr>`;
    }).join("") + `</table><p class="muted small">후보 ${c.candidates}개 · 같은 가드레일 · 아이템 번호 옆 작은 숫자는 수준</p>`;
  }
  async function loadEvaluation() {
    EVAL = await api("/api/evaluation");
    const ds = EVAL.dataset; const res = EVAL.results; const maxN = Math.max(...res.map(r => r.ndcg));
    const opName = META.operational_router;
    let html = `<div class="kv"><div><span class="muted">학습자</span><b>${ds.users.toLocaleString()}</b></div><div><span class="muted">학습 시도</span><b>${ds.study_attempts.toLocaleString()}</b></div><div><span class="muted">설정 수</span><b>${EVAL.configurations.toLocaleString()}</b></div><div><span class="muted">신호 수</span><b>${EVAL.signal_count}</b></div><div><span class="muted">테스트 사용자</span><b>${EVAL.test_audit.rows.toLocaleString()}</b></div><div><span class="muted">정답 없는 사용자</span><b>${EVAL.test_audit.zero_observed_target.toLocaleString()}</b></div><div><span class="muted">QA 검사</span><b>${EVAL.qa.filter(q => q.passed).length}/${EVAL.qa.length}</b></div><div><span class="muted">MF·MLP 학습</span><b>${EVAL.neural_enabled ? "포함" : "제외"}</b></div></div>`;
    html += `<h4>방법별 NDCG@5 (사용자 평균, 테스트 ${EVAL.test_audit.week}주차)</h4>` + res.map(r => `<div class="evbar ${r.method === opName ? "op" : ""}"><span title="${esc(r.method)}">${esc(r.method)}</span><div class="ebar"><i style="width:${(100 * r.ndcg / maxN).toFixed(1)}%"></i></div><span class="num">${fmt(r.ndcg, 4)}</span></div>`).join("");
    html += `<div class="table-wrap"><table class="table"><tr><th>방법</th><th>NDCG@5</th><th>Diversity@5</th><th>Hit@5</th><th>전역 1위 대비 차이 [95% 구간]</th></tr>` + res.map(r => `<tr><td>${esc(r.method)}</td><td class="num">${fmt(r.ndcg)}</td><td class="num">${fmt(r.diversity, 3)}</td><td class="num">${fmt(r.hit_diagnostic, 3)}</td><td class="num">${fmt(r.difference_vs_global)} [${fmt(r.ci_low)}, ${fmt(r.ci_high)}]</td></tr>`).join("") + `</table></div>`;
    const g = EVAL.group_results.filter(x => x.method === "Global");
    const vars = { gender: "성별", age_band: "연령대", income_q: "소득분위", click_tier: "학습활동" };
    html += `<h4>전역 1위 설정의 집단별 NDCG@5 (진단용, 동등 대우의 증거가 아님)</h4><div class="table-wrap"><table class="table"><tr><th>변수</th><th>집단</th><th>사용자</th><th>NDCG@5</th><th>95% 구간</th></tr>` + g.map(x => `<tr><td>${vars[x.variable]}</td><td>${esc(META.labels[x.variable][x.group])}</td><td class="num">${x.users.toLocaleString()}</td><td class="num">${fmt(x.ndcg)}</td><td class="num">[${fmt(x.ci_low)}, ${fmt(x.ci_high)}]</td></tr>`).join("") + `</table></div>`;
    const ex = EVAL.exposure.filter(x => x.method === "RouterNoGender");
    if (ex.length) html += `<h4>심화·레버리지 콘텐츠 노출 비율 (운영 라우터, 집단별)</h4><div class="table-wrap"><table class="table"><tr><th>변수</th><th>집단</th><th>사용자</th><th>Top-5 중 심화·레버리지 비율</th></tr>` + ex.map(x => `<tr><td>${vars[x.variable]}</td><td>${esc(META.labels[x.variable][x.group])}</td><td class="num">${x.users.toLocaleString()}</td><td class="num">${fmt(x.advanced_share, 3)}</td></tr>`).join("") + `</table></div>`;
    html += `<h4>검증 상위 설정 (${EVAL.validation_audit.week}주차)</h4><div class="table-wrap"><table class="table"><tr><th>#</th><th>기법군</th><th>설정</th><th>검증 NDCG@5</th><th>Diversity</th></tr>` + EVAL.validation_top.slice(0, 10).map(j => `<tr><td>${j.job_id}</td><td>${esc(j.family)}</td><td>${esc(j.name)}</td><td class="num">${fmt(j.ndcg)}</td><td class="num">${fmt(j.diversity, 3)}</td></tr>`).join("") + `</table></div>`;
    html += `<p class="muted small">번들 생성 ${esc(EVAL.created_at)} · 운영 라우터 ${esc(EVAL.selection.operational)} · λ ${JSON.stringify(EVAL.selection.router_lambdas)} · 모의 데이터이므로 수치는 실제 학습자 성과가 아닙니다.</p>`;
    $("#eval-view").innerHTML = html;
  }

  // ---------- 9단계 ----------
  function designPayload() { return { saved_from: "학습 설계 스튜디오", version: META.version, summary: `${state.source === "existing" ? "#" + state.learnerId : state.learner.label || "새 학습자"} · k=${state.settings.k} · ${state.settings.algorithm || "운영 라우터"}`, state: { ...state, result: null, simResult: null, compare: null, learnerInfo: null }, memo: state.memo, result: state.result }; }
  async function saveDesign() {
    const name = $("#design-name").value.trim(); if (!name) return toast("설계 이름을 적어 주세요");
    state.memo = $("#design-memo").value; const r = await api("/api/designs", { name, payload: designPayload() });
    $("#design-status").textContent = `저장됨: ${r.saved} (${r.saved_at})`; listDesigns(); save();
  }
  async function listDesigns() {
    const ds = await api("/api/designs");
    $("#design-list").innerHTML = ds.length ? ds.map(d => `<li><span><b>${esc(d.name)}</b><br><span class="muted small">${esc(d.saved_at)} · ${esc(d.summary)}</span></span><span><button class="btn small" data-load="${esc(d.name)}">불러오기</button> <button class="btn small ghost" data-rm="${esc(d.name)}">삭제</button></span></li>`).join("") : `<li class="muted">저장된 설계가 없습니다.</li>`;
    $$("[data-load]").forEach(b => b.onclick = async () => { const d = await api(`/api/designs/${encodeURIComponent(b.dataset.load)}`); applyDesign(d.payload); toast(`'${d.name}'을 불러왔습니다`); });
    $$("[data-rm]").forEach(b => b.onclick = async () => { await api(`/api/designs/${encodeURIComponent(b.dataset.rm)}`, null, "DELETE"); listDesigns(); });
  }
  function applyDesign(p) {
    if (!p || !p.state) return toast("설계 파일 형식이 아닙니다");
    const s = p.state; Object.assign(state, { ...s, result: null, simResult: null, compare: null, learnerInfo: null, memo: p.memo || "" });
    if (state.source === "existing" && state.learnerId != null) api(`/api/learners/${state.learnerId}`).then(i => { state.learnerInfo = i; });
    $("#nl-text").value = state.nl.text || ""; $$("input[name=source]").forEach(r => r.checked = r.value === state.source); $("#existing-picker").hidden = state.source !== "existing";
    save(); goStep(2);
  }
  function exportCSV() {
    if (!state.result) return toast("추천을 먼저 계산하세요");
    const rows = [["rank", "item_id", "title", "topic", "level", "score", "reason"]].concat(state.result.items.map(i => [i.rank, i.item_id, i.title, i.topic, i.level, i.score.toFixed(4), i.reason]));
    download("recommendation.csv", "﻿" + rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n"), "text/csv");
  }

  // ---------- 바인딩·시작 ----------
  function bind() {
    $("#nav-prev").onclick = () => goStep(state.step - 1);
    $("#nav-next").onclick = () => goStep(state.step === 9 ? 1 : state.step + 1);
    $("#checklist-toggle").onclick = () => { $("#checklist-items").hidden = !$("#checklist-items").hidden; renderChecklist(); };
    $("#btn-new").onclick = () => { try { localStorage.removeItem("etfrec-draft"); } catch (e) { } location.reload(); };
    $("#btn-saved").onclick = () => goStep(9);
    $("#btn-file").onclick = () => { $("#file-menu").hidden = !$("#file-menu").hidden; };
    document.addEventListener("click", e => { if (!e.target.closest(".menu")) $("#file-menu").hidden = true; });
    $$("#file-menu button").forEach(b => b.onclick = () => {
      const a = b.dataset.act; $("#file-menu").hidden = true;
      if (a === "export-json") download("design.json", JSON.stringify(designPayload(), null, 2));
      if (a === "import-json") $("#import-file").click();
      if (a === "export-csv") exportCSV();
      if (a === "export-rec-json") { if (!state.result) return toast("추천을 먼저 계산하세요"); download("recommendation.json", JSON.stringify(state.result, null, 2)); }
    });
    $("#import-file").onchange = e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => applyDesign(JSON.parse(t))).catch(() => toast("JSON을 읽지 못했습니다")); e.target.value = ""; };
    $$("input[name=source]").forEach(r => r.onchange = () => { state.source = r.value; $("#existing-picker").hidden = r.value !== "existing"; state.result = null; renderChecklist(); save(); if (r.value === "existing" && !$("#learner-results").innerHTML) searchLearners(); });
    $("#learner-search").onclick = searchLearners; $("#learner-query").onkeydown = e => { if (e.key === "Enter") searchLearners(); };
    $("#nl-parse").onclick = () => parseNL().catch(e => toast(e.message)); $("#nl-text").oninput = e => { state.nl.text = e.target.value; };
    $("#skip-to-direct").onclick = () => goStep(2);
    bindBasic(); bindSettings();
    $("#quiz-apply").onclick = () => { const n = $$(".dq:checked").length; const lv = n >= 3 ? 3 : n >= 1 ? 2 : 1; state.learner.placement = lv; state.touched.placement = true; state.result = null; renderTopics(); save(); toast(`진단 결과: 수준 ${lv}`); };
    $("#ev-add").onclick = addEvent;
    $("#log-parse").onclick = () => parseLog($("#log-text").value).catch(e => toast(e.message));
    $("#log-file").onchange = e => { const f = e.target.files[0]; if (f) f.text().then(t => parseLog(t)).catch(e => toast(e.message)); };
    $("#run-recommend").onclick = () => runRecommend().catch(e => toast(e.message));
    $("#zoom-in").onclick = () => { state.zoom = Math.min(160, state.zoom + 20); if (state.result) renderMap(state.result.topic_map, "#topic-map"); };
    $("#zoom-out").onclick = () => { state.zoom = Math.max(60, state.zoom - 20); if (state.result) renderMap(state.result.topic_map, "#topic-map"); };
    $("#run-sim").onclick = () => runSim().catch(e => toast(e.message));
    $("#run-compare").onclick = () => renderCompare(true).catch(e => toast(e.message));
    $("#design-save").onclick = () => saveDesign().catch(e => toast(e.message));
    $("#design-export").onclick = () => { state.memo = $("#design-memo").value; download("design.json", JSON.stringify(designPayload(), null, 2)); };
    $("#rec-export").onclick = exportCSV;
    $("#design-memo").oninput = e => { state.memo = e.target.value; };
  }
  async function boot() {
    load();
    [META, CATALOG, EXAMPLES] = await Promise.all([api("/api/meta"), api("/api/catalog"), api("/api/examples")]);
    $("#bundle-info").textContent = `번들 ${META.created_at} · 학습자 ${META.n_users.toLocaleString()}명 · 단원 ${META.n_items}개 · 운영 설정 #${META.operational_algorithm.aid}`;
    $("#notice").textContent = META.notice + " 모의 데이터로 실행한 수업용 추천이며 실서비스 효과 검증이 아닙니다.";
    renderExamples(); bind(); $("#nl-text").value = state.nl.text || "";
    $$("input[name=source]").forEach(r => r.checked = r.value === state.source); $("#existing-picker").hidden = state.source !== "existing";
    if (state.source === "existing" && state.learnerId != null) { try { state.learnerInfo = await api(`/api/learners/${state.learnerId}`); } catch (e) { state.learnerId = null; } }
    goStep(state.step || 1);
  }
  boot().catch(e => { $("#rec-status").textContent = e.message; document.body.insertAdjacentHTML("afterbegin", `<div class="warn">서버에 연결하지 못했습니다: ${esc(e.message)}</div>`); });
})();
