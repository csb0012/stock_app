"""API 응답 형식 — 관심종목·투자종목·종목 조회·대시보드·AI 추천에 미국 주간거래 가격이 붙는지, 국내·오류 행은 그대로인지"""
import pytest

from tests.conftest import run
from app.models.watchlist import WatchlistItem
from app.models.portfolio import PortfolioItem
from app.services import us_daytime, stock_master

DAY = {"label": "주간거래", "price": 320.53, "base": 304.41, "change": 16.12, "change_rate": 5.3,
       "volume": 10, "time": "17:31", "hours_kst": "10:00~18:00", "source": "KIS 주간거래"}


def candles(n=30, start=100.0):
    return [{"date": f"2026-10-{(i % 28) + 1:02d}", "open": start + i, "high": start + i + 2,
             "low": start + i - 2, "close": start + i, "volume": 1000} for i in range(n)]


def analyzed(symbol, market, price):
    return {"symbol": symbol, "market": market, "name": symbol, "price": price, "change_rate": -2.89,
            "candles": candles(), "indicators": {"rsi": 32.8},
            "prediction": {"probability": 36, "buy_price": price * 0.97, "buy_gap_pct": -3.0,
                           "target_price": price * 1.05, "stop_loss": price * 0.93},
            "style": {}}


@pytest.fixture
def daytime_on(monkeypatch):
    async def fake_many(symbols, extended=True):
        return {s: dict(DAY) for s in symbols if s == "AVGO"}
    monkeypatch.setattr(us_daytime, "get_many", fake_many)


def add_rows(Session, user, model, rows):
    async def go():
        async with Session() as s:
            for r in rows:
                s.add(model(user_id=user.id, **r))
            await s.commit()
    run(go())


def test_watchlist_analysis_shape_and_daytime(api_client, monkeypatch, daytime_on):
    client, Session, user = api_client
    add_rows(Session, user, WatchlistItem, [
        {"symbol": "005930", "market": "KR", "name": "삼성전자", "target_price": 180000},
        {"symbol": "AVGO", "market": "US", "name": "브로드컴"},
        {"symbol": "BAD", "market": "US", "name": "오류종목"},
    ])
    from app.api.routes import watchlist as wl

    async def fake_analyze(items, period="6mo"):
        return {("KR", "005930"): analyzed("005930", "KR", 177800),
                ("US", "AVGO"): analyzed("AVGO", "US", 304.41),
                ("US", "BAD"): {"symbol": "BAD", "market": "US", "error": "yfinance 가격 데이터 부족 (0일)"}}
    monkeypatch.setattr(wl, "analyze_items", fake_analyze)
    wl._analysis_cache.invalidate()

    r = client.get("/api/watchlist/analysis")
    assert r.status_code == 200
    rows = {x["symbol"]: x for x in r.json()}
    kr, us, bad = rows["005930"], rows["AVGO"], rows["BAD"]
    assert kr["current_price"] == 177800 and "daytime" not in kr
    assert kr["target_reached"] is True and kr["target_gap_pct"] == pytest.approx(-1.22, abs=0.01)
    assert us["daytime"]["price"] == 320.53 and us["current_price"] == 304.41
    assert us["prediction"]["target_price"] > us["current_price"] > us["prediction"]["stop_loss"]
    assert bad["error"].startswith("yfinance") and "daytime" not in bad
    for k in ("change_5d", "change_20d", "high_period", "low_period", "period_days", "rsi"):
        assert k in kr


def test_watchlist_analysis_empty(api_client):
    client, _, _ = api_client
    from app.api.routes import watchlist as wl
    wl._analysis_cache.invalidate()
    assert client.get("/api/watchlist/analysis").json() == []


def test_watchlist_crud(api_client, monkeypatch):
    client, _, _ = api_client
    monkeypatch.setattr(stock_master, "get", lambda m, s: {"name": "브로드컴"} if s == "AVGO" else None)
    r = client.post("/api/watchlist/", json={"symbol": "AVGO", "market": "US"})
    assert r.status_code == 200 and r.json()["name"] == "브로드컴"
    assert client.post("/api/watchlist/", json={"symbol": "AVGO", "market": "US"}).status_code == 400   # 중복
    assert client.post("/api/watchlist/", json={"symbol": "NOPE", "market": "US"}).status_code == 400   # 마스터에 없음
    item_id = r.json()["id"]
    r = client.put(f"/api/watchlist/{item_id}", json={"memo": "  AI 반도체  ", "target_price": 280})
    assert r.json()["memo"] == "AI 반도체" and r.json()["target_price"] == 280
    r = client.put(f"/api/watchlist/{item_id}", json={"target_price": 0})   # 0 이하 → 목표가 삭제
    assert r.json()["target_price"] is None
    assert client.put("/api/watchlist/99999", json={"memo": "x"}).status_code == 404
    client.delete(f"/api/watchlist/{item_id}")
    assert client.get("/api/watchlist/").json() == []


def test_portfolio_analysis_daytime(api_client, monkeypatch, daytime_on):
    client, Session, user = api_client
    add_rows(Session, user, PortfolioItem, [{"symbol": "AVGO", "market": "US", "name": "브로드컴", "quantity": 2, "avg_price": 300}])
    from app.api.routes import portfolio as pf

    async def fake_analyze(items, period="6mo"):
        return {("US", "AVGO"): analyzed("AVGO", "US", 304.41)}

    async def fake_fx():
        return 1400.0
    monkeypatch.setattr(pf, "analyze_items", fake_analyze)
    monkeypatch.setattr(pf, "get_usdkrw", fake_fx)
    pf._analysis_cache.invalidate()
    data = client.get("/api/portfolio/analysis").json()
    row = data["items"][0]
    assert row["daytime"]["price"] == 320.53
    assert data["totals"]["USD"]["count"] == 1 and data["usdkrw"] == 1400.0


def test_market_bigtech_daytime(api_client, monkeypatch, daytime_on):
    client, _, _ = api_client
    from app.api.routes import market

    async def fake_bigtech():
        return {"items": [{"symbol": "AVGO", "name": "브로드컴", "price": 304.41, "change_rate": -12.19},
                          {"symbol": "AAPL", "name": "애플", "price": 230.0, "change_rate": 0.5}]}
    monkeypatch.setitem(market._SECTIONS, "bigtech", fake_bigtech)
    market._overview.invalidate()
    items = client.get("/api/market/overview/bigtech").json()["items"]
    assert items[0]["daytime"]["change_rate"] == 5.3 and "daytime" not in items[1]
    assert "updated_at" in client.get("/api/market/overview/bigtech").json()


def test_market_status_daytime_field(api_client):
    client, _, _ = api_client
    st = client.get("/api/market/status").json()
    assert set(st["US"]["daytime"]) >= {"open", "session_date", "hours_kst", "end_kst"}
    assert "daytime" not in st["KR"]
    assert set(st["US"]["extended"]) >= {"open", "label", "hours_kst"} and "extended" not in st["KR"]


def test_market_bigtech_skips_extended(api_client, monkeypatch):
    """대시보드 빅테크·ETF 는 시간외 가격(ext)이 따로 있어서 프리·애프터마켓을 daytime 으로 또 붙이지 않음"""
    client, _, _ = api_client
    from app.api.routes import market
    seen = []

    async def fake_many(symbols, extended=True):
        seen.append(extended)
        return {}
    monkeypatch.setattr(us_daytime, "get_many", fake_many)

    async def fake_bigtech():
        return {"items": [{"symbol": "AVGO", "name": "브로드컴", "price": 304.41}]}
    monkeypatch.setitem(market._SECTIONS, "bigtech", fake_bigtech)
    market._overview.invalidate()
    client.get("/api/market/overview/bigtech")
    assert seen == [False]


def test_quote_us_daytime(api_client, monkeypatch, daytime_on):
    client, _, _ = api_client
    from app.api.routes import stocks

    async def fake_us_many(symbols, period="6mo", with_news=True):
        return {s: analyzed(s, "US", 304.41) for s in symbols}

    async def fake_live(items):
        return {}

    async def fake_news(keys):
        return {}
    monkeypatch.setattr(stocks, "analyze_us_many", fake_us_many)
    monkeypatch.setattr(stocks, "live_prices", fake_live)
    monkeypatch.setattr(stocks, "get_news_many", fake_news)
    monkeypatch.setattr(stock_master, "get", lambda m, s: {"name": "브로드컴"} if (m, s) == ("US", "AVGO") else None)
    body = client.get("/api/stocks/quote/US/AVGO").json()
    assert body["daytime"]["price"] == 320.53 and "candles" not in body
    assert client.get("/api/stocks/quote/XX/AVGO").status_code == 400


def test_recommendations_daytime(api_client, monkeypatch, daytime_on):
    client, _, _ = api_client
    from app.api.routes import stocks

    async def fake_live(kind):
        return {"items": [{"symbol": "AVGO", "market": "US", "price": 304.41},
                          {"symbol": "005930", "market": "KR", "price": 177800}], "errors": []}
    monkeypatch.setattr(stocks, "_live", fake_live)
    items = client.get("/api/stocks/recommendations/longterm").json()["items"]
    assert items[0]["daytime"]["price"] == 320.53 and "daytime" not in items[1]
    assert client.get("/api/stocks/recommendations/nope").status_code == 404


def test_screener_us_after_hours(api_client, monkeypatch):
    """종목탐색 미국 표: 애프터마켓이면 daytime(시간외 가격), _ext 원값은 응답에 안 나감"""
    import datetime as dt
    from zoneinfo import ZoneInfo
    from app.api.routes import stocks
    from app.services import market_calendar
    client, _, _ = api_client
    ses = market_calendar.us_ext_session(dt.datetime(2026, 11, 25, 19, 40, tzinfo=ZoneInfo("America/New_York")))
    monkeypatch.setattr(us_daytime, "us_ext_session", lambda: ses)
    t = dt.datetime(2026, 11, 25, 19, 35, tzinfo=ZoneInfo("America/New_York")).timestamp()
    monkeypatch.setattr(stocks, "_us_screener_sync", lambda mode: [
        {"symbol": "NVDA", "name": "엔비디아", "market": "US", "price": 149.3, "change_rate": -3.91,
         "_ext": {"post": {"price": 151.68, "time": t}}}])
    stocks._screener_swr["us"].invalidate() if hasattr(stocks._screener_swr["us"], "invalidate") else None
    rows = client.get("/api/stocks/screener/us/trading_value").json()
    assert rows[0]["price"] == 149.3 and rows[0]["daytime"]["price"] == 151.68 and "_ext" not in rows[0]
