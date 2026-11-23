// e2e 화면 테스트용 가짜 API 응답 — 백엔드 응답과 같은 필드 이름 (backend/tests/test_routes.py 가 실제 형식을 검사)
// 실제 데이터처럼 보이는 숫자지만 화면 검증용일 뿐, 앱 코드는 이 파일을 쓰지 않음.

const now = new Date().toISOString().slice(0, 19);
const iso = (d) => d.toISOString().slice(0, 10);
const day = (off) => { const d = new Date(); d.setDate(d.getDate() + off); return iso(d); };

export const DAYTIME = {
  label: "주간거래", price: 320.53, base: 304.41, change: 16.12, change_rate: 5.3, volume: 1200,
  time: "17:31", hours_kst: "10:00~18:00", source: "KIS 주간거래",
};

const pred = (p, price, kr) => ({
  probability: p, confidence: "보통", signal: p >= 55 ? "매수 고려" : p <= 45 ? "관망" : "중립",
  target_label: "월요일(11/23)", target_date: "2026-11-23",
  buy_price: kr ? Math.round(price * 0.965) : +(price * 0.964).toFixed(2), buy_gap_pct: -3.5,
  buy_low: price * 0.95, buy_high: price * 0.97,
  buy_comment: "하락 우세 — 최근 20일 저점에서 하락이 멈추는지(양봉·거래량 감소) 확인 후 매수",
  target_price: kr ? Math.round(price * 1.06) : +(price * 1.053).toFixed(2),
  stop_loss: kr ? Math.round(price * 0.93) : +(price * 0.93).toFixed(2),
  summary: "학습 모델(결합) 하락 우세 (36%) — 주요 근거: 60일선 이격 -25.0%(↑), 20일선 이격 -13.8%(↓), 당일 종가 위치(고가~저가) +0.28(↓) · 지표 점수 기준 44%",
  model_status: "학습 모델 미사용 (방향 적중률 48.3%가 우연 수준)",
  factors: [
    { name: "RSI", short: "RSI 32", detail: "과매도 근처", impact: "up", score: 20, max: 30 },
    { name: "MACD", short: "MACD", detail: "데드크로스", impact: "down", score: 5, max: 25 },
    { name: "이평", short: "이평", detail: "20일선 아래", impact: "neutral", score: 12, max: 25 },
  ],
  events: [], disclaimer: "참고용 예측입니다. 투자 손실에 대한 책임은 본인에게 있습니다.",
});

const wl = (id, symbol, market, name, price, chg, p, extra = {}) => ({
  id, symbol, market, name, memo: null, target_price: null, added_at: now,
  current_price: price, change_rate: chg, prediction: pred(p, price, market === "KR"), rsi: 32.79,
  high_period: price * 1.8, low_period: price * 0.98, period_days: market === "KR" ? 100 : 128,
  change_5d: -9.65, change_20d: -16.53, target_gap_pct: null, target_reached: false, ...extra,
});

export const WATCHLIST = [
  wl(1, "005930", "KR", "삼성전자", 177800, -2.89, 36, { memo: "HBM 수주 확인 후 매수", target_price: 175000, target_gap_pct: 1.6 }),
  wl(2, "0167A0", "KR", "SOL AI반도체TOP2플러스", 11270, -1.1, 36),
  wl(3, "AVGO", "US", "브로드컴", 304.41, -12.19, 48, { daytime: DAYTIME }),
  wl(4, "SOXL", "US", "SOXL (반도체 3배 레버리지)", 30.88, -31.83, 48),
  wl(5, "BAD", "US", "조회실패종목", undefined, undefined, 50),
];
WATCHLIST[4] = { id: 5, symbol: "BAD", market: "US", name: "조회실패종목", memo: null, target_price: null, error: "yfinance 가격 데이터 부족 (0일)" };
for (let i = 0; i < 4; i++) WATCHLIST.push(wl(10 + i, `00${i}660`, "KR", `테스트종목${i + 1}`, 50000 + i * 1000, i - 1.5, 40 + i * 8));

export const WATCH_LIST_BASIC = WATCHLIST.map(({ id, symbol, market, name, memo, target_price, added_at }) =>
  ({ id, symbol, market, name, memo, target_price, added_at }));

export const MARKET_STATUS = {
  KR: { market: "KR", state: "장 마감", open: false, local_time: "17:31", next_open: "2026-11-24", next_open_label: "내일", next_open_kst: "화 11/24 09:00" },
  US: { market: "US", state: "개장 전", open: false, local_time: "03:31", next_open: "2026-11-23", next_open_label: "월요일(11/23)", next_open_kst: "월 11/23 23:30",
        daytime: { open: true, session_date: "2026-11-23", hours_kst: "10:00~18:00", end_kst: "18:00" } },
};

export const BIGTECH = {
  items: [
    { symbol: "AVGO", name: "브로드컴", price: 304.41, change: -42.24, change_rate: -12.19, as_of: "2026-11-20", source: "Yahoo Finance", daytime: DAYTIME },
    { symbol: "AAPL", name: "애플", price: 230.1, change: 1.2, change_rate: 0.52, as_of: "2026-11-20", source: "Yahoo Finance",
      ext: { price: 231.0, label: "애프터마켓", time: "11/20 19:55 ET", change_rate: 0.39 } },
  ], updated_at: now, refreshing: false,
};

const rec = (symbol, market, name, price, p, extra = {}) => ({
  symbol, name, market, exchange: market === "US" ? "NAS" : null, category: "stock", price, change_rate: -1.2, per: 30, pbr: 5,
  prediction: pred(p, price, market === "KR"), news: { total: 1, headlines: [{ title: `${name} 관련 기사`, url: "https://example.com/a", tone: "neg", press: "Reuters", date: "11/21" }] },
  long_term_score: 70, short_term_score: 60, indicators: { rsi: 40, macd_hist: -1 }, ...extra,
});

export const RECS = {
  items: [rec("005930", "KR", "삼성전자", 177800, 36), rec("AVGO", "US", "브로드컴", 304.41, 48, { daytime: DAYTIME })],
  errors: [], updated_at: now, refreshing: false, live_errors: [],
};

export const QUOTE_AVGO = {
  ...rec("AVGO", "US", "브로드컴", 304.41, 48, { daytime: DAYTIME }), volume: 60000000,
  indicators: { rsi: 28.4, macd_hist: -3.12, ma20: 340.2, ma60: 330.5, bb_upper: 370.1, bb_lower: 300.2 },
  news: { total: 2, source: "Yahoo Finance", headlines: [
    { title: "Broadcom falls on report Google cut 2027 shipment plans", url: "https://example.com/1", tone: "neg", press: "Reuters", date: "11/20" },
    { title: "Is Broadcom's drop a chance to buy?", url: "https://example.com/2", tone: "pos", press: "Trefis", date: "11/23" }] },
};

export const SEARCH = [{ symbol: "AVGO", market: "US", name: "브로드컴", exchange: "NAS", type: "stock" }];

export const PORTFOLIO_LIST = [{ id: 1, symbol: "AVGO", market: "US", name: "브로드컴", quantity: 2, avg_price: 300 }];
export const PORTFOLIO = {
  items: [{ ...PORTFOLIO_LIST[0], current_price: 304.41, change_rate: -12.19, invested: 600, value: 608.82, pnl_pct: 1.47,
            pnl_amount: 8.82, day_pnl: -84.48, prediction: pred(48, 304.41, false), warning: null, weight: 100, daytime: DAYTIME }],
  totals: { KRW: { invested: 0, value: 0, pnl: 0, day_pnl: 0, count: 0, pnl_pct: 0 },
            USD: { invested: 600, value: 608.82, pnl: 8.82, day_pnl: -84.48, count: 1, pnl_pct: 1.47 } },
  usdkrw: 1400, fx_error: null,
  combined_krw: { invested: 840000, value: 852348, pnl: 12348, pnl_pct: 1.47, day_pnl: -118272 },
};

const explain = (about, words) => ({ about, metric: "주간 청구 건수", scenarios: Object.fromEntries(words.map((w) => [w, `${w} 시 시장 영향`])) });
export const CALENDAR = {
  source: "FRED 공식 발표 일정·발표값 + 연준 FOMC 일정",
  disclaimer: "해설은 일반적인 경향입니다.", errors: [], retry: false, updated_at: now, refreshing: false,
  events: [
    { date: day(-4), key: "unemployment insurance weekly claims report", event: "미국 신규 실업수당 청구", country: "US", impact: "medium",
      released: true, actual: "23.5만 건", prev: "22.1만 건", period: "11/14 주", metric: "주간 청구 건수", change: "up", change_text: "▲ 1.4만 건 증가",
      explain: { ...explain("한 주 동안 처음 실업수당을 신청한 사람 수.", ["증가", "감소", "같음"]), effect: "실직자 증가 → 고용 약화 신호 → 금리 인하 기대 ↑." } },
    { date: day(-3), key: "surveys of consumers", event: "미시간대 소비자심리", country: "US", impact: "low",
      released: false, note: "FRED 에 아직 반영 전 (보통 발표 후 1시간 안에 올라옴)", explain: explain("소비자심리지수", ["개선", "악화", "같음"]) },
    { date: day(2), key: "gross domestic product", event: "미국 GDP", country: "US", impact: "high", released: false,
      explain: explain("미국 경제 성장률", ["성장 가속", "성장 둔화", "같음"]) },
  ],
};
// 업데이트 전 백엔드가 주던 예전 형식 (발표값·해설 없음) — 화면에 '-' 만 보이던 상황 재현용
export const CALENDAR_OLD = {
  source: "FRED", errors: [], updated_at: now,
  events: [{ date: day(-4), event: "미국 신규 실업수당 청구", country: "US", impact: "medium", actual: null, previous: null, estimate: null }],
};

// ---------- 퀀트 점수 · 시장 상태 · 예측 적중 기록 ----------
export const QUANT_ROW = {
  score: 9, pct: 87, grade: "A", factors: { rs: 92, trend: 85, updown: 70, lowvol: 40, high52: 88 },
  beat_rate: 57.4, bucket: "80~100", price: 177800, date: "2026-11-20", universe: 2412,
};
export const TRACK = { hit: 14, miss: 9, n: 23, accuracy: 60.9, conf_hit: 6, conf_n: 9, conf_accuracy: 66.7, live: 5, enough: true, days: 90 };
WATCHLIST[0].quant = QUANT_ROW;
WATCHLIST[0].track = TRACK;
WATCHLIST[2].track = { ...TRACK, hit: 3, miss: 1, n: 4, accuracy: 75, enough: false };
RECS.items[0].quant = QUANT_ROW;
RECS.items[0].track = TRACK;

const regimeVal = (s) => ["상승 추세", "상승 압박", "하락 추세"].map((st, i) => ({
  state: st, n: 300 - i * 50, up_rate: [62.1, 55.0, 48.3][i], avg_ret: [1.8, 0.6, -0.9][i], base_up_rate: 57.2 }));
const reg = (key, name, market, state, extra = {}) => ({
  key, name, market, ticker: "^X", state, advice: `${state} 설명`, as_of: "2026-11-20", close: 2500, vs_ma50: -2.1, vs_ma200: state === "하락 추세" ? -4.2 : 3.3,
  ma200_up: state !== "하락 추세", dist_days: 3, since: "2026-11-02", days_in_state: 14, validation: regimeVal(), horizon_days: 20,
  period: ["2022-09-01", "2026-11-20"], ...extra,
});
export const REGIME = {
  items: {
    KOSPI: reg("KOSPI", "코스피", "KR", "상승 압박"),
    KOSDAQ: reg("KOSDAQ", "코스닥", "KR", "하락 추세"),
    SPX: reg("SPX", "S&P 500", "US", "상승 추세"),
    NASDAQ: reg("NASDAQ", "나스닥 종합", "US", "상승 추세", { dist_days: null }),
  },
  rules: { dist_window: 25, dist_drop_pct: -0.2, dist_warn: 5 }, updated_at: now, refreshing: false,
};

export const QUANT = {
  quant: {
    date: "2026-11-20", universe: 2412, horizon_days: 20, useful: true,
    weights: { rs: 0.35, trend: 0.25, updown: 0.1, lowvol: 0.05, high52: 0.25 },
    ic: { rs: 0.041, trend: 0.03, updown: 0.012, lowvol: 0.006, high52: 0.03 },
    validation: {
      train: ["2026-07-01", "2026-07-20"], test: ["2026-08-20", "2026-10-22"], ic: 0.035, spread: 2.41, n: 52000,
      train_weights: {},
      buckets: [
        { range: "80~100", lo: 80, hi: 100, n: 10400, beat_rate: 56.2, avg_excess: 1.21 },
        { range: "60~80", lo: 60, hi: 80, n: 10400, beat_rate: 52.0, avg_excess: 0.4 },
        { range: "40~60", lo: 40, hi: 60, n: 10400, beat_rate: 49.8, avg_excess: -0.1 },
        { range: "20~40", lo: 20, hi: 40, n: 10400, beat_rate: 47.9, avg_excess: -0.5 },
        { range: "0~20", lo: 0, hi: 20, n: 10400, beat_rate: 45.1, avg_excess: -1.2 },
      ],
    },
    factors: [
      { key: "rs", name: "모멘텀(RS)", about: "최근 1·3·6개월 수익률 가중" }, { key: "trend", name: "추세", about: "이평 정배열" },
      { key: "updown", name: "거래량 매집", about: "상승일/하락일 거래량" }, { key: "lowvol", name: "안정성", about: "저변동성" },
      { key: "high52", name: "고점 근접", about: "200일 고점 대비" },
    ],
    top: [
      { symbol: "005930", name: "삼성전자", ...QUANT_ROW, themes: [{ name: "반도체" }], accum: 55 },
      { symbol: "000660", name: "SK하이닉스", ...QUANT_ROW, score: 10, pct: 95, grade: "A+", themes: [], accum: null },
      { symbol: "035420", name: "NAVER", ...QUANT_ROW, score: 6, pct: 55, grade: "B", beat_rate: 49.8, themes: [], accum: 30 },
    ],
  },
  error: null, status: { running: false, done: 0, total: 0, stale: false }, base_date: "2026-11-20",
};
