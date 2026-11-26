// KIS 모의투자 주문 · 관리자 페이지 화면 테스트용 가짜 응답 — 백엔드 응답과 같은 필드 이름
// (backend/tests/test_kis_trade.py · test_invite_totp.py 가 실제 형식을 검사). 앱 코드는 이 파일을 쓰지 않음.

export const ADMIN_ME = { id: 1, username: "boss", display_name: "boss", totp_enabled: true, totp_required: true, is_admin: true,
  email: "b@naver.com", created_at: "2026-11-01T00:00:00" };

export const ADMIN_SUMMARY = { users: 2, active: 2, blocked: 0, totp_missing: 1, admins: 1, invites_active: 1, login_fail_7d: 3, login_users_24h: 1 };

export const ADMIN_USER_2 = {
  id: 2, username: "friend", display_name: "친구", is_admin: false, is_active: true, totp_enabled: false, email: "fr***@naver.com", phone: null,
  invited_by: "boss", created_at: "2026-11-20T00:00:00", password_leaked: false, locked_until: null, login_fail_7d: 1, ips: ["10.7.7.7"],
  usage: { watchlist: 3, portfolio: 0, paper_accounts: 1, paper_sims: 2 },
  events: [
    { at: 1795000100, kind: "login_fail", ok: false, ip: "10.7.7.7", user_agent: "Mozilla/5.0 (Windows NT 10.0) Chrome/120", detail: null },
    { at: 1795000000, kind: "signup", ok: true, ip: "10.7.7.7", user_agent: "Mozilla/5.0 (iPhone) Safari/604", detail: null },
  ],
};

export const ADMIN_EVENTS = { items: [
  { at: 1795000100, kind: "login_fail", ok: false, ip: "10.7.7.7", user_agent: null, detail: null, user: "friend" },
  { at: 1795000050, kind: "invite_create", ok: true, ip: "10.0.0.1", user_agent: null, detail: "…9PWD · 동생", user: "boss" },
] };

const LIMIT_META = {
  max_order_krw: { default: 2000000, min: 100000, max: 100000000, label: "1회 매수 한도 (원)" },
  max_orders_day: { default: 10, min: 1, max: 50, label: "하루 주문 횟수" },
  max_loss_krw: { default: 500000, min: 10000, max: 100000000, label: "하루 손실 한도 (원)" },
  max_gap_pct: { default: 3, min: 0.5, max: 15, label: "제안 뒤 가격 상승 허용 (%)" },
  fast_drop_pct: { default: 3, min: 1, max: 15, label: "10분 급락 → 매수 취소 (%)" },
  index_drop_pct: { default: 2, min: 0.5, max: 10, label: "지수 하락 → 매수 보류 (%)" },
  limit_slip_pct: { default: 0.3, min: 0, max: 2, label: "매수 지정가 여유 (%)" },
  intraday_runs: { default: 3, min: 0, max: 5, label: "장중 AI 제안 횟수 (0 = 끔)" },
};

export const KIS_STATUS = {
  configured: true, server: "모의투자 (가상 자금)", account: "****3456-01", account_source: "KIS_MOCK_ACCOUNT_NO",
  notify: { configured: true, server: "ntfy.sh", token: false, link: "https://mystock.duckdns.org/kis", last: { ok: true, error: null, at: 1795000000 } }, halted: false, halted_reason: null, halted_at: null,
  limits: { max_order_krw: 2000000, max_orders_day: 10, max_loss_krw: 500000, max_gap_pct: 3, fast_drop_pct: 3, index_drop_pct: 2, limit_slip_pct: 0.3, intraday_runs: 3 },
  limit_meta: LIMIT_META,
  intraday: { slots: ["10:00", "12:00", "14:00"], done: ["10:00"], running: false, last: "2026-11-24T10:01:40+09:00", result: "10:00 새 매수 제안 1건", error: null },
  param_meta: { max_positions: { default: 5, min: 1, max: 15, label: "최대 보유 종목 수" }, buy_score: { default: 60, min: 50, max: 90, label: "매수 기준 AI 점수" },
    sell_score: { default: 45, min: 20, max: 60, label: "매도 기준 AI 점수" }, stop_pct: { default: 7, min: 2, max: 30, label: "손절 %" },
    take_pct: { default: 15, min: 3, max: 100, label: "익절(목표) %" }, max_hold: { default: 20, min: 2, max: 120, label: "최대 보유 거래일" } },
  watch: { last: "2026-11-24T10:00:05+09:00", error: null, symbols: 4, realtime: 0, rest: 4, missing: 0, every: 5, index_change: -0.42, index_error: null,
           buy_after_open: 5, stops_ok: true,
           ws: { connected: false, subscribed: 0, last_error: "2026-11-24T09:58:00 ConnectionRefusedError: 연결 거부", last_message: null, reconnects: 3 } },
  params: { max_positions: 5, buy_score: 60, sell_score: 45, stop_pct: 7, take_pct: 15, max_hold: 20, trailing: true, adaptive: true, trend_filter: true },
  orders_today: 1, window: "open", last_proposal_day: "2026-11-23", last_error: null, loop: { last_tick: "2026-11-24T10:00:00", last_error: null },
  baseline: true, day_loss: -120000,
  log: [{ ts: "2026-11-23T15:45:10+09:00", base_date: "2026-11-23", regime: "상승 추세", events: [], manual: false, universe: 42,
          orders: ["매수 삼성전자 — AI 점수 72 — 상승확률 61%", "매도 SK하이닉스 — AI 점수 40 (매도 기준 45 미만)"], notes: ["학습형 비중: 상승확률 50% · 퀀트 35% · 매집 15%"] }],
  balance: { cash: 8200000, d2_cash: 8150000, total: 10120000, stock_value: 1970000, prev_total: 10000000, pnl: 70000, holdings: [
    { symbol: "000660", name: "SK하이닉스", qty: 3, sellable: 3, avg: 190000, price: 200000, value: 600000, pnl: 30000, pnl_pct: 5.26, stop: 176700, target: 218500, hold_days: 4 },
  ] },
  balance_error: null, mismatches: [],
};

export const KIS_OPEN = { items: [
  { id: 11, created_at: 1795000000, base_date: "2026-11-23", source: "ai", side: "buy", symbol: "005930", name: "삼성전자", qty: null, budget: 2000000,
    ref_price: 70000, reason: "AI 점수 72 — 상승확률 61% · 퀀트 A(85) · 시장 상승 추세", score: 72, status: "proposed", status_label: "승인 대기",
    expires_at: 1795060000, decided_at: null, submitted_at: null, order_price: null, odno: null, filled_qty: 0, filled_price: null, message: null },
  { id: 12, created_at: 1795000000, base_date: "2026-11-23", source: "ai", side: "sell", symbol: "000660", name: "SK하이닉스", qty: 3, budget: null,
    ref_price: 200000, reason: "AI 점수 40 (매도 기준 45 미만)", score: 40, status: "proposed", status_label: "승인 대기",
    expires_at: 1795060000, decided_at: null, submitted_at: null, order_price: null, odno: null, filled_qty: 0, filled_price: null, message: null },
  { id: 9, created_at: 1794900000, base_date: "2026-11-20", source: "ai", side: "buy", symbol: "035420", name: "NAVER", qty: 10, budget: 2000000,
    ref_price: 190000, reason: "AI 점수 66", score: 66, status: "submitted", status_label: "주문 접수",
    expires_at: 1795060000, decided_at: 1794950000, submitted_at: 1794960000, order_price: 191000, limit_price: 191600, cancel_req: null, odno: "0000000007",
    filled_qty: 0, filled_price: null, message: "주문번호 0000000007 · 지정가 191,600원" },
  { id: 10, created_at: 1794900000, base_date: "2026-11-20", source: "ai", side: "buy", symbol: "005380", name: "현대차", qty: null, budget: 1500000,
    ref_price: 250000, reason: "AI 점수 63", score: 63, status: "approved", status_label: "승인 — 조건 맞으면 주문",
    expires_at: 1795060000, decided_at: 1794950000, submitted_at: null, order_price: null, limit_price: null, cancel_req: null, odno: null, filled_qty: 0, filled_price: null,
    message: "제안 때 250,000원 → 지금 260,000원 (+4.0%, 허용 +3%) — 비싸서 기다림 (쫓아가서 안 삼)" },
], status_labels: {} };

export const KIS_ALL = { items: [
  { ...KIS_OPEN.items[2] },
  { id: 15, created_at: 1795000100, base_date: "2026-11-24", source: "intraday", side: "buy", symbol: "051910", name: "LG화학", qty: null, budget: 2000000,
    ref_price: 300000, reason: "장중 판단 10:00 — AI 점수 70 — 상승확률 62%", score: 70, status: "rejected", status_label: "거절", expires_at: 1795060000,
    decided_at: 1795000200, submitted_at: null, order_price: null, limit_price: null, cancel_req: null, odno: null, filled_qty: 0, filled_price: null, message: null },
  { id: 13, created_at: 1794990000, base_date: "2026-11-24", source: "stop", side: "sell", symbol: "000270", name: "기아", qty: 5, budget: null,
    ref_price: 92000, reason: "손절가 도달 — 자동 매도 (장중 92,000원 · 손절 93,000원)", score: null, status: "filled", status_label: "체결",
    expires_at: 1795060000, decided_at: 1794990000, submitted_at: 1794990001, order_price: 92000, limit_price: null, cancel_req: null, odno: "0000000010",
    filled_qty: 5, filled_price: 91900, message: "주문번호 0000000010 · 시장가" },
  { id: 14, created_at: 1794980000, base_date: "2026-11-23", source: "ai", side: "buy", symbol: "068270", name: "셀트리온", qty: null, budget: 2000000,
    ref_price: 180000, reason: "AI 점수 68", score: 68, status: "cancelled", status_label: "취소", expires_at: 1795060000,
    decided_at: 1794950000, submitted_at: null, order_price: null, limit_price: null, cancel_req: null, odno: null, filled_qty: 0, filled_price: null,
    message: "급변으로 자동 취소 — 10분 안에 -3.4% 급락 (182,000 → 175,800원, 기준 −3%)" },
  { id: 8, created_at: 1794800000, base_date: "2026-11-19", source: "ai", side: "buy", symbol: "051910", name: "LG화학", qty: null, budget: 2000000,
    ref_price: 300000, reason: "AI 점수 64", score: 64, status: "blocked", status_label: "안전장치로 안 보냄", expires_at: 1794900000,
    decided_at: 1794850000, submitted_at: null, order_price: null, odno: null, filled_qty: 0, filled_price: null,
    message: "제안 때 300,000원 → 지금 312,000원 (+4.0%, 허용 3.0%) — 비싸져서 안 삼" },
], status_labels: {} };

export const KIS_LOG = { items: [
  { id: 5, at: 1794990000, action: "auto_stop", order_id: 13, ok: true, detail: "기아 5주 손절가 도달 — 자동 매도", by: "자동" },
  { id: 4, at: 1794980000, action: "auto_cancel", order_id: 14, ok: false, detail: "셀트리온: 10분 안에 -3.4% 급락", by: "자동" },
  { id: 3, at: 1794960000, action: "submitted", order_id: 9, ok: true, detail: "주문번호 0000000007 — 모의투자 매수주문이 완료되었습니다", by: "자동" },
  { id: 2, at: 1794950000, action: "approve", order_id: 9, ok: true, detail: "매수 NAVER", by: "boss" },
  { id: 1, at: 1794850000, action: "blocked", order_id: 8, ok: false, detail: "LG화학: 비싸져서 안 삼", by: "자동" },
] };
