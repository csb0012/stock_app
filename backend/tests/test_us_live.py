"""미국 현재가를 KIS 해외 현재가로 (Yahoo 는 KIS 가 실패한 종목만, 출처 표시) — AI 추천·모의투자(live_prices)·관심/투자종목(analyze_items)"""
import datetime as dt

import pytest

from tests.conftest import run
from app.services import quote, stock_master
from app.services.kis_api import kis_client, KISError


@pytest.fixture
def us(monkeypatch):
    quote._us_live_cache.clear()
    calls = []
    prices = {"AAPL": 231.5, "AVGO": 320.53, "BRK.B": 0.0}

    async def kis_price(symbol, exchange="NAS"):
        calls.append((symbol, exchange))
        if symbol == "FAIL":
            raise KISError("KIS HHDFS00000300 실패 (HTTP 500, EGW00000): 테스트")
        return {"price": prices.get(symbol, 0.0), "change_rate": -1.23, "volume": 1000}
    monkeypatch.setattr(kis_client, "get_us_stock_price", kis_price)
    monkeypatch.setattr(stock_master, "get", lambda m, s: {"exchange": {"AAPL": "NAS", "AVGO": "NAS", "BRK.B": "NYS"}.get(s, "AMS"), "name": s})
    yf_calls = []

    def yf_last(symbols):
        yf_calls.append(list(symbols))
        return {s: 99.0 for s in symbols if s == "FAIL"}
    monkeypatch.setattr(quote, "_yf_last_sync", yf_last)
    monkeypatch.setattr(quote, "is_market_open", lambda m: True)
    return calls, yf_calls


def test_kis_first_with_exchange_and_source(us):
    calls, yf_calls = us
    out = run(quote.us_live_prices(["AAPL", "AVGO"]))
    assert out[("US", "AAPL")] == {"price": 231.5, "change_rate": -1.23, "volume": 1000, "source": "KIS"}
    assert calls == [("AAPL", "NAS"), ("AVGO", "NAS")] and yf_calls == []      # Yahoo 는 안 부름


def test_fallback_to_yahoo_only_for_failed_and_labelled(us):
    calls, yf_calls = us
    out = run(quote.us_live_prices(["AAPL", "FAIL", "BRK.B"]))
    assert out[("US", "AAPL")]["source"] == "KIS"
    f = out[("US", "FAIL")]
    assert f["price"] == 99.0 and f["source"] == "Yahoo (KIS 실패)" and "EGW00000" in f["kis_error"]
    assert "error" in out[("US", "BRK.B")] and "NYS:BRK.B" in out[("US", "BRK.B")]["error"]   # KIS 0원 + Yahoo 도 없음 → 이유
    assert sorted(yf_calls[0]) == ["BRK.B", "FAIL"]


def test_cache_ttl(us, monkeypatch):
    calls, _ = us
    run(quote.us_live_prices(["AAPL"]))
    run(quote.us_live_prices(["AAPL"]))
    assert len(calls) == 1                            # 10초(실서버)·60초(모의) 안에는 다시 안 물음
    t = quote.time.time()
    monkeypatch.setattr(quote.time, "time", lambda: t + 700)
    run(quote.us_live_prices(["AAPL"]))
    assert len(calls) == 2


def test_live_prices_uses_kis_for_us(us):
    out = run(quote.live_prices([{"market": "US", "symbol": "AVGO"}]))
    assert out[("US", "AVGO")]["price"] == 320.53 and out[("US", "AVGO")]["source"] == "KIS"


def test_watchlist_analysis_uses_kis_price(us, monkeypatch):
    """관심종목·투자종목(analyze_items): 일봉은 yfinance, 현재가·등락률은 KIS → 오늘 봉에 반영해 확률 계산"""
    today = quote.market_today("US")
    cs, d, p = [], today - dt.timedelta(days=200), 200.0
    while d < today:
        if d.weekday() < 5:
            cs.append({"date": d.isoformat(), "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1e6})
            p *= 1.001
        d += dt.timedelta(days=1)

    async def hist(symbols, period="6mo"):
        return {s: list(cs) for s in symbols}

    async def nothing(*a, **k):
        return {}
    monkeypatch.setattr(quote, "batch_yf_history", hist)
    monkeypatch.setattr(quote, "get_news_many", nothing)
    monkeypatch.setattr(quote, "us_valuations", nothing)
    out = run(quote.analyze_items([{"market": "US", "symbol": "AAPL"}]))
    r = out[("US", "AAPL")]
    assert r["price"] == 231.5 and r["change_rate"] == -1.23 and r["price_source"] == "KIS"
    assert r["candles"][-1]["close"] == 231.5 and r["candles"][-1]["date"] == today.isoformat()   # 장중이면 오늘 봉 추가
    # KIS·Yahoo 1분봉 둘 다 실패 → 일봉 마지막 값으로 분석은 되고, 출처가 'Yahoo (KIS 실패)' (화면에 '지연 가능' 표시)
    f = run(quote.analyze_items([{"market": "US", "symbol": "NOPE"}]))[("US", "NOPE")]
    assert f["price"] == round(cs[-1]["close"], 2) and f["price_source"] == "Yahoo (KIS 실패)" and "KIS" in f["live_error"]


def test_us_price_sign(monkeypatch):
    async def get(path, tr, params):
        return {"output": {"last": "100.5", "diff": "1.5", "rate": "1.47", "sign": "5", "tvol": "10"}}
    monkeypatch.setattr(kis_client, "_get", get)
    p = run(kis_client.get_us_stock_price("AAPL", "NAS"))
    assert p["change"] == -1.5 and p["change_rate"] == -1.47 and p["price"] == 100.5
