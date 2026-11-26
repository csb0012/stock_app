"""KIS 모의투자 주문 — AI 가 주문을 제안하고 관리자가 승인한 매수만, 장중에 조건이 맞을 때 모의투자 서버로 주문 (사용자 결정 2026-11-25).
위험을 줄이는 일(손절가 도달 매도 · 급변 때 매수 취소)은 승인 없이 자동 + 휴대폰 알림 (사용자 결정 2026-11-26).

흐름
  1. 제안: 국내 장 마감 15분 뒤(15:45~) AI 모의투자와 같은 판단 함수로 'KIS 모의투자 계좌의 실제 잔고'를 놓고 판단
     → 매수·매도 제안 (승인 대기). 새 제안이 생기면 관리자에게 알림. '무엇을 살지'는 하루 한 번 (AI 가 일봉으로 만들어지고 검증됨)
  2. 승인: 관리자가 2단계 코드를 넣고 승인 (선택한 여러 건을 한 번에) = '아래 조건 안에서 사도 된다'
  3. 장중 실시간 감시 watch() — WATCH_EVERY(5)초마다, KIS 실시간 체결가(웹소켓, 없으면 REST 시세 15초마다):
     - 승인한 매수: 개장 BUY_AFTER_OPEN(5)분 뒤부터, 제안 때보다 +허용%(3) 넘게 비싸지 않고 · 지수가 −2% 넘게 빠지지 않고 ·
       VI(변동성 완화장치)·거래 정지가 아니면 → 지정가(현재가 +0.3%, 호가 단위 올림)로 주문. 안 맞으면 기다림 (15:20 까지)
     - 급변 = 제안 때보다 −(허용×2)%(6) 넘게 하락 · 10분 안에 −3% 넘게 급락 → 승인 대기·조건 대기·접수된(안 체결) 매수를 자동 취소
     - 손절가 이하 → 승인 없이 바로 시장가 매도 (긴급 정지 버튼으로 멈춘 동안은 안 함 · 하루 손실 한도 정지 중엔 함)
     - 목표가 이상 → 매도 제안 (승인해야 팔림 — 급하지 않아서)
  4. 체결 확인: 장중 1분마다 KIS 일별 체결 조회로 맞춤 → 앱 기록(보유 수량)에 반영
제안은 다음 거래일 장 마감(15:30)까지만 유효. 그 뒤엔 만료 (오래된 판단으로 주문하지 않게).
매수 = 지정가(정한 가격보다 비싸게 안 삼), 매도 = 시장가(손절은 빨리). 지정가를 KIS 에 미리 걸어 두지 않고 앱이 조건을 보다가 보냄
→ 앱이 꺼져 있으면 '안 사는 쪽'으로 끝남 (급락 중에 걸어 둔 주문이 체결되는 일이 없게).

안전장치
  - 모의투자 서버 전용 (kis_order 가 실거래 주소를 거부) · 관리자만 · 승인할 때마다 2단계 코드
  - 1회 매수 한도(원) · 하루 주문 횟수(자동 손절은 안 막음) · 하루 손실 한도(전날 총자산 대비, 넘으면 자동 정지 — 손절은 계속)
  - 매도는 위험을 줄이는 주문이라 가격 확인 안 함
  - 같은 종목에 보내는 중/접수된 주문이 있거나 오늘 같은 방향으로 이미 체결됐으면 안 보냄 (두 번 주문 방지)
  - 한 제안은 한 번만 승인됨 (조건부 UPDATE) · 주문 보내기 전에 '보내는 중'으로 먼저 저장 → 서버가 꺼져도 다시 안 보냄(결과 모름으로 표시)
  - KIS 잔고와 앱 기록(앱이 체결시킨 수량)이 다르면 매수 안 함 — HTS 에서 직접 사고팔았으면 '기준 다시 맞추기'
  - 긴급 정지: 바로 모든 주문을 멈추고 승인 대기·접수된(안 체결) 주문을 취소. 다시 시작은 2단계 코드
  - 모든 일은 kis_log(감사 로그)에 남김
"""
import asyncio
import json
import math
import time
from datetime import datetime, date, timedelta

from sqlalchemy import select, update, func as sa_func

from app.core.database import AsyncSessionLocal
from app.models.kis import KisTrade, KisOrder, KisLog
from app.services import kis_order
from app.services.kis_api import KISConnectionError
from app.services import paper_engine as pe
from app.services.market_calendar import _TZ, is_trading_day, next_trading_day, session_hours

MARKET = "KR"
# 이름: (기본값, 최소, 최대)
LIMITS = {
    "max_order_krw": (2_000_000, 100_000, 100_000_000),
    "max_orders_day": (10, 1, 50),
    "max_loss_krw": (500_000, 10_000, 100_000_000),
    "max_gap_pct": (3.0, 0.5, 15.0),
    "fast_drop_pct": (3.0, 1.0, 15.0),
    "index_drop_pct": (2.0, 0.5, 10.0),
    "limit_slip_pct": (0.3, 0.0, 2.0),
}
LIMIT_LABELS = {
    "max_order_krw": "1회 매수 한도 (원)", "max_orders_day": "하루 주문 횟수", "max_loss_krw": "하루 손실 한도 (원)",
    "max_gap_pct": "제안 뒤 가격 상승 허용 (%)", "fast_drop_pct": "10분 급락 → 매수 취소 (%)",
    "index_drop_pct": "지수 하락 → 매수 보류 (%)", "limit_slip_pct": "매수 지정가 여유 (%)",
}
STATUS_LABELS = {
    "proposed": "승인 대기", "approved": "승인 — 조건 맞으면 주문", "submitting": "보내는 중", "submitted": "주문 접수",
    "filled": "체결", "partial": "일부 체결", "unfilled": "안 체결", "unknown": "결과 모름 (KIS 에서 확인)",
    "rejected": "거절", "expired": "기한 지남", "cancelled": "취소", "blocked": "안전장치로 안 보냄", "failed": "KIS 거부",
}
OPEN_AFTER = 1            # 개장 몇 분 뒤 승인된 주문 보내기
STOP_BEFORE_CLOSE = 10    # 장 마감 몇 분 전부터 새 주문 안 보냄 (15:20~ 동시호가)
PROPOSE_AFTER = 15        # 장 마감 몇 분 뒤 제안
PROPOSE_RETRY = 1800      # 자동 제안이 실패하면 이만큼(초) 뒤 다시 (매분 KIS 를 부르지 않게)
EXIT_EVERY = 300          # 장중 손절·목표 확인 / 손실 한도 확인 주기 (초)
LOG_KEEP = 60
BUY_AFTER_OPEN = 5        # 개장 몇 분 뒤부터 매수 (개장 직후엔 가격이 크게 출렁임)
WATCH_EVERY = 5           # 장중 실시간 감시 주기 (초)
DROP_WINDOW = 600         # '10분 급락' 을 보는 시간 (초)
REST_EVERY = 15           # 실시간 체결가가 없을 때 REST 시세를 받는 주기 (초)
INDEX_EVERY = 60          # 지수 확인 주기 (초)
STOP_RETRY = 120          # 자동 손절이 안 나갔으면(막힘·실패) 이만큼(초) 뒤 다시
STOP_TRIES = 3            # 하루 한 종목 자동 손절 시도 횟수
WAIT_RETRY = 30           # 주문 직전 확인에서 '기다림'이 나온 매수는 이만큼(초) 뒤 다시 확인 (REST 호출 줄이기)
ACTIVE = ("submitting", "submitted")           # KIS 로 나갔고 아직 끝나지 않은 주문
SENT = ("submitting", "submitted", "filled", "partial", "unfilled", "unknown")   # 하루 주문 횟수에 세는 것

_lock = asyncio.Lock()   # 제안·주문·체결 반영은 하나씩 (잔고·횟수 확인이 겹치지 않게)
_status: dict = {"last_tick": None, "last_error": None}
_last_exit = 0.0
_balance_cache: dict = {"at": 0.0, "data": None, "error": None}
_hist: dict = {}          # 종목 → [(시각, 가격)] 최근 DROP_WINDOW 초 (10분 급락 확인용)
_rest: dict = {"at": 0.0, "data": {}, "error": None}     # REST 시세 (실시간 값이 없는 종목)
_index: dict = {"at": 0.0, "change": None, "error": None}
_next_try: dict = {}      # 주문 id → 다시 확인할 시각
_wait_kind: dict = {}     # 주문 id → 마지막 기다림 이유 종류 (감사 로그는 이유가 바뀔 때만)
_watch: dict = {"last": None, "error": None, "symbols": 0, "realtime": 0, "rest": 0, "missing": 0}


class TradeError(Exception):
    pass


def _kst() -> datetime:
    return datetime.now(_TZ[MARKET])


def _hm(now: datetime) -> int:
    return now.hour * 60 + now.minute


def configured() -> bool:
    return kis_order.creds() is not None


def clean_limits(raw: dict | None, base: dict | None = None) -> dict:
    raw, out = raw or {}, {}
    for k, (dflt, lo, hi) in LIMITS.items():
        v = raw.get(k, (base or {}).get(k, dflt))
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{LIMIT_LABELS[k]} 값이 숫자가 아님")
        if math.isnan(v) or not (lo <= v <= hi):
            raise ValueError(f"{LIMIT_LABELS[k]} 는 {lo:,}~{hi:,} 사이여야 함")
        out[k] = int(v) if isinstance(dflt, int) else round(v, 2)
    return out


def market_window(now: datetime | None = None) -> str:
    """closed(휴장·장 전·장 후) / open(주문 가능) / closing(마감 직전 — 새 주문 안 보냄)"""
    now = now or _kst()
    if not is_trading_day(MARKET, now.date()):
        return "closed"
    o, c = session_hours(MARKET, now.date())
    hm = _hm(now)
    if o + OPEN_AFTER <= hm < c - STOP_BEFORE_CLOSE:
        return "open"
    if c - STOP_BEFORE_CLOSE <= hm <= c:
        return "closing"
    return "closed"


def expiry_for(base_date: str) -> float:
    """판단 기준일 다음 거래일 장 마감 시각 (유닉스 초)"""
    d = next_trading_day(MARKET, date.fromisoformat(base_date))
    c = session_hours(MARKET, d)[1]
    return datetime(d.year, d.month, d.day, c // 60, c % 60, tzinfo=_TZ[MARKET]).timestamp()


def _limits(row: KisTrade) -> dict:
    """저장된 한도 + 새로 생긴 항목은 기본값 (업데이트 전 DB 에 없는 값)"""
    return clean_limits(json.loads(row.limits or "{}"))


def _stops_ok(row: KisTrade) -> bool:
    """정지 중에도 자동 손절은 하나 — 하루 손실 한도로 멈춘 경우만 (긴급 정지 버튼 = 모두 멈춤)"""
    return not row.halted or (row.halted_reason or "").startswith("하루 손실 한도")


# ---------------- 저장 ----------------

async def _row(db) -> KisTrade:
    row = await db.get(KisTrade, 1)
    if row is None:
        row = KisTrade(id=1, halted=False, limits=json.dumps(clean_limits({})),
                       params=json.dumps(pe.clean_params({}), ensure_ascii=False), state="{}")
        db.add(row)
        await db.flush()
    return row


def _state(row: KisTrade) -> dict:
    s = json.loads(row.state or "{}")
    s.setdefault("meta", {})      # 종목 → {name, entry_date, hold_days, peak, stop, target, avg}
    s.setdefault("log", [])
    s.setdefault("expected", None)   # 종목 → 앱 기록 보유 수량 (None = 아직 기준 없음)
    return s


def _save(row: KisTrade, s: dict):
    s["log"] = s["log"][-LOG_KEEP:]
    row.state = json.dumps(s, ensure_ascii=False)


async def audit(db, action: str, detail: str = "", user_id: int | None = None, order_id: int | None = None, ok: bool = True):
    db.add(KisLog(at=time.time(), user_id=user_id, action=action, order_id=order_id, ok=ok, detail=(detail or "")[:1000]))


def _today_start() -> float:
    n = _kst()
    return datetime(n.year, n.month, n.day, tzinfo=_TZ[MARKET]).timestamp()


# ---------------- 잔고 · 대조 · 손실 한도 ----------------

async def fetch_balance(max_age: float = 0) -> dict:
    """KIS 잔고 (max_age 초 안에 받은 게 있으면 그것)"""
    if max_age and _balance_cache["data"] and time.time() - _balance_cache["at"] < max_age:
        return _balance_cache["data"]
    try:
        b = await kis_order.balance()
    except Exception as e:
        _balance_cache["error"] = str(e)[:300]
        raise
    _balance_cache.update(at=time.time(), data=b, error=None)
    return b


def mismatches(s: dict, bal: dict) -> list:
    """앱 기록(앱이 체결시킨 수량) vs KIS 잔고 → 다른 종목 [{symbol, name, app, kis}]"""
    exp = s.get("expected")
    if exp is None:
        return []
    kis = {h["symbol"]: h for h in bal["holdings"]}
    out = []
    for sym in sorted(set(exp) | set(kis)):
        a, k = int(exp.get(sym, 0)), int(kis.get(sym, {}).get("qty", 0))
        if a != k:
            out.append({"symbol": sym, "name": (kis.get(sym) or {}).get("name") or (s["meta"].get(sym) or {}).get("name") or sym,
                        "app": a, "kis": k})
    return out


def _meta_for(h: dict, params: dict, day: str) -> dict:
    avg = float(h.get("avg") or h.get("price") or 0)
    return {"name": h["name"], "entry_date": day, "hold_days": 0, "peak": avg, "avg": avg,
            "stop": avg * (1 - params["stop_pct"] / 100), "target": avg * (1 + params["take_pct"] / 100)}


def baseline(s: dict, bal: dict, params: dict):
    """지금 KIS 잔고를 앱 기록 기준으로 (처음 연결 · '기준 다시 맞추기')"""
    day = _kst().date().isoformat()
    s["expected"] = {h["symbol"]: h["qty"] for h in bal["holdings"]}
    s["meta"] = {sym: m for sym, m in s["meta"].items() if sym in s["expected"]}
    for h in bal["holdings"]:
        s["meta"].setdefault(h["symbol"], _meta_for(h, params, day))


def day_loss(s: dict, bal: dict) -> float:
    """오늘 손실(원, 이익이면 음수) = 오늘 기준 총자산 − 지금 총자산. 기준 = KIS 전날 총자산, 없으면 오늘 처음 본 총자산"""
    today = _kst().date().isoformat()
    ds = s.get("day_start") or {}
    if ds.get("date") != today:
        ds = {"date": today, "total": bal["prev_total"] or bal["total"]}
        s["day_start"] = ds
    return float(ds["total"]) - float(bal["total"])


async def _halt(db, row: KisTrade, reason: str, user_id: int | None):
    if row.halted:
        return
    row.halted, row.halted_reason, row.halted_at = True, reason, time.time()
    n = (await db.execute(update(KisOrder).where(KisOrder.status.in_(("proposed", "approved")))
                          .values(status="cancelled", message=f"정지로 취소 — {reason}"))).rowcount
    await audit(db, "halt", f"{reason} (승인 대기·대기 주문 {n}건 취소)", user_id, ok=False)
    _alert_admins("[StockApp] KIS 모의투자 주문 정지", f"주문을 멈췄습니다: {reason}\n"
                  + ("손절가 자동 매도는 계속합니다.\n" if _stops_ok(row) else "")
                  + "다시 시작하려면 앱의 'KIS 모의투자 주문' 화면에서 2단계 코드로 다시 시작하세요.",
                  priority=5, tags=["rotating_light"])


async def check_loss(db, row: KisTrade, s: dict, bal: dict, limits: dict) -> float:
    loss = day_loss(s, bal)
    if loss >= limits["max_loss_krw"] and not row.halted:
        await _halt(db, row, f"하루 손실 한도 도달 — 오늘 {loss:,.0f}원 손실 (한도 {limits['max_loss_krw']:,}원)", None)
    return loss


# ---------------- 제안 ----------------

def _positions_for_decide(s: dict, bal: dict, params: dict) -> dict:
    day = _kst().date().isoformat()
    pos = {}
    for h in bal["holdings"]:
        m = s["meta"].get(h["symbol"]) or _meta_for(h, params, day)
        s["meta"][h["symbol"]] = m
        pos[h["symbol"]] = {**m, "name": h["name"] or m["name"], "qty": h["qty"], "avg": h["avg"] or m["avg"],
                            "last": h["price"] or m.get("peak", 0), "buy_fee": 0.0}
    return pos


async def propose(user_id: int | None = None) -> dict:
    """확정된 마지막 종가로 판단 → 매수·매도 제안 (이전 승인 대기 제안은 만료). user_id = 손으로 실행한 관리자"""
    from app.services import papertrade
    if not configured():
        raise TradeError("KIS 모의투자 키가 없음")
    async with _lock:
        async with AsyncSessionLocal() as db:
            row = await _row(db)
            if row.halted:
                raise TradeError(f"정지 중이라 제안을 만들지 않음 — {row.halted_reason}")
            params, s = json.loads(row.params), _state(row)
            owner = user_id or await _owner_id(db)
            try:
                bal = await fetch_balance()
                if s["expected"] is None:
                    baseline(s, bal, params)
                    await audit(db, "baseline", f"처음 연결 — KIS 잔고 {len(bal['holdings'])}종목을 앱 기록 기준으로")
                positions = _positions_for_decide(s, bal, params)
                a = await papertrade.analyze_live(MARKET, owner, positions, params)
                rows, last = a["rows"], a["last"]
                if s.get("last_close") != last:   # 종가 반영(하루 한 번): 보유일·최고가·추격 손절
                    closes = {sym: r["close"] for sym, r in rows.items() if sym in positions}
                    closes["__day__"] = last
                    pe.after_close({"positions": positions}, closes, params)
                    for sym, p in positions.items():
                        s["meta"][sym].update(hold_days=p["hold_days"], peak=p["peak"], stop=p["stop"])
                    s["last_close"] = last
                state = {"cash": float(max(0, bal["d2_cash"])), "positions": positions}
                orders, notes = pe.decide(state, rows, a["regime"], a["events"], params, MARKET)
            except Exception as e:
                why = str(e)[:300] or type(e).__name__
                row.last_error = f"{_kst().isoformat(timespec='seconds')} 제안 실패: {why}"
                await audit(db, "propose_fail", why, user_id, ok=False)
                await db.commit()
                raise
            now = time.time()
            old = (await db.execute(update(KisOrder).where(KisOrder.status == "proposed")
                                    .values(status="expired", message="새 제안으로 바뀜"))).rowcount
            exp = expiry_for(last)
            made = []
            for o in orders:
                r = rows.get(o["symbol"]) or {}
                k = KisOrder(created_at=now, base_date=last, source="ai", side=o["side"], symbol=o["symbol"], name=o["name"],
                             qty=int(o["qty"]) if o["side"] == "sell" else None, budget=o.get("budget"),
                             ref_price=r.get("close"), reason=o["reason"], score=o.get("score") or r.get("score"),
                             status="proposed", expires_at=exp)
                db.add(k)
                made.append(k)
            top = [{"symbol": sym, "name": r["name"], "score": r["score"], "prob": r["prob"]}
                   for sym, r in sorted(rows.items(), key=lambda kv: -kv[1]["score"])[:5]]
            s["log"].append({"ts": _kst().isoformat(timespec="seconds"), "base_date": last, "regime": a["regime"],
                             "events": a["events"], "manual": bool(user_id), "notes": notes
                             + ([pe.weights_text(a["aw"])] if params.get("adaptive") else [])
                             + ([f"일봉 못 받은 종목 {len(a['errors'])}개"] if a["errors"] else []),
                             "orders": [f"{'매수' if o['side'] == 'buy' else '매도'} {o['name']} — {o['reason']}" for o in orders],
                             "top": top, "universe": len(rows)})
            if not user_id:
                row.last_proposal_day = _kst().date().isoformat()
            row.last_error = None
            _save(row, s)
            await db.flush()
            await audit(db, "propose", f"기준일 {last} · 제안 {len(made)}건" + (f" · 예전 제안 {old}건 만료" if old else "")
                        + (" (손으로 실행)" if user_id else ""), user_id)
            await db.commit()
    if made:
        _alert_admins(f"[StockApp] AI 주문 제안 {len(made)}건 — 승인 대기",
                      "\n".join(f"- {'매수' if k.side == 'buy' else '매도'} {k.name}({k.symbol})"
                                + (f" {k.budget:,.0f}원어치" if k.side == "buy" and k.budget else f" {k.qty}주" if k.qty else "") for k in made)
                      + "\n\n앱의 'KIS 모의투자 주문' 화면에서 2단계 코드로 승인하세요. 승인하지 않으면 주문하지 않습니다. (다음 거래일 15:30 까지)",
                      priority=4, tags=["chart_with_upwards_trend"])
    return {"proposed": len(made), "base_date": last, "notes": notes}


# ---------------- 장중 가격 · 급변 판단 ----------------

async def _fetch_prices(symbols: list) -> dict:
    """종목 → (가격, 출처 'ws'|'rest'). KIS 실시간 체결가(10초 안 값) 우선, 없는 종목은 REST 멀티종목 시세(REST_EVERY 초마다).
    못 받은 종목은 빠짐 (가격을 지어내지 않음)"""
    from app.services import kis_ws
    from app.services.kis_api import kis_client
    kis_ws.want(symbols)
    out, missing = {}, []
    for sym in symbols:
        p = kis_ws.get(sym)
        if p and p.get("price"):
            out[sym] = (float(p["price"]), "ws")
        else:
            missing.append(sym)
    now = time.time()
    if missing and now - _rest["at"] >= REST_EVERY:
        _rest["at"] = now
        try:
            for i in range(0, len(missing), 30):
                for sym, r in (await kis_client.get_kr_multi_price(missing[i:i + 30])).items():
                    _rest["data"][sym] = (float(r["price"]), now)
            _rest["error"] = None
        except Exception as e:   # noqa: BLE001 — 다음 주기에 다시. 그동안 그 종목은 판단 안 함
            _rest["error"] = f"REST 시세 실패: {str(e)[:150]}"
    for sym in missing:
        v = _rest["data"].get(sym)
        if v and now - v[1] <= REST_EVERY * 3:
            out[sym] = (v[0], "rest")
    return out


def _record(prices: dict):
    now = time.time()
    for sym, px in prices.items():
        h = _hist.setdefault(sym, [])
        h.append((now, float(px)))
        while h and now - h[0][0] > DROP_WINDOW:
            h.pop(0)


def fast_drop(symbol: str, px: float) -> tuple | None:
    """최근 10분 최고가 대비 지금 가격 (등락률 %, 최고가). 기록이 없으면 None"""
    now = time.time()
    h = [p for t, p in _hist.get(symbol, []) if now - t <= DROP_WINDOW]
    if not h:
        return None
    hi = max(h + [px])
    return round((px / hi - 1) * 100, 6), hi


def shock_reason(k: KisOrder, px: float, limits: dict) -> str | None:
    """매수를 취소할 급변인가 → 이유 (아니면 None)"""
    if k.ref_price:
        gap = round((px / k.ref_price - 1) * 100, 6)   # (부동소수 오차로 딱 경계값이 넘친 것으로 보이지 않게)
        if gap < -2 * limits["max_gap_pct"]:
            return (f"제안 때 {k.ref_price:,.0f}원 → 지금 {px:,.0f}원 ({gap:.1f}%, 허용 −{2 * limits['max_gap_pct']:g}%) "
                    f"— 급락 (판단 때와 상황이 다름)")
    fd = fast_drop(k.symbol, px)
    if fd and fd[0] <= -limits["fast_drop_pct"]:
        return f"10분 안에 {fd[0]:.1f}% 급락 ({fd[1]:,.0f} → {px:,.0f}원, 기준 −{limits['fast_drop_pct']:g}%)"
    return None


async def _index_change() -> float | None:
    """코스피·코스닥 중 더 많이 빠진 쪽의 전일 대비 등락률(%) — INDEX_EVERY 초 캐시. 못 받으면 None"""
    from app.services.kis_api import kis_client
    now = time.time()
    if now - _index["at"] < INDEX_EVERY:
        return _index["change"]
    _index["at"] = now
    try:
        a, b = await kis_client.get_kr_index("0001"), await kis_client.get_kr_index("1001")
        _index.update(change=min(float(a["change_rate"]), float(b["change_rate"])), error=None)
    except Exception as e:   # noqa: BLE001 — 지수를 모르면 매수는 기다림 (이유를 화면에 표시)
        _index.update(change=None, error=str(e)[:200])
    return _index["change"]


def buy_wait_reason(k: KisOrder, px: float, limits: dict, idx_change: float | None, now: datetime | None = None) -> tuple | None:
    """승인한 매수를 지금은 안 보내고 기다릴 이유 → (종류, 문구). 다 괜찮으면 None"""
    now = now or _kst()
    o, _c = session_hours(MARKET, now.date())
    if _hm(now) < o + BUY_AFTER_OPEN:
        return "open", f"개장 {BUY_AFTER_OPEN}분 뒤부터 매수 (개장 직후엔 가격이 크게 출렁임)"
    if k.ref_price:
        gap = round((px / k.ref_price - 1) * 100, 6)
        if gap > limits["max_gap_pct"]:
            return "gap", (f"제안 때 {k.ref_price:,.0f}원 → 지금 {px:,.0f}원 (+{gap:.1f}%, 허용 +{limits['max_gap_pct']:g}%) "
                           f"— 비싸서 기다림 (쫓아가서 안 삼)")
    if idx_change is None:
        return "index", "코스피·코스닥 지수를 못 받아 기다림" + (f" ({_index['error'][:80]})" if _index.get("error") else "")
    if idx_change <= -limits["index_drop_pct"]:
        return "index", f"지수 {idx_change:.1f}% 하락 (기준 −{limits['index_drop_pct']:g}%) — 시장 전체가 빠져서 매수 보류"
    return None


async def _set_wait(order_id: int, kind: str, why: str):
    """조건 대기 이유를 주문에 적음 (승인 상태일 때만 — 그 사이 처리된 주문은 안 건드림). 감사 로그는 이유 종류가 바뀔 때만"""
    async with AsyncSessionLocal() as db:
        await db.execute(update(KisOrder).where(KisOrder.id == order_id, KisOrder.status == "approved").values(message=why))
        if _wait_kind.get(order_id) != kind:
            _wait_kind[order_id] = kind
            await audit(db, "wait", why, order_id=order_id)
        await db.commit()


async def _auto_cancel(db, k: KisOrder, why: str) -> dict:
    """(아직 KIS 로 안 나간) 매수를 급변으로 자동 취소 + 휴대폰 알림"""
    k.status, k.message = "cancelled", f"급변으로 자동 취소 — {why}"
    await audit(db, "auto_cancel", f"{k.name}: {why}", order_id=k.id, ok=False)
    await db.commit()
    _push(f"매수 자동 취소 — {k.name}", f"{k.name}({k.symbol}) 매수를 취소했습니다: {why}", 4, ["no_entry_sign"])
    return {"status": "cancelled", "message": k.message}


async def check_exits(prices: dict | None = None) -> int:
    """보유 종목 손절·목표 확인. 손절가 이하 → 승인 없이 바로 시장가 매도(자동 손절, 사용자 결정 2026-11-26),
    목표가 이상 → 매도 제안(승인해야 팔림). prices = 실시간 감시 가격 {종목: 가격} (없으면 KIS 잔고의 현재가 + 하루 손실 확인)"""
    stops, made = [], []
    async with _lock:
        async with AsyncSessionLocal() as db:
            row = await _row(db)
            s, limits = _state(row), _limits(row)
            if prices is None:
                bal = await fetch_balance()
                await check_loss(db, row, s, bal, limits)
                held = {h["symbol"]: (h["sellable"], h["name"], h["price"]) for h in bal["holdings"] if h["sellable"] >= 1 and h["price"]}
            else:
                held = {sym: (int(q), (s["meta"].get(sym) or {}).get("name") or sym, prices[sym])
                        for sym, q in (s["expected"] or {}).items() if int(q) > 0 and prices.get(sym)}
            today0, now = _today_start(), time.time()
            sells = (await db.execute(select(KisOrder).where(KisOrder.side == "sell", (
                KisOrder.status.in_(("proposed", "approved") + ACTIVE)) | (KisOrder.created_at >= today0)))).scalars().all()
            close_today = expiry_for((_kst().date() - timedelta(days=1)).isoformat())
            for sym, (qty, name, px) in held.items():
                m = s["meta"].get(sym)
                if not m:
                    continue
                mine = [o for o in sells if o.symbol == sym]
                if px <= m["stop"]:
                    if not _stops_ok(row):
                        continue
                    if any(o.status in ACTIVE or (o.status == "unknown" and o.created_at >= today0)
                           or (o.source == "stop" and o.status == "approved") for o in mine):
                        continue   # 이미 파는 중 / 결과 모름 (두 번 팔지 않음)
                    tries = [o.created_at for o in mine if o.source == "stop" and o.created_at >= today0]
                    if len(tries) >= STOP_TRIES or (tries and now - max(tries) < STOP_RETRY):
                        continue
                    k = KisOrder(created_at=now, base_date=_kst().date().isoformat(), source="stop", side="sell", symbol=sym,
                                 name=name, qty=qty, ref_price=px, status="approved", decided_at=now, expires_at=close_today,
                                 reason=f"손절가 도달 — 자동 매도 (장중 {px:,.0f}원 · 손절 {m['stop']:,.0f}원)")
                    db.add(k)
                    stops.append(k)
                elif px >= m["target"] and not row.halted:
                    if any(o.status in ("proposed", "approved") + ACTIVE or (o.source == "exit" and o.created_at >= today0) for o in mine):
                        continue   # 제안 중이거나 오늘 이미 제안함 (거절했으면 오늘은 다시 안 물음)
                    k = KisOrder(created_at=now, base_date=_kst().date().isoformat(), source="exit", side="sell", symbol=sym,
                                 name=name, qty=qty, ref_price=px, status="proposed", expires_at=close_today,
                                 reason=f"목표가 도달 (장중 {px:,.0f}원 · 목표 {m['target']:,.0f}원) — 승인하면 매도")
                    db.add(k)
                    made.append(k)
            if made or stops:
                await db.flush()
                for k in made:
                    await audit(db, "propose_exit", f"{k.name} {k.reason}", order_id=k.id)
                for k in stops:
                    await audit(db, "auto_stop", f"{k.name} {k.qty}주 {k.reason}", order_id=k.id)
            _save(row, s)
            await db.commit()
    if made:
        _alert_admins(f"[StockApp] 목표가 매도 제안 {len(made)}건",
                      "\n".join(f"- {k.name}: {k.reason}" for k in made) + "\n\n승인해야 매도합니다.", priority=4, tags=["dart"])
    for k in stops:
        r = await submit(k.id, auto=True)
        if r.get("status") == "submitted":   # 막힘·실패는 submit 이 따로 알림
            _push(f"자동 손절 매도 — {k.name}", f"{k.name}({k.symbol}) {k.qty}주 시장가 매도 주문: {k.reason}", 5, ["rotating_light"])
    return len(made) + len(stops)


# ---------------- 승인 · 거절 · 취소 ----------------

async def approve(ids: list, user_id: int) -> list:
    """승인 대기 → 승인 (한 번만). 장중이면 바로 주문. → [{id, status, message}]"""
    out = []
    async with AsyncSessionLocal() as db:
        row = await _row(db)
        if row.halted:
            raise TradeError(f"정지 중 — {row.halted_reason}. 다시 시작한 뒤 승인하세요")
        now = time.time()
        for i in ids:
            r = await db.execute(update(KisOrder).where(KisOrder.id == i, KisOrder.status == "proposed", KisOrder.expires_at > now)
                                 .values(status="approved", decided_by=user_id, decided_at=now))
            if r.rowcount != 1:
                out.append({"id": i, "status": None, "message": "승인할 수 없음 (이미 처리됐거나 기한 지남)"})
                continue
            k = await db.get(KisOrder, i)
            await audit(db, "approve", f"{'매수' if k.side == 'buy' else '매도'} {k.name}", user_id, i)
            out.append({"id": i, "status": "approved"})
        await db.commit()
    if market_window() == "open":
        for o in out:
            if o["status"] == "approved":
                o.update(await submit(o["id"]))
    return out


async def reject(ids: list, user_id: int) -> int:
    async with AsyncSessionLocal() as db:
        n = 0
        for i in ids:
            r = await db.execute(update(KisOrder).where(KisOrder.id == i, KisOrder.status.in_(("proposed", "approved")))
                                 .values(status="rejected", decided_by=user_id, decided_at=time.time()))
            if r.rowcount:
                n += 1
                await audit(db, "reject", "", user_id, i)
        await db.commit()
        return n


async def cancel_sent(order_id: int, user_id: int | None, why: str | None = None) -> str:
    """접수됐는데 아직 안 체결된 주문을 KIS 에서 취소. why = 자동 취소 이유 (사람이 누른 취소면 None).
    취소 전에 들어온 체결을 먼저 기록하고, 취소가 KIS 체결 내역에 반영되면 cancelled(일부 체결이면 partial)"""
    async with _lock:
        async with AsyncSessionLocal() as db:
            k = await db.get(KisOrder, order_id)
            if k is None:
                raise LookupError("없는 주문")
            if k.status != "submitted" or not k.odno:
                raise TradeError("접수된(안 체결) 주문만 취소할 수 있음")
            if k.cancel_req:
                return "이미 취소를 요청했습니다 — KIS 체결 내역에 반영되면 상태가 바뀝니다"
            row = await _row(db)
            s = _state(row)
            try:
                await _sync_fills(db, row, s)
            except Exception as e:   # noqa: BLE001 — 체결 확인이 안 돼도 취소는 시도 (다음 확인 때 맞춰짐)
                print(f"[kis_trade] 취소 전 체결 확인 실패: {str(e)[:150]}")
            if k.status != "submitted":
                await db.commit()
                return f"이미 {STATUS_LABELS.get(k.status, k.status)} — 취소할 것이 없음"
            try:
                r = await kis_order.cancel(k.odno, k.orgno or "")
            except Exception as e:
                await audit(db, "cancel_fail", (f"{why} · " if why else "") + str(e)[:300], user_id, order_id, ok=False)
                await db.commit()
                raise TradeError(f"KIS 취소 실패: {str(e)[:200]}")
            k.cancel_req = time.time()
            k.message = (f"{why} — " if why else "") + f"취소 요청 — {r['msg']}".strip(" —")
            await audit(db, "auto_cancel" if why else "cancel", (f"{k.name}: {why} · " if why else "") + r["msg"], user_id, order_id,
                        ok=not why)
            try:
                await _sync_fills(db, row, s)   # 취소가 바로 보이면 상태 확정
            except Exception as e:   # noqa: BLE001
                print(f"[kis_trade] 취소 후 체결 확인 실패: {str(e)[:150]}")
            await db.commit()
            return k.message


# ---------------- 주문 ----------------

async def _price_now(symbol: str, bal: dict) -> float:
    """매도 주문 직전 현재가 (잔고의 현재가 우선)"""
    from app.services.kis_api import kis_client
    for h in bal["holdings"]:
        if h["symbol"] == symbol and h["price"]:
            return float(h["price"])
    return float((await kis_client.get_kr_stock_price(symbol))["price"])


async def _quote(symbol: str) -> dict:
    """매수 주문 직전 현재가 + VI(변동성 완화장치)·거래 정지 여부 (KIS REST 현재가)"""
    from app.services.kis_api import kis_client
    q = await kis_client.get_kr_stock_price(symbol)
    return {"price": float(q["price"]), "vi": bool(q.get("vi")), "halted": bool(q.get("halted"))}


def _push(title: str, body: str, priority: int = 3, tags: list | None = None):
    """주문 결과는 휴대폰 푸시만 (메일까지 보내면 너무 많음). NTFY_TOPIC 없으면 아무것도 안 함"""
    from app.services import notify
    notify.send_bg(title, body, priority, tags)


async def _block(db, k: KisOrder, why: str) -> dict:
    k.status, k.message = "blocked", why
    await audit(db, "blocked", f"{k.name}: {why}", order_id=k.id, ok=False)
    await db.commit()
    _push(f"주문 안 보냄 — {k.name}", f"{'매수' if k.side == 'buy' else '매도'} {k.name}({k.symbol}) 안전장치로 막음: {why}", 4, ["no_entry"])
    return {"status": "blocked", "message": why}


async def _wait(db, k: KisOrder, kind: str, why: str) -> dict:
    """(_lock 안) 지금은 안 보내고 기다림 — 승인 상태 그대로, 이유만 적음"""
    k.message = why
    if _wait_kind.get(k.id) != kind:
        _wait_kind[k.id] = kind
        await audit(db, "wait", why, order_id=k.id)
    await db.commit()
    _next_try[k.id] = time.time() + WAIT_RETRY
    return {"status": "approved", "message": why, "wait": True}


async def submit(order_id: int, auto: bool = False) -> dict:
    """승인된 주문 1건을 안전장치 확인 후 KIS 모의투자로 보냄 → {status, message}. auto = 사람이 누르지 않고 감시가 보냄 (알림)"""
    async with _lock:
        async with AsyncSessionLocal() as db:
            k = await db.get(KisOrder, order_id)
            if k is None or k.status != "approved":
                return {"status": k.status if k else None, "message": "승인된 주문이 아님"}
            row = await _row(db)
            s, limits, params = _state(row), _limits(row), json.loads(row.params)
            stop = k.source == "stop"
            if row.halted and not (stop and _stops_ok(row)):
                return await _block(db, k, f"정지 중 — {row.halted_reason}")
            if k.expires_at <= time.time():
                k.status, k.message = "expired", "기한 지남 (다음 거래일 장 마감까지만 유효)"
                await db.commit()
                return {"status": "expired", "message": k.message}
            if market_window() != "open":
                return {"status": "approved", "message": "장이 열리면 조건을 확인해서 주문합니다"}
            if k.side == "buy":
                o = session_hours(MARKET, _kst().date())[0]
                if _hm(_kst()) < o + BUY_AFTER_OPEN:
                    return await _wait(db, k, "open", f"개장 {BUY_AFTER_OPEN}분 뒤부터 매수 (개장 직후엔 가격이 크게 출렁임)")
            sent_today = (await db.execute(select(sa_func.count()).select_from(KisOrder).where(
                KisOrder.status.in_(SENT), KisOrder.submitted_at >= _today_start()))).scalar() or 0
            if sent_today >= limits["max_orders_day"] and not stop:   # 자동 손절은 위험을 줄이는 주문이라 안 막음
                return await _block(db, k, f"오늘 주문 {sent_today}건 — 하루 주문 횟수 한도({limits['max_orders_day']}건)")
            if stop:   # 이미 파는 중이거나 결과 모름인 매도만 막음
                dup = (await db.execute(select(KisOrder.id).where(KisOrder.id != k.id, KisOrder.symbol == k.symbol, KisOrder.side == "sell", (
                    KisOrder.status.in_(ACTIVE)) | ((KisOrder.status == "unknown") & (KisOrder.created_at >= _today_start()))))).first()
            else:
                dup = (await db.execute(select(KisOrder.id).where(KisOrder.id != k.id, KisOrder.symbol == k.symbol, (
                    KisOrder.status.in_(ACTIVE)) | ((KisOrder.side == k.side) & KisOrder.status.in_(("filled", "partial", "unknown"))
                                                    & (KisOrder.submitted_at >= _today_start()))))).first()
            if dup:
                return await _block(db, k, "같은 종목 주문이 이미 접수·체결됐거나 결과를 모름 (두 번 주문 방지 — 결과 모름이면 KIS 앱에서 확인)")
            try:
                bal = await fetch_balance()
            except Exception as e:
                return await _block(db, k, f"KIS 잔고를 못 받아 확인 불가 — {str(e)[:150]}")
            loss = await check_loss(db, row, s, bal, limits)
            _save(row, s)
            if row.halted and not (stop and _stops_ok(row)):
                await db.commit()
                return await _block(db, k, row.halted_reason)
            if s["expected"] is None:
                baseline(s, bal, params)
                _save(row, s)
            limit_px = None
            if k.side == "buy":
                try:
                    q = await _quote(k.symbol)
                except Exception as e:   # noqa: BLE001 — 잠깐 못 받은 것: 기다렸다가 다시
                    return await _wait(db, k, "price", f"현재가를 못 받아 기다림 — {str(e)[:150]}")
                px = q["price"]
                if px <= 0:
                    return await _wait(db, k, "price", "현재가 0 (거래 정지 종목?) — 기다림")
                if await _sync_fills(db, row, s):   # 앞 주문의 체결을 먼저 기록에 반영 (반영 전이면 잔고와 달라 보임)
                    bal = await fetch_balance()
                mm = mismatches(s, bal)
                if mm:
                    return await _block(db, k, "KIS 잔고와 앱 기록이 다름 — " + ", ".join(
                        f"{m['name']} 앱 {m['app']}주/KIS {m['kis']}주" for m in mm[:3]) + " ('기준 다시 맞추기' 후 다시)")
                why = shock_reason(k, px, limits)
                if why:
                    return await _auto_cancel(db, k, why)
                if q["halted"]:
                    return await _wait(db, k, "halted", "거래 정지 중 — 풀리면 다시 확인")
                if q["vi"]:
                    return await _wait(db, k, "vi", "변동성 완화장치(VI) 발동 중 — 가격이 급하게 움직여 잠깐 단일가 매매, 풀리면 다시 확인")
                w = buy_wait_reason(k, px, limits, await _index_change())
                if w:
                    return await _wait(db, k, *w)
                limit_px = kis_order.tick_up(px * (1 + limits["limit_slip_pct"] / 100))
                money = min(float(k.budget or 0), float(limits["max_order_krw"]), float(max(0, bal["d2_cash"])))
                qty = math.floor(money / (limit_px * 1.001))   # 수수료 여유
                if qty < 1:
                    return await _block(db, k, f"살 수 있는 돈 {money:,.0f}원으로 1주(지정가 {limit_px:,.0f}원)도 못 삼")
            else:
                try:
                    px = await _price_now(k.symbol, bal)
                except Exception as e:
                    return await _block(db, k, f"현재가를 못 받음 — {str(e)[:150]}")
                h = next((h for h in bal["holdings"] if h["symbol"] == k.symbol), None)
                qty = min(int(k.qty or 0), int(h["sellable"]) if h else 0)
                if qty < 1:
                    return await _block(db, k, "팔 수 있는 수량이 없음 (KIS 잔고 기준)")
            # 보내기 전에 '보내는 중'으로 저장 — 응답 전에 서버가 꺼져도 다시 보내지 않음 (결과 모름으로 표시)
            k.status, k.qty, k.order_price, k.limit_price, k.submitted_at = "submitting", qty, px, limit_px, time.time()
            how = f"지정가 {limit_px:,.0f}원" if limit_px else "시장가"
            await audit(db, "submit", f"{'매수' if k.side == 'buy' else '매도'} {k.name} {qty}주 {how} (현재가 {px:,.0f}원 · 오늘 손익 {(-loss or 0.0):+,.0f}원)"
                        + (" — 자동 손절" if stop else " — 조건 충족" if auto else ""), order_id=k.id)
            await db.commit()
            try:
                r = await kis_order.order(k.side, k.symbol, qty, limit_px)
            except KISConnectionError as e:
                if e.maybe_sent:   # 요청은 갔는데 답을 못 받음 → 들어갔을 수 있음. 다시 보내지 않고 사람이 확인
                    k.status, k.message = "unknown", f"주문을 보냈는데 KIS 응답을 못 받음 — KIS 앱에서 체결 여부를 확인하세요 ({str(e)[:200]})"
                    await audit(db, "submit_unknown", k.message, order_id=k.id, ok=False)
                    await db.commit()
                    _push(f"주문 결과 확인 필요 — {k.name}", f"{k.name}({k.symbol}) {qty}주: {k.message}", 5, ["warning"])
                    return {"status": "unknown", "message": k.message}
                k.status, k.message = "failed", f"KIS 연결 실패 — 주문은 안 들어감: {str(e)[:200]}"
                await audit(db, "submit_fail", k.message, order_id=k.id, ok=False)
                await db.commit()
                _push(f"KIS 주문 못 보냄 — {k.name}", f"{k.name}({k.symbol}): {k.message}", 4, ["x"])
                return {"status": "failed", "message": k.message}
            except Exception as e:
                k.status, k.message = "failed", f"KIS 주문 거부: {str(e)[:250]}"
                await audit(db, "submit_fail", k.message, order_id=k.id, ok=False)
                await db.commit()
                _push(f"KIS 주문 거부 — {k.name}", f"{'매수' if k.side == 'buy' else '매도'} {k.name}({k.symbol}) {qty}주: {k.message}", 4, ["x"])
                return {"status": "failed", "message": k.message}
            _balance_cache["data"] = None   # 잔고가 바뀜 — 화면이 예전 잔고로 '대조 다름'을 띄우지 않게
            _wait_kind.pop(k.id, None)
            _next_try.pop(k.id, None)
            k.status, k.odno, k.orgno = "submitted", r["odno"], r["orgno"]
            k.message = f"주문번호 {r['odno']} · {how}" + (f" — {r['msg']}" if r["msg"] else "")
            await audit(db, "submitted", k.message, order_id=k.id)
            await db.commit()
            if auto and k.side == "buy":
                _push(f"매수 주문 — {k.name}", f"{k.name}({k.symbol}) {qty}주 {how} (현재가 {px:,.0f}원) — 승인한 조건이 맞아 주문했습니다", 3,
                      ["shopping_cart"])
            return {"status": "submitted", "message": k.message}


async def submit_approved() -> int:
    """승인된 주문을 보냄 (매도 먼저 — 판 돈으로 삼). 기다리는 중인 매수는 WAIT_RETRY 초가 지난 것만"""
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(select(KisOrder.id).where(KisOrder.status == "approved").order_by(
            (KisOrder.side == "buy"), KisOrder.id))).scalars().all()
    n = 0
    for i in ids:
        if _next_try.get(i, 0) > time.time():
            continue
        r = await submit(i, auto=True)
        n += r.get("status") == "submitted"
    return n


# ---------------- 체결 반영 ----------------

def _apply_fill(s: dict, k: KisOrder, delta: int, price: float, params: dict):
    exp = s["expected"] if s["expected"] is not None else {}
    cur = int(exp.get(k.symbol, 0))
    if k.side == "buy":
        exp[k.symbol] = cur + delta
        m = s["meta"].get(k.symbol)
        if not m or cur == 0:
            s["meta"][k.symbol] = {"name": k.name, "entry_date": _kst().date().isoformat(), "hold_days": 0, "peak": price,
                                   "avg": price, "stop": price * (1 - params["stop_pct"] / 100),
                                   "target": price * (1 + params["take_pct"] / 100)}
    else:
        left = max(0, cur - delta)
        if left:
            exp[k.symbol] = left
        else:
            exp.pop(k.symbol, None)
            s["meta"].pop(k.symbol, None)
    s["expected"] = exp


async def refresh_fills(final: bool = False) -> int:
    """오늘 접수한 주문을 KIS 체결 내역과 맞춤. final = 장 마감 뒤 (안 체결 확정)"""
    async with _lock:
        async with AsyncSessionLocal() as db:
            row = await _row(db)
            s = _state(row)
            changed = await _sync_fills(db, row, s, final)
            await db.commit()
            return changed


async def _sync_fills(db, row, s: dict, final: bool = False, apply: bool = True) -> int:
    """(_lock 안에서) 오늘 접수한 주문의 새 체결을 앱 기록(expected)에 더하고 s 를 row 에 저장 (commit 은 부르는 쪽).
    apply=False = 기록에 더하지 않고 '이미 반영됨'으로만 표시 — 기준 다시 맞추기 때 (KIS 잔고에 이미 들어간 체결을 나중에 또 더하지 않게)"""
    ks = (await db.execute(select(KisOrder).where(KisOrder.status == "submitted",
                                                  KisOrder.submitted_at >= _today_start()))).scalars().all()
    if not ks:
        return 0
    ex = {e["odno"]: e for e in await kis_order.executions(_kst().date())}
    params = json.loads(row.params)
    if s["expected"] is None:
        s["expected"] = {}
    changed = 0
    for k in ks:
        e = ex.get(k.odno)
        if e is None:
            if final:
                k.status, k.message = "unknown", "KIS 체결 내역에 이 주문번호가 없음 — KIS 앱에서 확인"
                await audit(db, "fill_unknown", k.message, order_id=k.id, ok=False)
                _push(f"주문 결과 확인 필요 — {k.name}", f"{k.name}({k.symbol}): {k.message}", 4, ["warning"])
                changed += 1
            continue
        delta = int(e["filled"]) - int(k.filled_qty or 0)
        if delta > 0:
            if apply:
                _apply_fill(s, k, delta, float(e["avg_price"] or k.order_price or 0), params)
            k.filled_qty, k.filled_price = int(e["filled"]), float(e["avg_price"] or 0) or None
            changed += 1
        if k.filled_qty >= (k.qty or 0) and k.filled_qty > 0:
            k.status = "filled"
            await audit(db, "filled", f"{k.name} {k.filled_qty}주 평균 {k.filled_price or 0:,.0f}원", order_id=k.id)
            _push(f"체결 — {'매수' if k.side == 'buy' else '매도'} {k.name}", f"{k.name}({k.symbol}) {k.filled_qty}주 · 평균 {k.filled_price or 0:,.0f}원 (모의투자)",
                  3, ["white_check_mark"])
        elif (e["cancelled"] or (final and e["remain"] >= 0)
              or (k.cancel_req and (e["remain"] <= 0 or int(e.get("cancel_qty") or 0) > 0))):
            gone = e["cancelled"] or k.cancel_req
            k.status = "partial" if k.filled_qty else "cancelled" if gone else "unfilled"
            await audit(db, k.status, f"{k.name} {k.filled_qty}/{k.qty}주" + (" (취소 확인)" if gone else ""), order_id=k.id,
                        ok=bool(k.filled_qty))
            changed += 1
    _save(row, s)
    if changed:
        _balance_cache["data"] = None
    return changed


# ---------------- 정지 · 다시 시작 · 기준 · 설정 ----------------

async def halt(user_id: int, reason: str = "") -> dict:
    """긴급 정지 — 2단계 코드 없이 바로 (급할 때). 승인 대기·대기 주문 취소 + 접수된(안 체결) 주문 KIS 취소 시도"""
    async with AsyncSessionLocal() as db:
        row = await _row(db)
        await _halt(db, row, f"긴급 정지 버튼{(' — ' + reason.strip()[:100]) if reason.strip() else ''}", user_id)
        await db.commit()
        sent = (await db.execute(select(KisOrder.id).where(KisOrder.status == "submitted"))).scalars().all()
    cancelled, failed = 0, []
    for i in sent:
        try:
            await cancel_sent(i, user_id)
            cancelled += 1
        except Exception as e:
            failed.append(str(e)[:100])
    msg = "주문을 멈췄습니다" + (f" · 접수된 주문 {cancelled}건 취소 요청" if cancelled else "") + (
        f" · 취소 못 한 주문 {len(failed)}건 — KIS 앱에서 확인하세요" if failed else "")
    return {"message": msg}


async def resume(user_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        row = await _row(db)
        if not row.halted:
            return {"message": "정지 상태가 아닙니다"}
        row.halted, row.halted_reason, row.halted_at = False, None, None
        await audit(db, "resume", "", user_id)
        await db.commit()
    return {"message": "다시 시작했습니다 — 하루 손실 한도를 넘은 상태면 다음 확인 때 다시 멈춥니다"}


async def rebaseline(user_id: int) -> dict:
    async with _lock:
        async with AsyncSessionLocal() as db:
            row = await _row(db)
            s = _state(row)
            # 체결 중인 주문: KIS 잔고에 이미 들어간 체결은 '반영됨'으로 표시 (안 하면 다음 체결 확인 때 한 번 더 더해져 앱 기록이 KIS 보다 많아짐)
            await _sync_fills(db, row, s, apply=False)
            bal = await fetch_balance()
            before = mismatches(s, bal)
            baseline(s, bal, json.loads(row.params))
            _save(row, s)
            await audit(db, "baseline", "기준 다시 맞추기 — " + (", ".join(f"{m['name']} {m['app']}→{m['kis']}주" for m in before) or "차이 없음"), user_id)
            await db.commit()
    return {"message": "KIS 잔고를 앱 기록 기준으로 맞췄습니다"}


async def set_config(user_id: int, limits: dict | None, params: dict | None) -> dict:
    async with AsyncSessionLocal() as db:
        row = await _row(db)
        old_l, old_p = _limits(row), json.loads(row.params)
        new_l = clean_limits(limits, old_l) if limits is not None else old_l
        new_p = pe.clean_params({**old_p, **params}) if params is not None else old_p
        row.limits, row.params = json.dumps(new_l), json.dumps(new_p, ensure_ascii=False)
        diff = [f"{LIMIT_LABELS.get(k) or pe.PARAM_LABELS.get(k, k)} {old.get(k)}→{v}"
                for old, new in ((old_l, new_l), (old_p, new_p)) for k, v in new.items() if old.get(k) != v]
        await audit(db, "config", ", ".join(diff) or "변경 없음", user_id)
        await db.commit()
    return {"limits": new_l, "params": new_p, "message": "설정을 저장했습니다"}


# ---------------- 화면 ----------------

def order_row(k: KisOrder) -> dict:
    return {"id": k.id, "created_at": k.created_at, "base_date": k.base_date, "source": k.source, "side": k.side,
            "symbol": k.symbol, "name": k.name, "qty": k.qty, "budget": k.budget, "ref_price": k.ref_price,
            "reason": k.reason, "score": k.score, "status": k.status, "status_label": STATUS_LABELS.get(k.status, k.status),
            "expires_at": k.expires_at, "decided_at": k.decided_at, "submitted_at": k.submitted_at,
            "order_price": k.order_price, "limit_price": k.limit_price, "cancel_req": k.cancel_req, "odno": k.odno,
            "filled_qty": k.filled_qty, "filled_price": k.filled_price, "message": k.message}


async def overview(with_balance: bool = True) -> dict:
    if with_balance and configured():
        try:   # 체결된 주문을 먼저 앱 기록에 반영 — 반영 전이면 잔고와 달라 보여 '기준 다시 맞추기'를 누르게 됨
            await refresh_fills()
        except Exception as e:   # noqa: BLE001 — 잔고 칸이 오류를 따로 보여줌
            print(f"[kis_trade] 화면용 체결 확인 실패: {str(e)[:150]}")
    async with AsyncSessionLocal() as db:
        row = await _row(db)
        await db.commit()
        s, limits = _state(row), _limits(row)
        sent_today = (await db.execute(select(sa_func.count()).select_from(KisOrder).where(
            KisOrder.status.in_(SENT), KisOrder.submitted_at >= _today_start()))).scalar() or 0
        out = {
            "configured": configured(), "server": "모의투자 (가상 자금)", "account": kis_order.masked_account(),
            "account_source": kis_order.account_source(),
            "notify": __import__("app.services.notify", fromlist=["status"]).status(),
            "halted": bool(row.halted), "halted_reason": row.halted_reason, "halted_at": row.halted_at,
            "limits": limits, "limit_meta": {k: {"default": d, "min": lo, "max": hi, "label": LIMIT_LABELS[k]}
                                             for k, (d, lo, hi) in LIMITS.items()},
            "params": json.loads(row.params), "orders_today": int(sent_today), "window": market_window(),
            "last_proposal_day": row.last_proposal_day, "last_error": row.last_error, "loop": dict(_status),
            "watch": {**_watch, "every": WATCH_EVERY, "index_change": _index["change"], "index_error": _index["error"],
                      "buy_after_open": BUY_AFTER_OPEN, "stops_ok": _stops_ok(row)},
            "baseline": s["expected"] is not None, "log": list(reversed(s["log"][-10:])),
            "balance": None, "balance_error": None, "mismatches": [], "day_loss": None,
        }
        if with_balance and out["configured"]:
            try:
                bal = await fetch_balance(max_age=20)
                out["balance"] = bal
                if row.last_error and "INVALID_CHECK_ACNO" in row.last_error:
                    # 계좌번호 오류로 제안이 실패했었는데 이제 잔고가 받아짐 (.env 를 고치고 다시 켬)
                    # → 지난 오류는 지우고, 오늘 자동 제안을 다시 하게 (장 마감 15분 뒤면 1분 안에)
                    async with AsyncSessionLocal() as db2:
                        r2 = await _row(db2)
                        r2.last_error = None
                        if r2.last_proposal_day == _kst().date().isoformat():
                            r2.last_proposal_day = None
                        await audit(db2, "account_ok", "계좌 확인됨 — 계좌번호 오류로 실패한 제안을 다시 합니다")
                        await db2.commit()
                        out["last_error"], out["last_proposal_day"] = None, r2.last_proposal_day
                mm = mismatches(s, bal)
                if mm:   # 아직 체결 중인 주문이 있는 종목 = 곧 맞춰짐 (기준 맞추기 필요 없음)
                    async with AsyncSessionLocal() as db3:
                        busy = set((await db3.execute(select(KisOrder.symbol).where(
                            KisOrder.status.in_(("submitting", "submitted")), KisOrder.submitted_at >= _today_start()))).scalars().all())
                    for m in mm:
                        m["pending"] = m["symbol"] in busy
                out["mismatches"] = mm
                out["day_loss"] = day_loss(s, bal)
                meta = s["meta"]
                for h in bal["holdings"]:
                    m = meta.get(h["symbol"]) or {}
                    h["stop"], h["target"], h["hold_days"] = m.get("stop"), m.get("target"), m.get("hold_days")
            except Exception as e:
                out["balance_error"] = str(e)[:700]
        return out


async def list_orders(kind: str = "open", limit: int = 100) -> list:
    async with AsyncSessionLocal() as db:
        q = select(KisOrder)
        if kind == "open":
            q = q.where(KisOrder.status.in_(("proposed", "approved") + ACTIVE))
        rows = (await db.execute(q.order_by(KisOrder.id.desc()).limit(max(1, min(limit, 300))))).scalars().all()
        return [order_row(k) for k in rows]


async def list_log(limit: int = 100) -> list:
    from app.models.user import User
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(KisLog).order_by(KisLog.id.desc()).limit(max(1, min(limit, 500))))).scalars().all()
        ids = {r.user_id for r in rows if r.user_id}
        names = dict((await db.execute(select(User.id, User.username).where(User.id.in_(ids)))).all()) if ids else {}
        return [{"id": r.id, "at": r.at, "action": r.action, "order_id": r.order_id, "ok": bool(r.ok), "detail": r.detail,
                 "by": names.get(r.user_id) if r.user_id else "자동"} for r in rows]


# ---------------- 알림 · 자동 운영 ----------------

async def _owner_id(db) -> int:
    from app.models.user import User
    uid = (await db.execute(select(User.id).where(User.is_admin.is_(True)).order_by(User.id).limit(1))).scalar()
    return uid or 0


def _alert_admins(subject: str, body: str, priority: int = 3, tags: list | None = None):
    """관리자 알림 — 휴대폰 푸시(ntfy, NTFY_TOPIC 있을 때) + 인증된 이메일(메일 설정 있을 때). 뒤에서 보냄, 실패해도 주문 흐름은 그대로"""
    from app.services import mailer, notify
    from app.models.user import User
    notify.send_bg(subject.replace("[StockApp] ", ""), body, priority, tags)
    if not mailer.configured():
        return

    async def go():
        try:
            async with AsyncSessionLocal() as db:
                to = (await db.execute(select(User.email).where(User.is_admin.is_(True), User.is_active.isnot(False),
                                                                User.email_verified.is_(True)))).scalars().all()
            for t in to:
                if t:
                    await mailer.send(t, subject, body)
        except Exception as e:   # noqa: BLE001
            print(f"[kis] 알림 메일 실패: {type(e).__name__}: {str(e)[:100]}")
    try:
        asyncio.get_running_loop().create_task(go())
    except RuntimeError:
        pass


async def expire_old() -> int:
    async with AsyncSessionLocal() as db:
        n = (await db.execute(update(KisOrder).where(KisOrder.status.in_(("proposed", "approved")), KisOrder.expires_at <= time.time())
                              .values(status="expired", message="기한 지남 (다음 거래일 장 마감까지만 유효)"))).rowcount
        if n:
            await audit(db, "expire", f"{n}건 기한 지남")
        await db.commit()
        return n


async def mark_interrupted():
    """서버가 주문 보내는 도중 꺼졌으면 그 주문은 '결과 모름' (다시 보내지 않음)"""
    async with AsyncSessionLocal() as db:
        n = (await db.execute(update(KisOrder).where(KisOrder.status == "submitting")
                              .values(status="unknown", message="주문을 보내던 중 서버가 꺼짐 — KIS 앱에서 체결 여부를 확인하세요"))).rowcount
        if n:
            await audit(db, "interrupted", f"보내던 주문 {n}건 결과 모름", ok=False)
        await db.commit()


def _propose_failed_at(last_error: str | None, today: date) -> float | None:
    """오늘 자동 제안이 실패했으면 그 시각 (last_error = 'ISO시각 제안 실패: ...')"""
    if not last_error or "제안 실패" not in last_error:
        return None
    try:
        t = datetime.fromisoformat(last_error.split(" ", 1)[0])
    except ValueError:
        return None
    return t.timestamp() if t.date() == today else None


async def watch() -> dict:
    """장중 실시간 감시 (WATCH_EVERY 초마다): ① 손절가 → 자동 매도 / 목표가 → 매도 제안 ② 급변 → 매수 자동 취소
    ③ 승인한 매수 중 조건이 맞는 것 → 지정가 주문. 가격을 못 받은 종목은 이번엔 판단하지 않음"""
    if not configured() or market_window() != "open":
        return {}
    async with AsyncSessionLocal() as db:
        row = await _row(db)
        await db.commit()
        s, limits, halted = _state(row), _limits(row), bool(row.halted)
        buys = (await db.execute(select(KisOrder).where(KisOrder.side == "buy", KisOrder.status.in_(
            ("proposed", "approved", "submitted"))))).scalars().all()
    held = [sym for sym, q in (s["expected"] or {}).items() if int(q) > 0]
    syms = sorted(set(held) | {k.symbol for k in buys})
    _watch.update(last=_kst().isoformat(timespec="seconds"), symbols=len(syms))
    if not syms:
        _watch.update(realtime=0, rest=0, missing=0, error=None)
        return {"symbols": 0}
    raw = await _fetch_prices(syms)
    prices = {sym: p for sym, (p, _src) in raw.items()}
    _record(prices)
    miss = len(syms) - len(raw)
    _watch.update(realtime=sum(1 for _p, src in raw.values() if src == "ws"), rest=sum(1 for _p, src in raw.values() if src == "rest"),
                  missing=miss, error=_rest["error"] if miss else None)
    done = {"stops": 0, "cancelled": 0, "sent": 0}
    # ① 손절·목표
    hp = {sym: prices[sym] for sym in held if sym in prices}
    if hp:
        done["stops"] = await check_exits(hp)
    # ② 급변 → 매수 자동 취소 (정지 중이면 접수된 매수도 취소)
    for k in buys:
        px = prices.get(k.symbol)
        if k.status == "submitted":
            if k.cancel_req:
                continue
            why = f"주문 정지 중 ({row.halted_reason})" if halted else shock_reason(k, px, limits) if px else None
            if not why:
                continue
            try:
                await cancel_sent(k.id, None, why=f"자동 취소 — {why}")
                done["cancelled"] += 1
                _push(f"매수 자동 취소 — {k.name}", f"{k.name}({k.symbol}) 접수된 매수 주문을 KIS 에서 취소했습니다: {why}", 4, ["no_entry_sign"])
            except Exception as e:   # noqa: BLE001
                _push(f"자동 취소 실패 — {k.name}", f"{k.name}({k.symbol}) 매수 주문 취소 실패 — KIS 앱에서 확인하세요: {str(e)[:150]}", 5, ["warning"])
        elif px:
            why = shock_reason(k, px, limits)
            if why:
                async with _lock:
                    async with AsyncSessionLocal() as db:
                        k2 = await db.get(KisOrder, k.id)
                        if k2 and k2.status in ("proposed", "approved"):
                            await _auto_cancel(db, k2, why)
                            done["cancelled"] += 1
    # ③ 승인한 주문 보내기 (매도 먼저). 매수는 가볍게 먼저 확인하고 맞을 때만 submit (submit 이 KIS 로 한 번 더 확인)
    if not halted:
        async with AsyncSessionLocal() as db:
            ready = (await db.execute(select(KisOrder).where(KisOrder.status == "approved").order_by(
                (KisOrder.side == "buy"), KisOrder.id))).scalars().all()
        idx = await _index_change() if any(k.side == "buy" for k in ready) else None
        for k in ready:
            if _next_try.get(k.id, 0) > time.time():
                continue
            if k.side == "buy":
                px = prices.get(k.symbol)
                if px is None:
                    continue
                w = buy_wait_reason(k, px, limits, idx)
                if w:
                    await _set_wait(k.id, *w)
                    continue
            r = await submit(k.id, auto=True)
            done["sent"] += r.get("status") == "submitted"
    return done


async def tick():
    global _last_exit
    if not configured():
        return
    await expire_old()
    now = _kst()
    if not is_trading_day(MARKET, now.date()):
        return
    o, c = session_hours(MARKET, now.date())
    hm, w = _hm(now), market_window(now)
    async with AsyncSessionLocal() as db:
        row = await _row(db)
        await db.commit()
        halted, last_day, last_err = row.halted, row.last_proposal_day, row.last_error
    if w == "open":
        if not halted:
            await submit_approved()
        await refresh_fills()
        if time.time() - _last_exit >= EXIT_EVERY:
            _last_exit = time.time()
            await check_exits()
    elif w == "closing":
        await refresh_fills()
    elif hm >= c + PROPOSE_AFTER:
        await refresh_fills(final=True)
        failed_at = _propose_failed_at(last_err, now.date())
        retry = failed_at is not None and time.time() - failed_at >= PROPOSE_RETRY
        if not halted and (last_day != now.date().isoformat() or retry):
            try:
                await propose()
            except Exception:
                async with AsyncSessionLocal() as db:   # 실패해도 매분 다시 하지 않게 — 30분 뒤 다시 (또는 손으로 '지금 제안 만들기')
                    row = await _row(db)
                    row.last_proposal_day = now.date().isoformat()
                    await db.commit()
                raise


async def loop():
    from app.services.kis_api import mark_background
    mark_background()
    try:
        await mark_interrupted()
    except Exception as e:
        print(f"[kis] 시작 정리 실패: {e}")
    await asyncio.sleep(20)
    last_tick = 0.0
    while True:
        if _mono() - last_tick >= 60:   # 1분마다: 기한·체결 확인·손실 한도·장 마감 후 제안
            last_tick = _mono()
            try:
                await tick()
                _status["last_tick"] = datetime.now().isoformat(timespec="seconds")
            except Exception as e:
                _status["last_error"] = f"{datetime.now().isoformat(timespec='seconds')} {str(e)[:200]}"
                print(f"[kis] 자동 운영 실패: {e}")
        try:   # 5초마다: 장중 실시간 감시
            await watch()
        except Exception as e:   # noqa: BLE001
            _watch["error"] = f"{datetime.now().isoformat(timespec='seconds')} {str(e)[:200]}"
            print(f"[kis] 실시간 감시 실패: {e}")
        await asyncio.sleep(WATCH_EVERY)


def _mono() -> float:
    import time as _t
    return _t.monotonic()
