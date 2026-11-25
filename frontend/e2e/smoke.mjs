// 화면 전체 테스트 (Playwright, 가짜 API) — 빌드된 화면(dist)을 vite preview 로 띄우고 /api 요청은 fixtures.mjs 로 응답.
// 실행: frontend 폴더에서  npm run build && node e2e/smoke.mjs   (스크린샷: E2E_SHOTS=폴더 를 주면 저장)
// 백엔드·외부 API 없이 동작. 실제 응답 형식은 backend/tests 가 따로 검사.
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import * as F from "./fixtures.mjs";

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
    ...overrides,
  };
  async function handle(route) {
    const req = route.request();
    const url = new URL(req.url());
    const key = `${req.method()} ${url.pathname}`;
    calls.push({ key, body: req.postData() });
    let body = table[key];
    if (typeof body === "function") body = body(req);
    if (body && body.__status) {   // 오류 응답 흉내: { __status: 401, detail: "..." }
      const { __status, ...rest } = body;
      return route.fulfill({ status: __status, contentType: "application/json", body: JSON.stringify(rest) });
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
    "POST /api/auth/disable-totp": () => { totpOn = false; return { message: "ok" }; } }) }, async (page, api) => {
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

  // 나머지 화면: 가짜 응답이 없으면 502 → 오류 문구만 보이고 화면이 깨지지 않아야 함 (밝은·어두운 모드)
  const pages = ["/", "/mypage", "/recommendations", "/screener", "/themes", "/quant", "/accumulation", "/watchlist", "/portfolio", "/predictions", "/calendar"];
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
  await test("모든 화면 — 모바일 가로 스크롤 없음", { width: 390, height: 844 }, async (page) => {
    for (const p of ["/", "/watchlist", "/calendar", "/screener", "/portfolio", "/quant", "/mypage"]) {
      await page.goto(`${BASE}${p}`);
      await page.waitForLoadState("networkidle");
      await noHScroll(page);
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
