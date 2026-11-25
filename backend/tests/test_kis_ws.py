"""KIS 실시간 체결가 웹소켓 — 메시지 해석 · 구독 목록 · 오래된 값 안 씀 · PINGPONG · 현재가가 REST 대신 실시간 값을 씀"""
import asyncio
import datetime as dt
import json

import pytest

from tests.conftest import run
from app.services import kis_ws

# KIS 문서 예시와 같은 형식 (H0STCNT0 한 건 = 46 필드)
REC = ("005930^093354^71900^5^-100^-0.14^72023.83^72100^72400^71700^71900^71800^1^3052507^219853241700^5105^6937^1832^84.90^"
       "1366314^1159996^1^0.39^20.28^090020^5^-200^090820^5^-500^092619^2^200^20231218^20^N^65945^216924^1118750^2053292^0.05^"
       "5571923^54.79^0^^72100")
REC2 = REC.replace("005930^093354^71900", "000660^093355^135000", 1)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    kis_ws._prices.clear()
    kis_ws._interest.clear()
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(kis_ws, "_now", lambda: clock["t"])
    return clock


def test_parse_single_and_multi():
    assert len(REC.split("^")) == 46
    r = kis_ws.parse(f"0|H0STCNT0|001|{REC}")
    assert r == [{"symbol": "005930", "time": "093354", "price": 71900, "change": -100.0, "change_rate": -0.14, "volume": 3052507}]
    two = kis_ws.parse(f"0|H0STCNT0|002|{REC}^{REC2}")
    assert [x["symbol"] for x in two] == ["005930", "000660"] and two[1]["price"] == 135000
    assert kis_ws.parse("1|H0STCNI0|001|암호문") == [] and kis_ws.parse("0|H0STASP0|001|x^y") == []
    assert kis_ws.parse('{"header":{"tr_id":"PINGPONG"}}') == [] and kis_ws.parse("0|H0STCNT0|001|a^b") == []


def test_interest_ttl_cap_and_freshness(clean):
    kis_ws.want(["005930", "bad!", "000660"])
    assert set(kis_ws.desired()) == {"005930", "000660"}
    clean["t"] += kis_ws.INTEREST_TTL + 1
    kis_ws.want(["035420"])
    assert kis_ws.desired() == ["035420"]          # 2분 동안 안 물은 종목은 구독 해제
    kis_ws.want([f"{i:06d}" for i in range(60)])
    assert len(kis_ws.desired()) == kis_ws.MAX_SUBS
    kis_ws._store(kis_ws.parse(f"0|H0STCNT0|001|{REC}"))
    assert kis_ws.get("005930")["price"] == 71900
    clean["t"] += kis_ws.FRESH + 1
    assert kis_ws.get("005930") is None            # 오래된 값은 실시간으로 안 씀


class FakeWS:
    def __init__(self, incoming):
        self.incoming, self.sent = list(incoming), []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, m):
        self.sent.append(m)

    async def recv(self):
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.sleep(5)


def test_session_subscribes_echoes_ping_and_stores(monkeypatch, clean):
    ping = json.dumps({"header": {"tr_id": "PINGPONG", "datetime": "20261126093000"}})
    ok = json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "005930"}, "body": {"rt_cd": "0", "msg1": "SUBSCRIBE SUCCESS"}})
    ws = FakeWS([ok, ping, f"0|H0STCNT0|001|{REC}"])
    calls = {"n": 0}

    def session_open():
        calls["n"] += 1
        return calls["n"] < 6        # 메시지 3개를 받은 뒤 장 마감으로

    async def key():
        return "approval-xyz"
    monkeypatch.setattr(kis_ws, "approval_key", key)
    monkeypatch.setattr(kis_ws, "in_session", session_open)
    kis_ws.want(["005930"])
    assert run(kis_ws.session(lambda url: ws)) == "장 시간 끝"
    sub = json.loads(ws.sent[0])
    assert sub["header"] == {"approval_key": "approval-xyz", "custtype": "P", "tr_type": "1", "content-type": "utf-8"}
    assert sub["body"]["input"] == {"tr_id": "H0STCNT0", "tr_key": "005930"}
    assert ping in ws.sent                           # PINGPONG 은 그대로 돌려보냄
    assert kis_ws.get("005930")["price"] == 71900
    assert kis_ws._status["connected"] is False


def test_session_unsubscribes_and_ends_when_nobody_watches(monkeypatch, clean):
    ws = FakeWS([])
    monkeypatch.setattr(kis_ws, "in_session", lambda: True)

    async def key():
        return "k"
    monkeypatch.setattr(kis_ws, "approval_key", key)
    kis_ws.want(["005930"])
    real_sleep = asyncio.sleep

    async def fast_recv():
        clean["t"] += 40          # 1초 기다릴 때마다 시계를 40초씩
        await real_sleep(0)
        raise asyncio.TimeoutError
    monkeypatch.setattr(ws, "recv", fast_recv)
    monkeypatch.setattr(kis_ws.asyncio, "wait_for", lambda coro, timeout: coro)
    assert run(kis_ws.session(lambda url: ws)) == "보는 종목 없음"
    kinds = [json.loads(m)["header"]["tr_type"] for m in ws.sent]
    assert kinds == ["1", "2"]                       # 2분 지나 구독 해제 → 1분 더 아무도 안 보면 끊음


def test_in_session_hours():
    kst = kis_ws._TZ["KR"]
    assert kis_ws.in_session(dt.datetime(2026, 11, 24, 9, 0, tzinfo=kst))
    assert not kis_ws.in_session(dt.datetime(2026, 11, 24, 15, 40, tzinfo=kst))
    assert not kis_ws.in_session(dt.datetime(2026, 11, 22, 10, 0, tzinfo=kst))   # 일요일


def test_live_endpoint_and_live_prices_use_ws(api_client, monkeypatch, clean):
    from app.services import quote
    from app.services.kis_api import kis_client
    client, Session, user = api_client
    r = client.get("/api/stocks/live", params={"symbols": "005930,000660"}).json()
    assert r["items"] == {} and set(kis_ws.desired()) == {"005930", "000660"}     # 물으면 구독 목록에 올라감
    kis_ws._store(kis_ws.parse(f"0|H0STCNT0|001|{REC}"))
    r = client.get("/api/stocks/live", params={"symbols": "005930,000660"}).json()
    assert r["items"]["005930"] == {"price": 71900, "change": -100.0, "change_rate": -0.14, "volume": 3052507, "time": "093354", "age": 0.0}
    asked = []

    async def multi(codes):
        asked.append(list(codes))
        return {c: {"price": 1, "change_rate": 0.0, "volume": 1} for c in codes}
    monkeypatch.setattr(kis_client, "get_kr_multi_price", multi)
    out = run(quote.live_prices([{"market": "KR", "symbol": "005930"}, {"market": "KR", "symbol": "000660"}]))
    assert out[("KR", "005930")]["price"] == 71900 and asked == [["000660"]]   # 실시간 값이 있는 종목은 REST 안 부름


def test_analyze_items_keeps_symbols_with_live_price(monkeypatch, clean):
    """실시간 가격이 있는 국내 종목이 관심종목·투자종목 분석(analyze_items)에서 빠져 '분석 결과 없음'이 뜨던 문제 (2026-11-25 점검에서 발견)
    — 실시간 값은 현재가(live_prices)에만 쓰고, 분석 목록에서는 빼지 않음"""
    from app.services import quote
    kis_ws._store(kis_ws.parse(f"0|H0STCNT0|001|{REC}"))
    asked = []

    async def kr_many(symbols, count=100, with_news=True):
        asked.extend(symbols)
        return {s: {"symbol": s, "market": "KR", "current_price": 1} for s in symbols}
    monkeypatch.setattr(quote, "analyze_kr_many", kr_many)
    out = run(quote.analyze_items([{"market": "KR", "symbol": "005930"}, {"market": "KR", "symbol": "000660"}]))
    assert asked == ["005930", "000660"] and set(out) == {("KR", "005930"), ("KR", "000660")}
