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
