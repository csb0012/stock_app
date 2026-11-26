// 투자 대가(13F) · 가치주 찾기 · 수급 동향 가짜 응답 — 필드 이름은 backend/app/api/routes/signals.py 응답과 같게
const holder = (key, name, weight, change, pct = null) => ({ key, name, weight, change, share_change_pct: pct });

export const GURUS = {
  gurus: [
    { key: "tepper", name: "데이비드 테퍼", firm: "아팔루사", style: "위기 때 싸게 사는 역발상 투자", period: "2026-09-30", filed: "2026-11-16",
      prev_period: "2026-06-30", stale: false, n_holdings: 24, total_value: 6.1e9, est_return_1y: 26.8, est_coverage: 98.4, n_new: 2, n_sold: 1,
      top: [{ ticker: "MU", issuer: "MICRON", weight: 17.61, change: "add" }, { ticker: "AMZN", issuer: "AMAZON", weight: 14.75, change: "reduce" }] },
    { key: "buffett", name: "워런 버핏", firm: "버크셔 해서웨이", style: "좋은 기업을 적정 가격에 사서 오래 보유하는 가치투자", period: "2026-09-30",
      filed: "2026-11-16", prev_period: "2026-06-30", stale: false, n_holdings: 30, total_value: 3.04e11, est_return_1y: 12.1, est_coverage: 95.6,
      n_new: 1, n_sold: 0, top: [{ ticker: "AAPL", issuer: "APPLE INC", weight: 24.95, change: "same" }] },
    { key: "ackman", name: "빌 애크먼", firm: "퍼싱 스퀘어", style: "소수 우량주 집중", period: "2026-03-31", filed: "2026-05-15",
      prev_period: "2025-12-31", stale: true, n_holdings: 11, total_value: 1.2e10, est_return_1y: -6.5, est_coverage: 100, n_new: 0, n_sold: 0, top: [] },
  ],
  validation: {
    horizon_days: 63, benchmark: "SPY", n: 775, avg_excess: -1.9, beat_rate: 42.3, avg_return: 3.1, pending: 130, missing: 6, validated: false,
    multi: { n: 255, avg_excess: -5.52, beat_rate: 38.0, avg_return: -1.38 },
    by_guru: { buffett: { n: 12, avg_excess: 2.1, beat_rate: 58.3, avg_return: 6.2 }, tepper: { n: 30, avg_excess: -3.2, beat_rate: 40.0, avg_return: 1.0 } },
    recent: [],
  },
  validation_ai: { horizon_days: 63, benchmark: "SPY", n: 120, avg_excess: 1.4, beat_rate: 56.1, avg_return: 5.2, pending: 20, missing: 0,
    validated: true, multi: { n: 10 }, by_guru: {}, recent: [], rule: "AI 점수 60↑ · 상승확률 55%↑ · 50일선 위", signals: 775, passed: 120 },
  status: { running: false, step: null, done: 33, total: 33, message: "대가 33명 · 종목 735개", errors: [], cusip_pending: 0, stale: false },
  updated_at: "2026-11-26T07:15:47", errors: [], unmapped: 40,
};

export const GURU_STOCKS = {
  items: [
    { ticker: "AMZN", name: "아마존닷컴", n_holders: 14, n_buyers: 3, n_sellers: 4, change_52w: 8.2, per: 31.2, pbr: 6.1, price: 230,
      holders: [holder("klarman", "세스 클라만", 18.49, "same")], buyers: [holder("mandel", "스티븐 맨델", 9.1, "new")],
      sellers: [holder("tepper", "데이비드 테퍼", 14.75, "reduce", -20)] },
  ],
  updated_at: "2026-11-26T07:15:47", sort: "holders",
};

export const GURU_DETAIL = {
  guru: GURUS.gurus[1],
  holdings: [
    { cusip: "037833100", ticker: "AAPL", name: "애플", issuer: "APPLE INC", cls: "COM", weight: 24.95, value: 7.6e10, shares: 2.3e8,
      change: "same", share_change_pct: 0, prev_weight: 26.1, change_52w: 27.6, price: 355.58, n_holders: 12 },
    { cusip: "H1467J104", ticker: "CB", name: "처브", issuer: "CHUBB LIMITED", cls: "COM", weight: 2.8, value: 8e9, shares: 2.7e7,
      change: "add", share_change_pct: 31.5, prev_weight: 2.1, change_52w: 4.4, price: 290, n_holders: 3 },
    { cusip: "999999999", ticker: null, name: null, issuer: "NEW CO", cls: "COM", weight: 0.5, value: 1e9, shares: 1e6,
      change: "new", share_change_pct: null, prev_weight: null, change_52w: null, price: null, n_holders: null },
  ],
  sold: [{ cusip: "111111111", ticker: "DVA", issuer: "DAVITA", prev_weight: 1.2 }],
};

export const VALUE_SCREENS = {
  KR: [
    { key: "undervalued_growth", name: "저평가 성장주", about: "PER 15배 이하인데 매출·영업이익이 전년보다 10% 넘게 늘어난 회사" },
    { key: "cheap_value", name: "아직 저렴한 가치주", about: "순자산보다 싸게 거래되는(PBR 0.8배 이하) 흑자 회사" },
    { key: "dividend", name: "고배당주", about: "최근 1년 배당수익률 4% 이상 흑자 회사" },
  ],
  US: [
    { key: "undervalued_growth", name: "저평가 성장주", about: "Yahoo '저평가 성장주'" },
    { key: "dividend", name: "미래의 배당왕", about: "배당을 3년 넘게 연속으로 늘린 회사" },
  ],
  status: { running: false, done: 0, total: 0, kr_symbols: 1834, kr_last: "2026-11-26", message: null },
};

export const VALUE_KR = {
  items: [
    { symbol: "005930", market: "KR", name: "삼성전자", price: 171300, per: 5.37, pbr: 1.84, roe: 34.3, op_margin: 46.1, sales_yoy: 126.9,
      op_yoy: 783.1, div_yield: 3.45, debt: 28.9, eps_ttm: 31887, q: "202609", quant_grade: "A", quant_score: 9, trend_pct: 88,
      flow_label: "쌍끌이 3일 연속", flow_streak: 3 },
  ],
  total: 1, universe: 1834, status: VALUE_SCREENS.status,
};

export const VALUE_US = {
  items: [{ symbol: "NVDA", market: "US", name: "엔비디아", price: 180.2, per: 16.04, pbr: 13.5, div_yield: 0.64, change_52w: 42.1, market_cap: 4.4e12 }],
  total: 269,
};

const flowRow = (symbol, name, extra) => ({
  symbol, name, date: "2026-11-25", days: 5, streak: 0, sell_streak: 0, label: null, frgn5: 0, orgn5: 0, prsn5: 0,
  frgn_amt5: 0, orgn_amt5: 0, prsn_amt5: 0, frgn_amt1: 0, orgn_amt1: 0, prsn_amt1: 0, intensity: null, price: 10000, ...extra,
});
export const FLOWS = {
  date: "2026-11-25", n: 1820, universe: 1834,
  lists: {
    double: [flowRow("005930", "삼성전자", { streak: 3, label: "쌍끌이 3일 연속", frgn_amt5: 3.2e11, orgn_amt5: 1.1e11, prsn_amt5: -4.3e11, intensity: 4.12, price: 171300 })],
    foreign: [flowRow("000660", "SK하이닉스", { frgn_amt5: 5.1e11, orgn_amt5: -2e10, prsn_amt5: -4.9e11 })],
    institution: [], retail_buy: [flowRow("035420", "NAVER", { label: "개인만 순매수 (외국인·기관 순매도)", prsn_amt5: 8e10, frgn_amt5: -5e10, orgn_amt5: -3e10 })],
    retail_sell: [], double_sell: [],
  },
  daily: ["2026-11-19", "2026-11-20", "2026-11-21", "2026-11-24", "2026-11-25"].map((date, i) => ({
    date, frgn: (i - 2) * 2e11, orgn: 1e11, prsn: (2 - i) * 2e11 - 1e11, n: 1800, double: 100 + i })),
  status: { running: false, done: 0, total: 0, symbols: 1820, rows: 54000 },
  retail: { retail: { n: 2400, beat_rate: 44.2, avg_excess: -1.3 }, double: { n: 900, beat_rate: 53.0, avg_excess: 0.9 }, dates: 8, active: false,
    horizon: 20, penalty: 5, rule: "개인 5일 순매수 > 0 이고 외국인+기관 5일 순매수 < 0", need: "표본 300↑·날짜 10↑·평균 초과 -0.5%p 이하·이긴 비율 47.0% 이하" },
};

export const SIGNALS_KR = {
  guru: null, flow: { date: "2026-11-25", days: 5, streak: 3, sell_streak: 0, label: "쌍끌이 3일 연속", frgn5: 1e6, orgn5: 5e5, prsn5: -1.5e6,
    frgn_amt5: 3.2e11, orgn_amt5: 1.1e11, prsn_amt5: -4.3e11, intensity: 4.1, price: 171300 },
  value: { q: "202609", per: 5.37, pbr: 1.84, roe: 34.3, op_margin: 46.1, sales_yoy: 126.9, op_yoy: 783.1, div_yield: 3.45, debt: 28.9 },
  score_parts: [{ key: "value", label: "가치(저PER·저PBR)", points: 3.2, pct: 82, note: "퀀트 비중 12%" },
                { key: "flow", label: "수급(외국인+기관)", points: 0, pct: 91, note: "아직 검증 안 됨 — 점수엔 안 넣고 참고만" }],
  bonus: 3.2,
};
export const SIGNALS_US = {
  guru: { n_holders: 3, n_buyers: 1, n_sellers: 0, holders: [holder("buffett", "워런 버핏", 24.95, "same")], buyers: [holder("lilu", "리 루", 5.2, "new")],
    sellers: [], period: "2026-09-30", points: 0, validated: false, validation: { n: 775, avg_excess: -1.9, beat_rate: 42.3, horizon_days: 63 } },
  value: null, flow: null,
  score_parts: [{ key: "guru", label: "투자 대가", points: 0, note: "검증 미달 — 점수엔 안 넣고 참고만" }], bonus: 0,
};
