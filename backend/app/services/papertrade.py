"""AI 모의투자 — 데이터 받기 · 과거 시뮬레이션 실행 · 실시간 모의투자 계좌 운영 (계산은 paper_engine)

과거 시뮬레이션
  - 기간(1~24개월)·시작 자금·매매 규칙을 받아 백그라운드로 계산 → paper_sim 테이블에 결과 저장
  - 대상 종목: AI 추천 후보 목록(고정) — 지금 점수가 높은 종목을 고르면 '미래를 보고 고른 것'이 되므로
    퀀트·매집 상위 종목은 과거 시뮬레이션 대상에 넣지 않음. (현재 상장 종목이라 상장폐지 종목은 빠지는 한계는 있음)
  - 데이터: 국내 KIS 일봉 / 미국·지수 yfinance / 미국 주요 발표 일정(FRED·연준, 일정은 미리 공개되는 정보)
실시간 모의투자
  - 계좌를 만들면 바로 최근 종가 기준으로 판단 → 장중이면 그 자리에서 현재가로 체결, 아니면 다음 개장 직후 체결
  - 매 거래일 장 마감 15분 뒤(국내 15:45 · 미국 16:15 ET) 판단 → 대기 주문 → 다음 개장 1분 뒤 현재가로 체결
  - 장중 5분마다 손절가·목표가 확인 → 닿으면 그 현재가로 바로 매도
  - 실시간은 과거 시뮬레이션과 같은 판단 함수에 AI 추천 확률(학습 모델 포함)과 국내 전 종목 퀀트·매집 결과를 넣음
  - 대상 종목: AI 추천 후보 + 내 관심·투자종목 + (국내) 전 종목 퀀트·매집 상위 + 보유 종목
"""
import asyncio
import json
import time
from datetime import date, datetime, timedelta

from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.models.paper import PaperSim, PaperAccount, PaperTrade, PaperEquity
from app.models.watchlist import WatchlistItem
from app.models.portfolio import PortfolioItem
from app.services import paper_engine as pe
from app.services import stock_master
from app.services.kis_api import kis_client, KISRateLimitError
from app.services.market_calendar import (_TZ, is_trading_day, is_market_open, market_today, next_trading_day,
                                          session_hours, last_session_date)

INDEX = {"KR": ("^KS11", "코스피"), "US": ("^GSPC", "S&P 500")}
MONTHS = (1, 3, 6, 12, 24)
MAX_ACCOUNTS = 5
LOG_KEEP = 60
DECIDE_AFTER_CLOSE = 15     # 장 마감 몇 분 뒤 판단 (종가 확정 대기)
FILL_AFTER_OPEN = 1         # 개장 몇 분 뒤 대기 주문 체결
EXIT_CHECK_EVERY = 300      # 장중 손절·목표 확인 주기 (초)

_sim_lock = asyncio.Lock()
_sim_progress: dict = {}    # sim_id → {"phase", "done", "total"}
_acct_locks: dict = {}
_last_exit_check: dict = {}
_decide_failed: dict = {}   # 계좌 → 장 마감 후 자동 판단 실패 시각 (30분 뒤 다시 — 매분 KIS 호출 반복 방지)
DECIDE_RETRY = 1800
_loop_status: dict = {"last_tick": None, "last_error": None}


def _lock(acc_id: int) -> asyncio.Lock:
    return _acct_locks.setdefault(acc_id, asyncio.Lock())


def config() -> dict:
    """화면 기본값·설명"""
    return {
        "markets": {m: {"capital": pe.CAPITAL[m][0], "min_capital": pe.CAPITAL[m][1], "max_capital": pe.CAPITAL[m][2],
                        "currency": pe.COSTS[m]["currency"], "benchmark": INDEX[m][1],
                        "costs": {k: v for k, v in pe.COSTS[m].items() if k != "currency"}} for m in ("KR", "US")},
        "params": {k: {"default": d, "min": lo, "max": hi, "label": pe.PARAM_LABELS[k]} for k, (d, lo, hi) in pe.PARAMS.items()},
        "trailing": {"default": True, "label": pe.PARAM_LABELS["trailing"]},
        "options": {k: {"default": True, "label": pe.PARAM_LABELS[k]} for k in ("adaptive", "trend_filter")},
        "months": list(MONTHS), "weights": pe.WEIGHTS, "regime_exposure": pe.REGIME_EXPOSURE,
        "min_prob": pe.MIN_PROB, "max_accounts": MAX_ACCOUNTS,
    }


# ---------------- 데이터 ----------------

def base_universe(market: str) -> list:
    from app.api.routes.stocks import KR_LONGTERM, US_LONGTERM, US_SHORTTERM_EXTRA   # 순환 import 방지
    src = KR_LONGTERM if market == "KR" else US_LONGTERM + US_SHORTTERM_EXTRA
    seen, out = set(), []
    for c in src:
        if c["symbol"] in seen:
            continue
        seen.add(c["symbol"])
        m = stock_master.get(market, c["symbol"]) or {}
        out.append({"symbol": c["symbol"], "name": m.get("name") or c["name"]})
    return out


def _closed_only(market: str, candles: list) -> list:
    """오늘 장이 아직 안 끝났으면 오늘(미완성) 봉을 뺌 — 판단은 확정된 종가로만"""
    if not candles:
        return candles
    today = market_today(market).isoformat()
    if candles[-1]["date"][:10] >= today:
        now = datetime.now(_TZ[market])
        closed = now.hour * 60 + now.minute > session_hours(market, now.date())[1]
        if not closed or candles[-1]["date"][:10] > today:
            return candles[:-1]
    return candles


async def fetch_stocks(market: str, items: list, kr_count: int, us_period: str, progress=None) -> tuple:
    """→ ({종목: {name, candles}}, 오류 목록). 국내는 KIS(호출 제한이면 잠시 쉬고 그 종목만 다시), 미국은 yfinance 한 번에.
    progress(단계, 완료, 전체): 종목마다 호출 (예외를 올리면 중단)"""
    from app.services.quote import batch_yf_history
    out, errors = {}, []
    if market == "US":
        hist = await batch_yf_history([i["symbol"] for i in items], us_period)
        for i in items:
            cs = hist.get(i["symbol"]) or []
            if len(cs) < 60:
                errors.append(f"{i['name']}({i['symbol']}): 일봉 {len(cs)}개")
                continue
            out[i["symbol"]] = {"name": i["name"], "candles": cs}
        return out, errors
    for n, i in enumerate(items):
        if progress:
            progress(f"일봉 받는 중 ({i['name']})", n, len(items))
        for attempt in range(3):
            try:
                cs = (await kis_client.get_kr_chart(i["symbol"], kr_count))["candles"]
                if len(cs) < 60:
                    errors.append(f"{i['name']}({i['symbol']}): 일봉 {len(cs)}개")
                else:
                    out[i["symbol"]] = {"name": i["name"], "candles": cs}
                break
            except KISRateLimitError as e:
                if attempt == 2:
                    errors.append(f"{i['name']}({i['symbol']}): {e}")
                else:
                    await asyncio.sleep(10 * (attempt + 1))
            except Exception as e:
                errors.append(f"{i['name']}({i['symbol']}): {str(e)[:120]}")
                break
    return out, errors


async def fetch_index(market: str, period: str) -> list:
    from app.services.quote import batch_yf_history
    t = INDEX[market][0]
    cs = (await batch_yf_history([t], period)).get(t) or []
    if len(cs) < 200:
        raise RuntimeError(f"{INDEX[market][1]} 지수 일봉 {len(cs)}개 — yfinance 조회 실패 (시장 상태 판단에 필요)")
    return cs


async def macro_events(start: str, end: str) -> tuple:
    """미국 주요 발표 일정 (FRED 높은 영향 지표 + 연준 FOMC) → (일정, 못 받은 사유 목록)"""
    from app.core.config import settings
    from app.services.econ_calendar import _fred_calendar, _fomc_calendar, err_text
    evs, notes = [], []
    if settings.fred_api_key:
        try:
            evs += [e for e in await _fred_calendar(start, end) if e["impact"] == "high"]
        except Exception as e:
            notes.append(f"FRED 발표 일정 못 받음: {err_text(e)}")
    else:
        notes.append("FRED_API_KEY 없음 — CPI·고용 등 발표일 반영 안 됨 (옵션 만기일만)")
    try:
        evs += await _fomc_calendar(start, end)
    except Exception as e:
        notes.append(f"FOMC 일정 못 받음: {err_text(e)}")
    return evs, notes


# ---------------- 과거 시뮬레이션 ----------------

class SimCancelled(Exception):
    pass


_cancel: set = set()   # 중단을 요청한 시뮬레이션 번호


def cancel_sim(sim_id: int) -> bool:
    """계산 중이면 중단 요청 (다음 진행 표시 시점 — 길어야 몇 초 — 에 멈춤). 계산 중이 아니면 False"""
    if sim_id not in _sim_progress:
        return False
    _cancel.add(sim_id)
    _sim_progress[sim_id]["phase"] = "중단하는 중"
    return True


def sim_progress(sim_id: int) -> dict | None:
    return _sim_progress.get(sim_id)


def busy() -> bool:
    return _sim_lock.locked()


async def create_sim(user_id: int, market: str, capital, months: int, params: dict | None) -> PaperSim:
    if market not in ("KR", "US"):
        raise ValueError("시장은 KR 또는 US")
    if months not in MONTHS:
        raise ValueError(f"기간은 {', '.join(map(str, MONTHS))}개월 중 하나")
    capital = pe.check_capital(market, capital)
    params = pe.clean_params(params)
    if busy():
        raise RuntimeError("다른 시뮬레이션을 계산하는 중입니다 — 끝난 뒤 다시 시작하세요")
    async with AsyncSessionLocal() as db:
        sim = PaperSim(user_id=user_id, market=market, capital=capital, months=months,
                       params=json.dumps(params, ensure_ascii=False), status="running")
        db.add(sim)
        await db.commit()
        await db.refresh(sim)
    _sim_progress[sim.id] = {"phase": "대기 중", "done": 0, "total": 1}
    task = asyncio.create_task(_run_sim(sim.id, market, capital, months, params))
    task.add_done_callback(lambda t: t.cancelled() or (t.exception() and print(f"[paper] 시뮬레이션 오류: {t.exception()}")))
    return sim


async def _run_sim(sim_id: int, market: str, capital: float, months: int, params: dict):
    from app.services.kis_api import mark_background
    mark_background()
    prog = _sim_progress[sim_id]

    def progress(phase, done, total):
        if sim_id in _cancel:
            raise SimCancelled()
        prog.update(phase=phase, done=done, total=total)

    async with _sim_lock:
        try:
            end = last_session_date(market)
            if not (is_trading_day(market, end) and not is_market_open(market) and
                    (end < market_today(market) or _after_close(market))):
                end -= timedelta(days=1)          # 오늘 장이 아직 안 끝났으면 어제까지
            start = (end - timedelta(days=int(months * 30.44))).isoformat()
            end_s = end.isoformat()
            items = base_universe(market)
            progress(f"일봉 받는 중 ({len(items)}종목)", 0, len(items))
            kr_count = months * 22 + pe.WARMUP + 20 + int(pe.ADAPT_WARMUP_DAYS * 0.7)   # 학습형 비중용 앞쪽 점수까지
            stocks, errors = await fetch_stocks(market, items, kr_count, "5y", progress)
            if len(stocks) < max(3, len(items) // 2):
                raise RuntimeError(f"일봉을 받은 종목이 {len(stocks)}/{len(items)}개뿐 — " + " / ".join(errors[:3]))
            index = await fetch_index(market, "5y")
            progress("경제 일정 받는 중", 0, 1)
            macro, notes = await macro_events(start, end_s)
            feats = await asyncio.to_thread(pe.prepare, stocks, market, start, end_s, progress)
            result = await asyncio.to_thread(pe.simulate, stocks, index, macro, market, capital, start, end_s, params,
                                             progress, feats)
            if params.get("adaptive") or params.get("trend_filter"):
                # 같은 데이터·같은 설정에서 개선 옵션만 끈 '기본 방식' — 개선이 실제로 나은지 매번 비교해 보여줌
                base_params = {**params, "adaptive": False, "trend_filter": False}

                def base_progress(phase, done, total):
                    progress(f"비교용 기본 방식 — {phase}", done, total)
                base = await asyncio.to_thread(pe.simulate, stocks, index, macro, market, capital, start, end_s,
                                               base_params, base_progress, feats)
                result["compare"] = {"params": base_params, "summary": base["summary"],
                                     "equity": [{"date": c["date"], "equity": c["equity"]} for c in base["equity"]]}
            result["notes"] = notes + ([f"일봉 못 받은 종목 {len(errors)}개: " + " / ".join(errors[:3])] if errors else [])
            result["universe"] = [{"symbol": s, "name": v["name"]} for s, v in stocks.items()]
            result["benchmark"] = INDEX[market][1]
            result["params"] = params
            progress("결과 저장 중", 1, 1)
            await _save_sim(sim_id, status="done", summary=json.dumps(result["summary"], ensure_ascii=False),
                            result=json.dumps(result, ensure_ascii=False))
        except SimCancelled:
            print(f"[paper] 시뮬레이션 {sim_id} 중단 (사용자 요청)")
            try:
                await _save_sim(sim_id, status="cancelled", error="사용자가 중단함")
            except Exception as e2:
                print(f"[paper] 시뮬레이션 {sim_id} 중단 기록 실패: {type(e2).__name__}: {e2}")
        except Exception as e:
            print(f"[paper] 시뮬레이션 {sim_id} 실패: {e}")
            try:
                await _save_sim(sim_id, status="failed", error=str(e)[:500])
            except Exception as e2:
                print(f"[paper] 시뮬레이션 {sim_id} 실패 기록도 실패: {type(e2).__name__}: {e2}")
        finally:
            _sim_progress.pop(sim_id, None)
            _cancel.discard(sim_id)


SAVE_RETRY_WAITS = (5, 15, 30)   # DB 가 잠겨 있으면(다른 큰 저장 중) 이만큼 기다렸다가 다시 저장 (초)


def _db_locked(e: BaseException) -> bool:
    return "database is locked" in str(e)


async def _save_sim(sim_id: int, **fields):
    """시뮬레이션 결과·실패 저장. 몇 분 걸려 계산한 결과가 잠깐의 DB 잠금으로 버려지지 않게 잠금이면 다시 시도"""
    for attempt in range(len(SAVE_RETRY_WAITS) + 1):
        try:
            async with AsyncSessionLocal() as db:
                sim = await db.get(PaperSim, sim_id)
                if sim is None:
                    return
                for k, v in fields.items():
                    setattr(sim, k, v)
                sim.finished_at = datetime.now()
                await db.commit()
                return
        except Exception as e:
            if not _db_locked(e) or attempt == len(SAVE_RETRY_WAITS):
                raise
            print(f"[paper] 시뮬레이션 {sim_id} 저장 — DB 잠김, {SAVE_RETRY_WAITS[attempt]}초 뒤 다시")
            await asyncio.sleep(SAVE_RETRY_WAITS[attempt])


def _after_close(market: str) -> bool:
    now = datetime.now(_TZ[market])
    return now.hour * 60 + now.minute > session_hours(market, now.date())[1]


def sim_row(sim: PaperSim, full: bool = False) -> dict:
    d = {"id": sim.id, "market": sim.market, "capital": sim.capital, "months": sim.months,
         "params": json.loads(sim.params), "status": sim.status, "error": sim.error,
         "summary": json.loads(sim.summary) if sim.summary else None,
         "created_at": sim.created_at.isoformat() if sim.created_at else None,
         "progress": sim_progress(sim.id) if sim.status == "running" else None}
    if full and sim.result:
        d["result"] = json.loads(sim.result)
    return d


# ---------------- 실시간 모의투자 ----------------

def _state(acc: PaperAccount) -> dict:
    s = json.loads(acc.state)
    s.setdefault("positions", {})
    s.setdefault("pending", [])
    s.setdefault("log", [])
    return s


def _save_state(acc: PaperAccount, s: dict):
    s["log"] = s["log"][-LOG_KEEP:]
    acc.state = json.dumps(s, ensure_ascii=False)


async def create_account(user_id: int, market: str, capital, params: dict | None, name: str | None) -> PaperAccount:
    if market not in ("KR", "US"):
        raise ValueError("시장은 KR 또는 US")
    capital = pe.check_capital(market, capital)
    params = pe.clean_params(params)
    async with AsyncSessionLocal() as db:
        n = len((await db.execute(select(PaperAccount.id).where(PaperAccount.user_id == user_id))).all())
        if n >= MAX_ACCOUNTS:
            raise ValueError(f"모의투자 계좌는 {MAX_ACCOUNTS}개까지 — 안 쓰는 계좌를 지우고 만드세요")
        acc = PaperAccount(user_id=user_id, market=market, capital=capital, name=(name or "").strip()[:30] or None,
                           params=json.dumps(params, ensure_ascii=False),
                           state=json.dumps({**pe.new_state(capital), "pending": [], "log": []}))
        db.add(acc)
        await db.commit()
        await db.refresh(acc)
    return acc


async def _live_universe(acc: PaperAccount, state: dict) -> tuple:
    """→ (종목 목록, 덮어쓸 퀀트·매집 값)"""
    from app.services import accumulation
    items = {i["symbol"]: i for i in base_universe(acc.market)}
    async with AsyncSessionLocal() as db:
        for model in (WatchlistItem, PortfolioItem):
            rows = (await db.execute(select(model).where(model.user_id == acc.user_id, model.market == acc.market))).scalars().all()
            for r in rows:
                items.setdefault(r.symbol, {"symbol": r.symbol, "name": r.name or r.symbol})
    for sym, p in state["positions"].items():
        items.setdefault(sym, {"symbol": sym, "name": p["name"]})
    overrides = {}
    if acc.market == "KR":
        r = accumulation.result() or {}
        cands = r.get("candidates") or []
        ok = {c["symbol"] for c in cands}
        for c in cands[:10]:
            items.setdefault(c["symbol"], {"symbol": c["symbol"], "name": c["name"]})
        q = r.get("quant") or {}
        for t in (q.get("top") or [])[:10]:
            items.setdefault(t["symbol"], {"symbol": t["symbol"], "name": t.get("name") or t["symbol"]})
        scores, qs = r.get("scores") or {}, q.get("scores") or {}
        for sym in items:
            o = {}
            if sym in qs:
                o.update(quant=qs[sym]["pct"], grade=qs[sym]["grade"])
            if sym in scores:
                o.update(accum=scores[sym], accum_ok=sym in ok)
            if o:
                overrides[sym] = o
    return list(items.values()), overrides


def _now_ts(market: str) -> str:
    return datetime.now(_TZ[market]).isoformat(timespec="seconds")


async def _record_trade(db, acc_id: int, t: dict, ts: str):
    db.add(PaperTrade(account_id=acc_id, ts=ts, symbol=t["symbol"], name=t["name"], side=t["side"], qty=t["qty"],
                      price=t["price"], amount=t["amount"], fee=t["fee"], pnl=t["pnl"], pnl_pct=t["pnl_pct"],
                      reason=t["reason"]))


async def decide_account(acc_id: int, manual: bool = False) -> dict:
    """확정된 마지막 종가로 판단 → 대기 주문. 장중이면(수동 실행·계좌 개설) 바로 현재가로 체결"""
    from app.services.quote import analyze_candles
    from app.services import events
    async with _lock(acc_id):
        async with AsyncSessionLocal() as db:
            acc = await db.get(PaperAccount, acc_id)
            if acc is None:
                raise LookupError("계좌 없음")
            market, params, state = acc.market, json.loads(acc.params), _state(acc)
            if not manual and acc.last_decision_day == market_today(market).isoformat():
                return {"ok": True, "skipped": "오늘 판단 이미 함"}   # 자동 실행이 기다리는 사이 다른 판단이 끝남
            try:
                items, overrides = await _live_universe(acc, state)
                stocks, errors = await fetch_stocks(market, items, 320, "2y")
                for s in stocks.values():
                    s["candles"] = _closed_only(market, s["candles"])
                stocks = {k: v for k, v in stocks.items() if len(v["candles"]) >= 60}
                if not stocks:
                    raise RuntimeError("일봉을 받은 종목이 없음 — " + " / ".join(errors[:3]))
                last = max(s["candles"][-1]["date"][:10] for s in stocks.values())
                stocks = {k: v for k, v in stocks.items() if v["candles"][-1]["date"][:10] == last}
                probs = {}
                for sym, s in stocks.items():
                    try:
                        a = await asyncio.to_thread(analyze_candles, market, s["candles"], 0, 0, None, None, sym)
                        probs[sym] = a["prediction"]["probability"]
                    except Exception as e:   # 학습 모델 포함 확률 실패 → 규칙 점수 확률 (build_features 가 계산)
                        print(f"[paper] {sym} AI 추천 확률 실패: {e}")
                adaptive = bool(params.get("adaptive"))
                # 학습형 비중: 최근 약 140거래일 점수와 그 뒤 결과로 (오늘 판단엔 오늘까지 확정된 결과만)
                feat_from = (date.fromisoformat(last) - timedelta(days=200)).isoformat() if adaptive else last
                feats = await asyncio.to_thread(pe.build_features, stocks, market, feat_from, probs, overrides)
                rows = feats.get(last) or {}
                aw = (await asyncio.to_thread(pe.adaptive_weights, feats, pe.forward_labels(stocks), last)) if adaptive else None
                pe.rescore(rows, aw["weights"] if aw else pe.WEIGHTS)
                index = _closed_only(market, await fetch_index(market, "2y"))
                regime = pe.regime_on(pe.regime_map(index), last)
                nxt = next_trading_day(market, date.fromisoformat(last)).isoformat()
                ev = pe.event_labels(market, nxt, events._cache["events"])
                # 종가 반영(하루 한 번): 보유일·최고가·추격 손절
                if state.get("last_close") != last:
                    closes = {s: r["close"] for s, r in rows.items() if s in state["positions"]}
                    closes["__day__"] = last
                    pe.after_close(state, closes, params)
                    state["last_close"] = last
                orders, notes = pe.decide(state, rows, regime, ev, params, market)
                state["pending"] = [{**o, "created": _now_ts(market), "base_date": last} for o in orders]
                prices = {s: p["last"] for s, p in state["positions"].items()}
                eq = pe.equity_of(state, prices)
                bench = float(index[-1]["close"]) if index else None
                if acc.bench_start is None and bench:
                    acc.bench_start = bench
                old = (await db.execute(select(PaperEquity).where(PaperEquity.account_id == acc_id,
                                                                   PaperEquity.date == last))).scalar_one_or_none()
                if old:
                    old.equity, old.cash, old.bench = eq, state["cash"], bench
                else:
                    db.add(PaperEquity(account_id=acc_id, date=last, equity=eq, cash=state["cash"], bench=bench))
                top = [{"symbol": s, "name": r["name"], "score": r["score"], "prob": r["prob"], "quant": r["quant"],
                        "accum": r["accum"]} for s, r in sorted(rows.items(), key=lambda kv: -kv[1]["score"])[:5]]
                state["log"].append({"ts": _now_ts(market), "base_date": last, "regime": regime, "events": ev,
                                     "manual": manual, "notes": ([pe.weights_text(aw)] if adaptive else []) + notes
                                     + ([f"일봉 못 받은 종목 {len(errors)}개"] if errors else []),
                                     "orders": [f"{'매수' if o['side'] == 'buy' else '매도'} {o['name']} — {o['reason']}" for o in orders],
                                     "top": top, "universe": len(rows)})
                acc.last_decision_day = market_today(market).isoformat() if _after_close(market) or not is_trading_day(
                    market, market_today(market)) else acc.last_decision_day
                acc.last_error = None
                _save_state(acc, state)
                await db.commit()
            except Exception as e:
                acc.last_error = f"{_now_ts(market)} 판단 실패: {str(e)[:300]}"
                await db.commit()
                raise
    if is_market_open(market):
        await fill_pending(acc_id)
    return {"ok": True}


async def fill_pending(acc_id: int) -> int:
    """대기 주문을 지금 현재가로 체결 (매도 먼저). 현재가를 못 받은 주문은 남겨 둠"""
    from app.services.quote import live_prices
    async with _lock(acc_id):
        async with AsyncSessionLocal() as db:
            acc = await db.get(PaperAccount, acc_id)
            if acc is None:
                return 0
            state, params, market = _state(acc), json.loads(acc.params), acc.market
            if not state["pending"]:
                return 0
            live = await live_prices([{"market": market, "symbol": o["symbol"]} for o in state["pending"]])
            ts, day, n, left, acts = _now_ts(market), market_today(market).isoformat(), 0, [], []
            for o in sorted(state["pending"], key=lambda x: x["side"] != "sell"):
                px = (live.get((market, o["symbol"])) or {}).get("price")
                if not px:
                    left.append(o)
                    continue
                if o["side"] == "sell":
                    t = pe.fill_sell(state, o["symbol"], float(px), day, o["reason"], market)
                else:
                    t = pe.fill_buy(state, o["symbol"], o["name"], o["budget"], float(px), day, o["reason"], params, market)
                    if t is None:
                        acts.append(f"{o['name']} 매수 취소 — 현금 부족 또는 가격 상승으로 1주도 못 삼")
                if t:
                    await _record_trade(db, acc_id, t, ts)
                    acts.append(pe._act_text(t, market))
                    n += 1
            state["pending"] = left
            if acts:
                state["log"].append({"ts": ts, "fills": acts, "notes": [f"현재가 못 받아 대기 {len(left)}건"] if left else []})
            _save_state(acc, state)
            await db.commit()
            return n


async def check_exits(acc_id: int) -> int:
    """장중: 현재가가 손절가 이하 / 목표가 이상이면 바로 매도"""
    from app.services.quote import live_prices
    async with _lock(acc_id):
        async with AsyncSessionLocal() as db:
            acc = await db.get(PaperAccount, acc_id)
            if acc is None:
                return 0
            state, market = _state(acc), acc.market
            if not state["positions"]:
                return 0
            live = await live_prices([{"market": market, "symbol": s} for s in state["positions"]])
            ts, day, acts = _now_ts(market), market_today(market).isoformat(), []
            for sym in list(state["positions"]):
                px = (live.get((market, sym)) or {}).get("price")
                if not px:
                    continue
                p = state["positions"][sym]
                why = ("손절가 도달 (장중)" if px <= p["stop"] else "목표가 도달 (장중)" if px >= p["target"] else None)
                if why:
                    t = pe.fill_sell(state, sym, float(px), day, why, market)
                    await _record_trade(db, acc_id, t, ts)
                    acts.append(pe._act_text(t, market))
                    state["pending"] = [o for o in state["pending"] if o["symbol"] != sym]
            if acts:
                state["log"].append({"ts": ts, "fills": acts})
                _save_state(acc, state)
                await db.commit()
            return len(acts)


async def account_view(acc: PaperAccount, db, full: bool = False) -> dict:
    """화면용: 현재가로 평가 (못 받으면 마지막 종가)"""
    from app.services.quote import live_prices
    state, market = _state(acc), acc.market
    live, price_error = {}, None
    if state["positions"]:
        try:
            live = await live_prices([{"market": market, "symbol": s} for s in state["positions"]])
        except Exception as e:
            price_error = f"현재가 조회 실패 — 마지막 종가로 평가: {str(e)[:120]}"
    for s, p in state["positions"].items():
        px = (live.get((market, s)) or {}).get("price")
        if px:
            p["last"] = float(px)
    prices = {s: p["last"] for s, p in state["positions"].items()}
    eq = pe.equity_of(state, prices)
    eqs = (await db.execute(select(PaperEquity).where(PaperEquity.account_id == acc.id).order_by(PaperEquity.date))).scalars().all()
    bench_ret = None
    if acc.bench_start and eqs and eqs[-1].bench:
        bench_ret = round((eqs[-1].bench / acc.bench_start - 1) * 100, 2)
    d = {
        "id": acc.id, "name": acc.name, "market": market, "capital": acc.capital, "params": json.loads(acc.params),
        "created_at": acc.created_at.isoformat() if acc.created_at else None, "active": acc.active,
        "cash": round(state["cash"], 2), "equity": round(eq, 2), "return_pct": round((eq / acc.capital - 1) * 100, 2),
        "bench_return_pct": bench_ret, "benchmark": INDEX[market][1],
        "positions": pe.positions_view(state, market), "pending": state["pending"],
        "last_decision_day": acc.last_decision_day, "last_error": acc.last_error, "price_error": price_error,
        "market_open": is_market_open(market),
    }
    if full:
        trades = (await db.execute(select(PaperTrade).where(PaperTrade.account_id == acc.id)
                                   .order_by(PaperTrade.id.desc()).limit(300))).scalars().all()
        d["trades"] = [{"ts": t.ts, "symbol": t.symbol, "name": t.name, "side": t.side, "qty": t.qty, "price": t.price,
                        "amount": t.amount, "fee": t.fee, "pnl": t.pnl, "pnl_pct": t.pnl_pct, "reason": t.reason} for t in trades]
        sells = [t for t in trades if t.side == "sell" and t.pnl is not None]
        d["stats"] = {"trades": len(sells), "win_rate": round(sum(t.pnl > 0 for t in sells) / len(sells) * 100, 1) if sells else None,
                      "realized": round(sum(t.pnl for t in sells), 2), "fees": round(sum(t.fee for t in trades), 2)}
        b0 = acc.bench_start
        d["equity_curve"] = [{"date": e.date, "equity": round(e.equity, 2), "cash": round(e.cash, 2),
                              "bench": round(acc.capital * e.bench / b0, 2) if b0 and e.bench else None} for e in eqs]
        d["log"] = list(reversed(state["log"]))
    return d


async def delete_account(acc_id: int):
    async with _lock(acc_id):
        async with AsyncSessionLocal() as db:
            await db.execute(delete(PaperTrade).where(PaperTrade.account_id == acc_id))
            await db.execute(delete(PaperEquity).where(PaperEquity.account_id == acc_id))
            await db.execute(delete(PaperAccount).where(PaperAccount.id == acc_id))
            await db.commit()
    _acct_locks.pop(acc_id, None)


async def delete_user_data(db, user_id: int):
    """회원 탈퇴 시 (auth.delete-account 의 같은 트랜잭션에서)"""
    ids = [i for (i,) in (await db.execute(select(PaperAccount.id).where(PaperAccount.user_id == user_id))).all()]
    if ids:
        await db.execute(delete(PaperTrade).where(PaperTrade.account_id.in_(ids)))
        await db.execute(delete(PaperEquity).where(PaperEquity.account_id.in_(ids)))
        await db.execute(delete(PaperAccount).where(PaperAccount.id.in_(ids)))
    await db.execute(delete(PaperSim).where(PaperSim.user_id == user_id))


# ---------------- 자동 운영 ----------------

def status() -> dict:
    return dict(_loop_status, sim_running=busy())


async def tick():
    """1분마다: 개장 직후 대기 주문 체결 · 장중 손절/목표 확인 · 장 마감 후 판단"""
    async with AsyncSessionLocal() as db:
        accs = (await db.execute(select(PaperAccount).where(PaperAccount.active.is_(True)))).scalars().all()
        accs = [(a.id, a.market, a.last_decision_day, bool(json.loads(a.state).get("pending"))) for a in accs]
    for acc_id, market, last_day, has_pending in accs:
        now = datetime.now(_TZ[market])
        today = now.date()
        if not is_trading_day(market, today):
            continue
        hm = now.hour * 60 + now.minute
        open_hm, close_hm = session_hours(market, today)
        try:
            if open_hm + FILL_AFTER_OPEN <= hm <= close_hm:
                if has_pending:
                    await fill_pending(acc_id)
                if time.time() - _last_exit_check.get(acc_id, 0) >= EXIT_CHECK_EVERY:
                    _last_exit_check[acc_id] = time.time()
                    await check_exits(acc_id)
            elif (hm >= close_hm + DECIDE_AFTER_CLOSE and last_day != today.isoformat()
                  and time.time() - _decide_failed.get(acc_id, 0) >= DECIDE_RETRY):
                try:
                    await decide_account(acc_id)
                    _decide_failed.pop(acc_id, None)
                except Exception:
                    _decide_failed[acc_id] = time.time()
                    raise
        except Exception as e:
            _loop_status["last_error"] = f"{datetime.now().isoformat(timespec='seconds')} 계좌 {acc_id}: {str(e)[:200]}"
            print(f"[paper] 계좌 {acc_id} 자동 운영 실패: {e}")


async def mark_interrupted():
    """서버가 계산 도중 꺼졌던 시뮬레이션(상태가 계속 '계산 중')을 실패로 — 안 그러면 지우지도 중단하지도 못함"""
    from sqlalchemy import update
    async with AsyncSessionLocal() as db:
        r = await db.execute(update(PaperSim).where(PaperSim.status == "running")
                             .values(status="failed", error="서버가 다시 시작돼 계산이 중단됨 — 다시 시작하세요"))
        await db.commit()
        if r.rowcount:
            print(f"[paper] 중단된 시뮬레이션 {r.rowcount}건 정리")


async def loop():
    from app.services.kis_api import mark_background
    mark_background()
    try:
        await mark_interrupted()
    except Exception as e:
        print(f"[paper] 중단된 시뮬레이션 정리 실패: {e}")
    await asyncio.sleep(30)
    while True:
        try:
            await tick()
            _loop_status["last_tick"] = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            _loop_status["last_error"] = f"{datetime.now().isoformat(timespec='seconds')} {str(e)[:200]}"
            print(f"[paper] 자동 운영 실패: {e}")
        await asyncio.sleep(60)
