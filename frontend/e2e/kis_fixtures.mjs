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
};

export const KIS_STATUS = {
  configured: true, server: "모의투자 (가상 자금)", account: "****3456-01", halted: false, halted_reason: null, halted_at: null,
  limits: { max_order_krw: 2000000, max_orders_day: 10, max_loss_krw: 500000, max_gap_pct: 3 }, limit_meta: LIMIT_META,
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
    expires_at: 1795060000, decided_at: 1794950000, submitted_at: 1794960000, order_price: 191000, odno: "0000000007", filled_qty: 0, filled_price: null, message: "주문번호 0000000007" },
], status_labels: {} };

export const KIS_ALL = { items: [
  { ...KIS_OPEN.items[2] },
  { id: 8, created_at: 1794800000, base_date: "2026-11-19", source: "ai", side: "buy", symbol: "051910", name: "LG화학", qty: null, budget: 2000000,
    ref_price: 300000, reason: "AI 점수 64", score: 64, status: "blocked", status_label: "안전장치로 안 보냄", expires_at: 1794900000,
    decided_at: 1794850000, submitted_at: null, order_price: null, odno: null, filled_qty: 0, filled_price: null,
    message: "제안 때 300,000원 → 지금 312,000원 (+4.0%, 허용 3.0%) — 비싸져서 안 삼" },
], status_labels: {} };

export const KIS_LOG = { items: [
  { id: 3, at: 1794960000, action: "submitted", order_id: 9, ok: true, detail: "주문번호 0000000007 — 모의투자 매수주문이 완료되었습니다", by: "자동" },
  { id: 2, at: 1794950000, action: "approve", order_id: 9, ok: true, detail: "매수 NAVER", by: "boss" },
  { id: 1, at: 1794850000, action: "blocked", order_id: 8, ok: false, detail: "LG화학: 비싸져서 안 삼", by: "자동" },
] };
