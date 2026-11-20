import axios from "axios";

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
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

// Auth
export const authApi = {
  login: (username: string, password: string, totp_code?: string) =>
    api.post("/auth/login", { username, password, totp_code }),
  me: () => api.get("/auth/me"),
  setupTotp: () => api.post("/auth/setup-totp"),
  enableTotp: (totp_code: string) => api.post("/auth/enable-totp", { totp_code }),
};

// Market
export const marketApi = {
  overview: () => api.get("/market/overview"),
  calendar: () => api.get("/market/calendar"),
};

// Stocks
export const stockApi = {
  kr: (symbol: string) => api.get(`/stocks/kr/${symbol}`),
  us: (symbol: string, exchange = "NAS") => api.get(`/stocks/us/${symbol}?exchange=${exchange}`),
  volumeSurge: () => api.get("/stocks/volume-surge"),
  longterm: () => api.get("/stocks/recommendations/longterm"),
  shortterm: () => api.get("/stocks/recommendations/shortterm"),
  search: (q: string, market = "ALL") =>
    api.get(`/stocks/search?q=${encodeURIComponent(q)}&market=${market}`),
  screenerKR: (mode: string) => api.get(`/stocks/screener/kr/${mode}`),
  screenerUS: (mode: string) => api.get(`/stocks/screener/us/${mode}`),
};

// Watchlist
export const watchlistApi = {
  list: () => api.get("/watchlist/"),
  add: (symbol: string, market: string, name: string) =>
    api.post("/watchlist/", { symbol, market, name }),
  remove: (id: number) => api.delete(`/watchlist/${id}`),
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
