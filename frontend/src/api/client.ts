import axios from "axios";
import { clearPersisted } from "./persist";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      clearPersisted();
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

/** 백엔드가 보낸 오류 메시지(detail)를 꺼낸다 — 화면에 그대로 보여주기 위함 */
export function errMsg(e: any): string {
  return e?.response?.data?.detail || e?.message || "알 수 없는 오류";
}

// Auth
export const authApi = {
  login: (username: string, password: string, totp_code?: string) =>
    api.post("/auth/login", { username, password, totp_code }),
  me: () => api.get("/auth/me"),
  setupTotp: () => api.post("/auth/setup-totp"),
  enableTotp: (totp_code: string) => api.post("/auth/enable-totp", { totp_code }),
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
};

// Stocks
export const stockApi = {
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
