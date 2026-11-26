"""미국 주간거래 가격: 시간 판단 · KIS 응답 변환 · 캐시 · 목록에 붙이기"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import run
from app.services import us_daytime, market_calendar
from app.services.kis_api import kis_client, KISError

KST = ZoneInfo("Asia/Seoul")


def kst(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=KST)


# ---------------- 주간거래 시간 ----------------

@pytest.mark.parametrize("when, expected", [
    (kst(2026, 11, 23, 9, 59), False),    # 월요일 개장 전
    (kst(2026, 11, 23, 10, 0), True),     # 개장
    (kst(2026, 11, 23, 17, 31), True),    # 사용자 화면 시각 (토스 320.53 을 본 시간)
    (kst(2026, 11, 23, 17, 59), True),
    (kst(2026, 11, 23, 18, 0), False),    # 겨울: 미국 04:00 ET = 한국 18:00 → 프리마켓으로 넘어감
    (kst(2026, 11, 21, 12, 0), False),    # 토요일
    (kst(2026, 11, 22, 12, 0), False),    # 일요일
    (kst(2026, 11, 26, 12, 0), False),    # 미국 추수감사절(휴장) — 한국은 평일이지만 미국 거래일 아님
    (kst(2026, 7, 6, 16, 59), True),      # 서머타임: 미국 04:00 EDT = 한국 17:00
    (kst(2026, 7, 6, 17, 0), False),
])
def test_session_window(when, expected):
    s = market_calendar.us_daytime_session(when)
    assert s["open"] is expected
    assert s["session_date"] == when.date().isoformat()


def test_session_hours_text_winter_summer():
    assert market_calendar.us_daytime_session(kst(2026, 11, 23, 12, 0))["hours_kst"] == "10:00~18:00"
    assert market_calendar.us_daytime_session(kst(2026, 7, 6, 12, 0))["hours_kst"] == "10:00~17:00"


def test_market_status_has_daytime_only_for_us():
    assert "daytime" in market_calendar.market_status("US")
    assert "daytime" not in market_calendar.market_status("KR")


# ---------------- KIS 응답 → 화면 값 ----------------

SESSION = {"open": True, "session_date": "2026-11-23", "hours_kst": "10:00~18:00", "end_kst": "18:00"}


def test_build_computes_change_from_base():
    # 브로드컴: 금요일 종가 304.41, 주간거래 320.53 → +5.30%
    v = us_daytime.build({"price": 320.53, "base": 304.41, "change": 0, "change_rate": 0, "volume": 1200},
                         SESSION, kst(2026, 11, 23, 17, 31).timestamp())
    assert v["price"] == 320.53 and v["base"] == 304.41
    assert v["change"] == pytest.approx(16.12, abs=0.01)
    assert v["change_rate"] == pytest.approx(5.30, abs=0.01)
    assert v["time"] == "17:31" and v["label"] == "주간거래"


def test_build_down_and_flat_and_no_trade():
    down = us_daytime.build({"price": 95.0, "base": 100.0}, SESSION, 0)
    assert down["change_rate"] == -5.0 and down["change"] == -5.0
    flat = us_daytime.build({"price": 100.0, "base": 100.0}, SESSION, 0)
    assert flat["change_rate"] == 0.0                     # -0.0 이 아니라 0.0
    assert us_daytime.build({"price": 0, "base": 100.0}, SESSION, 0) is None   # 체결 없음
    assert us_daytime.build({}, SESSION, 0) is None


def test_build_without_base_uses_kis_rate():
    v = us_daytime.build({"price": 50.0, "base": 0, "change": 1.5, "change_rate": 3.09}, SESSION, 0)
    assert v["base"] is None and v["change_rate"] == 3.09


def test_build_penny_stock_keeps_precision():
    assert us_daytime.build({"price": 0.1234, "base": 0.12}, SESSION, 0)["price"] == 0.1234


# ---------------- KIS 호출 ----------------

def test_kis_daytime_exchange_codes(monkeypatch):
    calls = []

    async def fake_get(path, tr_id, params):
        calls.append((tr_id, params["EXCD"], params["SYMB"]))
        return {"output": {"last": "320.5300", "base": "304.4100", "diff": "16.12", "rate": "5.30", "tvol": "1200"}}
    monkeypatch.setattr(kis_client, "_get", fake_get)
    r = run(kis_client.get_us_daytime_price("AVGO", "NAS"))
    run(kis_client.get_us_daytime_price("KO", "NYS"))
    run(kis_client.get_us_daytime_price("SPY", "ams"))
    assert [c[1] for c in calls] == ["BAQ", "BAY", "BAA"]
    assert calls[0][0] == "HHDFS00000300"
    assert r == {"price": 320.53, "base": 304.41, "change": 16.12, "change_rate": 5.30, "volume": 1200}
    with pytest.raises(KISError):
        run(kis_client.get_us_daytime_price("X", "HKS"))


def test_kis_daytime_empty_output(monkeypatch):
    async def fake_get(path, tr_id, params):
        return {"output": {"last": "", "base": ""}}
    monkeypatch.setattr(kis_client, "_get", fake_get)
    r = run(kis_client.get_us_daytime_price("AVGO", "NAS"))
    assert r["price"] == 0.0 and r["base"] == 0.0


# ---------------- 여러 종목 + 캐시 ----------------

@pytest.fixture
def fake_kis(monkeypatch):
    us_daytime._cache.clear()
    state = {"calls": [], "fail": set(), "prices": {"AVGO": (320.53, 304.41), "NVDA": (180.0, 176.0), "ZERO": (0, 10.0)}}

    async def fake_price(symbol, exchange):
        state["calls"].append((symbol, exchange))
        if symbol in state["fail"]:
            raise KISError("KIS HHDFS00000300 실패: 테스트 오류")
        p, b = state["prices"].get(symbol, (0, 0))
        return {"price": p, "base": b, "change": 0, "change_rate": 0, "volume": 10}
    monkeypatch.setattr(kis_client, "get_us_daytime_price", fake_price)
    monkeypatch.setattr(us_daytime, "us_daytime_session", lambda: SESSION)
    # 실제 시각이 프리·애프터마켓이어도 Yahoo 를 부르지 않게 (주간거래만 보는 테스트)
    monkeypatch.setattr(us_daytime, "us_ext_session", lambda: {"open": False, "label": None})
    yield state
    us_daytime._cache.clear()


def test_get_many_closed_session_calls_nothing(fake_kis, monkeypatch):
    monkeypatch.setattr(us_daytime, "us_daytime_session", lambda: {**SESSION, "open": False})
    assert run(us_daytime.get_many(["AVGO"])) == {}
    assert fake_kis["calls"] == []


def test_get_many_cache_and_no_trade(fake_kis):
    out = run(us_daytime.get_many(["AVGO", "NVDA", "ZERO", "AVGO"]))
    assert set(out) == {"AVGO", "NVDA"}            # 체결 없는 종목은 빠짐, 중복은 한 번만
    assert len(fake_kis["calls"]) == 3
    run(us_daytime.get_many(["AVGO", "ZERO"]))     # 30초 캐시 — 다시 안 부름 (체결 없음도 캐시)
    assert len(fake_kis["calls"]) == 3


def test_get_many_error_not_cached(fake_kis):
    fake_kis["fail"].add("NVDA")
    out = run(us_daytime.get_many(["NVDA"]))
    assert "error" in out["NVDA"] and "테스트 오류" in out["NVDA"]["error"]
    fake_kis["fail"].clear()
    out = run(us_daytime.get_many(["NVDA"]))        # 실패는 캐시 안 함 → 다음엔 성공
    assert out["NVDA"]["price"] == 180.0


def test_attach_returns_copies_and_clears_stale(fake_kis, monkeypatch):
    rows = [{"symbol": "AVGO", "market": "US", "price": 304.41},
            {"symbol": "005930", "market": "KR", "price": 177800},
            {"symbol": "NVDA", "market": "US", "daytime": {"price": 1}}]
    out = run(us_daytime.attach(rows))
    assert out[0]["daytime"]["price"] == 320.53
    assert "daytime" not in out[1]                 # 국내 종목은 안 붙임
    assert "daytime" not in rows[0]                # 원본(캐시된 행)은 안 바뀜
    # 주간거래가 끝나면 예전 daytime 이 남지 않음
    monkeypatch.setattr(us_daytime, "us_daytime_session", lambda: {**SESSION, "open": False})
    out2 = run(us_daytime.attach(rows))
    assert all("daytime" not in r for r in out2)


def test_attach_market_key_none_for_dashboard_rows(fake_kis):
    out = run(us_daytime.attach([{"symbol": "AVGO", "name": "브로드컴"}], market_key=None))
    assert out[0]["daytime"]["change_rate"] == pytest.approx(5.30, abs=0.01)


def test_attach_empty():
    assert run(us_daytime.attach([])) == []


# ---------------- 프리마켓 · 애프터마켓 (Yahoo 5분봉) ----------------
import pandas as pd

NY = ZoneInfo("America/New_York")


def et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=NY)


@pytest.mark.parametrize("when, label, hours", [
    (et(2026, 11, 25, 19, 20), "애프터마켓", "06:00~10:00"),   # 사용자가 본 시각 (한국 11/26 09:20)
    (et(2026, 11, 25, 16, 0), "애프터마켓", "06:00~10:00"),
    (et(2026, 11, 25, 15, 59), None, None),                    # 정규장
    (et(2026, 11, 25, 20, 0), None, None),                     # 애프터마켓 끝
    (et(2026, 11, 25, 3, 59), None, None),
    (et(2026, 11, 25, 4, 0), "프리마켓", "18:00~23:30"),
    (et(2026, 11, 25, 9, 29), "프리마켓", "18:00~23:30"),
    (et(2026, 11, 26, 17, 0), None, None),                     # 추수감사절 휴장
    (et(2026, 11, 28, 17, 0), None, None),                     # 토요일
    (et(2026, 7, 6, 17, 0), "애프터마켓", "05:00~09:00"),       # 서머타임
])
def test_ext_session(when, label, hours):
    s = market_calendar.us_ext_session(when)
    assert s["open"] == (label is not None) and s["label"] == label and s["hours_kst"] == hours


def test_market_status_has_extended_only_for_us():
    assert "extended" in market_calendar.market_status("US")
    assert "extended" not in market_calendar.market_status("KR")


def _bars(rows):
    """[(ET 시각, {종목: 종가})] → yf.download(여러 종목) 모양"""
    idx = pd.DatetimeIndex([t for t, _ in rows]).tz_convert(NY)
    syms = sorted({s for _, d in rows for s in d})
    close = pd.DataFrame([[d.get(s) for s in syms] for _, d in rows], index=idx, columns=syms, dtype=float)
    return pd.concat({"Close": close}, axis=1)


AFTER = market_calendar.us_ext_session(et(2026, 11, 25, 19, 20))
PRE = market_calendar.us_ext_session(et(2026, 11, 25, 5, 0))
BARS = [
    (et(2026, 11, 24, 15, 55), {"AVGO": 300.0, "NVDA": 170.0}),
    (et(2026, 11, 24, 19, 55), {"AVGO": 299.0}),                 # 전날 애프터마켓 — 오늘 프리마켓 값으로 쓰면 안 됨
    (et(2026, 11, 25, 4, 30), {"AVGO": 301.0}),
    (et(2026, 11, 25, 15, 55), {"AVGO": 304.0, "NVDA": 176.0}),
    (et(2026, 11, 25, 16, 5), {"AVGO": 306.0}),
    (et(2026, 11, 25, 19, 15), {"AVGO": 307.5}),
]


def test_yf_ext_sync_after_and_pre(monkeypatch):
    import yfinance as yf
    calls = []

    def fake_download(symbols, **kw):
        calls.append(kw)
        return _bars(BARS)
    monkeypatch.setattr(yf, "download", fake_download)
    got = us_daytime._yf_ext_sync(["AVGO", "NVDA"], AFTER)
    assert calls[0]["prepost"] is True and calls[0]["interval"] == "5m"
    assert got["AVGO"]["price"] == 307.5 and got["AVGO"]["base"] == 304.0
    assert got["AVGO"]["at"].strftime("%H:%M") == "19:15"
    assert "NVDA" not in got                     # 애프터마켓 체결 없음 → 빠짐 (종가를 시간외 가격처럼 안 보임)
    pre = us_daytime._yf_ext_sync(["AVGO"], PRE)
    assert pre["AVGO"]["price"] == 301.0 and pre["AVGO"]["base"] == 300.0   # 전날 정규장 대비


def test_yf_ext_sync_failures_are_errors(monkeypatch):
    """yfinance 는 접속 실패에도 예외 없이 빈 표를 줌 → 조용히 사라지지 않고 오류. 봉이 하나도 없는 종목도 오류 (체결 없음과 구분)"""
    import yfinance as yf
    monkeypatch.setattr(yf, "download", lambda symbols, **kw: pd.DataFrame())
    with pytest.raises(RuntimeError, match="응답 없음"):
        us_daytime._yf_ext_sync(["AVGO"], AFTER)
    monkeypatch.setattr(yf, "download", lambda symbols, **kw: _bars(BARS))
    got = us_daytime._yf_ext_sync(["AVGO", "NVDA", "GONE"], AFTER)
    assert "error" in got["GONE"] and "NVDA" not in got and got["AVGO"]["price"] == 307.5


def test_build_ext_uses_row_close():
    raw = {"price": 307.5, "base": 304.0, "at": et(2026, 11, 25, 19, 15)}
    v = us_daytime.build_ext(raw, AFTER, 304.41)   # 행의 현재가 = KIS 정규장 종가
    assert v["label"] == "애프터마켓" and v["price"] == 307.5 and v["base"] == 304.41
    assert v["change_rate"] == pytest.approx(1.02, abs=0.01)
    assert v["time"] == "09:15" and v["et_time"] == "19:15 ET" and v["source"] == "Yahoo 시간외"
    assert us_daytime.build_ext(raw, AFTER)["change_rate"] == pytest.approx(1.15, abs=0.01)   # 행 가격 없으면 Yahoo 정규장 마지막 봉


@pytest.fixture
def after_hours(monkeypatch):
    us_daytime._ext_cache.clear()
    state = {"calls": 0, "fail": False}

    def fake_sync(symbols, session):
        state["calls"] += 1
        if state["fail"]:
            raise RuntimeError("Yahoo 막힘")
        out = {s: {"price": 307.5, "base": 304.0, "at": et(2026, 11, 25, 19, 15)} for s in symbols if s == "AVGO"}
        out.update({s: {"error": "Yahoo 5분봉 없음 (이 종목 조회 실패)"} for s in symbols if s == "GONE"})
        return out
    monkeypatch.setattr(us_daytime, "_yf_ext_sync", fake_sync)
    monkeypatch.setattr(us_daytime, "us_daytime_session", lambda: {**SESSION, "open": False})
    monkeypatch.setattr(us_daytime, "us_ext_session", lambda: AFTER)
    yield state
    us_daytime._ext_cache.clear()


def test_attach_after_hours(after_hours):
    rows = [{"symbol": "AVGO", "market": "US", "current_price": 304.41},
            {"symbol": "NVDA", "market": "US", "current_price": 176.0},
            {"symbol": "005930", "market": "KR", "current_price": 177800}]
    out = run(us_daytime.attach(rows))
    d = out[0]["daytime"]
    assert d["label"] == "애프터마켓" and d["price"] == 307.5 and d["base"] == 304.41
    assert "daytime" not in out[1] and "daytime" not in out[2]
    run(us_daytime.attach(rows))                 # 60초 캐시 (체결 없음도)
    assert after_hours["calls"] == 1
    assert run(us_daytime.attach(rows, extended=False))[0].get("daytime") is None


def test_attach_after_hours_error_not_cached(after_hours):
    after_hours["fail"] = True
    out = run(us_daytime.attach([{"symbol": "AVGO", "market": "US", "price": 304.41}]))
    assert out[0]["daytime"]["label"] == "애프터마켓" and "Yahoo 막힘" in out[0]["daytime"]["error"]
    after_hours["fail"] = False
    out = run(us_daytime.attach([{"symbol": "AVGO", "market": "US", "price": 304.41}]))
    assert out[0]["daytime"]["price"] == 307.5 and after_hours["calls"] == 2
    out = run(us_daytime.attach([{"symbol": "GONE", "market": "US", "price": 1.0}]))
    assert out[0]["daytime"]["label"] == "애프터마켓" and "조회 실패" in out[0]["daytime"]["error"]
    run(us_daytime.attach([{"symbol": "GONE", "market": "US", "price": 1.0}]))
    assert after_hours["calls"] == 4                # 종목 실패도 캐시 안 함


# ---------------- 미국 스크리너 (Yahoo 시세의 pre/postMarketPrice) ----------------

def _srow(sym, price, post=None):
    r = {"symbol": sym, "name": sym, "market": "US", "price": price, "change_rate": -3.91}
    if post:
        r["_ext"] = {"post": {"price": post[0], "time": post[1].timestamp()}}
    return r


def test_attach_screener_uses_quote_fields(after_hours):
    rows = [_srow("NVDA", 149.30, (151.68, et(2026, 11, 25, 19, 35))),     # 사용자 화면: 149.30 → 애프터 151.68
            _srow("MU", 601.25, (600.0, et(2026, 11, 24, 19, 59))),        # 어제 애프터마켓 값 → 안 씀 (5분봉으로)
            _srow("AVGO", 304.41)]                                          # 시세에 시간외 없음 → 5분봉으로
    out = run(us_daytime.attach_screener(rows))
    d = out[0]["daytime"]
    assert d["label"] == "애프터마켓" and d["price"] == 151.68 and d["base"] == 149.30
    assert d["change_rate"] == pytest.approx(1.59, abs=0.01) and d["et_time"] == "19:35 ET"
    assert "daytime" not in out[1]                     # 5분봉에도 오늘 애프터 체결 없음
    assert out[2]["daytime"]["price"] == 307.5
    assert all("_ext" not in r for r in out) and "_ext" in rows[0]    # 캐시된 원본은 그대로
    assert after_hours["calls"] == 1                   # 시세에 있던 NVDA 는 따로 안 받음


def test_attach_screener_closed_and_limit(after_hours, monkeypatch):
    rows = [_srow(f"S{i}", 10.0) for i in range(50)]
    seen = []

    async def fake_many(symbols, session):
        seen.extend(symbols)
        return {}
    monkeypatch.setattr(us_daytime, "_ext_many", fake_many)
    run(us_daytime.attach_screener(rows))
    assert len(seen) == 30                              # 200종목 전부 받지 않음 (앞쪽만)
    monkeypatch.setattr(us_daytime, "us_ext_session", lambda: {"open": False, "label": None})
    out = run(us_daytime.attach_screener([_srow("NVDA", 149.3, (151.68, et(2026, 11, 25, 19, 35)))]))
    assert "daytime" not in out[0] and "_ext" not in out[0]


def test_us_screener_keeps_ext_quote_fields(monkeypatch):
    from app.api.routes import stocks
    monkeypatch.setattr(stocks.yf, "screen", lambda q, count=200: {"quotes": [
        {"symbol": "NVDA", "shortName": "NVIDIA", "regularMarketPrice": 149.3, "regularMarketChangePercent": -3.91,
         "regularMarketVolume": 100, "postMarketPrice": 151.68, "postMarketTime": 1795000000},
        {"symbol": "MU", "shortName": "Micron", "regularMarketPrice": 601.25, "regularMarketVolume": 10}]})
    rows = {r["symbol"]: r for r in stocks._us_screener_sync("trading_value")}
    assert rows["NVDA"]["_ext"] == {"post": {"price": 151.68, "time": 1795000000}}
    assert rows["MU"]["_ext"] == {}
