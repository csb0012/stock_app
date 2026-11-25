"""AI 모의투자: 매매 규칙·체결 계산 · 미래 데이터 미사용 · 시장 상태/이벤트 반영 · API (과거 시뮬레이션·실시간 계좌)"""
import datetime as dt
import time

import numpy as np
import pytest

from tests.conftest import run
from app.services import paper_engine as pe


def series(n, seed, drift=0.0005, start=dt.date(2024, 1, 2), vol=0.02):
    rng = np.random.default_rng(seed)
    p = 100 * np.cumprod(1 + rng.normal(drift, vol, n))
    out, d = [], start
    for x in p:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        o = x * (1 + rng.normal(0, 0.005))
        out.append({"date": d.isoformat(), "open": o, "high": max(o, x) * 1.01, "low": min(o, x) * 0.99, "close": x,
                    "volume": float(rng.integers(500_000, 2_000_000))})
        d += dt.timedelta(days=1)
    return out


def universe(k=8, n=360):
    return {f"S{i}": {"name": f"종목{i}", "candles": series(n, i)} for i in range(k)}


# ---------------- 규칙 · 계산 ----------------

def test_clean_params_defaults_and_range():
    p = pe.clean_params({})
    assert p["max_positions"] == 5 and p["stop_pct"] == 7.0 and p["trailing"] is True
    assert pe.clean_params({"max_positions": "3", "trailing": False}) == {**p, "max_positions": 3, "trailing": False}
    with pytest.raises(ValueError, match="손절"):
        pe.clean_params({"stop_pct": 50})
    with pytest.raises(ValueError, match="매도 기준"):
        pe.clean_params({"buy_score": 55, "sell_score": 55})
    with pytest.raises(ValueError, match="숫자"):
        pe.clean_params({"max_hold": "abc"})
    with pytest.raises(ValueError, match="시작 자금"):
        pe.check_capital("KR", 100)
    assert pe.check_capital("US", None) == pe.CAPITAL["US"][0]


def test_ai_score_weights():
    assert pe.ai_score(50, 50, None, False) == 50
    assert pe.ai_score(None, None, None, False) == 50                # 데이터 없으면 중립
    assert pe.ai_score(65, 99, 80, True) == 100 or pe.ai_score(65, 99, 80, True) >= 99
    assert pe.ai_score(35, 1, 0, True) < 15
    assert pe.ai_score(60, 70, 90, False) < pe.ai_score(60, 70, 90, True)   # 제외 조건이면 매집 가산 없음
    assert pe.ai_score(60, 70, 30, True) == pe.ai_score(60, 70, None, False)  # 40점 이하는 가산 0


def test_fill_buy_sell_costs_and_pnl():
    params = pe.clean_params({})
    st = pe.new_state(1_000_000)
    t = pe.fill_buy(st, "A", "가", 300_000, 10_000, "2026-01-02", "r", params, "KR")
    c = pe.COSTS["KR"]
    px = 10_000 * (1 + c["slip"])
    assert t["qty"] == 29 and abs(t["price"] - px) < 1e-6
    assert abs(st["cash"] - (1_000_000 - 29 * px * (1 + c["fee"]))) < 1e-6
    assert st["positions"]["A"]["stop"] == pytest.approx(px * 0.93)
    s = pe.fill_sell(st, "A", 11_000, "2026-01-05", "목표", "KR")
    sp = 11_000 * (1 - c["slip"])
    expect = 29 * sp * (1 - c["fee"] - c["tax"]) - 29 * px * (1 + c["fee"])
    assert s["pnl"] == pytest.approx(expect, abs=0.01) and st["positions"] == {}
    assert st["cash"] == pytest.approx(1_000_000 + expect, abs=0.01)
    assert pe.fill_buy(st, "B", "나", 5_000, 10_000, "d", "r", params, "KR") is None   # 1주도 못 삼


def test_intraday_exit_order():
    p = {"stop": 93.0, "target": 115.0, "avg": 100.0}
    assert pe.intraday_exit(p, 90, 95, 89)[0] == 90           # 갭하락 → 시가
    assert pe.intraday_exit(p, 100, 120, 92)[0] == 93.0       # 손절·목표 둘 다 → 손절 먼저 (보수적)
    assert pe.intraday_exit(p, 116, 118, 114)[0] == 116       # 갭상승 → 시가
    assert pe.intraday_exit(p, 100, 116, 99)[0] == 115.0
    assert pe.intraday_exit(p, 100, 110, 95) is None


def test_trailing_stop_and_hold_days():
    params = pe.clean_params({"stop_pct": 10})
    st = pe.new_state(1e6)
    pe.fill_buy(st, "A", "가", 1e5, 100, "d0", "r", params, "US")
    pe.after_close(st, {"A": 100, "__day__": "d0"}, params)
    assert st["positions"]["A"]["hold_days"] == 0
    pe.after_close(st, {"A": 130, "__day__": "d1"}, params)
    p = st["positions"]["A"]
    assert p["hold_days"] == 1 and p["stop"] == pytest.approx(117.0)   # 최고 종가 130 의 -10%
    pe.after_close(st, {"A": 120, "__day__": "d2"}, params)
    assert p["stop"] == pytest.approx(117.0)                          # 내려가지는 않음


def _rows(scores: dict, close=100.0, prob=60):
    return {s: {"name": s, "close": close, "prob": prob, "quant": 80, "grade": "A", "accum": None, "accum_ok": False,
                "score": sc} for s, sc in scores.items()}


def test_decide_regime_cap_and_event_half():
    params = pe.clean_params({"max_positions": 5})
    rows = _rows({f"S{i}": 80 - i for i in range(8)})
    st = pe.new_state(1_000_000)
    up, _ = pe.decide(st, rows, "상승 추세", [], params, "US")
    assert len(up) == 5 and all(o["budget"] == pytest.approx(200_000) for o in up)
    assert [o["symbol"] for o in up] == ["S0", "S1", "S2", "S3", "S4"]           # 점수 높은 순
    down, notes = pe.decide(st, rows, "하락 추세", [], params, "US")
    assert sum(o["budget"] for o in down) <= 300_000 + 1 and any("30%" in n for n in notes)
    ev, notes = pe.decide(st, rows, "상승 추세", ["FOMC 금리결정 발표일"], params, "US")
    assert all(o["budget"] == pytest.approx(100_000) for o in ev) and "절반" in ev[0]["reason"]
    low, notes = pe.decide(st, _rows({"A": 55}), "상승 추세", [], params, "US")
    assert low == [] and any("맞는 종목 없음" in n for n in notes)


def test_decide_sell_rules():
    params = pe.clean_params({"max_hold": 5})
    st = pe.new_state(1e6)
    for s in ("A", "B", "C", "D"):
        pe.fill_buy(st, s, s, 1e5, 100, "d", "r", params, "US")
    st["positions"]["C"]["hold_days"] = 5
    rows = {**_rows({"A": 30}), **_rows({"B": 60}, prob=38), **_rows({"C": 60}), **_rows({"D": 60})}
    orders, _ = pe.decide(st, rows, "상승 추세", [], params, "US")
    sells = {o["symbol"]: o["reason"] for o in orders if o["side"] == "sell"}
    assert set(sells) == {"A", "B", "C"}
    assert "매도 기준" in sells["A"] and "40%" in sells["B"] and "최대 보유일" in sells["C"]


def test_event_labels():
    macro = [{"date": "2026-11-25", "event": "미국 GDP"}]
    assert pe.event_labels("US", "2026-11-25", macro) == ["GDP 발표일"]
    assert pe.event_labels("KR", "2026-11-26", macro) == ["간밤 미국 GDP 결과 반영"]
    assert pe.event_labels("KR", "2026-11-25", macro) == []
    assert "옵션 만기일" in pe.event_labels("KR", "2026-11-12", [])          # 둘째 목요일
    assert any("위칭" in x for x in pe.event_labels("US", "2026-12-18", []))  # 12월 셋째 금요일


# ---------------- 시뮬레이션 ----------------

def _sim(stocks, idx, start, end):
    return pe.simulate(stocks, idx, [], "US", 100_000, start, end, pe.clean_params({"max_positions": 3}))


def test_simulate_accounting_and_shape():
    stocks, idx = universe(), series(360, 99, 0.0003)
    dates = [c["date"] for c in stocks["S0"]["candles"]]
    r = _sim(stocks, idx, dates[280], dates[-1])
    s = r["summary"]
    assert r["days"] == len(r["equity"]) == len(r["log"]) == 80
    assert r["equity"][0]["equity"] == pytest.approx(100_000)       # 첫날은 판단만 (체결은 다음 날 시가)
    assert s["final_equity"] == r["equity"][-1]["equity"]
    held = sum(p["value"] for p in r["positions"])
    assert r["equity"][-1]["cash"] + held == pytest.approx(s["final_equity"], rel=1e-6)
    assert s["bench_return_pct"] is not None and s["mdd_pct"] <= 0
    buys = [t for t in r["trades"] if t["side"] == "buy"]
    assert buys and all(t["date"] > dates[280] for t in buys)        # 판단 다음 날부터 체결
    # 매수 체결가 = 그날 시가(+슬리피지) — 판단한 날 종가가 아님
    bars = {(s_, c["date"]): c for s_, v in stocks.items() for c in v["candles"]}
    for t in buys:
        if "손절" not in t["reason"]:
            assert t["price"] == pytest.approx(bars[(t["symbol"], t["date"])]["open"] * (1 + pe.COSTS["US"]["slip"]), rel=1e-6)
    assert all(len(p) <= 3 for p in [r["positions"]])


def test_simulate_no_future_data():
    """X 일 이후 데이터를 바꿔도 X 일까지의 판단·체결·자산은 같아야 함 (다음 날 데이터를 모르는 상태)"""
    stocks, idx = universe(), series(360, 99, 0.0003)
    dates = [c["date"] for c in stocks["S0"]["candles"]]
    start, cut = dates[280], dates[320]
    a = _sim(stocks, idx, start, dates[-1])
    stocks2 = {k: {"name": v["name"], "candles": [dict(c) for c in v["candles"]]} for k, v in stocks.items()}
    rng = np.random.default_rng(7)
    for v in stocks2.values():
        for c in v["candles"]:
            if c["date"] > cut:
                f = float(rng.uniform(0.5, 1.8))
                for k in ("open", "high", "low", "close"):
                    c[k] *= f
    idx2 = [dict(c, close=c["close"] * (0.7 if c["date"] > cut else 1)) for c in idx]
    b = _sim(stocks2, idx2, start, dates[-1])
    la = [x for x in a["log"] if x["date"] <= cut]
    lb = [x for x in b["log"] if x["date"] <= cut]
    assert la == lb                                    # 판단(주문 사유 포함)·자산 동일
    assert [t for t in a["trades"] if t["date"] <= cut] == [t for t in b["trades"] if t["date"] <= cut]
    assert a["log"] != b["log"]                        # 이후는 실제로 달라짐 (테스트가 의미 있는지)


def test_simulate_too_short():
    stocks = universe(3, 200)
    with pytest.raises(ValueError, match="부족"):
        pe.simulate(stocks, series(200, 9), [], "US", 1e5, "2030-01-01", "2030-02-01", pe.clean_params({}))


# ---------------- API ----------------

@pytest.fixture
def api_client(monkeypatch, tmp_path):
    """conftest 의 api_client 와 같지만 임시 파일 DB — 백그라운드 작업과 화면 요청이 각자 연결을 쓰게
    (메모리 DB 는 연결 하나를 같이 써서 한쪽의 rollback 이 다른 쪽의 쓰기를 지울 수 있음)"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.database import Base, get_db
    from app.api.routes import papertrade as paper_route
    from app.api.routes.auth import get_current_user
    from app.models import user as user_model, watchlist as _w, portfolio as _p, paper as _pp  # noqa: F401
    from app.services import papertrade

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as s:
            u = user_model.User(username="tester", hashed_password="x")
            s.add(u)
            await s.commit()
            await s.refresh(u)
            return u
    user = run(setup())

    async def _db():
        async with Session() as s:
            yield s
    app = FastAPI()
    app.include_router(paper_route.router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(papertrade, "AsyncSessionLocal", Session)
    with TestClient(app) as client:
        yield client, Session, user
    run(engine.dispose())


def _recent_universe(k, n):
    """오늘 근처에서 끝나는 가짜 일봉 (시뮬레이션 기간 = 오늘부터 거꾸로 N개월)"""
    start = dt.date.today() - dt.timedelta(days=int(n * 7 / 5) + 3)
    return {f"S{i}": {"name": f"종목{i}", "candles": series(n, i, start=start)} for i in range(k)}


def _fake_data(monkeypatch, n=360):
    from app.services import papertrade
    stocks = _recent_universe(6, n)
    start = dt.date.today() - dt.timedelta(days=int(n * 7 / 5) + 3)

    async def fetch_stocks(market, items, kr_count, us_period):
        return {k: dict(v) for k, v in stocks.items()}, ["X(X): 일봉 0개"]

    async def fetch_index(market, period):
        return series(n, 99, 0.0003, start=start)

    async def macro(start, end):
        return [], ["FRED_API_KEY 없음"]

    async def live_prices(items):
        return {(i["market"], i["symbol"]): {"price": stocks[i["symbol"]]["candles"][-1]["close"]} for i in items}

    monkeypatch.setattr(papertrade, "fetch_stocks", fetch_stocks)
    monkeypatch.setattr(papertrade, "fetch_index", fetch_index)
    monkeypatch.setattr(papertrade, "macro_events", macro)
    from app.services import quote
    monkeypatch.setattr(quote, "live_prices", live_prices)
    return stocks


def _wait(client, url, done, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(url).json()
        if done(r):
            return r
        time.sleep(0.3)
    raise AssertionError(f"시간 초과: {r}")


def test_api_simulation_flow(api_client, monkeypatch):
    client, Session, user = api_client
    _fake_data(monkeypatch)
    from app.services import papertrade
    monkeypatch.setattr(papertrade, "base_universe", lambda m: [{"symbol": f"S{i}", "name": f"종목{i}"} for i in range(6)])
    cfg = client.get("/api/paper/config").json()
    assert cfg["markets"]["KR"]["capital"] == 10_000_000 and cfg["months"] == [1, 3, 6, 12, 24]
    assert client.post("/api/paper/simulations", json={"market": "JP", "months": 3}).status_code == 422
    assert client.post("/api/paper/simulations", json={"market": "US", "months": 5}).status_code == 422
    assert client.post("/api/paper/simulations", json={"market": "US", "months": 3, "capital": 10}).status_code == 422
    r = client.post("/api/paper/simulations", json={"market": "US", "months": 3, "capital": 50_000,
                                                     "params": {"max_positions": 3}})
    assert r.status_code == 200 and r.json()["status"] == "running"
    sid = r.json()["id"]
    d = _wait(client, f"/api/paper/simulations/{sid}", lambda x: x["status"] != "running")
    assert d["status"] == "done", d.get("error")
    res = d["result"]
    for k in ("summary", "equity", "trades", "log", "positions", "notes", "universe", "benchmark", "params"):
        assert k in res
    assert res["summary"]["capital"] == 50_000 and res["params"]["max_positions"] == 3
    assert any("FRED" in n for n in res["notes"]) and any("일봉 못 받은" in n for n in res["notes"])
    lst = client.get("/api/paper/simulations").json()
    assert lst["items"][0]["id"] == sid and "result" not in lst["items"][0] and lst["items"][0]["summary"]
    assert client.delete(f"/api/paper/simulations/{sid}").status_code == 200
    assert client.get(f"/api/paper/simulations/{sid}").status_code == 404


def test_api_simulation_failure_is_reported(api_client, monkeypatch):
    client, Session, user = api_client
    from app.services import papertrade

    async def boom(*a, **k):
        raise RuntimeError("KIS 연결 실패 (테스트)")
    monkeypatch.setattr(papertrade, "fetch_stocks", boom)
    sid = client.post("/api/paper/simulations", json={"market": "KR", "months": 1}).json()["id"]
    d = _wait(client, f"/api/paper/simulations/{sid}", lambda x: x["status"] != "running")
    assert d["status"] == "failed" and "KIS 연결 실패" in d["error"]


def test_api_live_account_flow(api_client, monkeypatch):
    client, Session, user = api_client
    stocks = _fake_data(monkeypatch)
    from app.services import papertrade, quote
    monkeypatch.setattr(papertrade, "base_universe", lambda m: [{"symbol": f"S{i}", "name": f"종목{i}"} for i in range(6)])
    monkeypatch.setattr(papertrade, "_closed_only", lambda m, c: c)
    monkeypatch.setattr(papertrade, "is_market_open", lambda m: True)        # 장중 → 판단 후 바로 체결

    def fake_analyze(market, candles, *a):
        return {"prediction": {"probability": 70}}
    monkeypatch.setattr(quote, "analyze_candles", fake_analyze)
    assert client.post("/api/paper/accounts", json={"market": "US", "capital": 5}).status_code == 422
    r = client.post("/api/paper/accounts", json={"market": "US", "capital": 100_000, "name": "테스트",
                                                  "params": {"max_positions": 2, "buy_score": 55, "sell_score": 40}})
    assert r.status_code == 200
    aid = r.json()["id"]
    d = _wait(client, f"/api/paper/accounts/{aid}", lambda x: x["log"] and x["trades"])
    assert d["name"] == "테스트" and d["market"] == "US" and d["last_error"] is None
    assert len(d["positions"]) <= 2 and d["positions"] and d["pending"] == []
    buy = d["trades"][-1]
    assert buy["side"] == "buy" and "AI 점수" in buy["reason"] and "상승확률 70%" in buy["reason"]
    assert d["cash"] < 100_000 and d["equity"] == pytest.approx(d["cash"] + sum(p["value"] for p in d["positions"]), rel=1e-6)
    assert d["equity_curve"] and d["equity_curve"][0]["bench"] == pytest.approx(100_000)
    assert d["log"][0].get("fills") or d["log"][-1].get("orders")
    lst = client.get("/api/paper/accounts").json()["items"]
    assert lst[0]["id"] == aid and "trades" not in lst[0]

    # 손절: 현재가를 손절가 아래로
    sym = d["positions"][0]["symbol"]

    async def crash(items):
        return {(i["market"], i["symbol"]): {"price": 1.0} for i in items}
    monkeypatch.setattr(quote, "live_prices", crash)
    assert run(papertrade.check_exits(aid)) >= 1
    d2 = client.get(f"/api/paper/accounts/{aid}").json()
    assert all(p["symbol"] != sym for p in d2["positions"])
    assert any(t["side"] == "sell" and "손절" in t["reason"] and t["pnl"] < 0 for t in d2["trades"])

    assert client.put(f"/api/paper/accounts/{aid}/active", params={"active": False}).json()["active"] is False
    assert client.delete(f"/api/paper/accounts/{aid}").status_code == 200
    assert client.get(f"/api/paper/accounts/{aid}").status_code == 404


def test_api_account_limit_and_ownership(api_client, monkeypatch):
    client, Session, user = api_client
    from app.services import papertrade
    from app.models.paper import PaperAccount

    async def noop(acc_id, manual=False):
        return {"ok": True}
    monkeypatch.setattr(papertrade, "decide_account", noop)
    for _ in range(papertrade.MAX_ACCOUNTS):
        assert client.post("/api/paper/accounts", json={"market": "KR"}).status_code == 200
    r = client.post("/api/paper/accounts", json={"market": "KR"})
    assert r.status_code == 422 and "5개까지" in r.json()["detail"]

    async def other():
        async with Session() as s:
            a = PaperAccount(user_id=999, market="KR", capital=1e7, params="{}", state='{"cash": 1, "positions": {}}')
            s.add(a)
            await s.commit()
            return a.id
    oid = run(other())
    assert client.get(f"/api/paper/accounts/{oid}").status_code == 404
    assert client.delete(f"/api/paper/accounts/{oid}").status_code == 404


def test_closed_only_drops_unfinished_today(monkeypatch):
    from app.services import papertrade
    today = papertrade.market_today("US").isoformat()
    cs = [{"date": "2020-01-02"}, {"date": today}]
    monkeypatch.setattr(papertrade, "session_hours", lambda m, d: (0, 24 * 60))   # 아직 장중
    assert papertrade._closed_only("US", cs) == cs[:1]
    monkeypatch.setattr(papertrade, "session_hours", lambda m, d: (0, -1))         # 이미 마감
    assert papertrade._closed_only("US", cs) == cs


def test_auto_decision_skips_if_already_done_today(api_client, monkeypatch):
    """계좌를 만들며 판단한 직후 자동 실행(tick)이 같은 날 또 판단하지 않음 (KIS 호출 낭비 방지)"""
    client, Session, user = api_client
    from app.services import papertrade
    from app.models.paper import PaperAccount

    async def setup():
        async with Session() as s:
            a = PaperAccount(user_id=user.id, market="KR", capital=1e7, params="{}", state='{"cash": 1e7, "positions": {}}',
                             last_decision_day=papertrade.market_today("KR").isoformat())
            s.add(a)
            await s.commit()
            return a.id
    aid = run(setup())

    async def boom(*a, **k):
        raise AssertionError("다시 판단하면 안 됨")
    monkeypatch.setattr(papertrade, "_live_universe", boom)
    assert run(papertrade.decide_account(aid))["skipped"]
    with pytest.raises(AssertionError):
        run(papertrade.decide_account(aid, manual=True))      # 수동 실행은 그래도 함


def test_sim_save_retries_when_db_locked(api_client, monkeypatch):
    """백테스트가 큰 저장을 하는 동안 DB 가 잠겨 몇 분 계산한 시뮬레이션 결과가 'database is locked' 로 버려졌음
    (2026-11-25 사용자 PC) → 잠금이면 기다렸다가 다시 저장"""
    import sqlite3
    import threading
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.services import papertrade
    from app.models.paper import PaperSim
    client, Session, user = api_client
    path = Session.kw["bind"].url.database
    # 잠금을 빨리 포기하는 연결 (실제 PC 의 느린 디스크에서 5초 한도를 넘긴 상황 흉내)
    eng = create_async_engine(f"sqlite+aiosqlite:///{path}", connect_args={"timeout": 0.5})
    Fast = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(papertrade, "AsyncSessionLocal", Fast)
    monkeypatch.setattr(papertrade, "SAVE_RETRY_WAITS", (1, 1, 2))

    async def mk():
        async with Fast() as s:
            sim = PaperSim(user_id=user.id, market="KR", capital=1e7, months=1, params="{}")
            s.add(sim)
            await s.commit()
            return sim.id
    sid = run(mk())
    locked = threading.Event()

    def hold():
        c = sqlite3.connect(path)
        c.execute("BEGIN EXCLUSIVE")
        locked.set()
        time.sleep(2.5)            # 첫 저장·첫 재시도는 실패, 그 뒤엔 성공해야 함
        c.rollback()
        c.close()
    th = threading.Thread(target=hold)
    th.start()
    locked.wait()
    run(papertrade._save_sim(sid, status="done", summary='{"return_pct": 1}'))
    th.join()

    async def get():
        async with Fast() as s:
            return await s.get(PaperSim, sid)
    sim = run(get())
    run(eng.dispose())
    assert sim.status == "done" and sim.summary and sim.finished_at is not None

    # 잠금이 아닌 오류는 바로 올림 (다시 시도 안 함)
    monkeypatch.setattr(papertrade, "AsyncSessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("다른 오류")))
    with pytest.raises(RuntimeError, match="다른 오류"):
        run(papertrade._save_sim(sid, status="done"))


def test_db_wait_limit_is_long():
    """다른 연결이 쓰는 동안 기다리는 한도 (기본 5초면 느린 디스크에서 큰 저장 중 'database is locked')"""
    from app.core import database
    assert database.DB_TIMEOUT >= 30
