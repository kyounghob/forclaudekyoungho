// UI 점검: 11단계를 실제로 조작하며 스크린샷을 남긴다. 실행: node scripts/ui_walkthrough.mjs [base_url] [out_dir]
import { chromium } from "playwright";
import fs from "node:fs";

const base = process.argv[2] || "http://127.0.0.1:8765";
const out = process.argv[3] || "docs/screens";
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.PW_CHROMIUM || undefined });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1.5 });
const errors = [];
page.on("pageerror", e => errors.push("pageerror: " + e.message));
page.on("console", m => { if (m.type() === "error") errors.push("console: " + m.text()); });
page.on("requestfailed", r => errors.push("request: " + r.url()));
// 전체 페이지 캡처에서는 고정 상단 바·하단 이동 바를 문서 흐름에 두고 토스트를 숨긴다(화면 중간에 겹쳐 찍히지 않도록).
const shot = async (name, full = true) => {
  await page.waitForTimeout(400);
  await page.evaluate(f => document.body.classList.toggle("shotmode", f), full);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: full });
  await page.evaluate(() => document.body.classList.remove("shotmode"));
  console.log("shot", name);
};
const step = async (n) => { await page.click("#nav-next"); await page.waitForSelector(`.step[data-step="${n}"]:not([hidden])`); };

await page.goto(base, { waitUntil: "networkidle" });
await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
await page.reload({ waitUntil: "networkidle" });
await page.addStyleTag({ content: "body.shotmode .topbar{position:static!important} body.shotmode .step-nav{position:static!important} body.shotmode .toast{display:none!important}" });
await page.click("#checklist-toggle");
await shot("01_idea");
// 1단계: 연금 로드맵 예시 → 자연어 파싱
await page.click('[data-ex="6"]');
await page.click("#nl-parse");
await page.waitForSelector("#nl-result:not([hidden])");
await shot("01_idea_parsed");
// 2단계: 기본 정보·목적
await step(2);
await page.fill("#f-label", "홍길동(예시)");
await shot("02_basic", false);
// 3단계: 진단 퀴즈 — 처음 10문항은 정답, 나머지는 1번 보기
await step(3);
await page.waitForSelector(".qcard");
const answers = { q01: 1, q02: 1, q03: 1, q04: 1, q05: 2, q06: 1, q07: 1, q08: 2, q09: 1, q10: 1, q11: 1, q12: 1, q13: 1, q14: 1, q15: 1, q16: 1 };
for (const [q, v] of Object.entries(answers)) await page.check(`input[name="quiz-${q}"][value="${v}"]`);
await page.click("#quiz-score");
await page.waitForSelector("#quiz-result:not([hidden])");
await shot("03_diagnosis");
await page.click("#quiz-apply");
await page.waitForTimeout(300);
// 4단계: 학습 기록(진단 통과 + 직접 추가)
await step(4);
await page.selectOption("#ev-item", "3");
await page.check("#ev-pass");
await page.click("#ev-add");
await shot("04_history");
// 5단계: 로드맵
await step(5);
await page.waitForSelector(".rm-stage", { timeout: 20000 });
await shot("05_roadmap");
// 6단계: 설정
await step(6);
await shot("06_settings", false);
// 7단계: 추천 미리보기
await step(7);
await page.waitForSelector("#rec-view:not([hidden])", { timeout: 20000 });
await shot("07_preview");
// 8단계: 시뮬레이션
await step(8);
await page.click('[data-pass]');
await page.check("#w-gender");
await page.click("#run-sim");
await page.waitForSelector("#sim-view:not([hidden])", { timeout: 20000 });
await shot("08_simulation");
// 9단계: ETF 유형 연결·데이터 출처
await step(9);
await page.waitForSelector(".type-card", { timeout: 20000 });
await page.waitForSelector("#sources-table tr");
await shot("09_types");
// 10단계: 비교·평가
await step(10);
await page.waitForSelector("#compare-view table", { timeout: 30000 });
await page.waitForSelector("#eval-view .evbar", { timeout: 30000 });
await shot("10_compare_eval");
// 11단계: 저장
await step(11);
await page.fill("#design-name", "연금 목적 초급 학습자 예시");
await page.fill("#design-memo", "자연어 초안 → 진단 퀴즈 → 로드맵 → 가드레일 기본 → 성별 뒤집기 불변 확인");
await page.click("#design-save");
await page.waitForSelector("#design-list li b", { timeout: 10000 });
await shot("11_save");
// 기존 학습자 경로
await page.click('#stepper li[data-step="1"]');
await page.check('input[name=source][value=existing]');
await page.waitForSelector(".learner-card button");
await page.fill("#learner-query", "연금");
await page.click("#learner-search");
await page.waitForSelector(".learner-card button");
await page.click(".learner-card button");
await page.waitForSelector(".learner-card.selected");
await page.click('#stepper li[data-step="4"]');
await page.waitForSelector("#existing-history table");
await shot("04_history_existing", false);
await page.click('#stepper li[data-step="5"]');
await page.waitForSelector(".rm-stage", { timeout: 20000 });
await page.waitForFunction(() => document.querySelector("#roadmap-status").textContent.includes("학습자 #"), null, { timeout: 20000 });
await shot("05_roadmap_existing", false);
await page.click('#stepper li[data-step="7"]');
await page.waitForSelector("#rec-view:not([hidden])", { timeout: 20000 });
await page.waitForFunction(() => document.querySelector("#rec-status").textContent.includes("학습자 #"), null, { timeout: 20000 });
await shot("07_preview_existing");
// 모바일 폭: 체크리스트를 접고 현재 단계 패널로 스크롤한 뒤 화면 크기로 찍는다
await page.setViewportSize({ width: 400, height: 860 });
await page.click("#checklist-toggle");
const toStep = async (n) => { await page.click(`#stepper li[data-step="${n}"]`); await page.waitForSelector(`.step[data-step="${n}"]:not([hidden])`); await page.waitForTimeout(600); await page.evaluate(k => document.querySelector(`.step[data-step="${k}"]`).scrollIntoView({ block: "start" }), n); await page.waitForTimeout(300); };
await toStep(7);
await page.waitForSelector("#rec-view:not([hidden])", { timeout: 20000 });
const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
console.log("mobile scrollWidth", scrollW);
await shot("07_preview_mobile", false);
await toStep(5);
await page.waitForSelector(".rm-stage", { timeout: 20000 });
await shot("05_roadmap_mobile", false);
await toStep(9);
await page.waitForSelector(".type-card", { timeout: 20000 });
await shot("09_types_mobile", false);
await browser.close();
console.log("errors:", errors.length ? errors : "none");
if (errors.length) process.exit(1);
