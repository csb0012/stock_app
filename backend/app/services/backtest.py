"""과거 예측 백테스트 — 최근 90일 동안 매 거래일마다 "그날까지의 일봉만 보고" 다음 거래일을 예측해 채점

예) 대상일 11/19 → 11/18 종가까지의 일봉(최근 130개)으로 지표·확률 계산 → 11/19 실제 등락과 비교.
대상일 이후 데이터는 절대 쓰지 않는다 (미래 정보 누설 방지).

- 결과는 prediction_backtest 테이블(stock_app.db)에 저장 → 이미 계산한 날짜는 다시 계산하지 않음 (증분)
- 대상 종목: AI 추천 후보(국내 장기·미국 장기·미국 단기) + 관심종목 + 투자종목
- 뉴스·FRED·Finnhub·DART 는 과거 시점 기록이 없어 빼고, 기술적 지표(RSI·MACD·볼린저·이평)만 사용
- 서버 시작 후, 그리고 하루 한 번(30분 채점 주기에 확인) 자동 실행. 예측 검증 화면의 버튼으로도 실행
"""
import asyncio
import json
from datetime import date, datetime

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.prediction import BacktestLog
from app.models.watchlist import WatchlistItem
from app.models.portfolio import PortfolioItem
from app.services import stock_master
from app.services.kis_api import KISRateLimitError
from app.services.analysis import calc_technical_indicators, predict_next_day
from app.services.market_calendar import market_today, is_market_open, _after_close

RETRY_WAITS = (10, 30, 60)  # 초당 호출 제한으로 실패한 종목만 이만큼 기다렸다가 다시 계산 (초)
DAYS = 90        # 대상일 기준 최근 90일 (달력 기준)
WINDOW = 130     # 예측에 쓰는 일봉 개수 (실시간 AI 추천과 같음)
KR_COUNT = 240   # 90일치 대상일 + 지표 계산용 과거 일봉

_lock = asyncio.Lock()
_status = {
    "running": False, "done": 0, "total": 0, "current": None, "added": 0,
    "started_at": None, "finished_at": None, "last_run_date": None, "errors": [], "retry_wait": None,
}


def status() -> dict:
    return dict(_status)


def _closed(market: str, d: str) -> bool:
    """그 날짜 일봉이 확정됐는지 (오늘 장중이면 아직 미확정)"""
    today = market_today(market).isoformat()
    if d < today:
        return True
    return d == today and not is_market_open(market) and _after_close(market)


async def _universe() -> list:
    from app.api.routes.stocks import KR_LONGTERM, US_LONGTERM, US_SHORTTERM_EXTRA  # 순환 import 방지
    seen, out = set(), []

    def add(market, symbol, name):
        if (market, symbol) in seen:
            return
        seen.add((market, symbol))
        out.append({"market": market, "symbol": symbol, "name": name})

    for c in KR_LONGTERM + US_LONGTERM + US_SHORTTERM_EXTRA:
        m = stock_master.get(c["market"], c["symbol"]) or {}
        add(c["market"], c["symbol"], m.get("name") or c["name"])
    async with AsyncSessionLocal() as db:
        for model in (WatchlistItem, PortfolioItem):
            for r in (await db.execute(select(model))).scalars().all():
                add(r.market, r.symbol, r.name)
    return out


def _simulate(stock: dict, candles: list, have: set, cutoff: str) -> list:
    """CPU 작업 (스레드에서 실행): 대상일마다 전날까지의 일봉으로 예측 → 채점용 dict 목록"""
    out = []
    for ti in range(1, len(candles)):
        t = candles[ti]["date"][:10]
        if t < cutoff or t in have or not _closed(stock["market"], t):
            continue
        hist = candles[max(0, ti - WINDOW):ti]  # 대상일 전날까지만
        if len(hist) < 30:
            continue
        ind = calc_technical_indicators(hist)
        p = predict_next_day(hist, ind)  # 뉴스·외부데이터 없음 (과거 시점 기록 없음)
        out.append({"ti": ti, "target_date": t, "base_date": hist[-1]["date"][:10],
                    "base_price": float(hist[-1]["close"]), "pred": p})
    return out


async def run(force: bool = False) -> dict:
    """백테스트 실행 (이미 실행 중이면 상태만 반환). force=True 면 기존 기록을 지우고 다시 계산"""
    if _lock.locked():
        return status()
    async with _lock:
        _status.update(running=True, done=0, total=0, current=None, added=0, errors=[], retry_wait=None,
                       started_at=datetime.now().isoformat(timespec="seconds"), finished_at=None)
        try:
            await _run(force)
            _status["last_run_date"] = date.today().isoformat()
        except Exception as e:
            _status["errors"].append(f"백테스트 실패: {e}")
            print(f"[backtest] 실패: {e}")
        finally:
            _status.update(running=False, current=None, finished_at=datetime.now().isoformat(timespec="seconds"))
    return status()


async def _run(force: bool):
    # 순환 import 방지
    from app.services.quote import kr_chart, batch_yf_history
    from app.services.prediction_log import grade, index_change_fn, _INDEX

    cutoff = date.fromordinal(date.today().toordinal() - DAYS).isoformat()
    stocks = await _universe()
    _status["total"] = len(stocks)

    async with AsyncSessionLocal() as db:
        if force:
            await db.execute(delete(BacktestLog))
            await db.commit()
        existing: dict = {}
        for m, s, t in (await db.execute(select(BacktestLog.market, BacktestLog.symbol, BacktestLog.target_date))).all():
            existing.setdefault((m, s), set()).add(t)

    idx_change = index_change_fn(await batch_yf_history([v[0] for v in _INDEX.values()], "1y"))
    us_syms = [s["symbol"] for s in stocks if s["market"] == "US"]
    us_hist = await batch_yf_history(us_syms, "1y") if us_syms else {}

    async def one(st: dict):
        _status["current"] = st["name"] or st["symbol"]
        if st["market"] == "KR":
            candles = (await kr_chart(st["symbol"], KR_COUNT))["candles"]
        else:
            candles = us_hist.get(st["symbol"], [])
        if len(candles) < 40:
            raise ValueError(f"일봉 {len(candles)}개 — 데이터 부족")
        have = existing.get((st["market"], st["symbol"]), set())
        sims = await asyncio.to_thread(_simulate, st, candles, have, cutoff)
        if sims:
            async with AsyncSessionLocal() as db:
                for x in sims:
                    p = x["pred"]
                    log = BacktestLog(
                        market=st["market"], symbol=st["symbol"], name=st["name"], sources="백테스트",
                        base_date=x["base_date"], target_date=x["target_date"], base_price=x["base_price"],
                        probability=int(p["probability"]), signal=p.get("signal"), summary=p.get("summary"),
                        factors=json.dumps(p.get("factors", []), ensure_ascii=False),
                    )
                    grade(log, candles, x["ti"], idx_change)
                    db.add(log)
                await db.commit()
            _status["added"] += len(sims)

    def fail(st: dict, e: Exception):
        _status["errors"].append(f"{st['name'] or st['symbol']}({st['symbol']}): {e}")
        print(f"[backtest] {st['symbol']} 실패: {e}")

    retry = []
    for st in stocks:
        try:
            await one(st)
            _status["done"] += 1
        except KISRateLimitError:
            retry.append(st)  # 나중에 이 종목만 다시
        except Exception as e:
            fail(st, e)
            _status["done"] += 1

    # 초당 호출 제한으로 실패한 종목: 호출이 풀릴 때까지 기다렸다가 그 종목만 다시 계산
    for n, wait in enumerate(RETRY_WAITS):
        if not retry:
            break
        names = ", ".join(s["name"] or s["symbol"] for s in retry[:3]) + (" 외" if len(retry) > 3 else "")
        _status["retry_wait"] = {"seconds": wait, "count": len(retry), "names": names, "round": n + 1}
        _status["current"] = f"초당 호출 제한 — {wait}초 후 {len(retry)}종목 다시 계산 ({names})"
        print(f"[backtest] {_status['current']}")
        await asyncio.sleep(wait)
        _status["retry_wait"] = None
        pending, retry = retry, []
        for st in pending:
            try:
                await one(st)
                _status["done"] += 1
            except KISRateLimitError as e:
                if n == len(RETRY_WAITS) - 1:
                    fail(st, e)
                    _status["done"] += 1
                else:
                    retry.append(st)
            except Exception as e:
                fail(st, e)
                _status["done"] += 1


def due() -> bool:
    """오늘 아직 안 돌았으면 True"""
    return not _status["running"] and _status["last_run_date"] != date.today().isoformat()
