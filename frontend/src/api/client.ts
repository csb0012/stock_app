import axios from "axios";
import { clearPersisted } from "./persist";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  // 로그인 토큰은 Authorization 이 아니라 X-Access-Token 으로 보냄 — 클라우드 서버의 접속 비밀번호(Caddy basic auth)가
  // 브라우저의 Authorization 헤더를 쓰는데, 거기에 토큰을 넣으면 접속 비밀번호가 지워져 모든 요청이 401 이 됨
  if (token) config.headers["X-Access-Token"] = token;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // 로그인 만료 → 로그인 화면으로. 단, 로그인 요청 자체의 401(비밀번호 틀림)은 화면에 오류를 보여줘야 하므로
    // 새로고침하지 않음 (예전엔 새로고침돼서 '틀렸다'는 문구가 사라졌음)
    const url = String(err.config?.url || "");
    const isLoginCall = /\/auth\/(login|register|signup|password\/(forgot|reset))/.test(url);
    if (err.response?.status === 401 && !isLoginCall) {
      localStorage.removeItem("token");
      clearPersisted();
      if (window.location.pathname !== "/login") window.location.href = "/login";
    }
    // 2단계 인증 필수인데 아직 안 켬 → 2단계 설정 화면으로 (서버가 X-Totp-Required 헤더를 붙여 403)
    if (err.response?.status === 403 && err.response?.headers?.["x-totp-required"] && window.location.pathname !== "/setup-2fa") {
      window.location.href = "/setup-2fa";
    }
    return Promise.reject(err);
  }
);

export default api;

/** 백엔드가 보낸 오류 메시지(detail)를 꺼낸다 — 화면에 그대로 보여주기 위함 */
export function errMsg(e: any): string {
  const d = e?.response?.data?.detail;
  // 입력 검증 오류(422)는 [{loc, msg}] 목록으로 옴 → 문장만 꺼냄 (예전엔 '[object Object]')
  if (Array.isArray(d)) return d.map((x: any) => String(x?.msg || x).replace(/^Value error, /, "")).join(" / ");
  if (d && typeof d === "object") return JSON.stringify(d);
  return d || e?.message || "알 수 없는 오류";
}

// Auth
export type Contact = { email: string } | { phone: string };
export const authApi = {
  login: (username: string, password: string, totp_code?: string) =>
    api.post("/auth/login", { username, password, totp_code }),
  me: () => api.get("/auth/me"),
  setupTotp: () => api.post("/auth/setup-totp"),
  enableTotp: (totp_code: string) => api.post("/auth/enable-totp", { totp_code }),
  disableTotp: (totp_code: string) => api.post("/auth/disable-totp", { totp_code }),
  options: () => api.get("/auth/options"),
  // contact = { email } 또는 { phone } — 본인인증 수단 하나
  // invite_code = 관리자가 만든 초대 코드 (초대 전용 가입일 때)
  signupSendCode: (contact: Contact, invite_code?: string) => api.post("/auth/signup/send-code", { ...contact, invite_code: invite_code || undefined }),
  register: (username: string, password: string, contact: Contact, code: string, nickname?: string, invite_code?: string) =>
    api.post("/auth/register", { username, password, ...contact, code, nickname: nickname || undefined, invite_code: invite_code || undefined }),
  forgot: (contact: Contact) => api.post("/auth/password/forgot", contact),
  reset: (contact: Contact, code: string, new_password: string) => api.post("/auth/password/reset", { ...contact, code, new_password }),
  changePassword: (current_password: string, new_password: string) =>
    api.post("/auth/password/change", { current_password, new_password }),
  emailSendCode: (email: string) => api.post("/auth/email/send-code", { email }),
  emailVerify: (email: string, code: string) => api.post("/auth/email/verify", { email, code }),
  phoneSendCode: (phone: string) => api.post("/auth/phone/send-code", { phone }),
  phoneVerify: (phone: string, code: string) => api.post("/auth/phone/verify", { phone, code }),
  removeContact: (kind: "email" | "phone", password: string) => api.post("/auth/contact/remove", { kind, password }),
  updateProfile: (nickname: string) => api.put("/auth/profile", { nickname }),
  logoutAll: () => api.post("/auth/logout-all"),
  activity: (limit = 30) => api.get("/auth/activity", { params: { limit } }),
  deleteAccount: (password: string, totp_code?: string) => api.post("/auth/delete-account", { password, totp_code }),
};

// 관리자(앱 주인) — 초대 코드 · 회원 관리. 만들기·차단은 2단계 코드를 다시 받음
export const adminApi = {
  invites: () => api.get("/admin/invites"),
  createInvite: (memo: string, days: number, totp_code: string) => api.post("/admin/invites", { memo, days, totp_code }),
  revokeInvite: (id: number) => api.delete(`/admin/invites/${id}`),
  users: () => api.get("/admin/users"),
  setActive: (id: number, active: boolean, totp_code: string) => api.put(`/admin/users/${id}/active`, { active, totp_code }),
  summary: () => api.get("/admin/summary"),
  user: (id: number) => api.get(`/admin/users/${id}`),
  events: () => api.get("/admin/events"),
};

// KIS 모의투자 주문 (관리자만) — AI 제안 → 2단계 코드로 승인 → 모의투자 서버 주문
export const kisApi = {
  status: () => api.get("/kis/status"),
  orders: (kind: "open" | "all") => api.get("/kis/orders", { params: { kind } }),
  log: () => api.get("/kis/log"),
  propose: () => api.post("/kis/propose", {}, { timeout: 600_000 }),
  approve: (ids: number[], totp_code: string) => api.post("/kis/orders/approve", { ids, totp_code }, { timeout: 120_000 }),
  reject: (ids: number[]) => api.post("/kis/orders/reject", { ids }),
  cancel: (id: number) => api.post(`/kis/orders/${id}/cancel`),
  halt: (reason: string) => api.post("/kis/halt", { reason }),
  notifyTest: () => api.post("/kis/notify-test"),
  resume: (totp_code: string) => api.post("/kis/resume", { totp_code }),
  baseline: () => api.post("/kis/baseline", {}),
  config: (limits: Record<string, number>, params: Record<string, any> | null, totp_code: string) =>
    api.put("/kis/config", { limits, params, totp_code }),
};

// 규칙 기반 챗봇 (처음 조회하는 데이터는 몇 초 걸릴 수 있어 1분까지 기다림)
export const chatApi = {
  send: (messages: { role: string; content: string }[]) => api.post("/chat", { messages }, { timeout: 60_000 }),
};

// Market
export const marketApi = {
  overview: () => api.get("/market/overview"),
  section: (name: string) => api.get(`/market/overview/${name}`),
  calendar: () => api.get("/market/calendar"),
  status: () => api.get("/market/status"),
  regime: () => api.get("/market/regime", { timeout: 120_000 }),
};

// Stocks
export const stockApi = {
  // 국내 실시간 현재가 (서버가 KIS 웹소켓으로 받아 둔 값 — KIS 호출 없음)
  live: (symbols: string[]) => api.get("/stocks/live", { params: { symbols: symbols.join(",") } }),
  kr: (symbol: string) => api.get(`/stocks/kr/${symbol}`),
  us: (symbol: string, exchange = "NAS") => api.get(`/stocks/us/${symbol}?exchange=${exchange}`),
  volumeSurge: () => api.get("/stocks/volume-surge"),
  longterm: () => api.get("/stocks/recommendations/longterm"),
  // 장기 보유 분석 (과거 월봉 통계 — 처음엔 수십 초 걸릴 수 있음)
  longtermHorizon: () => api.get("/stocks/recommendations/longterm/horizon", { timeout: 180_000 }),
  shortterm: () => api.get("/stocks/recommendations/shortterm"),
  search: (q: string, market = "ALL", limit = 30) =>
    api.get(`/stocks/search?q=${encodeURIComponent(q)}&market=${market}&limit=${limit}`),
  quote: (market: string, symbol: string) => api.get(`/stocks/quote/${market}/${encodeURIComponent(symbol)}`),
  screenerKR: (mode: string) => api.get(`/stocks/screener/kr/${mode}`),
  screenerUS: (mode: string) => api.get(`/stocks/screener/us/${mode}`),
};

// Watchlist
export const watchlistApi = {
  list: () => api.get("/watchlist/"),
  add: (symbol: string, market: string, name: string) =>
    api.post("/watchlist/", { symbol, market, name }),
  remove: (id: number) => api.delete(`/watchlist/${id}`),
  update: (id: number, data: { memo?: string; target_price?: number }) => api.put(`/watchlist/${id}`, data),
  analysis: () => api.get("/watchlist/analysis"),
};

// 테마별 주식 (네이버 테마 분류 + KIS 시세)
export const themeApi = {
  list: () => api.get("/themes"),
  detail: (no: string) => api.get(`/themes/${no}`),
  refresh: () => api.post("/themes/refresh"),
};

// 매집·바닥 다지기 탐지
export const accumApi = {
  result: (minScore = 50) => api.get("/accumulation", { params: { min_score: minScore } }),
  scan: () => api.post("/accumulation/scan"),
};

// 퀀트 점수 (국내 전 종목, 매집 탐지와 같은 스캔)
export const quantApi = {
  list: (limit = 100) => api.get("/quant", { params: { limit } }),
};

// 예측 검증
export const predictionApi = {
  review: (days = 90, market = "ALL", kind = "all", outcome = "all", limit = 200) =>
    api.get(`/predictions/review`, { params: { days, market, kind, outcome, limit } }),
  runBacktest: (force = false) => api.post(`/predictions/backtest`, null, { params: { force } }),
  backtestStatus: () => api.get(`/predictions/backtest/status`),
};

// Portfolio
export const portfolioApi = {
  list: () => api.get("/portfolio/"),
  add: (symbol: string, market: string, name: string, quantity: number, avg_price: number) =>
    api.post("/portfolio/", { symbol, market, name, quantity, avg_price }),
  update: (id: number, quantity: number, avg_price: number) =>
    api.put(`/portfolio/${id}`, { quantity, avg_price }),
  remove: (id: number) => api.delete(`/portfolio/${id}`),
  analysis: () => api.get("/portfolio/analysis"),
};

// AI 모의투자 — 과거 시뮬레이션 / 실시간 모의투자 계좌
export type PaperParams = Partial<{ max_positions: number; buy_score: number; sell_score: number; stop_pct: number;
  take_pct: number; max_hold: number; trailing: boolean; adaptive: boolean; trend_filter: boolean; entry_guard: boolean }>;
export const paperApi = {
  config: () => api.get("/paper/config"),
  sims: () => api.get("/paper/simulations"),
  sim: (id: number) => api.get(`/paper/simulations/${id}`),
  startSim: (market: string, capital: number, months: number, params: PaperParams) =>
    api.post("/paper/simulations", { market, capital, months, params }),
  removeSim: (id: number) => api.delete(`/paper/simulations/${id}`),
  cancelSim: (id: number) => api.post(`/paper/simulations/${id}/cancel`),
  accounts: () => api.get("/paper/accounts"),
  account: (id: number) => api.get(`/paper/accounts/${id}`),
  createAccount: (market: string, capital: number, name: string, params: PaperParams) =>
    api.post("/paper/accounts", { market, capital, name, params }),
  run: (id: number) => api.post(`/paper/accounts/${id}/run`),
  setActive: (id: number, active: boolean) => api.put(`/paper/accounts/${id}/active`, null, { params: { active } }),
  removeAccount: (id: number) => api.delete(`/paper/accounts/${id}`),
};
