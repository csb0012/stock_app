// 화면 전체 테스트 (Playwright, 가짜 API) — 빌드된 화면(dist)을 vite preview 로 띄우고 /api 요청은 fixtures.mjs 로 응답.
// 실행: frontend 폴더에서  npm run build && node e2e/smoke.mjs   (스크린샷: E2E_SHOTS=폴더 를 주면 저장)
// 백엔드·외부 API 없이 동작. 실제 응답 형식은 backend/tests 가 따로 검사.
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import * as F from "./fixtures.mjs";
import * as PF from "./paper_fixtures.mjs";
import * as KF from "./kis_fixtures.mjs";
import * as RF from "./pred_fixtures.mjs";
import * as SF from "./signal_fixtures.mjs";

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require("playwright")); }
catch { console.error("playwright 가 없습니다 — npm i -D playwright && npx playwright install chromium"); process.exit(2); }

const PORT = Number(process.env.E2E_PORT || 4173);
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = process.env.E2E_SHOTS || "";
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

// ---------------- 가짜 API ----------------
function makeApi(overrides = {}) {
  const calls = [];
  const table = {
    "GET /api/auth/me": { id: 1, username: "tester", nickname: null, display_name: "tester", totp_enabled: false, email: null, email_verified: false,
                          phone: null, phone_verified: false, verified: false, created_at: "2026-11-01T00:00:00", password_changed_at: null },
    "GET /api/auth/options": { signup_open: true, mail_configured: true, sms_configured: true },
    "GET /api/auth/activity": { items: [], recent_failures: 0 },
    "GET /api/market/status": F.MARKET_STATUS,
    "GET /api/market/overview/bigtech": F.BIGTECH,
    "GET /api/market/overview/etfs": { items: [], updated_at: F.BIGTECH.updated_at },
    "GET /api/market/calendar": F.CALENDAR,
    "GET /api/watchlist/": F.WATCH_LIST_BASIC,
    "GET /api/watchlist/analysis": F.WATCHLIST,
    "GET /api/stocks/recommendations/shortterm": F.RECS,
    "GET /api/stocks/recommendations/longterm": F.RECS,
    "GET /api/stocks/search": F.SEARCH,
    "GET /api/stocks/quote/US/AVGO": F.QUOTE_AVGO,
    "GET /api/stocks/screener/kr/trading_value": [],
    "GET /api/portfolio/": F.PORTFOLIO_LIST,
    "GET /api/portfolio/analysis": F.PORTFOLIO,
    "GET /api/chat/status": { model: "규칙 기반", ready: true },
    "GET /api/market/regime": F.REGIME,
    "GET /api/quant": F.QUANT,
    "GET /api/gurus": SF.GURUS,
    "GET /api/gurus/stocks": SF.GURU_STOCKS,
    "GET /api/gurus/buffett": SF.GURU_DETAIL,
    "GET /api/value/screens": SF.VALUE_SCREENS,
    "GET /api/value/KR/undervalued_growth": SF.VALUE_KR,
    "GET /api/value/US/undervalued_growth": SF.VALUE_US,
    "GET /api/flows/overview": SF.FLOWS,
    "GET /api/paper/config": PF.PAPER_CONFIG,
    "GET /api/paper/accounts": PF.PAPER_ACCOUNTS,
    "GET /api/paper/accounts/1": PF.PAPER_ACCOUNT,
    "GET /api/paper/simulations": PF.PAPER_SIMS,
    "GET /api/paper/simulations/1": PF.PAPER_SIM,
    ...overrides,
  };
  async function handle(route) {
    const req = route.request();
    const url = new URL(req.url());
    const key = `${req.method()} ${url.pathname}`;
    const hd = req.headers();
    calls.push({ key, query: url.search, body: req.postData(), token: hd["x-access-token"], authorization: hd["authorization"] });
    let body = table[key];
    if (typeof body === "function") body = body(req);
    if (body && body.__status) {   // 오류 응답 흉내: { __status: 401, detail: "...", __headers: {...} }
      const { __status, __headers, ...rest } = body;
      return route.fulfill({ status: __status, contentType: "application/json", headers: __headers, body: JSON.stringify(rest) });
    }
    if (body === undefined && req.method() !== "GET") body = { ok: true };
    if (body === undefined) {
      // 가짜 응답이 없는 화면 데이터 → 서버 오류처럼 (화면이 오류 문구를 보여야 하고 멈추면 안 됨)
      return route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: `e2e: 가짜 응답 없음 (${key})` }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  }
  return { handle, calls, table };
}

// ---------------- 작은 테스트 도구 ----------------
const results = [];
let browser;

async function withPage(opts, fn) {
  const { width = 1440, height = 900, theme = "light", api = makeApi(), token = true, init } = opts;
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  await ctx.addInitScript(([t, th, extra]) => {
    if (sessionStorage.getItem("e2e-init")) return;   // 새로고침 때는 다시 안 넣음 (화면이 저장한 값 유지)
    sessionStorage.setItem("e2e-init", "1");
    localStorage.clear();
    if (t) localStorage.setItem("token", "e2e-token");
    localStorage.setItem("theme", th);
    for (const [k, v] of Object.entries(extra || {})) localStorage.setItem(k, v);
  }, [token, theme, init || {}]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !/Failed to load resource|status of 502/.test(m.text())) errors.push(`console: ${m.text()}`);
  });
  await page.route("**/api/**", api.handle);
  try {
    await fn(page, api);
    if (errors.length) throw new Error(errors.join("\n"));
  } finally {
    await ctx.close();
  }
}

async function test(name, opts, fn) {
  const t0 = Date.now();
  try {
    await withPage(opts, fn);
    results.push({ name, ok: true, ms: Date.now() - t0 });
    console.log(`  ✓ ${name}`);
  } catch (e) {
    results.push({ name, ok: false, err: e.message });
    console.log(`  ✗ ${name}\n      ${String(e.message).split("\n").join("\n      ")}`);
  }
}

function expect(cond, msg) { if (!cond) throw new Error(msg); }
async function shot(page, name) { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); }
async function noHScroll(page) {
  const [sw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(sw <= iw + 1, `가로 스크롤 생김 (scrollWidth ${sw} > ${iw})`);
}
const text = (page) => page.locator("body").innerText();

// ---------------- 테스트 ----------------
async function run() {
  await test("사이드바: 종목검색 메뉴 없음 + 미국 주간거래 상태, /search → 종목탐색", {}, async (page) => {
    await page.goto(`${BASE}/search`);
    await page.waitForURL(/\/screener$/);
    await page.getByText("주간거래 중 (~18:00)").waitFor();
    const nav = await page.locator(".sidebar").innerText();
    expect(!nav.includes("종목검색"), "사이드바에 종목검색이 남아 있음");
    expect(nav.includes("종목탐색"), "사이드바에 종목탐색이 없음");
  });

  await test("종목탐색: 검색 → 상세 카드(주간거래·매입가/목표가/손절가·지표·뉴스)", {}, async (page) => {
    await page.goto(`${BASE}/screener`);
    const box = page.locator("input").first();
    await box.fill("브로드컴");
    await page.getByText("브로드컴").first().click();
    const card = page.getByTestId("quote-card");
    await card.getByText("Broadcom falls on report").waitFor();
    const t = await card.innerText();
    for (const s of ["주간거래", "$320.53", "+5.30%", "추천 매입가", "목표가 (익절)", "손절가", "RSI(14)", "과매도", "60일선"]) {
      expect(t.includes(s), `상세 카드에 '${s}' 없음`);
    }
    await shot(page, "screener-quote");
  });

  await test("관심종목: 국내/미국 탭 · 3열 카드 · 가격대 · 요약", {}, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    const grid = page.getByTestId("watch-grid");
    await grid.waitFor();
    await page.getByText("삼성전자").first().waitFor();
    const cols = await grid.evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
    expect(cols === 3, `1440px 에서 3열이 아님 (${cols}열)`);
    expect(await page.getByTestId("tab-KR").innerText().then((s) => s.includes("6")), "국내 탭 개수(6) 표시 안 됨");
    expect(await page.getByTestId("tab-US").innerText().then((s) => s.includes("3")), "미국 탭 개수(3) 표시 안 됨");
    const cards = page.getByTestId("watch-card");
    expect(await cards.count() === 6, `국내 카드 수 ${await cards.count()} (6 이어야 함)`);
    const first = await cards.first().innerText();
    for (const s of ["추천 매입가", "목표가 (익절)", "손절가", "₩171,577", "상승 36%", "HBM 수주"]) expect(first.includes(s), `카드에 '${s}' 없음`);
    const sum = await page.getByTestId("watch-summary").innerText();
    expect(sum.includes("6종목") && sum.includes("상승 확률 55% 이상"), `요약 줄 이상: ${sum}`);
    // 카드 높이: 예전(한 줄 전체 폭)보다 한 화면에 많이 — 첫 줄 3개가 같은 높이 줄에
    const ys = await cards.evaluateAll((els) => els.slice(0, 3).map((e) => Math.round(e.getBoundingClientRect().top)));
    expect(new Set(ys).size === 1, `첫 줄 카드 3개가 한 줄에 있지 않음 ${ys}`);
    await shot(page, "watchlist-kr");

    await page.getByTestId("tab-US").click();
    await page.getByText("브로드컴").waitFor();
    const us = await page.getByTestId("watch-grid").innerText();
    expect(us.includes("주간거래") && us.includes("$320.53"), "미국 탭 브로드컴 카드에 주간거래 가격 없음");
    expect(us.includes("시세 조회 실패: yfinance"), "조회 실패 종목의 오류 문구가 안 보임");
    expect(!us.includes("삼성전자"), "미국 탭에 국내 종목이 보임");
    await shot(page, "watchlist-us");
  });

  await test("관심종목: 표 보기 · 설정 기억 · 메모 저장(PUT) · 정렬", {}, async (page, api) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("tab-US").click();
    await page.getByRole("button", { name: "표", exact: true }).click();
    const table = page.getByTestId("watch-table");
    await table.waitFor();
    const t = await table.innerText();
    for (const s of ["추천 매입가", "목표가", "손절가", "주간 $320.53", "브로드컴"]) expect(t.includes(s), `표에 '${s}' 없음`);
    await shot(page, "watchlist-table");
    await page.reload();                                       // 탭·보기 방식 기억
    await page.getByTestId("watch-table").waitFor();
    expect((await page.getByTestId("tab-US").getAttribute("aria-selected")) === "true", "새로고침 후 미국 탭이 유지 안 됨");
    // 메모 저장
    await page.getByRole("button", { name: "메모·목표 매수가 수정" }).first().click();
    await page.getByPlaceholder("메모 (관심 이유, 매수 조건 등)").fill("e2e 메모");
    await page.getByRole("button", { name: "저장" }).click();
    await page.waitForTimeout(300);
    const put = api.calls.find((c) => c.key.startsWith("PUT /api/watchlist/"));
    expect(put && JSON.parse(put.body).memo === "e2e 메모", `메모 저장 요청 이상: ${JSON.stringify(put)}`);
    // 정렬: 상승확률순
    await page.getByRole("button", { name: "카드", exact: true }).click();
    await page.getByTestId("tab-KR").click();
    await page.getByRole("button", { name: "상승확률순" }).click();
    const firstName = await page.getByTestId("watch-card").first().innerText();
    expect(firstName.includes("테스트종목4"), "상승확률순 정렬이 안 됨 (테스트종목4 = 64% 가 먼저여야 함)");
  });

  await test("관심종목: 삭제는 확인 후에만", {}, async (page, api) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("watch-card").first().waitFor();
    page.once("dialog", (d) => d.dismiss());
    await page.getByRole("button", { name: "삭제" }).first().click();
    await page.waitForTimeout(200);
    expect(!api.calls.some((c) => c.key.startsWith("DELETE")), "취소했는데 삭제 요청이 감");
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "삭제" }).first().click();
    await page.waitForTimeout(200);
    expect(api.calls.some((c) => c.key === "DELETE /api/watchlist/1"), "확인했는데 삭제 요청이 안 감");
  });

  for (const theme of ["light", "dark"]) {
    await test(`관심종목: 모바일 390px 1열 · 가로 스크롤 없음 (${theme})`, { width: 390, height: 844, theme }, async (page) => {
      await page.goto(`${BASE}/watchlist`);
      await page.getByTestId("watch-card").first().waitFor();
      const cols = await page.getByTestId("watch-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
      expect(cols === 1, `390px 에서 ${cols}열`);
      await noHScroll(page);
      await shot(page, `watchlist-mobile-${theme}`);
    });
  }

  await test("휴대폰 390px: 사이드바는 ☰ 메뉴 · 본문이 화면 폭을 다 씀", { width: 390, height: 844 }, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("watch-card").first().waitFor();
    const side = await page.locator(".sidebar").boundingBox();
    expect(side.x + side.width <= 1, `사이드바가 화면에 보임 (x=${side.x})`);
    const cardW = await page.getByTestId("watch-card").first().evaluate((e) => e.getBoundingClientRect().width);
    expect(cardW >= 340, `카드 폭이 좁음 (${cardW}px)`);
    await page.getByRole("button", { name: "메뉴 열기" }).click();
    await page.waitForTimeout(300);
    expect((await page.locator(".sidebar").boundingBox()).x >= 0, "☰ 눌러도 메뉴가 안 열림");
    await shot(page, "mobile-menu-open");
    await page.locator(".sidebar").getByText("경제캘린더").click();
    await page.waitForURL(/\/calendar$/);
    await page.waitForTimeout(300);
    expect((await page.locator(".sidebar").boundingBox()).x < 0, "화면을 옮겼는데 메뉴가 안 닫힘");
  });

  await test("PC 1440px: 사이드바 항상 보임 · ☰ 버튼 없음", {}, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("watch-card").first().waitFor();
    expect((await page.locator(".sidebar").boundingBox()).x === 0, "PC 에서 사이드바가 안 보임");
    expect(!(await page.getByRole("button", { name: "메뉴 열기" }).isVisible()), "PC 에서 ☰ 버튼이 보임");
  });

  await test("관심종목: 빈 목록 / 분석 실패", { api: makeApi({ "GET /api/watchlist/": [], "GET /api/watchlist/analysis": [] }) }, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByText("관심종목을 추가해보세요").waitFor();
  });
  await test("관심종목: 분석 API 502 → 오류 문구", { api: makeApi({ "GET /api/watchlist/analysis": undefined }) }, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByText(/시세 조회 실패.*가짜 응답 없음/).waitFor({ timeout: 15000 });
  });

  await test("퀀트 점수 화면: 검증 표 · 요인 등급 · 필터 · 상세 카드", {}, async (page) => {
    await page.goto(`${BASE}/quant`);
    await page.getByTestId("quant-table").waitFor();
    const v = await page.getByTestId("quant-validation").innerText();
    for (const s of ["처음 보는 기간", "56.2%", "+2.41%p", "모멘텀(RS) 35%"]) expect(v.includes(s), `검증 영역에 '${s}' 없음`);
    const t = await page.getByTestId("quant-table").innerText();
    for (const s of ["SK하이닉스", "A+", "57.4%", "반도체"]) expect(t.includes(s), `퀀트 표에 '${s}' 없음`);
    expect(await page.getByTestId("regime-warning").count() === 1, "코스닥 하락 추세 경고가 없음");
    await page.getByRole("button", { name: "9점 이상" }).click();
    expect(!(await page.getByTestId("quant-table").innerText()).includes("NAVER"), "9점 이상 필터가 안 됨");
    await shot(page, "quant");
    await page.getByText("삼성전자").first().click();
    await page.getByTestId("quote-card").waitFor();
  });

  await test("투자 대가: 목록(추정 수익률 순) · 상세(변화) · 대가들이 산 종목 · 따라 사기 검증", {}, async (page, api) => {
    await page.goto(`${BASE}/gurus`);
    const list = page.getByTestId("guru-list");
    await list.waitFor();
    const t = await list.innerText();
    for (const s of ["데이비드 테퍼", "+26.8%", "워런 버핏", "최근 공시 없음", "신규 2", "MU 18%"]) expect(t.includes(s), `대가 목록에 '${s}' 없음`);
    await shot(page, "gurus");
    await page.getByText("워런 버핏").first().click();
    const det = page.getByTestId("guru-detail");
    await det.getByText("처브").waitFor();
    const dt = await det.innerText();
    for (const s of ["24.9%", "추가 매수 +31.5%", "신규 매수", "티커 변환 전", "전량 매도", "DVA(1.2%)"]) expect(dt.includes(s), `대가 상세에 '${s}' 없음`);
    await det.getByText("애플").click();
    await page.getByTestId("quote-card").waitFor();
    await page.getByRole("button", { name: "대가들이 산 종목" }).click();
    await page.getByTestId("guru-stocks").getByText("아마존닷컴").waitFor();
    const st = await page.getByTestId("guru-stocks").innerText();
    for (const s of ["아마존닷컴", "AMZN", "스티븐 맨델", "데이비드 테퍼", "+8.2%"]) expect(st.includes(s), `대가 종목 표에 '${s}' 없음`);
    await page.getByRole("button", { name: "이번 분기 많이 산" }).click();
    await page.waitForTimeout(200);
    expect(api.calls.some((c) => c.key === "GET /api/gurus/stocks" && c.query.includes("sort=buyers")), "정렬 바꿔도 다시 안 물음");
    await page.getByRole("button", { name: "따라 사기 검증" }).click();
    const v = await page.getByTestId("guru-validation").innerText();
    for (const s of ["다음 거래일 종가", "-1.9%p", "42.3%", "775건", "점수엔 안 넣음", "워런 버핏"]) expect(v.includes(s), `검증에 '${s}' 없음`);
    await shot(page, "gurus-validation");
  });

  await test("가치주 찾기: 국내 조건·표(PER·ROE·성장·퀀트·수급) → 미국 탭 · 선택 기억", {}, async (page) => {
    await page.goto(`${BASE}/value`);
    const tbl = page.getByTestId("value-table");
    await tbl.waitFor();
    const t = await tbl.innerText();
    for (const s of ["삼성전자", "5.4", "34.3%", "+126.9%", "쌍끌이 3일 연속", "A"]) expect(t.includes(s), `국내 가치 표에 '${s}' 없음`);
    expect((await page.getByTestId("value-screen-list").innerText()).includes("아직 저렴한 가치주"), "조건 목록 없음");
    await shot(page, "value-kr");
    await page.getByRole("button", { name: "미국", exact: true }).click();
    await page.getByText("엔비디아").waitFor();
    const u = await page.getByTestId("value-table").innerText();
    for (const s of ["16.0", "+42.1%", "$4.4T"]) expect(u.includes(s), `미국 가치 표에 '${s}' 없음`);
    await page.reload();
    await page.getByText("엔비디아").waitFor();      // 미국 탭 기억
    await page.getByText("엔비디아").click();
    await page.getByTestId("quote-card").waitFor();
  });

  await test("가치주 찾기: 국내 재무 아직 없음 문구 · 미국 Yahoo 실패 문구", { api: makeApi({
    "GET /api/value/KR/undervalued_growth": { items: [], total: 0, message: "국내 재무 데이터가 아직 없습니다 — 테스트", status: {} },
    "GET /api/value/US/undervalued_growth": { __status: 502, detail: "Yahoo 스크리너 실패: 테스트" } }) }, async (page) => {
    await page.goto(`${BASE}/value`);
    await page.getByText("국내 재무 데이터가 아직 없습니다 — 테스트").waitFor();
    await page.getByRole("button", { name: "미국", exact: true }).click();
    await page.getByText("Yahoo 스크리너 실패: 테스트").waitFor();
  });

  await test("수급 동향: 개미 동향 막대 · 쌍끌이/개미 순매수 목록", {}, async (page) => {
    await page.goto(`${BASE}/flows`);
    const d = page.getByTestId("flow-daily");
    await d.waitFor();
    const dt = await d.innerText();
    for (const s of ["최근 5일 개인", "외국인", "쌍끌이 104종목"]) expect(dt.includes(s), `개미 동향에 '${s}' 없음`);
    const t = await page.getByTestId("flow-table").innerText();
    for (const s of ["삼성전자", "쌍끌이 3일 연속", "+3,200억", "−4,300억", "+4.12%"]) expect(t.includes(s), `쌍끌이 표에 '${s}' 없음`);
    await shot(page, "flows");
    await page.getByRole("button", { name: /개미 순매수/ }).click();
    expect((await page.getByTestId("flow-table").innerText()).includes("개인만 순매수"), "개미 순매수 목록이 안 바뀜");
  });

  await test("AI 추천·종목 상세: 투자 대가·가치·쌍끌이 신호 배지", { api: makeApi({
    "GET /api/stocks/recommendations/shortterm": { ...F.RECS, items: F.RECS.items.map((x, i) => ({ ...x, signals: i === 0 ? SF.SIGNALS_KR : SF.SIGNALS_US })) },
    "GET /api/stocks/recommendations/longterm": { ...F.RECS, items: F.RECS.items.map((x, i) => ({ ...x, signals: i === 0 ? SF.SIGNALS_KR : SF.SIGNALS_US })) },
    "GET /api/stocks/quote/US/AVGO": { ...F.QUOTE_AVGO, signals: SF.SIGNALS_US } }) }, async (page) => {
    await page.goto(`${BASE}/recommendations`);
    await page.getByTestId("signal-badges").first().waitFor();
    const kr = await page.locator("body").innerText();
    for (const s of ["쌍끌이 3일 연속", "PER 5.4", "ROE 34%", "장기 +3.2"]) expect(kr.includes(s), `국내 추천 카드에 '${s}' 없음`);
    await page.getByRole("button", { name: /미국/ }).first().click();
    await page.getByTestId("guru-badge").first().waitFor();
    const us = await page.locator("body").innerText();
    for (const s of ["대가 3명 보유", "리 루 매수"]) expect(us.includes(s), `미국 추천 카드에 '${s}' 없음`);
    const tip = await page.getByTestId("guru-badge").first().getAttribute("title");
    expect(tip.includes("점수엔 안 넣음") && tip.includes("워런 버핏"), `대가 배지 설명 이상: ${tip}`);
    await shot(page, "recs-signals");
    await page.goto(`${BASE}/screener`);
    await page.locator("input").first().fill("브로드컴");
    await page.getByText("브로드컴").first().click();
    await page.getByTestId("quote-card").getByTestId("guru-badge").waitFor();
  });

  await test("퀀트 점수: 일봉 밖 요인(가치·수익성·수급) 쌓는 중 표시", { api: makeApi({ "GET /api/quant": { ...F.QUANT, quant: { ...F.QUANT.quant,
    weights: { ...F.QUANT.quant.weights, value: 0.1, flow: 0 },
    factors: [...F.QUANT.quant.factors,
      { key: "value", name: "가치(저PER·저PBR)", about: "x", extra: true, dates: 40, need_dates: 15, coverage: 1800 },
      { key: "flow", name: "수급(외국인+기관)", about: "x", extra: true, dates: 3, need_dates: 15, coverage: 1700 }] } } }) }, async (page) => {
    await page.goto(`${BASE}/quant`);
    await page.getByTestId("quant-validation").waitFor();
    const ex = await page.getByTestId("quant-extra-factor").allInnerTexts();
    expect(ex.some((x) => x.includes("가치(저PER·저PBR) 10%") && !x.includes("쌓는 중")), `가치 요인 표시 이상: ${ex}`);
    expect(ex.some((x) => x.includes("수급(외국인+기관) 0%") && x.includes("쌓는 중 3/15일")), `수급 요인 쌓는 중 표시 없음: ${ex}`);
    expect((await page.getByTestId("quant-table").innerText()).includes("가치"), "퀀트 표에 가치 열 없음");
  });

  await test("퀀트 점수 없음 / 계산 실패 문구", { api: makeApi({ "GET /api/quant": { quant: null, error: "퀀트 점수 계산 실패: 테스트", status: { running: false } } }) }, async (page) => {
    await page.goto(`${BASE}/quant`);
    await page.getByText("퀀트 점수 계산 실패: 테스트").waitFor();
  });

  await test("대시보드: 시장 상태 4개 지수 + 상태별 과거 성과", {}, async (page) => {
    await page.goto(`${BASE}/`);
    const panel = page.getByTestId("market-regime");
    await panel.getByText("코스닥").waitFor();
    const t = await panel.innerText();
    for (const s of ["상승 압박", "하락 추세", "상승 추세", "분산일 3"]) expect(t.includes(s), `시장 상태에 '${s}' 없음`);
    await panel.getByText("상태별 과거 성과").click();
    expect((await panel.innerText()).includes("◀ 지금"), "검증 표에 현재 상태 표시 없음");
    await shot(page, "dashboard-regime");
  });

  await test("관심종목: 퀀트 배지 · 예측 적중 기록 · 시장 경고(국내만)", {}, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("tab-KR").click();
    await page.getByTestId("quant-badge").first().waitFor();
    const first = await page.getByTestId("watch-card").first().innerText();
    expect(first.includes("퀀트 A · 9/10") && first.includes("예측 적중 60.9%"), `카드: ${first.slice(0, 200)}`);
    expect(await page.getByTestId("regime-warning").count() === 1, "국내 탭에 코스닥 하락 경고 없음");
    await page.getByTestId("tab-US").click();
    await page.getByText("브로드컴").waitFor();
    expect(await page.getByTestId("regime-warning").count() === 0, "미국은 상승 추세인데 경고가 뜸");
    expect((await page.getByTestId("watch-grid").innerText()).includes("예측 적중 75%"), "표본 적은 적중 기록도 흐리게 표시돼야 함");
  });

  await test("로그인: 비밀번호 틀리면 새로고침 없이 오류 문구", { token: false, api: makeApi({
    "POST /api/auth/login": { __status: 401, detail: "아이디 또는 비밀번호가 틀렸습니다" } }) }, async (page) => {
    await page.goto(`${BASE}/login`);
    let navs = 0;
    const navUrls = [];
    await page.waitForLoadState("networkidle");
    page.on("load", () => { navs++; navUrls.push(page.url()); });   // 실제 새로고침만 셈 (같은 화면 안 주소 갱신은 제외)
    await page.locator("input").nth(0).fill("me"); await page.locator("input").nth(1).fill("wrong");
    await page.keyboard.press("Enter");
    await page.getByText("아이디 또는 비밀번호가 틀렸습니다").waitFor();
    expect(navs === 0, `로그인 실패 후 화면이 새로고침됨 (${navs}번: ${navUrls.join(', ')})`);
  });

  await test("로그인: 성공하면 대시보드로", { token: false, api: makeApi({ "POST /api/auth/login": { access_token: "x", token_type: "bearer" } }) }, async (page) => {
    await page.goto(`${BASE}/login`);
    await page.locator("input").nth(0).fill("me"); await page.locator("input").nth(1).fill("pw");
    await page.keyboard.press("Enter");
    await page.waitForURL(`${BASE}/`);
  });

  await test("버튼 요청 실패 → 화면 아래 알림 (투자종목 삭제 404)", { api: makeApi({
    "DELETE /api/portfolio/1": { __status: 404, detail: "이미 없는 종목입니다" } }) }, async (page) => {
    await page.goto(`${BASE}/portfolio`);
    await page.getByText("브로드컴").first().waitFor();
    page.once("dialog", (d) => d.accept());
    await page.locator("main button:has(svg.lucide-trash2), main button:has(svg.lucide-trash-2)").first().click();
    const t = page.getByTestId("toast");
    await t.waitFor();
    expect((await t.innerText()).includes("이미 없는 종목입니다"), "알림 문구가 다름");
  });

  await test("투자종목: 삭제 확인 · 추가 창 Esc 로 닫기 · 수량 0 이면 추가 불가", {}, async (page, api) => {
    await page.goto(`${BASE}/portfolio`);
    await page.getByText("브로드컴").first().waitFor();
    page.once("dialog", (d) => d.dismiss());
    await page.locator("main button:has(svg.lucide-trash2), main button:has(svg.lucide-trash-2)").first().click();
    await page.waitForTimeout(200);
    expect(!api.calls.some((c) => c.key.startsWith("DELETE")), "취소했는데 삭제 요청이 감");
    await page.getByRole("button", { name: /종목 추가/ }).click();
    await page.getByText("투자종목 추가").waitFor();
    await page.locator("body").click({ position: { x: 5, y: 5 }, force: true }).catch(() => {});
    await page.getByRole("button", { name: /종목 추가/ }).click().catch(() => {});
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);
    expect(await page.getByText("투자종목 추가").count() === 0, "Esc 로 추가 창이 안 닫힘");
  });

  await test("관심종목: 입력 검증 오류(422)가 [object Object] 가 아니라 문장으로", { api: makeApi({
    "PUT /api/watchlist/1": { __status: 422, detail: [{ loc: ["body", "target_price"], msg: "Value error, 목표가가 이상합니다", type: "value_error" }] } }) }, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("tab-KR").click();
    await page.getByRole("button", { name: "메모·목표 매수가 수정" }).first().click();
    await page.getByRole("button", { name: "저장" }).click();
    await page.getByText("저장 실패: 목표가가 이상합니다").waitFor();
    expect(!(await page.locator("body").innerText()).includes("[object Object]"), "[object Object] 가 보임");
  });

  let totpOn = false;
  await test("마이페이지: 2단계 인증 켜기(QR → 코드 확인) · 끄기", { api: makeApi({
    "GET /api/auth/me": () => ({ id: 1, username: "tester", display_name: "tester", totp_enabled: totpOn, email: null }),
    "POST /api/auth/setup-totp": { qr_code: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", secret: "ABCDEF234567", uri: "otpauth://x" },
    "POST /api/auth/enable-totp": () => { totpOn = true; return { message: "ok" }; },
    "POST /api/auth/disable-totp": () => { totpOn = false; return { message: "2단계 인증을 껐습니다" }; } }) }, async (page, api) => {
    await page.goto(`${BASE}/`);
    await page.getByTestId("mypage-link").click();
    await page.waitForURL(/\/mypage$/);
    const dlg = page.getByTestId("totp-section");
    await dlg.getByRole("button", { name: /켜기/ }).click();
    await dlg.getByAltText("2단계 인증 QR 코드").waitFor();
    expect((await dlg.innerText()).includes("ABCDEF234567"), "직접 입력용 비밀값이 안 보임");
    const ok = dlg.getByRole("button", { name: "확인" });
    await dlg.getByLabel("인증 코드").fill("12ab3");
    expect(await ok.isDisabled(), "6자리 숫자가 아닌데 확인 버튼이 눌림");
    await dlg.getByLabel("인증 코드").fill("123456");
    await ok.click();
    await page.getByText(/2단계 인증을 켰습니다/).waitFor();
    expect(JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/enable-totp").body).totp_code === "123456", "코드가 그대로 안 감");
    await dlg.getByText("켜져 있음").waitFor();
    await dlg.getByLabel("인증 코드").fill("654321");
    await dlg.getByRole("button", { name: "끄기" }).click();
    await page.getByText("2단계 인증을 껐습니다").waitFor();
  });

  {
    let on = false;
    const QR = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";
    await test("2단계 필수: 비밀번호만 로그인 → QR 등록 화면 → 켜면 대시보드", { token: false, api: makeApi({
      "POST /api/auth/login": { access_token: "half", token_type: "bearer", totp_enabled: false, totp_setup_required: true },
      "GET /api/auth/me": () => ({ id: 1, username: "tester", display_name: "tester", totp_enabled: on, totp_required: true, email: null }),
      "POST /api/auth/setup-totp": { qr_code: QR, secret: "ABCDEF234567", uri: "otpauth://x" },
      "POST /api/auth/enable-totp": () => { on = true; return { message: "ok" }; } }) }, async (page, api) => {
      await page.goto(`${BASE}/login`);
      await page.locator("input").nth(0).fill("tester"); await page.locator("input").nth(1).fill("pw");
      await page.keyboard.press("Enter");
      await page.waitForURL(/\/setup-2fa$/);
      const box = page.getByTestId("setup-2fa");
      expect((await box.innerText()).includes("Google Authenticator"), "설명 없음");
      await page.goto(`${BASE}/watchlist`);                                // 다른 화면으로 가도 다시 등록 화면
      await page.waitForURL(/\/setup-2fa$/);
      await box.getByRole("button", { name: /켜기/ }).click();
      await box.getByAltText("2단계 인증 QR 코드").waitFor();
      await box.getByLabel("인증 코드").fill("123456");
      await box.getByRole("button", { name: "확인" }).click();
      await page.waitForURL(`${BASE}/`);
      await page.getByTestId("mypage-link").waitFor();
      await shot(page, "after-2fa");
    });
  }

  {
    let n = 0;
    await test("2단계 필수: 서버가 403(X-Totp-Required)이면 등록 화면으로 (저장된 내 정보가 오래돼도)", { api: makeApi({
      "GET /api/auth/me": () => ({ id: 1, username: "tester", display_name: "tester", totp_enabled: ++n === 1, totp_required: true, email: null }),
      "GET /api/watchlist/": { __status: 403, __headers: { "X-Totp-Required": "1" }, detail: "2단계 인증을 먼저 켜야 합니다" },
      "GET /api/watchlist/analysis": { __status: 403, __headers: { "X-Totp-Required": "1" }, detail: "2단계 인증을 먼저 켜야 합니다" } }) }, async (page) => {
      await page.goto(`${BASE}/watchlist`);
      await page.waitForURL(/\/setup-2fa$/);
      await page.getByTestId("setup-2fa").getByRole("button", { name: /켜기/ }).waitFor();
      await page.waitForTimeout(500);
      expect(page.url().endsWith("/setup-2fa"), `등록 화면에 머물러야 함: ${page.url()}`);
    });
  }

  await test("회원가입: 초대 코드가 있어야 인증 코드를 받고, 가입하면 2단계 등록부터", { token: false, api: makeApi({
    "GET /api/auth/options": { signup_open: true, invite_required: true, totp_required: true, mail_configured: true, sms_configured: true },
    "POST /api/auth/signup/send-code": { message: "me@naver.com 로 인증 코드를 보냈습니다 (10분 유효)" },
    "POST /api/auth/register": { message: "가입 완료", username: "newbie", access_token: "new-token", token_type: "bearer", totp_setup_required: true },
    "GET /api/auth/me": { id: 2, username: "newbie", display_name: "newbie", totp_enabled: false, totp_required: true, email: "me@naver.com" } }) }, async (page, api) => {
    await page.goto(`${BASE}/signup`);
    const send = page.getByRole("button", { name: "인증 코드 받기" });
    await page.getByPlaceholder("you@naver.com").fill("me@naver.com");
    expect(await send.isDisabled(), "초대 코드 없이 인증 코드 받기가 눌림");
    await page.getByLabel("초대 코드").fill("k7qm-2xra-9pw");
    expect(await send.isDisabled(), "11글자인데 눌림");
    await page.getByLabel("초대 코드").fill("k7qm-2xra-9pwd");
    expect((await page.getByLabel("초대 코드").inputValue()) === "K7QM-2XRA-9PWD", "대문자로 안 바뀜");
    await send.click();
    await page.getByText(/인증 코드를 보냈습니다/).waitFor();
    expect(JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/signup/send-code").body).invite_code === "K7QM-2XRA-9PWD", "초대 코드가 안 감");
    await page.getByPlaceholder("000000").fill("123456");
    await page.locator("input[autocomplete=username]").fill("newbie");
    await page.locator("input[autocomplete=new-password]").first().fill("zxcv5678");
    await page.locator("input[autocomplete=new-password]").nth(1).fill("zxcv5678");
    await page.getByRole("button", { name: "가입하기" }).click();
    await page.waitForURL(/\/setup-2fa$/);
    expect(JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/register").body).invite_code === "K7QM-2XRA-9PWD", "가입 요청에 초대 코드 없음");
  });

  await test("관심종목: 국내 장중이면 KIS 실시간 현재가(2초)로 가격만 바꿈 · 장 마감이면 실시간 요청 안 함", { api: makeApi({
    "GET /api/market/status": { ...F.MARKET_STATUS, KR: { ...F.MARKET_STATUS.KR, state: "장중", open: true } },
    "GET /api/stocks/live": { items: { "005930": { price: 178500, change: -4600, change_rate: -2.51, volume: 1, time: "101530", age: 0.4 } },
                              connected: true, session: true, source: "KIS 실시간 체결가 (웹소켓)" } }) }, async (page, api) => {
    await page.goto(`${BASE}/watchlist`);
    const card = page.getByTestId("watch-card").filter({ hasText: "삼성전자" }).first();
    await card.getByTestId("live-badge").waitFor();
    const t = await card.innerText();
    expect(t.includes("₩178,500") && t.includes("실시간 10:15:30") && !t.includes("₩177,800"), `실시간 가격 안 바뀜: ${t.slice(0, 120)}`);
    const q = api.calls.find((c) => c.key === "GET /api/stocks/live");
    expect(q, "실시간 요청 없음");
    await page.waitForTimeout(2300);
    expect(api.calls.filter((c) => c.key === "GET /api/stocks/live").length >= 2, "2초마다 다시 묻지 않음");
    const other = await page.getByTestId("watch-card").nth(1).innerText();
    expect(!other.includes("실시간"), "실시간 값이 없는 종목에도 실시간 표시");
  });

  await test("예측 검증: 지표 비중 자동 조정 — 덜 맞은 지표 비중·날짜별 검증 비교·사용 여부", { api: makeApi({
    "GET /api/predictions/review": RF.REVIEW, "GET /api/predictions/backtest/status": RF.BACKTEST_STATUS }) }, async (page) => {
    await page.goto(`${BASE}/predictions`);
    const kr = page.getByTestId("fw-KR");
    await kr.waitFor();
    const t = await kr.innerText();
    expect(t.includes("실시간 예측에 사용 중") && t.includes("×0.3") && t.includes("RSI") && /원래 \d+(\.\d)?% → 조정 \d+(\.\d)?%/.test(t), `국내 비중: ${t}`);
    const us = await page.getByTestId("fw-US").innerText();
    expect(us.includes("원래 비중 사용") && us.includes("줄일 지표 없음") && !us.includes("×0.3"), `미국 비중: ${us}`);
  });

  await test("관심종목 미국: KIS 현재가면 표시 없음 · KIS 실패로 Yahoo 가격이면 'Yahoo·지연 가능' 표시", { api: makeApi({
    "GET /api/watchlist/analysis": F.WATCHLIST.map((w) => w.market !== "US" ? w
      : { ...w, price_source: w.symbol === "AVGO" ? "Yahoo (KIS 실패)" : "KIS" }) }) }, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("tab-US").click();
    const avgo = page.getByTestId("watch-card").filter({ hasText: "브로드컴" }).first();
    await avgo.getByTestId("price-source").waitFor();
    expect((await avgo.getByTestId("price-source").innerText()) === "Yahoo·지연 가능", "Yahoo 표시 문구 이상");
    expect(await page.getByTestId("price-source").count() === 1, "KIS 가격인 종목에도 Yahoo 표시");
  });

  await test("미국 애프터마켓: 관심종목 카드·표·종목탐색·AI 추천은 현재가 자리에 '애프터마켓' + 그 가격 (종가는 안 보임)", { api: makeApi({
    "GET /api/market/status": { ...F.MARKET_STATUS, US: { ...F.MARKET_STATUS.US, state: "장 마감", daytime: { ...F.MARKET_STATUS.US.daytime, open: false },
      extended: { open: true, label: "애프터마켓", session_date: "2026-11-25", hours_kst: "06:00~10:00" } } },
    "GET /api/watchlist/analysis": F.WATCHLIST.map((w) => w.symbol === "AVGO" ? { ...w, daytime: F.AFTER } : w),
    "GET /api/stocks/quote/US/AVGO": { ...F.QUOTE_AVGO, daytime: F.AFTER },
    "GET /api/stocks/screener/us/trading_value": [
      { symbol: "NVDA", name: "엔비디아", market: "US", price: 149.3, change_rate: -3.91, volume: 1, trading_value_display: "$53.68B",
        daytime: { ...F.AFTER, price: 151.68, base: 149.3, change_rate: 1.59 } },
      { symbol: "MU", name: "마이크론 테크놀로지", market: "US", price: 601.25, change_rate: -4.57, volume: 1, trading_value_display: "$31.45B" }],
    "GET /api/stocks/recommendations/shortterm": { ...F.RECS, items: F.RECS.items.map((r) => r.symbol === "AVGO" ? { ...r, daytime: F.AFTER } : r) },
    "GET /api/stocks/recommendations/longterm": { ...F.RECS, items: F.RECS.items.map((r) => r.symbol === "AVGO" ? { ...r, daytime: F.AFTER } : r) } }) }, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("tab-US").click();
    const avgo = page.getByTestId("watch-card").filter({ hasText: "브로드컴" }).first();
    await avgo.getByTestId("session-tag").waitFor();
    expect((await avgo.getByTestId("session-tag").innerText()) === "애프터마켓", "애프터마켓 표시 없음");
    expect((await avgo.getByTestId("main-price").innerText()) === "$307.50", "현재가 자리가 애프터마켓 가격이 아님");
    const c = await avgo.innerText();
    expect(c.includes("+1.02%") && !c.includes("$304.41") && !c.includes("-12.19%"), `카드에 종가가 남음: ${c}`);
    expect((await avgo.getByTestId("session-tag").getAttribute("title")).includes("정규장 종가 $304.41"), "종가 안내(마우스 올림) 없음");
    expect((await text(page)).includes("애프터마켓 중 (~10:00)"), "사이드바에 애프터마켓 중 표시 없음");
    await page.getByRole("button", { name: "표", exact: true }).click();
    const row = await page.locator("tr").filter({ hasText: "브로드컴" }).first().innerText();
    expect(row.includes("애프터마켓") && row.includes("$307.50") && row.includes("+1.02%") && !row.includes("$304.41"), `표 보기: ${row}`);
    // 종목탐색 미국 표 (거래대금 순): 애프터마켓 가격이 있는 종목만 바뀜
    await page.goto(`${BASE}/screener`);
    await page.getByRole("button", { name: /미국/ }).first().click();
    const nv = page.locator("tr").filter({ hasText: "엔비디아" }).first();
    await nv.getByTestId("session-tag").waitFor();
    const nvt = await nv.innerText();
    expect(nvt.includes("애프터마켓") && nvt.includes("$151.68") && nvt.includes("+1.59%") && !nvt.includes("$149.30"), `스크리너 엔비디아: ${nvt}`);
    const mut = await page.locator("tr").filter({ hasText: "마이크론" }).first().innerText();
    expect(mut.includes("$601.25") && !mut.includes("애프터마켓"), `시간외 없는 종목: ${mut}`);
    // 종목탐색 (엔비디아 같은 종목 상세 카드)
    await page.goto(`${BASE}/screener`);
    await page.locator("input").first().fill("브로드컴");
    await page.getByText("브로드컴").first().click();
    const card = page.getByTestId("quote-card");
    await card.getByTestId("session-tag").waitFor();
    expect((await card.getByTestId("main-price").innerText()) === "$307.50", "종목탐색 현재가 자리가 애프터마켓 가격이 아님");
    expect(!(await card.locator("div").filter({ has: page.getByTestId("main-price") }).first().innerText()).includes("$304.41"), "종목탐색에 종가가 남음");
    // AI 추천 카드
    await page.goto(`${BASE}/recommendations`);
    await page.getByRole("button", { name: /미국/ }).first().click();
    const rc = page.locator(".card").filter({ hasText: "브로드컴" }).filter({ has: page.getByTestId("session-tag") }).first();
    await rc.waitFor();
    expect((await rc.innerText()).includes("$307.50"), "AI 추천 카드에 애프터마켓 가격 없음");
    await shot(page, "after-market");
  });

  await test("관심종목: 장 마감이면 실시간 요청 안 함", {}, async (page, api) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("watch-card").first().waitFor();
    await page.waitForTimeout(500);
    expect(!api.calls.some((c) => c.key === "GET /api/stocks/live"), "장 마감인데 실시간 요청");
    expect(await page.getByTestId("live-badge").count() === 0, "장 마감인데 실시간 표시");
  });

  const adminApi = (extra = {}) => makeApi({
    "GET /api/auth/me": KF.ADMIN_ME,
    "GET /api/admin/summary": KF.ADMIN_SUMMARY,
    "GET /api/admin/users/2": KF.ADMIN_USER_2,
    "GET /api/admin/events": KF.ADMIN_EVENTS,
    "GET /api/admin/invites": { items: [
      { id: 2, hint: "9PWD", memo: "동생", created_at: 1795000000, expires_at: 1795259200, used_at: null, used_by: null, status: "active" },
      { id: 1, hint: "AB12", memo: null, created_at: 1794000000, expires_at: 1794259200, used_at: 1794100000, used_by: "friend", status: "used" }], days_default: 3, days_max: 14 },
    "POST /api/admin/invites": { id: 3, code: "K7QM-2XRA-9PWD", expires_at: 1795259200, memo: "친구", message: "ok" },
    "GET /api/admin/users": { items: [
      { id: 1, username: "boss", display_name: "boss", is_admin: true, is_active: true, totp_enabled: true, verified: true, invited_by: null, created_at: "2026-11-01T00:00:00", last_login: 1795000000, me: true },
      { id: 2, username: "friend", display_name: "친구", is_admin: false, is_active: true, totp_enabled: false, verified: true, invited_by: "boss", created_at: "2026-11-20T00:00:00", last_login: null, me: false }] },
    "PUT /api/admin/users/2/active": { message: "friend 을(를) 차단했습니다 (모든 기기 로그아웃)" },
    "GET /api/kis/status": KF.KIS_STATUS,
    "GET /api/kis/orders": (req) => (new URL(req.url()).searchParams.get("kind") === "all" ? KF.KIS_ALL : KF.KIS_OPEN),
    "GET /api/kis/log": KF.KIS_LOG,
    ...extra,
  });

  await test("관리자 페이지: 사이드바 관리자 메뉴 · 요약 · 초대 코드(2단계) · 회원 상세 · 차단 · 보안 기록", { api: adminApi() }, async (page, api) => {
    page.on("dialog", (d) => d.accept());
    await page.goto(`${BASE}/mypage`);
    expect((await page.getByTestId("my-role").innerText()) === "관리자" && await page.getByTestId("role-help").count() === 0, "관리자 표시 이상");
    await page.getByTestId("admin-link").click();                 // 마이페이지엔 관리 기능 대신 링크만
    await page.waitForURL(/\/admin$/);
    const nav = await page.getByTestId("admin-nav").innerText();
    expect(nav.includes("관리자") && nav.includes("KIS 모의투자 주문"), `관리자 메뉴: ${nav}`);
    const sum = await page.getByTestId("admin-summary").innerText();
    expect(sum.includes("2명") && sum.includes("2단계 미등록") && sum.includes("3번"), `요약: ${sum}`);
    const inv = page.getByTestId("admin-invites");
    const t = await inv.getByTestId("invite-table").innerText();
    expect(t.includes("…9PWD") && t.includes("동생") && t.includes("사용됨") && t.includes("friend"), `초대 목록: ${t}`);
    const make = inv.getByRole("button", { name: "만들기" });
    await inv.getByLabel("초대 메모").fill("친구");
    expect(await make.isDisabled(), "2단계 코드 없이 만들기가 눌림");
    await inv.getByLabel("초대 2단계 코드").fill("246810");
    await make.click();
    await inv.getByTestId("invite-code").waitFor();
    expect((await inv.getByTestId("invite-code").innerText()) === "K7QM-2XRA-9PWD", "새 코드가 안 보임");
    const body = JSON.parse(api.calls.find((c) => c.key === "POST /api/admin/invites").body);
    expect(body.totp_code === "246810" && body.memo === "친구" && body.days === 3, `만들기 요청: ${JSON.stringify(body)}`);
    // 회원 상세
    const members = page.getByTestId("member-table");
    expect((await members.innerText()).includes("미등록"), "2단계 미등록 표시 없음");
    await members.getByRole("button", { name: "상세" }).nth(1).click();
    const det = await page.getByTestId("user-detail").innerText();
    expect(det.includes("fr***@naver.com") && det.includes("10.7.7.7") && det.includes("관심 3") && det.includes("로그인 실패") && det.includes("2단계 인증을 아직 등록하지"), `회원 상세: ${det}`);
    // 차단
    const block = members.getByRole("button", { name: /차단/ });
    expect(await block.count() === 1, "관리자 본인에게도 차단 버튼이 보임");
    expect(await block.isDisabled(), "2단계 코드 없이 차단이 눌림");
    await page.getByLabel("차단 2단계 코드").fill("135790");
    await block.click();
    await page.getByText(/차단했습니다/).waitFor();
    expect(JSON.parse(api.calls.find((c) => c.key === "PUT /api/admin/users/2/active").body).active === false, "차단 요청 이상");
    const ev = await page.getByTestId("admin-events").innerText();
    expect(ev.includes("friend") && ev.includes("로그인 실패") && ev.includes("초대 코드 만듦"), `보안 기록: ${ev}`);
    await shot(page, "admin-page");
  });

  await test("관리자 아님: 관리자 메뉴 없음 · /admin · /kis 는 첫 화면으로 · 마이페이지 링크 없음", {}, async (page, api) => {
    await page.goto(`${BASE}/mypage`);
    await page.getByTestId("totp-section").waitFor();
    expect(await page.getByTestId("admin-link").count() === 0, "일반 회원에게 관리자 링크가 보임");
    expect(await page.getByTestId("admin-nav").count() === 0, "일반 회원에게 관리자 메뉴가 보임");
    expect((await page.getByTestId("my-role").innerText()) === "일반 회원", "권한 표시 없음");
    const help = await page.getByTestId("role-help").innerText();
    expect(help.includes("create_admin.py --list") && help.includes("--admin tester"), `관리자 안내: ${help}`);
    for (const path of ["/admin", "/kis"]) {
      await page.goto(`${BASE}${path}`);
      await page.waitForURL((u) => u.pathname === "/");
    }
    expect(!api.calls.some((c) => c.key.startsWith("GET /api/admin") || c.key.startsWith("GET /api/kis")), "일반 회원 화면이 관리자 API 를 부름");
  });

  await test("KIS 모의투자: 잔고 · 제안 선택 → 2단계 코드로 승인 · 거절 · 주문 취소 · 기록 · 감사 로그", { api: adminApi({
    "POST /api/kis/orders/approve": { results: [{ id: 11, status: "submitted", message: "주문번호 0000000008" }, { id: 12, status: "submitted", message: "주문번호 0000000009" }] },
    "POST /api/kis/orders/reject": { message: "1건 거절했습니다" },
    "POST /api/kis/orders/9/cancel": { message: "취소 요청 — 모의투자 취소주문이 완료되었습니다" },
    "POST /api/kis/propose": { proposed: 1, base_date: "2026-11-24 장중 10:30", notes: [], intraday: true } }) }, async (page, api) => {
    page.on("dialog", (d) => d.accept());
    await page.goto(`${BASE}/kis`);
    const st = await page.getByTestId("kis-status").innerText();
    expect(st.includes("운영 중") && st.includes("****3456-01") && st.includes("1 / 10건") && st.includes("+120,000원"), `상태: ${st}`);
    const bal = await page.getByTestId("kis-balance").innerText();
    expect(bal.includes("SK하이닉스") && bal.includes("8,150,000원") && bal.includes("176,700원"), `잔고: ${bal}`);
    expect((await page.getByTestId("kis-notify-link").innerText()).includes("mystock.duckdns.org/kis"), "알림 링크 주소 안내 없음");
    expect(await page.getByTestId("kis-order-cards").count() === 0, "넓은 화면인데 카드 보기");
    const wl = await page.getByTestId("kis-watch").innerText();
    expect(wl.includes("5초마다") && wl.includes("4종목") && wl.includes("REST 4") && wl.includes("지수 -0.4%")
      && wl.includes("실시간 체결가 연결 안 됨") && wl.includes("연결 거부"), `실시간 감시: ${wl}`);
    // 설정: 묶음 3개 · 같은 줄 입력칸 높이(위치) 같음
    const cfg = page.getByTestId("kis-config");
    expect(await cfg.getByTestId("kis-config-group").count() === 4, "설정 묶음이 4개가 아님");
    const cfgText = await cfg.innerText();
    expect(cfgText.includes("주문 한도") && cfgText.includes("장중 감시 규칙") && cfgText.includes("장중 AI 판단 간격") && cfgText.includes("AI 매매 규칙") && cfgText.includes("1 ~ 15"), `설정: ${cfgText}`);
    for (const g of await cfg.getByTestId("kis-config-group").all()) {
      const tops = await g.locator("input").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
      const firstRowTop = Math.min(...tops);
      const firstRowLefts = await g.locator("input").evaluateAll((els, top) => els.filter((e) => Math.round(e.getBoundingClientRect().top) === top).length, firstRowTop);
      expect(firstRowLefts >= Math.min(3, tops.length), `설정 입력칸 높이가 들쭉날쭉: ${JSON.stringify(tops)}`);
    }
    const rules = await page.getByTestId("kis-rules").innerText();
    expect(rules.includes("+3% 이하") && rules.includes("−6%") && rules.includes("−3%") && rules.includes("지정가") && rules.includes("자동 매도") && rules.includes("승인 없이"),
      `자동 규칙: ${rules}`);
    const pr = page.getByTestId("kis-proposals");
    const prt = await pr.innerText();
    expect(prt.includes("비싸서 기다림") && prt.includes("조건 맞으면 주문") && prt.includes("지정가 191,600원"), `조건 대기·지정가: ${prt}`);
    // 장중 AI 판단: 간격·오늘 횟수·마지막 결과·다음 시각·확인 대기 · 장중이면 버튼이 '지금 장중 판단' → intraday=true
    const it = await pr.getByTestId("kis-intraday").innerText();
    expect(it.includes("09:30~15:00") && it.includes("5분마다") && it.includes("두 번 연속") && it.includes("오늘 7번") && it.includes("마지막 10:00 새 매수 제안 1건")
      && it.includes("(6.2초)") && it.includes("다음 10:05") && it.includes("확인 대기: 카카오") && it.includes("+3%"), `장중 제안: ${it}`);
    await pr.getByTestId("kis-propose").click();
    await page.getByText(/장중 판단 — 새 매수 제안 1건/).waitFor();
    expect(api.calls.find((c) => c.key === "POST /api/kis/propose").query === "?intraday=true", "장중인데 장중 판단으로 안 부름");
    const approve = pr.getByTestId("kis-approve");
    expect(await approve.isDisabled(), "아무것도 안 골랐는데 승인이 눌림");
    await pr.getByRole("button", { name: "모두 선택" }).click();
    expect(await approve.isDisabled(), "2단계 코드 없이 승인이 눌림");
    await pr.getByLabel("승인 2단계 코드").fill("112233");
    await approve.click();
    await page.getByText(/주문 접수 2/).waitFor();
    const ab = JSON.parse(api.calls.find((c) => c.key === "POST /api/kis/orders/approve").body);
    expect(JSON.stringify(ab.ids.sort()) === "[11,12]" && ab.totp_code === "112233", `승인 요청: ${JSON.stringify(ab)}`);
    await pr.getByLabel("삼성전자 선택").check();
    await pr.getByRole("button", { name: "거절" }).click();
    await page.getByText("1건 거절했습니다").waitFor();
    expect(JSON.parse(api.calls.find((c) => c.key === "POST /api/kis/orders/reject").body).ids[0] === 11, "거절 요청 이상");
    await pr.getByRole("button", { name: "주문 취소" }).click();
    await page.getByText(/취소 요청/).waitFor();
    const h = await page.getByTestId("kis-history").innerText();
    expect(h.includes("LG화학") && h.includes("안전장치로 안 보냄") && h.includes("비싸져서"), `주문 기록: ${h}`);
    expect(h.includes("자동 손절") && h.includes("시장가") && h.includes("급변으로 자동 취소"), `자동 손절·자동 취소 기록: ${h}`);
    expect(h.includes("매수 장중 AI") && h.includes("LG화학"), `장중 제안 기록: ${h}`);
    const au = await page.getByTestId("kis-audit").innerText();
    expect(au.includes("승인") && au.includes("boss") && au.includes("안전장치로 막음") && au.includes("자동 손절") && au.includes("급변 자동 취소"), `감사 로그: ${au}`);
    await shot(page, "kis-trade");
  });

  await test("KIS 모의투자: 긴급 정지(코드 없이) · 정지 중 승인 불가 · 다시 시작은 2단계 코드 · 잔고 대조 경고", { api: adminApi({
    "GET /api/kis/status": (req) => ({ ...KF.KIS_STATUS, halted: true, halted_reason: "긴급 정지 버튼", halted_at: 1795000000,
      watch: { ...KF.KIS_STATUS.watch, stops_ok: false },
      last_error: "2026-11-25T17:24:51+09:00 제안 실패: 일봉을 받은 종목이 없음",
      mismatches: [{ symbol: "000660", name: "SK하이닉스", app: 0, kis: 3, pending: false }] }),
    "POST /api/kis/halt": { message: "주문을 멈췄습니다" },
    "POST /api/kis/resume": { message: "다시 시작했습니다" },
    "POST /api/kis/baseline": { message: "KIS 잔고를 앱 기록 기준으로 맞췄습니다" } }) }, async (page, api) => {
    await page.goto(`${BASE}/kis`);
    const st = await page.getByTestId("kis-status").innerText();
    expect(st.includes("정지됨") && st.includes("긴급 정지 버튼") && !st.includes("손절 자동 매도는 계속"), `정지 상태: ${st}`);
    expect(await page.getByTestId("kis-halt").count() === 0, "정지 중인데 긴급 정지 버튼이 보임");
    const le = await page.getByTestId("kis-last-error").innerText();
    expect(le.includes("마지막 자동 제안 실패 — 2026-11-25 17:24:51") && le.includes("지금 제안 만들기"), `제안 실패 표시: ${le}`);
    await page.getByTestId("kis-proposals").getByRole("button", { name: "모두 선택" }).click();
    await page.getByLabel("승인 2단계 코드").fill("112233");
    expect(await page.getByTestId("kis-approve").isDisabled(), "정지 중인데 승인이 눌림");
    const resume = page.getByRole("button", { name: "다시 시작" });
    expect(await resume.isDisabled(), "2단계 코드 없이 다시 시작이 눌림");
    await page.getByLabel("다시 시작 2단계 코드").fill("445566");
    await resume.click();
    await page.getByText("다시 시작했습니다").waitFor();
    const mm = await page.getByTestId("kis-mismatch").innerText();
    expect(mm.includes("SK하이닉스: 앱 0주 / KIS 3주"), `대조 경고: ${mm}`);
    expect(await page.getByLabel("기준 맞추기 2단계 코드").count() === 0, "기준 맞추기에 아직 2단계 코드 칸이 있음");
    expect(await page.getByTestId("kis-mismatch-pending").count() === 0, "직접 산 종목인데 '체결 중' 안내");
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "기준 다시 맞추기" }).click();
    await page.getByText(/기준으로 맞췄습니다/).waitFor();
    expect(!("totp_code" in JSON.parse(api.calls.find((c) => c.key === "POST /api/kis/baseline").body || "{}")), "기준 맞추기에 코드를 보냄");
  });

  await test("KIS 모의투자: 앱 주문이 체결 중이라 다르면 '저절로 맞춰짐' 안내", { api: adminApi({
    "GET /api/kis/status": { ...KF.KIS_STATUS, mismatches: [{ symbol: "005610", name: "삼립", app: 0, kis: 12, pending: true }] } }) }, async (page) => {
    await page.goto(`${BASE}/kis`);
    const mm = await page.getByTestId("kis-mismatch").innerText();
    expect(mm.includes("삼립: 앱 0주 / KIS 12주 (체결 중)") && mm.includes("저절로 맞춰집니다"), `체결 중 안내: ${mm}`);
  });

  await test("KIS 모의투자: 운영 중 긴급 정지 버튼 → 확인 후 바로 정지 요청 · 설정 저장(2단계)", { api: adminApi({
    "POST /api/kis/halt": { message: "주문을 멈췄습니다" },
    "POST /api/kis/notify-test": { message: "시험 알림을 보냈습니다 — 휴대폰 ntfy 앱을 확인하세요" },
    "PUT /api/kis/config": { limits: KF.KIS_STATUS.limits, params: KF.KIS_STATUS.params, message: "설정을 저장했습니다" } }) }, async (page, api) => {
    page.on("dialog", (d) => d.accept());
    await page.goto(`${BASE}/kis`);
    const nt = page.getByTestId("kis-notify");
    expect((await nt.innerText()).includes("ntfy ntfy.sh) 켜짐"), `알림 표시: ${await nt.innerText()}`);
    await nt.getByRole("button", { name: "알림 시험 보내기" }).click();
    await page.getByText(/시험 알림을 보냈습니다/).waitFor();
    await page.getByTestId("kis-halt").click();
    await page.getByText("주문을 멈췄습니다").waitFor();
    expect(api.calls.some((c) => c.key === "POST /api/kis/halt"), "정지 요청 없음");
    const cfg = page.getByTestId("kis-config");
    await cfg.getByLabel("하루 주문 횟수").fill("5");
    await cfg.getByLabel("설정 2단계 코드").fill("998877");
    await cfg.getByRole("button", { name: "저장" }).click();
    await page.getByText("설정을 저장했습니다").waitFor();
    const b = JSON.parse(api.calls.find((c) => c.key === "PUT /api/kis/config").body);
    expect(b.limits.max_orders_day === 5 && b.params.stop_pct === 7 && b.totp_code === "998877", `설정 요청: ${JSON.stringify(b)}`);
  });

  await test("KIS 모의투자: 계좌번호 거부(INVALID_CHECK_ACNO) → 원인 안내 · 시세용 계좌를 빌려 쓰는 중 경고", { api: adminApi({
    "GET /api/kis/status": { ...KF.KIS_STATUS, account: "****5678-01", account_source: "KIS_ACCOUNT_NO", balance: null, mismatches: [], day_loss: null,
      notify: { configured: false, server: "ntfy.sh", token: false, last: { ok: null, error: null, at: null } },
      balance_error: "모의투자 서버가 계좌번호 ****5678-01 를 거부했습니다 (INVALID_CHECK_ACNO). 지금은 backend/.env 의 KIS_MOCK_* 가 비어 있어 KIS_ACCOUNT_NO(시세용 계좌번호)를 쓰는 중입니다" } }) }, async (page) => {
    await page.goto(`${BASE}/kis`);
    const acc = await page.getByTestId("kis-account").innerText();
    expect(acc.includes("****5678-01") && acc.includes("KIS_ACCOUNT_NO"), `계좌 표시: ${acc}`);
    expect((await page.getByTestId("kis-status").innerText()).includes("시세용 계좌번호를 쓰는 중"), "시세용 계좌 경고 없음");
    expect((await page.getByTestId("kis-notify").innerText()).includes("NTFY_TOPIC"), "알림 꺼짐 안내 없음");
    const err = await page.getByTestId("kis-balance-error").innerText();
    expect(err.includes("INVALID_CHECK_ACNO") && err.includes("KIS_MOCK_"), `잔고 오류 안내: ${err}`);
  });

  await test("KIS 모의투자: 키가 없으면 연결 안내만 (390px 가로 스크롤 없음)", { width: 390, height: 844, theme: "dark", api: adminApi({
    "GET /api/kis/status": { ...KF.KIS_STATUS, configured: false, account: null, balance: null, log: [] },
    "GET /api/kis/log": { items: [] } }) }, async (page, api) => {
    await page.goto(`${BASE}/kis`);
    const t = await page.getByTestId("kis-setup").innerText();
    expect(t.includes("KIS_MOCK_APP_KEY") && t.includes("모의투자 신청"), `연결 안내: ${t}`);
    expect(await page.getByTestId("kis-proposals").count() === 0, "키가 없는데 제안 구역이 보임");
    expect(!api.calls.some((c) => c.key === "GET /api/kis/orders"), "키가 없는데 주문 목록을 부름");
    await noHScroll(page);
  });

  await test("관리자·KIS 화면 폭 390px: 가로 스크롤 없음", { width: 390, height: 844, api: adminApi() }, async (page) => {
    for (const path of ["/admin", "/kis"]) {
      await page.goto(`${BASE}${path}`);
      await page.getByTestId(path === "/admin" ? "admin-summary" : "kis-balance").waitFor();
      await noHScroll(page);
      await shot(page, `mobile${path.replace("/", "-")}`);
    }
  });

  await test("휴대폰 알림을 누름(/kis?order=10, 폭 390px): 그 주문 카드로 이동·강조 · 표 대신 카드 · 규칙·설정 접힘 · 승인", { width: 390, height: 844, api: adminApi({
    "POST /api/kis/orders/approve": { results: [{ id: 11, status: "approved", message: "개장 5분 뒤부터 매수" }] } }) }, async (page, api) => {
    page.on("dialog", (d) => d.accept());
    await page.goto(`${BASE}/kis?order=10`);
    const cards = page.getByTestId("kis-order-cards");
    await cards.waitFor();
    const focused = page.locator('[data-focused="1"]');
    expect(await focused.count() === 1 && (await focused.getAttribute("data-order")) === "10", "알림의 주문이 강조되지 않음");
    await page.waitForTimeout(300);
    const box = await focused.boundingBox();
    expect(box && box.y >= 0 && box.y + box.height <= 844, `알림의 주문 카드가 화면 안에 없음: ${JSON.stringify(box)}`);
    expect((await focused.innerText()).includes("현대차") && (await focused.innerText()).includes("비싸서 기다림"), "강조된 카드 내용");
    expect(await page.getByTestId("kis-proposals").locator("table").count() === 0, "휴대폰인데 제안 표가 그대로");
    expect((await page.getByTestId("kis-holdings-cards").innerText()).includes("손절 176,700원"), "보유 종목 카드");
    expect((await page.getByTestId("kis-history-cards").innerText()).includes("자동 손절"), "주문 기록 카드");
    expect(!(await page.getByTestId("kis-rules-fold").evaluate((e) => e.open)), "자동 규칙이 펼쳐져 있음");
    const cfg = page.getByTestId("kis-config");
    expect(await cfg.locator("input").count() === 0, "설정이 접혀 있지 않음");
    await cfg.getByRole("button", { name: "설정 보기·바꾸기" }).click();
    const g = cfg.getByTestId("kis-config-group").first();
    const tops = await g.locator("input").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
    expect(tops.length === 3 && tops[0] === tops[1], `휴대폰 설정 2열 입력칸 높이 다름: ${tops}`);
    await noHScroll(page);
    await shot(page, "mobile-kis-cards");
    await cards.getByLabel("삼성전자 선택").check();
    await page.getByTestId("kis-approve-bar").getByLabel("승인 2단계 코드").fill("123456");
    await page.getByTestId("kis-approve").click();
    await page.getByText(/조건 대기 1/).waitFor();
    expect(JSON.parse(api.calls.find((c) => c.key === "POST /api/kis/orders/approve").body).ids[0] === 11, "휴대폰 승인 요청 이상");
  });

  await test("끝난 주문 알림(/kis?order=13 자동 손절, 폭 390px) → 주문 기록 카드로 이동·강조", { width: 390, height: 844, api: adminApi() }, async (page) => {
    await page.goto(`${BASE}/kis?order=13`);
    const f = page.locator('[data-focused="1"]');
    await f.waitFor();
    expect(await f.count() === 1 && (await f.innerText()).includes("기아") && (await f.innerText()).includes("자동 손절"), "주문 기록에서 강조 안 됨");
    await page.waitForTimeout(300);
    const box = await f.boundingBox();
    expect(box && box.y >= 0 && box.y + box.height <= 844, `강조된 기록이 화면 밖: ${JSON.stringify(box)}`);
  });

  await test("로그인이 풀린 채 알림 링크(/kis?order=10)를 열면 → 로그인 → 그 화면으로 돌아감", { token: false, api: adminApi({
    "POST /api/auth/login": { access_token: "x", token_type: "bearer" } }) }, async (page) => {
    await page.goto(`${BASE}/kis?order=10`);
    await page.waitForURL(/\/login\?next=%2Fkis%3Forder%3D10$/);
    await page.locator("input").nth(0).fill("boss"); await page.locator("input").nth(1).fill("pw");
    await page.keyboard.press("Enter");
    await page.waitForURL(`${BASE}/kis?order=10`);
    await page.locator('[data-focused="1"]').waitFor();
  });

  await test("로그인 next 에 다른 사이트 주소(//evil.com)를 넣어도 첫 화면으로", { token: false, api: makeApi({
    "POST /api/auth/login": { access_token: "x", token_type: "bearer" } }) }, async (page) => {
    await page.goto(`${BASE}/login?next=%2F%2Fevil.com%2Fx`);
    await page.locator("input").nth(0).fill("me"); await page.locator("input").nth(1).fill("pw");
    await page.keyboard.press("Enter");
    await page.waitForURL(`${BASE}/`);
  });

  await test("로그인 화면: 회원가입·비밀번호 찾기 링크 + 안내 문구", { token: false }, async (page) => {
    await page.goto(`${BASE}/login`);
    await page.getByRole("link", { name: "회원가입" }).click();
    await page.waitForURL(/\/signup$/);
    await page.goto(`${BASE}/login`);
    await page.getByRole("link", { name: "비밀번호 찾기" }).click();
    await page.waitForURL(/\/forgot$/);
  });

  await test("회원가입: 코드 받기 → 규칙 안내 → 가입하면 로그인", { token: false, api: makeApi({
    "POST /api/auth/signup/send-code": { message: "me@naver.com 로 인증 코드를 보냈습니다 (10분 유효)" },
    "POST /api/auth/register": { message: "가입 완료", username: "newbie", access_token: "new-token", token_type: "bearer" } }) }, async (page, api) => {
    await page.goto(`${BASE}/signup`);
    const send = page.getByRole("button", { name: "인증 코드 받기" });
    await page.getByPlaceholder("you@naver.com").fill("bad-email");
    expect(await send.isDisabled(), "이메일 형식이 틀렸는데 코드 받기가 눌림");
    await page.getByPlaceholder("you@naver.com").fill("Me@Naver.com");
    await send.click();
    await page.getByText(/인증 코드를 보냈습니다/).waitFor();
    expect(await page.getByRole("button", { name: /초$/ }).isDisabled(), "다시 받기 대기(60초)가 없음");
    const submit = page.getByRole("button", { name: "가입하기" });
    await page.getByPlaceholder("000000").fill("12a3456");
    await page.locator("input[autocomplete=username]").fill("newbie");
    await page.locator("input[autocomplete=new-password]").first().fill("short");
    await page.getByText("✗ 8자 이상").waitFor();
    await page.locator("input[autocomplete=new-password]").first().fill("newbie1234");
    await page.getByText("✗ 아이디를 넣을 수 없음").waitFor();
    await page.locator("input[autocomplete=new-password]").first().fill("zxcv5678");
    await page.locator("input[autocomplete=new-password]").nth(1).fill("zxcv5679");
    await page.getByText("✗ 위와 다름").waitFor();
    expect(await submit.isDisabled(), "비밀번호 확인이 다른데 가입 버튼이 눌림");
    await page.locator("input[autocomplete=new-password]").nth(1).fill("zxcv5678");
    await submit.click();
    await page.waitForURL(`${BASE}/`);
    const body = JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/register").body);
    expect(body.email === "me@naver.com" && body.code === "123456" && body.username === "newbie", `가입 요청 이상: ${JSON.stringify(body)}`);
    expect((await page.evaluate(() => localStorage.getItem("token"))) === "new-token", "가입 후 토큰이 저장 안 됨");
    await shot(page, "after-signup");
  });

  await test("회원가입: 메일 설정이 없으면 안내만", { token: false, api: makeApi({ "GET /api/auth/options": { signup_open: true, mail_configured: false } }) }, async (page) => {
    await page.goto(`${BASE}/signup`);
    await page.getByTestId("signup-closed").waitFor();
    expect((await page.getByTestId("signup-closed").innerText()).includes("SMTP"), "안내 문구 이상");
  });

  await test("회원가입: 휴대폰으로 인증 (탭 전환 · 하이픈 · 닉네임)", { token: false, api: makeApi({
    "POST /api/auth/signup/send-code": { message: "010-1234-5678 로 인증번호 문자를 보냈습니다 (10분 유효)" },
    "POST /api/auth/register": { message: "가입 완료", username: "phoneman", access_token: "phone-token", token_type: "bearer" } }) }, async (page, api) => {
    await page.goto(`${BASE}/signup`);
    await page.getByRole("tab", { name: "휴대폰으로 인증" }).click();
    const send = page.getByRole("button", { name: "인증 코드 받기" });
    await page.getByLabel("휴대폰 번호").fill("0212345678");
    expect(await send.isDisabled(), "휴대폰 번호가 아닌데 코드 받기가 눌림");
    await page.getByLabel("휴대폰 번호").fill("01012345678");
    expect((await page.getByLabel("휴대폰 번호").inputValue()) === "010-1234-5678", "하이픈 자동 입력 안 됨");
    await send.click();
    await page.getByText(/인증번호 문자를 보냈습니다/).waitFor();
    await page.getByPlaceholder("000000").fill("123456");
    await page.locator("input[autocomplete=username]").fill("phoneman");
    await page.getByLabel("닉네임").fill("폰맨");
    await page.locator("input[autocomplete=new-password]").first().fill("zxcv5678");
    await page.locator("input[autocomplete=new-password]").nth(1).fill("zxcv5678");
    await page.getByRole("button", { name: "가입하기" }).click();
    await page.waitForURL(`${BASE}/`);
    const sc = JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/signup/send-code").body);
    const body = JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/register").body);
    expect(sc.phone === "01012345678" && !sc.email, `코드 요청 이상: ${JSON.stringify(sc)}`);
    expect(body.phone === "01012345678" && !body.email && body.nickname === "폰맨" && body.code === "123456", `가입 요청 이상: ${JSON.stringify(body)}`);
  });

  await test("회원가입: 문자 설정이 없으면 휴대폰 탭은 못 누름", { token: false, api: makeApi({ "GET /api/auth/options": { signup_open: true, mail_configured: true, sms_configured: false } }) }, async (page) => {
    await page.goto(`${BASE}/signup`);
    const tab = page.getByRole("tab", { name: /휴대폰으로 인증/ });
    await tab.waitFor();
    expect(await tab.isDisabled(), "문자 설정이 없는데 휴대폰 탭이 눌림");
    expect((await tab.innerText()).includes("준비 안 됨"), "준비 안 됨 표시 없음");
  });

  await test("비밀번호 찾기: 휴대폰 번호로", { token: false, api: makeApi({
    "POST /api/auth/password/forgot": { message: "010-1234-5678 가 가입된 휴대폰 번호면 인증번호 문자를 보냈습니다 (10분 유효)" },
    "POST /api/auth/password/reset": { message: "비밀번호를 바꿨습니다 — 새 비밀번호로 로그인하세요", username: "phoneman" } }) }, async (page, api) => {
    await page.goto(`${BASE}/forgot`);
    await page.getByRole("tab", { name: "휴대폰으로 인증" }).click();
    await page.getByLabel("휴대폰 번호").fill("010-1234-5678");
    await page.getByRole("button", { name: "코드 받기" }).click();
    await page.getByText(/가입된 휴대폰 번호면/).waitFor();
    await page.getByPlaceholder("000000").fill("654321");
    await page.locator("input[autocomplete=new-password]").first().fill("newpass123");
    await page.locator("input[autocomplete=new-password]").nth(1).fill("newpass123");
    await page.getByRole("button", { name: "비밀번호 바꾸기" }).click();
    await page.waitForURL(/\/login$/);
    const b = JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/password/reset").body);
    expect(b.phone === "01012345678" && !b.email && b.code === "654321", `초기화 요청 이상: ${JSON.stringify(b)}`);
  });

  await test("회원가입: 서버 오류 문구 그대로 (이미 가입된 이메일)", { token: false, api: makeApi({
    "POST /api/auth/signup/send-code": { __status: 400, detail: "이미 가입된 이메일입니다 — 로그인하거나 비밀번호 찾기를 쓰세요" } }) }, async (page) => {
    await page.goto(`${BASE}/signup`);
    await page.getByPlaceholder("you@naver.com").fill("me@naver.com");
    await page.getByRole("button", { name: "인증 코드 받기" }).click();
    await page.getByText("이미 가입된 이메일입니다").waitFor();
  });

  await test("비밀번호 찾기: 코드 → 새 비밀번호 → 로그인 화면에 안내", { token: false, api: makeApi({
    "POST /api/auth/password/forgot": { message: "me@naver.com 가 가입된 이메일이면 인증 코드를 보냈습니다" },
    "POST /api/auth/password/reset": { message: "비밀번호를 바꿨습니다 — 새 비밀번호로 로그인하세요", username: "tester" } }) }, async (page, api) => {
    await page.goto(`${BASE}/forgot`);
    await page.getByPlaceholder("you@naver.com").fill("me@naver.com");
    await page.getByRole("button", { name: "코드 받기" }).click();
    await page.getByText(/가입된 이메일이면/).waitFor();
    await page.getByPlaceholder("000000").fill("654321");
    await page.locator("input[autocomplete=new-password]").first().fill("newpass123");
    await page.locator("input[autocomplete=new-password]").nth(1).fill("newpass123");
    await page.getByRole("button", { name: "비밀번호 바꾸기" }).click();
    await page.waitForURL(/\/login$/);
    expect((await page.getByTestId("login-notice").innerText()).includes("아이디: tester"), "로그인 화면 안내 없음");
    const b = JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/password/reset").body);
    expect(b.code === "654321" && b.new_password === "newpass123", "초기화 요청 이상");
  });

  await test("마이페이지: 내 정보 · 이메일 인증 · 비밀번호 변경(새 토큰) · 상단 이름", { api: makeApi({
    "POST /api/auth/email/send-code": { message: "me@naver.com 로 인증 코드를 보냈습니다" },
    "POST /api/auth/email/verify": { message: "이메일을 인증했습니다", email: "me@naver.com" },
    "POST /api/auth/password/change": { message: "비밀번호를 바꿨습니다 (다른 기기는 다시 로그인해야 함)", access_token: "rotated", token_type: "bearer" } }) }, async (page, api) => {
    await page.goto(`${BASE}/`);
    const link = page.getByTestId("mypage-link");
    await link.getByText("tester").waitFor();
    await link.getByTestId("unverified-dot").waitFor();
    await link.click();
    await page.getByTestId("my-info").getByText("tester").first().waitFor();
    const info = await page.getByTestId("my-info").innerText();
    expect(info.includes("본인인증") && !info.includes("바꾼 적 없음"), `내 정보 칸 이상: ${info}`);
    expect(!(await page.locator("body").innerText()).includes("바꾼 적 없음"), "필요 없는 '비밀번호 변경: 바꾼 적 없음' 이 남아 있음");
    const em = page.getByTestId("email-row");
    await em.getByRole("button", { name: "등록" }).click();
    await em.getByLabel("새 이메일").fill("me@naver.com");
    await em.getByRole("button", { name: "인증 코드 받기" }).click();
    await em.getByLabel("이메일 인증 코드").fill("111222");
    await em.getByRole("button", { name: "확인" }).click();
    await page.getByText("이메일을 인증했습니다").first().waitFor();
    expect(JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/email/verify").body).code === "111222", "인증 코드가 안 감");
    const pw = page.getByTestId("password-section");
    const btn = pw.getByRole("button", { name: "비밀번호 바꾸기" });
    await pw.locator("input[autocomplete=current-password]").fill("oldpass123");
    await pw.locator("input[autocomplete=new-password]").first().fill("oldpass123");
    await pw.locator("input[autocomplete=new-password]").nth(1).fill("oldpass123");
    expect(await btn.isDisabled(), "지금 비밀번호와 같은데 바꾸기가 눌림");
    await pw.locator("input[autocomplete=new-password]").first().fill("newpass456");
    await pw.locator("input[autocomplete=new-password]").nth(1).fill("newpass456");
    await btn.click();
    await page.getByText(/비밀번호를 바꿨습니다/).first().waitFor();
    expect((await page.evaluate(() => localStorage.getItem("token"))) === "rotated", "새 토큰으로 안 바뀜 (다음 요청부터 401 로 로그아웃됨)");
  });

  let nick = null;
  await test("마이페이지: 닉네임 바꾸면 상단 이름도 바뀜 · 규칙 안내 · 서버 오류 문구", { api: makeApi({
    "GET /api/auth/me": () => ({ id: 1, username: "tester", nickname: nick, display_name: nick || "tester", totp_enabled: false, email: "me@naver.com", phone: null, created_at: "2026-11-01T00:00:00" }),
    "PUT /api/auth/profile": (req) => {
      const n = JSON.parse(req.postData()).nickname;
      if (n === "taken") return { __status: 400, detail: "이미 쓰고 있는 닉네임입니다" };
      nick = n || null; return { message: "닉네임을 바꿨습니다", nickname: nick, display_name: nick || "tester" };
    } }) }, async (page) => {
    await page.goto(`${BASE}/mypage`);
    const sec = page.getByTestId("nickname-section");
    const save = sec.getByRole("button", { name: "저장" });
    expect(await page.getByTestId("mypage-link").getByTestId("unverified-dot").count() === 0, "이메일 인증했는데 노란 점이 보임");
    await sec.getByLabel("닉네임").fill("띄어 쓰기");
    await sec.getByText(/✗ 한글·영문·숫자/).waitFor();
    expect(await save.isDisabled(), "규칙에 안 맞는데 저장이 눌림");
    await sec.getByLabel("닉네임").fill("taken");
    await save.click();
    await sec.getByText("이미 쓰고 있는 닉네임입니다").waitFor();
    await sec.getByLabel("닉네임").fill("주식왕");
    await save.click();
    await page.getByTestId("mypage-link").getByText("주식왕").waitFor();
    await page.getByTestId("my-info").getByText("아이디 tester").waitFor();
    await shot(page, "mypage");
  });

  let phone = null;
  await test("마이페이지: 휴대폰 등록(자동 하이픈·문자 코드) → 이메일 삭제(비밀번호) 가능해짐", { api: makeApi({
    "GET /api/auth/me": () => ({ id: 1, username: "tester", display_name: "tester", totp_enabled: false, email: "me@naver.com", phone, created_at: "2026-11-01T00:00:00" }),
    "POST /api/auth/phone/send-code": { message: "010-1234-5678 로 인증번호 문자를 보냈습니다 (10분 유효)" },
    "POST /api/auth/phone/verify": () => { phone = "010-1234-5678"; return { message: "휴대폰 번호를 인증했습니다", phone }; },
    "POST /api/auth/contact/remove": { message: "이메일을 지웠습니다" } }) }, async (page, api) => {
    await page.goto(`${BASE}/mypage`);
    const em = page.getByTestId("email-row"), ph = page.getByTestId("phone-row");
    expect(await em.getByRole("button", { name: "삭제" }).isDisabled(), "본인인증 수단이 하나뿐인데 삭제가 눌림");
    await ph.getByRole("button", { name: "등록" }).click();
    await ph.getByLabel("새 휴대폰 번호").fill("01012345678");
    expect((await ph.getByLabel("새 휴대폰 번호").inputValue()) === "010-1234-5678", "하이픈이 자동으로 안 들어감");
    await ph.getByRole("button", { name: "인증 코드 받기" }).click();
    await ph.getByLabel("휴대폰 인증 코드").fill("654321");
    expect(JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/phone/send-code").body).phone === "01012345678", "번호가 숫자만으로 안 감");
    await ph.getByRole("button", { name: "확인" }).click();
    await ph.getByText("010-1234-5678").waitFor();
    await em.getByRole("button", { name: "삭제" }).click();
    await em.getByLabel("이메일 삭제 비밀번호").fill("pw12345678");
    await em.getByRole("button", { name: "이메일 삭제" }).click();
    await page.getByText("이메일을 지웠습니다").first().waitFor();
    const b = JSON.parse(api.calls.find((c) => c.key === "POST /api/auth/contact/remove").body);
    expect(b.kind === "email" && b.password === "pw12345678", `삭제 요청 이상: ${JSON.stringify(b)}`);
  });

  await test("마이페이지: 최근 활동 표 · 로그인 실패 경고 · 모든 기기 로그아웃(새 토큰)", { api: makeApi({
    "GET /api/auth/activity": { recent_failures: 2, items: [
      { at: 1764000000, kind: "login", ok: true, ip: "1.2.3.4", user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", detail: null },
      { at: 1763990000, kind: "login_fail", ok: false, ip: "5.6.7.8", user_agent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1", detail: "비밀번호 틀림" }] },
    "POST /api/auth/logout-all": { message: "다른 모든 기기·브라우저에서 로그아웃했습니다", access_token: "fresh", token_type: "bearer" } }) }, async (page, api) => {
    await page.goto(`${BASE}/mypage`);
    const sec = page.getByTestId("devices-section");
    await sec.getByTestId("fail-warning").getByText(/로그인 실패 2번/).waitFor();
    const t = await sec.getByTestId("activity-table").innerText();
    expect(t.includes("Chrome · Windows") && t.includes("Safari · iPhone/iPad") && t.includes("로그인 실패") && t.includes("비밀번호 틀림") && t.includes("5.6.7.8"), `활동 표 이상: ${t}`);
    page.once("dialog", (d) => d.dismiss());
    await sec.getByRole("button", { name: "모든 기기에서 로그아웃" }).click();
    await page.waitForTimeout(200);
    expect(!api.calls.some((c) => c.key === "POST /api/auth/logout-all"), "취소했는데 요청이 감");
    page.once("dialog", (d) => d.accept());
    await sec.getByRole("button", { name: "모든 기기에서 로그아웃" }).click();
    await page.getByText(/다른 모든 기기/).first().waitFor();
    expect((await page.evaluate(() => localStorage.getItem("token"))) === "fresh", "지금 화면이 새 토큰으로 안 바뀜");
    expect(page.url().endsWith("/mypage"), "지금 화면까지 로그아웃됨");
  });

  await test("마이페이지: 관심종목·투자종목 CSV 내려받기 (엑셀 한글용 BOM)", {}, async (page) => {
    await page.goto(`${BASE}/mypage`);
    const sec = page.getByTestId("data-section");
    const [dl] = await Promise.all([page.waitForEvent("download"), sec.getByRole("button", { name: /관심종목 CSV/ }).click()]);
    expect(/^watchlist-\d{4}-\d{2}-\d{2}\.csv$/.test(dl.suggestedFilename()), `파일 이름 이상: ${dl.suggestedFilename()}`);
    const { readFileSync } = await import("node:fs");
    const txt = readFileSync(await dl.path(), "utf8");
    expect(txt.startsWith("\uFEFF시장,종목코드,종목명") && txt.includes(F.WATCH_LIST_BASIC[0].symbol), `CSV 내용 이상: ${txt.slice(0, 120)}`);
    const [dl2] = await Promise.all([page.waitForEvent("download"), sec.getByRole("button", { name: /투자종목 CSV/ }).click()]);
    const txt2 = readFileSync(await dl2.path(), "utf8");
    expect(txt2.includes("AVGO") && txt2.includes("수량,평단가"), `투자종목 CSV 이상: ${txt2.slice(0, 120)}`);
  });

  await test("마이페이지: 탈퇴는 아이디 입력 + 비밀번호 + 확인 후 → 로그인 화면", { api: makeApi({
    "POST /api/auth/delete-account": { message: "탈퇴했습니다" } }) }, async (page, api) => {
    await page.goto(`${BASE}/mypage`);
    const sec = page.getByTestId("delete-section");
    const btn = sec.getByRole("button", { name: "탈퇴하기" });
    await sec.getByLabel("탈퇴 비밀번호").fill("pw1234567");
    await sec.getByLabel("탈퇴 확인 아이디").fill("someone");
    expect(await btn.isDisabled(), "아이디를 틀리게 썼는데 탈퇴 버튼이 눌림");
    await sec.getByLabel("탈퇴 확인 아이디").fill("tester");
    page.once("dialog", (d) => d.dismiss());
    await btn.click();
    await page.waitForTimeout(200);
    expect(!api.calls.some((c) => c.key === "POST /api/auth/delete-account"), "확인 창에서 취소했는데 탈퇴 요청이 감");
    page.once("dialog", (d) => d.accept());
    await btn.click();
    await page.waitForURL(/\/login$/);
    await page.getByTestId("login-notice").waitFor();
    expect(!(await page.evaluate(() => localStorage.getItem("token"))), "탈퇴 후 토큰이 남아 있음");
  });

  await test("대시보드: 빅테크 브로드컴 주간거래 표시", {}, async (page) => {
    await page.goto(`${BASE}/`);
    await page.getByText("브로드컴").waitFor();
    const row = await page.getByText("브로드컴").locator("xpath=ancestor::div[2]").innerText();
    expect(row.includes("주간거래") && row.includes("$320.53") && row.includes("$304.41"), `브로드컴 줄: ${row}`);
  });

  await test("AI 추천 · 투자종목: 미국 종목 주간거래 표시", {}, async (page) => {
    await page.goto(`${BASE}/recommendations`);
    await page.getByRole("button", { name: /미국/ }).first().click();
    await page.getByText("브로드컴").first().waitFor();
    expect(await page.getByTestId("daytime-price").count() >= 1, "AI 추천 카드에 주간거래 가격 없음");
    const t = await text(page);
    expect(t.includes("목표가 (익절)") && t.includes("손절가"), "AI 추천 카드 가격대 3칸 없음");
    await page.goto(`${BASE}/portfolio`);
    await page.getByText("브로드컴").first().waitFor();
    await page.getByTestId("daytime-price").first().waitFor();
  });

  await test("경제 캘린더: 실제·이전·변화·해설 + 반영 전 사유", {}, async (page) => {
    await page.goto(`${BASE}/calendar`);
    await page.getByText("23.5만 건").waitFor();
    const t = await text(page);
    for (const s of ["22.1만 건", "▲ 1.4만 건 증가", "값 없음", "미국 GDP"]) expect(t.includes(s), `캘린더에 '${s}' 없음`);
    await page.getByText("미국 신규 실업수당 청구").click();
    await page.getByText(/실직자 증가/).waitFor();
    expect(await page.getByTestId("calendar-old-format").count() === 0, "정상 데이터인데 예전 형식 경고가 뜸");
    await shot(page, "calendar");
  });

  await test("경제 캘린더: 백엔드가 예전 형식이면 재시작 안내", { api: makeApi({ "GET /api/market/calendar": F.CALENDAR_OLD }) }, async (page) => {
    await page.goto(`${BASE}/calendar`);
    await page.getByTestId("calendar-old-format").waitFor();
  });

  await test("저장된 예전 데이터(1시간 이내)도 화면을 열면 새로 받음", {
    init: { "rq-cache-v1": JSON.stringify({ ts: Date.now(), state: { mutations: [], queries: [{
      queryKey: ["calendar"], queryHash: '["calendar"]',
      state: { data: F.CALENDAR_OLD, dataUpdateCount: 1, dataUpdatedAt: Date.now() - 5 * 60 * 1000, error: null, errorUpdateCount: 0,
               errorUpdatedAt: 0, fetchFailureCount: 0, fetchFailureReason: null, fetchMeta: null, isInvalidated: false, status: "success", fetchStatus: "idle" } }] } }) },
  }, async (page, api) => {
    await page.goto(`${BASE}/calendar`);
    await page.getByText("23.5만 건").waitFor();             // 저장본(예전 형식) 대신 새 데이터
    expect(api.calls.some((c) => c.key === "GET /api/market/calendar"), "캘린더를 새로 요청하지 않음");
  });

  await test("AI 모의투자: 실시간 계좌 — 자산·보유 종목·거래 이유·판단 기록·그래프", {}, async (page) => {
    await page.goto(`${BASE}/paper`);
    await page.getByTestId("account-detail").waitFor();
    expect((await page.locator(".sidebar").innerText()).includes("AI 모의투자"), "사이드바에 AI 모의투자 메뉴 없음");
    const pos = await page.getByTestId("account-positions").innerText();
    for (const s of ["SK하이닉스", "손절가", "목표가"]) expect(pos.includes(s), `보유 종목 표에 '${s}' 없음`);
    const tr = await page.getByTestId("account-trades").innerText();
    expect(tr.includes("매수") && tr.includes("AI 점수"), "거래 내역에 매수·AI 점수 이유 없음");
    const log = await page.getByTestId("account-log").innerText();
    for (const s of ["종가 기준 판단", "시장 상승 추세", "점수 상위"]) expect(log.includes(s), `판단 기록에 '${s}' 없음`);
    await page.getByText("자산 그래프는 거래일이 2일 이상 쌓이면 표시됩니다").waitFor();   // 새 계좌 = 종가 기록 1일
    await page.getByTestId("how-toggle").click();
    expect((await page.getByTestId("how-body").innerText()).includes("다음 날 데이터를 모르는 상태"), "설명에 미래 데이터 미사용 문구 없음");
    await shot(page, "paper-live");
  });

  await test("AI 모의투자: 계좌 만들기 요청 · 실패 문구", { api: makeApi({
    "GET /api/paper/accounts": { items: [], status: {} },
    "POST /api/paper/accounts": { __status: 422, detail: "시작 자금은 1,000,000~10,000,000,000원 사이여야 함" } }) }, async (page, api) => {
    await page.goto(`${BASE}/paper`);
    await page.getByTestId("account-form").waitFor();
    expect(await page.getByTestId("opt-entry_guard").count() === 0, "실시간 계좌 만들기에 시뮬레이션 전용 옵션(급변 보호)이 보임");
    await page.getByTestId("account-capital").fill("100");
    await page.getByTestId("account-create").click();
    await page.getByTestId("account-create-error").getByText("시작 자금은").waitFor();
    const body = JSON.parse(api.calls.find((c) => c.key === "POST /api/paper/accounts").body);
    expect(body.market === "KR" && body.capital === 100, `요청 본문: ${JSON.stringify(body)}`);
  });

  await test("AI 모의투자: 과거 시뮬레이션 결과 · 시작 요청(기간·설정)", {}, async (page, api) => {
    await page.goto(`${BASE}/paper`);
    await page.getByTestId("tab-sim").click();
    await page.getByTestId("sim-detail").waitFor();
    const t = await page.locator("body").innerText();
    for (const s of ["최종 자산", "AI 수익률", "+1.00%", "최대 낙폭", "승률", "지수 대비"]) expect(t.includes(s), `결과에 '${s}' 없음`);
    // 개선 옵션 vs 기본 방식 비교 (같은 데이터)
    const cmp = await page.getByTestId("sim-compare").innerText();
    for (const s of ["학습형 가중치 + 추세 필터 + 급변 보호", "+1%", "-7.06%", "개선 옵션이 더 나았습니다"]) expect(cmp.includes(s), `비교 표에 '${s}' 없음: ${cmp}`);
    const gd = await page.getByTestId("sim-guard").innerText();
    expect(gd.includes("안 산 매수 3건") && gd.includes("기다렸다 산 매수 2건"), `급변 보호 결과: ${gd}`);
    expect((await page.getByTestId("sim-trades").innerText()).includes("매도"), "거래 내역 없음");
    expect((await page.getByTestId("sim-log").innerText()).length > 20, "판단 기록 없음");
    expect((await page.getByTestId("sim-notes").innerText()).includes("FRED"), "데이터 경고 없음");
    const chart = await page.getByTestId("equity-chart").innerText();
    expect(chart.includes("AI") && chart.includes("코스피 같은 금액") && chart.includes("기본 방식"), `그래프 범례: ${chart}`);
    expect(await page.getByTestId("equity-chart").locator("path").count() === 3, "AI·지수·기본 방식 선 3개가 아님");
    await shot(page, "paper-sim");
    await page.getByRole("button", { name: "6개월" }).click();
    await page.getByRole("button", { name: /매매 규칙/ }).click();
    await page.getByTestId("param-max_positions").fill("3");
    expect(await page.getByTestId("opt-adaptive").isChecked() && await page.getByTestId("opt-trend_filter").isChecked()
      && await page.getByTestId("opt-entry_guard").isChecked(), "개선 옵션 기본 켬이 아님");
    await page.getByTestId("opt-trend_filter").uncheck();
    await page.getByTestId("sim-start").click();
    await page.waitForTimeout(300);
    const call = api.calls.find((c) => c.key === "POST /api/paper/simulations");
    const body = JSON.parse(call.body);
    expect(body.months === 6 && body.params.max_positions === 3 && body.capital === 10000000 && body.params.trend_filter === false,
      `요청 본문: ${call.body}`);
    // 탭 기억
    await page.reload();
    await page.getByTestId("sim-detail").waitFor();
  });

  await test("AI 모의투자: 시뮬레이션 계산 중 진행 표시 / 실패 사유", { api: makeApi({
    "GET /api/paper/simulations": { busy: true, items: [
      { id: 1, market: "KR", capital: 1e7, months: 12, params: {}, status: "running", summary: null, progress: { phase: "매매 시뮬레이션 중", done: 40, total: 250 } },
      { id: 2, market: "US", capital: 1e4, months: 3, params: {}, status: "failed", error: "일봉을 받은 종목이 0/40개뿐", summary: null }] },
    "GET /api/paper/simulations/1": { id: 1, market: "KR", status: "running", progress: { phase: "매매 시뮬레이션 중", done: 40, total: 250 } },
    "GET /api/paper/simulations/2": { id: 2, market: "US", status: "failed", error: "일봉을 받은 종목이 0/40개뿐" } }),
    init: { "paper-tab": "sim" } }, async (page) => {
    await page.goto(`${BASE}/paper`);
    await page.getByTestId("sim-progress").getByText("40/250").waitFor();
    expect(await page.getByTestId("sim-start").isDisabled(), "계산 중인데 시작 버튼이 눌림");
    await page.getByTestId("sim-list").getByText("실패").click();
    await page.getByTestId("sim-error").getByText("0/40개뿐").waitFor();
  });

  await test("AI 모의투자: 계산 중 시뮬레이션 중단 버튼 (확인 후 요청) · 중단 표시", { api: makeApi({
    "GET /api/paper/simulations": { busy: true, items: [
      { id: 1, market: "KR", capital: 1e7, months: 12, params: {}, status: "running", summary: null, progress: { phase: "점수 계산 중 (삼성전자)", done: 3, total: 25 } },
      { id: 3, market: "KR", capital: 1e7, months: 3, params: {}, status: "cancelled", error: "사용자가 중단함", summary: null }] },
    "GET /api/paper/simulations/1": { id: 1, market: "KR", status: "running", progress: { phase: "점수 계산 중 (삼성전자)", done: 3, total: 25 } },
    "GET /api/paper/simulations/3": { id: 3, market: "KR", status: "cancelled", error: "사용자가 중단함" },
    "POST /api/paper/simulations/1/cancel": { message: "중단을 요청했습니다 — 몇 초 안에 멈춥니다" } }),
    init: { "paper-tab": "sim" } }, async (page, api) => {
    await page.goto(`${BASE}/paper`);
    await page.getByTestId("sim-cancel").waitFor();
    page.once("dialog", (d) => d.dismiss());                     // 취소하면 요청 안 함
    await page.getByTestId("sim-cancel").click();
    await page.waitForTimeout(200);
    expect(!api.calls.some((c) => c.key === "POST /api/paper/simulations/1/cancel"), "확인 취소했는데 중단 요청함");
    page.once("dialog", (d) => d.accept());
    await page.getByTestId("sim-cancel").click();
    await page.getByTestId("sim-cancel").getByText("중단하는 중").waitFor();
    expect(api.calls.some((c) => c.key === "POST /api/paper/simulations/1/cancel"), "중단 요청 안 보냄");
    await page.getByTestId("sim-list").getByText("중단", { exact: true }).click();
    await page.getByTestId("sim-cancelled").getByText("사용자가 중단함").waitFor();
  });

  await test("로그인 토큰은 X-Access-Token 으로 (Authorization 은 클라우드 접속 비밀번호 자리 — 덮으면 모든 요청 401)", {}, async (page, api) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("watch-card").first().waitFor();
    const calls = api.calls.filter((c) => c.key.startsWith("GET /api/"));
    expect(calls.length > 0 && calls.every((c) => c.token === "e2e-token"), "토큰을 X-Access-Token 으로 안 보냄");
    expect(calls.every((c) => !c.authorization), `Authorization 헤더를 씀: ${calls.find((c) => c.authorization)?.authorization}`);
  });

  // 서버(Caddy)가 붙이는 보안 정책(CSP)을 그대로 걸고 화면을 열어 봄 — 막히는 스크립트·이미지가 있으면 콘솔 오류로 실패
  const CSP = readFileSync(new URL("../../deploy/Caddyfile", import.meta.url), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
  for (const theme of ["dark", "light"]) {
    await test(`보안 정책(CSP)을 걸어도 화면·테마가 정상 (${theme})`, { theme, api: makeApi({
      "POST /api/auth/setup-totp": { qr_code: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", secret: "ABC", uri: "otpauth://x" } }) },
    async (page) => {
      await page.route(`${BASE}/**`, async (route) => {
        if (route.request().resourceType() !== "document") return route.fallback();
        const resp = await route.fetch();
        await route.fulfill({ response: resp, headers: { ...resp.headers(), "content-security-policy": CSP } });
      });
      for (const p of ["/", "/paper", "/watchlist", "/calendar", "/mypage"]) {
        await page.goto(`${BASE}${p}`);
        await page.waitForLoadState("networkidle");
        expect(await page.evaluate(() => document.documentElement.dataset.theme) === theme, `${p}: 테마 초기화 스크립트가 막힘`);
      }
      // 2단계 인증 QR(data: 이미지)도 보여야 함
      await page.getByTestId("totp-section").getByRole("button", { name: /켜기|설정/ }).first().click();
      await page.getByAltText("2단계 인증 QR 코드").waitFor();
    });
  }

  await test("유출된 비밀번호면 모든 화면 위에 경고 + 마이페이지 링크", { api: makeApi({
    "GET /api/auth/me": { id: 1, username: "tester", display_name: "tester", totp_enabled: false, email: null, phone: null, verified: false,
                          password_leaked: true, created_at: "2026-11-01T00:00:00" } }) }, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    const b = page.getByTestId("leaked-banner");
    await b.waitFor();
    expect((await b.innerText()).includes("유출 목록"), "경고 문구 없음");
    await b.getByRole("link").click();
    await page.waitForURL(/\/mypage/);
    await shot(page, "leaked-banner");
  });

  await test("정상 비밀번호면 경고 없음", {}, async (page) => {
    await page.goto(`${BASE}/watchlist`);
    await page.getByTestId("watch-card").first().waitFor();
    expect(await page.getByTestId("leaked-banner").count() === 0, "유출 아닌데 경고가 보임");
  });

  // 나머지 화면: 가짜 응답이 없으면 502 → 오류 문구만 보이고 화면이 깨지지 않아야 함 (밝은·어두운 모드)
  const pages = ["/", "/mypage", "/recommendations", "/screener", "/themes", "/quant", "/gurus", "/value", "/flows", "/accumulation", "/watchlist", "/portfolio", "/paper", "/predictions", "/calendar"];
  for (const theme of ["light", "dark"]) {
    await test(`모든 화면 열기 — 오류로 멈추지 않음 (${theme})`, { theme }, async (page) => {
      for (const p of pages) {
        await page.goto(`${BASE}${p}`);
        await page.waitForLoadState("networkidle");
        const h1 = await page.locator("h1").first().innerText().catch(() => "");
        expect(h1.length > 0, `${p}: 제목(h1)이 안 그려짐 — 화면이 깨졌을 수 있음`);
      }
    });
  }
  await test("휴대폰 390px: 캘린더·AI 모의투자는 카드 · 투자종목 칸 안 잘림 · 브리핑 새로고침 한 줄 · 예측 검증·종목탐색", { width: 390, height: 844, api: makeApi({
    "GET /api/predictions/review": RF.REVIEW, "GET /api/predictions/backtest/status": RF.BACKTEST_STATUS,
    "GET /api/stocks/screener/kr/trading_value": [
      { symbol: "005930", name: "삼성전자", market: "KR", price: 177800, change_rate: -2.89, volume: 1, trading_value_display: "1.2조" },
      { symbol: "000660", name: "SK하이닉스", market: "KR", price: 200000, change_rate: 1.2, volume: 1, trading_value_display: "8,400억" }] }) }, async (page) => {
    await page.goto(`${BASE}/calendar`);
    const cards = page.getByTestId("cal-card");
    await cards.first().waitFor();
    expect(await page.locator("main table, .page-body table").count() === 0, "휴대폰 캘린더에 표가 남음");
    const c0 = cards.first();
    const ev = await c0.locator("strong").first().evaluate((e) => e.getBoundingClientRect().width);
    expect(ev > 120, `이벤트 이름 칸이 너무 좁음(${ev}px)`);
    await c0.getByRole("button").click();
    expect((await c0.getAttribute("data-testid")) === "cal-card" && (await c0.getByRole("button").getAttribute("aria-expanded")) === "true", "눌러도 해설이 안 펼쳐짐");
    await noHScroll(page);
    await shot(page, "m2-calendar");
    await page.goto(`${BASE}/`);
    await page.getByRole("button", { name: "새로고침" }).first().waitFor();
    await page.getByText("브로드컴").first().waitFor();
    const nmText = await page.getByText("브로드컴").first().evaluate((e) => [e.scrollWidth, e.clientWidth]);
    expect(nmText[0] <= nmText[1] + 1, `대시보드 빅테크 이름이 잘림: ${nmText}`);
    const rb = await page.getByRole("button", { name: "새로고침" }).first().boundingBox();
    expect(rb && rb.height < 48, `새로고침 버튼이 세로로 쪼개짐 (높이 ${rb?.height})`);
    await page.goto(`${BASE}/portfolio`);
    await page.getByText("오늘 손익 · 비중").first().waitFor();
    const today = await page.getByText("오늘 손익 · 비중").first().boundingBox();
    expect(today && today.x + today.width <= 390, `투자종목 '오늘 손익' 칸이 화면 밖: ${JSON.stringify(today)}`);
    await shot(page, "m2-portfolio");
    await page.goto(`${BASE}/paper`);
    await page.getByTestId("account-detail").waitFor().catch(() => {});
    expect(await page.locator(".page-body table").count() === 0, "휴대폰 AI 모의투자에 표가 남음");
    const fab = await page.locator(".chat-fab").boundingBox();
    expect(fab && fab.width <= 46, `챗봇 버튼이 큼 (${fab?.width}px)`);
    await noHScroll(page);
    await shot(page, "m2-paper");
    await page.goto(`${BASE}/predictions`);
    await page.getByTestId("fw-KR").waitFor();
    expect(await page.getByTestId("method-cards").count() === 1, "휴대폰 예측 방식별 적중률이 카드가 아님");
    await noHScroll(page);
    await shot(page, "m2-predictions");
    await page.goto(`${BASE}/screener`);
    await page.getByText("SK하이닉스").first().waitFor();
    for (const nm of ["삼성전자", "SK하이닉스"]) {   // 이름이 두 줄로 쪼개지지 않음
      const h = await page.locator(".scr-name", { hasText: nm }).first().evaluate((e) => e.getBoundingClientRect().height);
      expect(h < 24, `종목탐색 표 '${nm}' 이 두 줄 (${h}px)`);
    }
    const tbl = await page.locator(".scr-table").evaluate((e) => [e.scrollWidth, e.parentElement.clientWidth]);
    expect(tbl[0] <= tbl[1] + 1, `종목탐색 표가 카드보다 넓음: ${tbl}`);
    await noHScroll(page);
    await shot(page, "m2-screener");
  });

  await test("모든 화면 — 모바일 가로 스크롤 없음", { width: 390, height: 844 }, async (page) => {
    for (const p of ["/", "/recommendations", "/screener", "/watchlist", "/portfolio", "/themes", "/quant", "/gurus", "/value", "/flows", "/accumulation", "/paper", "/predictions",
      "/calendar", "/mypage"]) {
      await page.goto(`${BASE}${p}`);
      await page.waitForLoadState("networkidle");
      await noHScroll(page);
      await shot(page, `m${p === "/" ? "-dashboard" : p.replace("/", "-")}`);
    }
  });
}

// ---------------- 실행 ----------------
async function waitServer(url, ms = 20000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try { if ((await fetch(url)).ok) return; } catch { /* 아직 안 뜸 */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`미리보기 서버가 안 뜸: ${url}`);
}

const server = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort", "--host", "127.0.0.1"],
  { cwd: new URL("..", import.meta.url).pathname, stdio: "ignore" });
try {
  await waitServer(`${BASE}/`);
  browser = await chromium.launch();
  console.log("화면 테스트 (가짜 API)");
  await run();
} finally {
  await browser?.close();
  server.kill();
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 통과${failed.length ? ` — 실패: ${failed.map((f) => f.name).join(", ")}` : ""}`);
process.exit(failed.length ? 1 : 0);
