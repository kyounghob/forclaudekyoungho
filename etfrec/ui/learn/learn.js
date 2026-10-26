// 학습자 화면: 가입·로그인 → 목적·성향·관심 주제 → 진단 퀴즈 → 추천·단원 학습·이해 확인 → 로드맵·ETF 유형·내 정보
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = x => `${Math.round((x || 0) * 100)}%`;
  let CFG = null, ME = null, LAST_RID = null, OPEN_FROM_REC = null;

  async function api(path, opts = {}) {
    const init = { method: opts.method || "GET", credentials: "same-origin", headers: { "X-Requested-With": "etfrec" } };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    const r = await fetch(path, init);
    const data = (r.headers.get("content-type") || "").includes("application/json") ? await r.json() : null;
    if (!r.ok) {
      const d = data && data.detail;
      const msg = Array.isArray(d) ? d.map(x => x.msg || JSON.stringify(x)).join(", ") : (d || `요청에 실패했습니다 (${r.status})`);
      const e = new Error(msg); e.status = r.status; throw e;
    }
    return data;
  }
  let toastTimer = null;
  function toast(msg, bad = false) {
    const t = $("#toast"); t.textContent = msg; t.className = "toast" + (bad ? " bad" : ""); t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  }
  function show(id) {
    $$(".view").forEach(v => { v.hidden = v.id !== "v-" + id; });
    $("#nav").hidden = !(ME && ME.profile_complete);
    $$("#nav button").forEach(b => b.classList.toggle("on", b.dataset.go === id));
    window.scrollTo(0, 0);
  }
  function go(h) { if (location.hash === "#/" + h) route(); else location.hash = "#/" + h; }
  async function guarded(fn) {
    try { await fn(); }
    catch (e) {
      if (e.status === 401) { ME = null; return renderAuth("login", "다시 로그인해 주세요"); }
      if (e.status === 409) return go("onboard");
      toast(e.message, true);
    }
  }

  async function route() {
    const [name, arg] = (location.hash.replace(/^#\/?/, "") || "home").split("/");
    if (!ME) return renderAuth("login");
    if (!ME.profile_complete && name !== "onboard" && name !== "quiz" && !(ME.is_admin && name === "me")) return renderOnboard(true);
    switch (name) {
      case "onboard": return renderOnboard(!ME.profile_complete);
      case "quiz": return guarded(renderQuiz);
      case "unit": return guarded(() => renderUnit(parseInt(arg, 10)));
      case "roadmap": return guarded(renderRoadmap);
      case "types": return guarded(renderTypes);
      case "me": return guarded(renderMe);
      default: return guarded(renderHome);
    }
  }

  // ---------- 가입·로그인 ----------
  function renderAuth(mode = "login", message = "") {
    show("auth");
    const signup = mode === "signup";
    $("#v-auth").innerHTML = `
      <div class="hero"><h1>목적에 맞는 ETF 공부, 다음에 볼 단원부터</h1>
        <p>투자 목적·기간·성향과 진단 결과로 66개 ETF 교육 단원 가운데 지금 공부할 단원을 골라 드립니다. 특정 상품의 매수·매도를 권하지 않습니다.</p></div>
      <div class="card">
        <div class="tabs" role="tablist">
          <button type="button" role="tab" aria-selected="${!signup}" data-mode="login" class="${signup ? "" : "on"}">로그인</button>
          <button type="button" role="tab" aria-selected="${signup}" data-mode="signup" class="${signup ? "on" : ""}">회원가입</button></div>
        <form id="f-auth" novalidate>
          <label for="a-user">아이디</label><input id="a-user" name="username" autocomplete="username" maxlength="30" required>
          ${signup ? `<p class="muted small">영문 소문자·숫자·._- 3~30자. 이메일·전화번호는 받지 않습니다.</p>` : ""}
          <label for="a-pw">비밀번호</label><input id="a-pw" name="password" type="password" autocomplete="${signup ? "new-password" : "current-password"}" maxlength="128" required>
          ${signup ? `<label for="a-pw2">비밀번호 확인 (8자 이상)</label><input id="a-pw2" name="password2" type="password" autocomplete="new-password" maxlength="128" required>
            ${CFG.invite_required ? `<label for="a-inv">초대 코드</label><input id="a-inv" name="invite_code" maxlength="64" required>` : ""}
            <details class="consent"><summary>개인정보 수집·이용 안내 (필수)</summary><p>${esc(CFG.consent_text).replace(/\n/g, "<br>")}</p></details>
            <label class="check"><input type="checkbox" name="consent"> 안내를 읽었고 수집·이용에 동의합니다</label>` : ""}
          <div class="btn-row"><button class="btn primary" type="submit">${signup ? "가입하고 시작하기" : "로그인"}</button></div>
          ${!signup && new URLSearchParams(location.search).get("admin") ? `<p class="muted small">관리자 계정으로 로그인하면 관리자 메뉴(파일럿 보고서·분석 자료·스튜디오)로 이동합니다.</p>` : ""}
          <p class="err" id="auth-err" role="alert">${esc(message)}</p>
        </form></div>`;
    $$("#v-auth [data-mode]").forEach(b => b.addEventListener("click", () => renderAuth(b.dataset.mode)));
    $("#f-auth").addEventListener("submit", async ev => {
      ev.preventDefault();
      const f = ev.target, err = $("#auth-err"), btn = f.querySelector("button[type=submit]");
      const username = f.username.value.trim().toLowerCase(), password = f.password.value;
      err.textContent = "";
      if (signup) {
        if (password.length < 8) return void (err.textContent = "비밀번호는 8자 이상입니다");
        if (password !== f.password2.value) return void (err.textContent = "비밀번호 확인이 다릅니다");
        if (!f.consent.checked) return void (err.textContent = "개인정보 수집·이용에 동의해야 가입할 수 있습니다");
      }
      btn.disabled = true;
      try {
        if (signup) await api("/api/auth/signup", { method: "POST", body: { username, password, consent: true, invite_code: f.invite_code ? f.invite_code.value : null } });
        else await api("/api/auth/login", { method: "POST", body: { username, password } });
        ME = await api("/api/me");
        if (new URLSearchParams(location.search).get("admin") && ME.is_admin) return void location.assign("/#/me");   // 관리자 메뉴(보고서·자료·스튜디오)
        history.replaceState(null, "", location.pathname + (ME.profile_complete ? "#/home" : "#/onboard"));
        route();
      } catch (e) { err.textContent = e.message; btn.disabled = false; }
    });
  }

  // ---------- 목적·성향·관심 주제 ----------
  function profileForm(p) {
    const radio = (name, value, label, checked) =>
      `<label class="opt"><input type="radio" name="${name}" value="${esc(value)}" ${checked ? "checked" : ""} required><span>${esc(label)}</span></label>`;
    const groups = {};
    CFG.topics.forEach(t => { (groups[t.group] = groups[t.group] || []).push(t); });
    const sel = new Set(p.interests || []);
    return `
      <fieldset><legend>투자 목적</legend><div class="choices">${Object.entries(CFG.goals).map(([k, v]) => radio("goal", k, v, p.goal === k)).join("")}</div></fieldset>
      <fieldset><legend>투자 기간</legend><div class="seg">${Object.entries(CFG.horizons).map(([k, v]) => radio("horizon", k, v, p.horizon === k)).join("")}</div></fieldset>
      <fieldset><legend>위험성향</legend><div class="seg">${CFG.risks.map((v, i) => radio("risk", i, v, p.risk === i)).join("")}</div></fieldset>
      <fieldset><legend>투자 경험</legend><div class="seg">${CFG.exps.map((v, i) => radio("exp", i, v, p.exp === i)).join("")}</div></fieldset>
      <fieldset><legend>관심 주제 (최대 2개, 선택)</legend>
        ${Object.entries(groups).map(([g, ts]) => `<div class="group-name">${esc(g)}</div><div class="seg">${ts.map(t =>
          `<label class="opt"><input type="checkbox" name="interests" value="${t.id}" ${sel.has(t.id) ? "checked" : ""}><span>${esc(t.name)}</span></label>`).join("")}</div>`).join("")}
      </fieldset>
      <fieldset><legend>학습 방식</legend><label class="check"><input type="checkbox" name="mobile" ${p.mobile === 0 ? "" : "checked"}> 주로 휴대폰으로 짧게 학습해요</label></fieldset>`;
  }
  function limitInterests(form) {
    const boxes = $$("input[name=interests]", form);
    const sync = () => { const n = boxes.filter(b => b.checked).length; boxes.forEach(b => { b.disabled = !b.checked && n >= 2; }); };
    boxes.forEach(b => b.addEventListener("change", sync)); sync();
  }
  function readProfile(form) {
    const v = n => { const x = form.querySelector(`input[name=${n}]:checked`); return x ? x.value : null; };
    if (!v("goal") || !v("horizon") || v("risk") === null || v("exp") === null) throw new Error("투자 목적·기간·위험성향·경험을 모두 골라 주세요");
    return { goal: v("goal"), horizon: v("horizon"), risk: +v("risk"), exp: +v("exp"), mobile: form.mobile.checked ? 1 : 0,
             interests: $$("input[name=interests]:checked", form).map(b => +b.value) };
  }
  function renderOnboard(first) {
    show("onboard");
    $("#v-onboard").innerHTML = `
      <h1>${first ? "학습 목적을 알려 주세요" : "학습 정보 수정"}</h1>
      <p class="muted">로드맵과 추천 점수에 쓰입니다. 연령·성별·소득은 묻지 않습니다.</p>
      <form id="f-profile" class="card">${profileForm((ME && ME.profile) || {})}
        <div class="btn-row"><button class="btn primary" type="submit">${first ? "다음: 진단 퀴즈" : "저장"}</button>
        ${first ? "" : `<a class="btn" href="#/me">취소</a>`}</div><p class="err" id="p-err" role="alert"></p></form>`;
    const f = $("#f-profile"); limitInterests(f);
    f.addEventListener("submit", async ev => {
      ev.preventDefault();
      try {
        const body = readProfile(f);
        await api("/api/me/profile", { method: "PUT", body });
        ME = await api("/api/me");
        if (first) go("quiz"); else { toast("저장했습니다"); go("me"); }
      } catch (e) { $("#p-err").textContent = e.message; }
    });
  }

  // ---------- 진단 퀴즈 ----------
  async function renderQuiz() {
    show("quiz");
    const qs = await api("/api/me/quiz");
    $("#v-quiz").innerHTML = `
      <h1>진단 퀴즈 ${qs.length}문항</h1>
      <p class="muted">아는 만큼만 답하세요. 맞힌 단원은 이미 아는 단원으로 보고 추천에서 뺍니다. 건너뛰면 기초 수준부터 시작합니다.</p>
      <form id="f-quiz" class="card">${qs.map((q, n) => `
        <div class="q" data-q="${esc(q.id)}"><p>${n + 1}. ${esc(q.text)} <span class="chip">${esc(q.topic)}</span></p>
          <div class="opts">${q.options.map((o, i) => `<label class="opt"><input type="radio" name="${esc(q.id)}" value="${i}"><span>${esc(o)}</span></label>`).join("")}</div>
          <div class="explain" hidden></div></div>`).join("")}
        <div class="btn-row"><button class="btn primary" type="submit">채점하기</button><button class="btn" type="button" id="q-skip">건너뛰기</button></div>
      </form><div id="q-result"></div>`;
    $("#q-skip").addEventListener("click", () => go("home"));
    $("#f-quiz").addEventListener("submit", async ev => {
      ev.preventDefault();
      const answers = {};
      $$("#f-quiz input[type=radio]:checked").forEach(r => { answers[r.name] = +r.value; });
      if (!Object.keys(answers).length) return toast("한 문항 이상 답해 주세요", true);
      await guarded(async () => {
        const r = await api("/api/me/diagnosis", { method: "POST", body: { answers } });
        (r.results || []).forEach(x => {
          const box = $(`#f-quiz .q[data-q="${x.id}"]`); if (!box || !x.answered) return;
          box.classList.add(x.correct ? "right" : "wrong");
          const e = box.querySelector(".explain"); e.hidden = false; e.textContent = `정답: ${x.correct_option} — ${x.explain}`;
        });
        ME = await api("/api/me");
        const known = r.mastered || [];
        $("#q-result").innerHTML = `<div class="card"><div class="eyebrow">진단 결과</div>
          <h2>수준 ${r.level} · ${esc(CFG.levels[r.level])}</h2><p>정답 ${r.correct}/${r.answered}문항 · 이미 아는 단원으로 인정 ${known.length}개</p>
          ${known.length ? `<form id="f-review"><p class="muted small">아래 단원은 이미 아는 것으로 보고 추천에서 뺍니다. 아직 잘 모르는 단원이 있으면 체크하세요. 다시 추천에 나옵니다.</p>
            <div class="opts">${known.map(k => `<label class="check"><input type="checkbox" name="unk" value="${k.item}"> ${esc(k.title)}</label>`).join("")}</div>
            <div class="btn-row"><button class="btn primary" type="submit">확인하고 추천 받기</button></div></form>`
          : `<div class="btn-row"><a class="btn primary" href="#/home">추천 받기</a></div>`}</div>`;
        const fr = $("#f-review");
        if (fr) fr.addEventListener("submit", ev => { ev.preventDefault(); guarded(async () => {
          const items = $$("input[name=unk]:checked", fr).map(b => +b.value);
          await api("/api/me/diagnosis/review", { method: "POST", body: { items } });
          if (items.length) toast(`${items.length}개 단원을 다시 추천 대상으로 돌렸어요`);
          go("home");
        }); });
        $("#q-result").scrollIntoView({ behavior: "smooth" });
      });
    });
  }

  // ---------- 홈: 로드맵 요약 + 추천 ----------
  async function renderHome() {
    show("home");
    $("#v-home").innerHTML = `<p class="muted">추천을 계산하는 중…</p>`;
    const [r, hist] = await Promise.all([api("/api/me/recommendations?k=5"), api("/api/me/history")]);
    LAST_RID = r.request_id;
    const rm = r.roadmap || {};
    $("#v-home").innerHTML = `
      <div class="card"><div class="eyebrow">${esc(rm.goal_label || "")} 로드맵</div>
        <h2>현재 단계: ${esc(rm.current_stage_name || "")}</h2>
        <div class="progress" role="progressbar" aria-valuenow="${Math.round((rm.progress || 0) * 100)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${pct(rm.progress)}"></i></div>
        <p class="muted">${rm.units_passed || 0}/${rm.units_total || 0}단원 통과 · 남은 학습 약 ${rm.minutes_left || 0}분
        ${rm.next_unit ? ` · 다음 단원 <a href="#/unit/${rm.next_unit.item}">${esc(rm.next_unit.title)}</a>` : ""}</p></div>
      <h3>지금 공부할 단원</h3>
      ${r.items.length ? `<ol class="recs">${r.items.map((it, i) => `
        <li class="card rec"><span class="rank">${i + 1}</span>
          <div><b>${esc(it.title)}</b> ${it.in_current_stage ? `<span class="tag">현재 단계</span>` : ""}</div>
          <div class="chips"><span class="chip">${esc(it.topic)}</span><span class="chip">${esc(it.level_name)}</span><span class="chip">약 ${it.minutes}분</span></div>
          <p class="reason">${esc(it.reason)}</p>
          ${it.detail ? `<details class="why"><summary>추천 근거 자세히</summary><p>${esc(it.detail)}</p></details>` : ""}
          <a class="btn primary" href="#/unit/${it.item}" data-rec="${it.item}">학습하기</a></li>`).join("")}</ol>`
        : `<div class="card"><p>지금 추천할 단원이 없습니다. 로드맵에서 남은 단원을 확인해 보세요.</p></div>`}
      ${r.shortfall > 0 && r.items.length ? `<p class="muted small">선수 학습을 마친 단원만 추천해서 지금은 ${r.items.length}개입니다.</p>` : ""}
      ${r.ask_rating ? `<div class="card" id="rate"><p><b>위 추천의 ‘추천 이유’가 이해되나요?</b></p>
        <div class="seg">${["전혀 아니다", "아니다", "보통", "그렇다", "매우 그렇다"].map((t, i) => `<button class="btn" type="button" data-rate="${i + 1}">${i + 1} ${t}</button>`).join("")}</div></div>` : ""}
      <h3>최근 학습</h3>
      ${hist.length ? `<ul class="card hist">${hist.slice(0, 6).map(h => `<li><a href="#/unit/${h.item}">${esc(h.title)}</a><span class="muted">${esc(h.kind)}${h.self_check ? "(스스로 확인)" : ""}</span></li>`).join("")}</ul>`
        : `<p class="muted">아직 기록이 없습니다. 추천 단원부터 시작해 보세요.</p>`}`;
    $$("#v-home [data-rec]").forEach(a => a.addEventListener("click", () => { OPEN_FROM_REC = +a.dataset.rec; }));
    $$("#rate [data-rate]").forEach(b => b.addEventListener("click", () => guarded(async () => {
      await api("/api/me/rating", { method: "POST", body: { request_id: r.request_id, value: +b.dataset.rate } });
      $("#rate").innerHTML = `<p class="muted">응답 고마워요. 추천 설명을 고치는 데 씁니다.</p>`;
    })));
  }

  // ---------- 단원 ----------
  async function renderUnit(item) {
    show("unit");
    const fromRec = OPEN_FROM_REC === item && LAST_RID;
    OPEN_FROM_REC = null;
    const d = await api(`/api/me/units/${item}` + (fromRec ? `?rid=${encodeURIComponent(LAST_RID)}` : ""));
    const st = d.status, L = d.lesson;
    $("#v-unit").innerHTML = `
      <a class="btn" href="#/home">← 추천으로</a>
      <div class="card">
        <div class="chips"><span class="chip">${esc(d.topic)}</span><span class="chip">수준 ${d.level} · ${esc(d.level_name)}</span><span class="chip">약 ${d.minutes}분</span>
          ${st.passed ? `<span class="tag">${st.by_diagnosis ? "진단으로 통과" : "이해 확인 완료"}</span>` : st.completed ? `<span class="tag warn">학습 완료</span>` : ""}</div>
        <h1>${esc(d.title)}</h1>
        ${d.prereq_titles.length ? `<p class="muted small">선수 단원: ${d.prereq_titles.map(esc).join(", ")}</p>` : ""}
        ${L ? `<h3>핵심 요점</h3><ul class="lesson">${L.points.map(p => `<li>${esc(p)}</li>`).join("")}</ul>
              ${L.example ? `<p><b>예시</b> ${esc(L.example)}</p>` : ""}<p class="muted small">기준일 ${esc(L.asof)} · 거래 전 기관 공지로 확인하세요</p>`
            : d.concepts.length ? `<h3>핵심 개념</h3><ul class="lesson">${d.concepts.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
        ${d.sources.length ? `<h3>학습 자료</h3><ul class="lesson">${d.sources.map(s => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)}</a> <span class="muted small">${esc(s.menu || "")}</span></li>`).join("")}</ul>` : ""}
        <div class="btn-row"><button class="btn" data-act="complete" type="button">학습 완료</button><button class="btn" data-act="save" type="button">저장</button></div>
      </div>
      <div class="card" id="check"><h3 style="margin-top:0">이해 확인</h3>
        ${st.passed ? `<p>이 단원은 통과로 기록되어 있습니다.</p>` : d.check ? `<form id="f-check"><p><b>${esc(d.check.text)}</b></p>
            <div class="opts">${d.check.options.map((o, i) => `<label class="opt"><input type="radio" name="ans" value="${i}"><span>${esc(o)}</span></label>`).join("")}</div>
            <div class="btn-row"><button class="btn primary" type="submit">확인</button></div><p class="err" id="c-msg" role="alert"></p></form>`
          : `<form id="f-self"><label class="check"><input type="checkbox" name="ok"> 핵심 요점을 이해했어요(이 단원은 확인 문항이 없어 스스로 표시합니다)</label>
            <div class="btn-row"><button class="btn primary" type="submit">이해 표시</button></div></form>`}
      </div>`;
    const send = async body => api(`/api/me/units/${item}/progress`, { method: "POST", body: { ...body, request_id: LAST_RID } });
    $$("#v-unit [data-act]").forEach(b => b.addEventListener("click", () => guarded(async () => {
      await send({ action: b.dataset.act }); toast(b.dataset.act === "save" ? "저장했습니다" : "학습 완료로 기록했습니다"); renderUnit(item);
    })));
    const fc = $("#f-check");
    if (fc) fc.addEventListener("submit", ev => { ev.preventDefault(); guarded(async () => {
      const a = fc.querySelector("input[name=ans]:checked"); if (!a) return toast("보기를 골라 주세요", true);
      const r = await send({ action: "check", answer: +a.value });
      if (r.correct) { toast("정답입니다. 통과로 기록했어요"); renderUnit(item); }
      else $("#c-msg").textContent = "아쉽게도 오답입니다. 요점을 다시 보고 도전해 보세요.";
    }); });
    const fs = $("#f-self");
    if (fs) fs.addEventListener("submit", ev => { ev.preventDefault(); guarded(async () => {
      if (!fs.ok.checked) return toast("이해했다면 체크해 주세요", true);
      await send({ action: "check", self_check: true }); toast("이해한 단원으로 기록했어요"); renderUnit(item);
    }); });
  }

  // ---------- 로드맵 ----------
  async function renderRoadmap() {
    show("roadmap");
    const rm = await api("/api/me/roadmap");
    const icon = s => s === "passed" ? "✓ 통과" : s === "available" ? "학습 가능" : "🔒 선수 필요";
    $("#v-roadmap").innerHTML = `
      <h1>${esc(rm.goal_label)} 로드맵</h1>
      <p class="muted">진행률 ${pct(rm.progress)} (${rm.units_passed}/${rm.units_total}단원) · 남은 학습 약 ${rm.minutes_left}분. 선수 단원을 마쳐야 다음 단원이 열립니다.</p>
      ${rm.stages.map(s => `<div class="card stage ${s.key === rm.current_stage ? "current" : ""}">
        <div class="eyebrow">${s.key === rm.current_stage ? "현재 단계" : s.done ? "완료" : ""}</div><h2>${esc(s.name)}</h2>
        <p class="muted small">${s.units && s.units.length ? `${s.passed}/${s.total} 통과 · 남은 ${s.minutes_left}분` : esc(s.note || "")}</p>
        ${(s.units || []).map(u => `<div class="unit-row"><a href="#/unit/${u.item}">${esc(u.title)}</a><small>${icon(u.status)}${u.missing_prereqs && u.missing_prereqs.length ? ` · ${u.missing_prereqs.map(esc).join(", ")}` : ""}</small></div>`).join("")}
      </div>`).join("")}`;
  }

  // ---------- ETF 유형 ----------
  async function renderTypes() {
    show("types");
    const t = await api("/api/me/types");
    const txt = v => Array.isArray(v) ? v.join(" · ") : (v || "");
    $("#v-types").innerHTML = `
      <h1>${esc(t.goal_label)}에 맞는 ETF 유형</h1>
      <p class="muted">필요한 개념 단원을 통과하면 유형 카드가 열립니다. 교육용 분류이며 개별 상품의 적합성 판단이나 매수 권유가 아닙니다.</p>
      ${t.cards.map(c => `<div class="card type-card ${c.unlocked ? "" : "locked"}">
        <div class="chips">${c.unlocked ? `<span class="tag">열림</span>` : `<span class="tag warn">개념 ${c.concepts_passed}/${c.concepts_total}</span>`}
          ${c.learn_only ? `<span class="chip">성향상 학습만 권장</span>` : ""}<span class="chip">위험 ${"●".repeat(c.risk || 0)}</span></div>
        <h2>${esc(c.name)}</h2><p>${esc(c.description)}</p>
        <details><summary>세금·연금계좌·규제·주의</summary>
          ${c.tax ? `<p class="kv"><b>세금</b> ${esc(txt(c.tax))}</p>` : ""}${c.pension ? `<p class="kv"><b>연금계좌</b> ${esc(txt(c.pension))}</p>` : ""}
          ${c.regulation ? `<p class="kv"><b>규제</b> ${esc(txt(c.regulation))}</p>` : ""}${c.cautions ? `<p class="kv"><b>주의</b> ${esc(txt(c.cautions))}</p>` : ""}
        </details></div>`).join("")}
      <p class="muted small">${esc(t.notice || "")}</p>`;
  }

  // ---------- 내 정보 ----------
  async function renderMe() {
    show("me");
    ME = await api("/api/me");
    const p = ME.profile, dg = p.diagnosis;
    $("#v-me").innerHTML = `
      <h1>내 정보</h1>
      ${ME.is_admin ? `<div class="card"><h3 style="margin-top:0">관리자</h3><div class="btn-row"><a class="btn" href="/studio">스튜디오 열기</a>
        <a class="btn" href="/api/admin/pilot-report" target="_blank" rel="noopener">파일럿 보고서 보기</a>
        <a class="btn" href="/api/admin/pilot-data">분석 자료 내려받기(zip)</a></div>
        <p class="muted small">보고서는 지금까지의 기록으로 계산합니다. 마감일 기준은 주소에 ?as_of=2026-11-29를 붙입니다.</p></div>` : ""}
      <div class="card"><p class="kv"><b>아이디</b> ${esc(ME.username)}${ME.is_admin ? ` <span class="tag">관리자</span>` : ""}</p>
        <p class="kv"><b>투자 목적</b> ${esc(CFG.goals[p.goal] || "")} · <b>기간</b> ${esc(CFG.horizons[p.horizon] || "")} · <b>위험성향</b> ${esc(CFG.risks[p.risk] || "")} · <b>경험</b> ${esc(CFG.exps[p.exp] || "")}</p>
        <p class="kv"><b>관심 주제</b> ${(p.interests || []).map(i => esc(CFG.topics[i].name)).join(", ") || "없음"}</p>
        <p class="kv"><b>진단</b> ${dg ? `수준 ${dg.level} · 정답 ${dg.correct}/${dg.answered}` : "아직 안 함"}</p>
        <div class="btn-row"><a class="btn" href="#/onboard">정보 수정</a><a class="btn" href="#/quiz">진단 다시 하기</a></div></div>
      <div class="card" id="survey"></div>
      <div class="card"><h3 style="margin-top:0">내 데이터</h3><p class="muted small">계정·학습 정보·학습 기록을 JSON 파일로 내려받습니다.</p>
        <div class="btn-row"><button class="btn" id="m-export" type="button">내 데이터 내려받기</button><button class="btn" id="m-logout" type="button">로그아웃</button></div></div>
      <div class="card"><h3 style="margin-top:0">계정 삭제</h3><p class="muted small">계정과 학습 기록, 추천 노출 기록을 바로 지웁니다. 되돌릴 수 없습니다.</p>
        <form id="f-del"><label for="d-pw">비밀번호 확인</label><input id="d-pw" name="password" type="password" autocomplete="current-password" required>
        <div class="btn-row"><button class="btn danger" type="submit">계정 삭제</button></div><p class="err" id="d-err" role="alert"></p></form></div>`;
    if (ME.is_admin) $("#survey").remove();                          // 관리자 응답은 분석에서 빠지므로 설문을 띄우지 않는다
    else renderSurvey(await api("/api/me/survey"));
    $("#m-export").addEventListener("click", () => guarded(async () => {
      const r = await fetch("/api/me/export", { credentials: "same-origin" });
      if (!r.ok) throw Object.assign(new Error("내려받지 못했습니다"), { status: r.status });
      const url = URL.createObjectURL(await r.blob()); const a = document.createElement("a");
      a.href = url; a.download = `etfrec-${ME.username}.json`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    }));
    $("#m-logout").addEventListener("click", () => guarded(async () => {
      await api("/api/auth/logout", { method: "POST" }); ME = null; history.replaceState(null, "", location.pathname); renderAuth("login", "로그아웃했습니다");
    }));
    $("#f-del").addEventListener("submit", ev => { ev.preventDefault(); guarded(async () => {
      if (!confirm("정말 계정과 모든 학습 기록을 지울까요?")) return;
      try { await api("/api/me", { method: "DELETE", body: { password: ev.target.password.value } }); }
      catch (e) { if (e.status === 401) return void ($("#d-err").textContent = e.message); throw e; }
      ME = null; history.replaceState(null, "", location.pathname); renderAuth("signup", "계정을 삭제했습니다");
    }); });
  }

  function renderSurvey(sv) {
    const box = $("#survey"), prev = (sv.answers && sv.answers.answers) || {};
    const scale = ["전혀 아니다", "아니다", "보통", "그렇다", "매우 그렇다"];
    box.innerHTML = `<h3 style="margin-top:0">마무리 설문 ${sv.done ? `<span class="tag">응답함</span>` : sv.suggested ? `<span class="tag warn">응답 부탁드려요</span>` : ""}</h3>
      <p class="muted small">${sv.suggested ? `가입한 지 ${sv.days}일이 지났어요. ` : ""}1분이면 끝나요. 추천을 고치는 데만 씁니다.${sv.done ? " 다시 제출하면 마지막 응답으로 바뀝니다." : ""}</p>
      <form id="f-survey">${sv.items.map(q => `<fieldset><legend>${esc(q.text)}</legend><div class="seg">${scale.map((t, i) =>
        `<label class="opt"><input type="radio" name="${q.key}" value="${i + 1}" ${prev[q.key] === i + 1 ? "checked" : ""}><span>${i + 1} ${t}</span></label>`).join("")}</div></fieldset>`).join("")}
        <label for="s-comment">불편했던 점이나 바라는 점 (선택, 이름·연락처 같은 개인정보는 적지 마세요)</label>
        <input id="s-comment" name="comment" maxlength="500" value="${esc((sv.answers && sv.answers.comment) || "")}">
        <div class="btn-row"><button class="btn primary" type="submit">${sv.done ? "다시 제출" : "제출"}</button></div><p class="err" id="s-err" role="alert"></p></form>`;
    $("#f-survey").addEventListener("submit", ev => { ev.preventDefault(); guarded(async () => {
      const f = ev.target, answers = {};
      for (const q of sv.items) { const x = f.querySelector(`input[name=${q.key}]:checked`); if (!x) return void ($("#s-err").textContent = "모든 문항에 답해 주세요"); answers[q.key] = +x.value; }
      await api("/api/me/survey", { method: "POST", body: { answers, comment: f.comment.value } });
      toast("설문에 응답해 주셔서 고마워요"); renderSurvey(await api("/api/me/survey"));
    }); });
  }

  // ---------- 시작 ----------
  $$("#nav button").forEach(b => b.addEventListener("click", () => go(b.dataset.go)));
  window.addEventListener("hashchange", route);
  (async () => {
    try { CFG = await api("/api/public/config"); }
    catch (e) { $("#v-loading").innerHTML = `<p class="err center">서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.</p>`; return; }
    $("#notice").textContent = CFG.notice;
    try { const s = await api("/api/auth/session"); ME = s.authenticated ? s : null; } catch (e) { ME = null; }
    route();
  })();
})();
