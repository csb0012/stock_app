"""KIS 모의투자 주문 — AI 제안 → 관리자 승인(2단계 코드) → 모의투자 서버 주문. 가짜 KIS(FakeBroker)로 안전장치를 확인
(1회 한도·하루 횟수·하루 손실 자동 정지·가격 상승·두 번 주문·잔고 대조·긴급 정지·결과 모름·실거래 서버 거부)"""
import datetime as dt
import json
from types import SimpleNamespace

import pyotp
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.conftest import run
from app.core.config import settings
from app.services import kis_order, kis_trade
from app.services.kis_api import KISClient, KISError, KIS_REAL_BASE, KIS_MOCK_BASE
from app.services.market_calendar import _TZ

KST = _TZ["KR"]
SECRET = pyotp.random_base32()


class FakeBroker:
    """KIS 모의투자 계좌 흉내: 시장가·현재가 이상 지정가는 바로 현재가로 체결 (현재가보다 낮은 지정가는 걸려 있음)"""

    def __init__(self):
        self.cash = 10_000_000
        self.prev_total = 10_000_000
        self.prices = {"005930": 70_000, "000660": 200_000}
        self.holdings = {}      # 종목 → [수량, 평균가]
        self.orders = []        # 보낸 주문
        self.fill = True
        self.fail = None
        self.vi = set()         # VI 발동 중인 종목
        self.index = 0.0        # 코스피·코스닥 중 더 빠진 쪽 등락률
        self.no_price = set()   # 실시간·REST 가격을 못 받는 종목

    async def balance(self):
        hs = [{"symbol": s, "name": f"종목{s}", "qty": q, "sellable": q, "avg": a, "price": self.prices[s],
               "value": q * self.prices[s], "pnl": 0, "pnl_pct": 0.0} for s, (q, a) in self.holdings.items()]
        stock = sum(h["value"] for h in hs)
        return {"cash": self.cash, "d2_cash": self.cash, "total": self.cash + stock, "stock_value": stock,
                "prev_total": self.prev_total, "pnl": 0, "holdings": hs}

    async def order(self, side, symbol, qty, price=None):
        if self.fail:
            raise KISError(self.fail)
        odno = f"{len(self.orders) + 1:010d}"
        px = self.prices[symbol]
        self.orders.append({"odno": odno, "side": side, "symbol": symbol, "qty": qty, "px": px, "filled": 0, "limit": price})
        if self.fill and (price is None or price >= px):
            self._fill(self.orders[-1])
        return {"odno": odno, "orgno": "00950", "time": "091500", "msg": "주문 전송 완료"}

    def _fill(self, o):
        q, a = self.holdings.get(o["symbol"], [0, 0])
        if o["side"] == "buy":
            self.cash -= o["qty"] * o["px"]
            self.holdings[o["symbol"]] = [q + o["qty"], o["px"]]
        else:
            self.cash += o["qty"] * o["px"]
            if q - o["qty"]:
                self.holdings[o["symbol"]] = [q - o["qty"], a]
            else:
                self.holdings.pop(o["symbol"])
        o["filled"] = o["qty"]

    async def executions(self, day=None):
        return [{"odno": o["odno"], "side": o["side"], "symbol": o["symbol"], "name": "", "qty": o["qty"],
                 "filled": o["filled"], "avg_price": o["px"] if o["filled"] else 0, "amount": 0,
                 "remain": o["qty"] - o["filled"], "cancelled": o.get("cancelled", False), "time": ""} for o in self.orders]

    async def cancel(self, odno, orgno):
        for o in self.orders:
            if o["odno"] == odno:
                o["cancelled"] = True
        return {"msg": "취소 완료"}


@pytest.fixture
def kenv(monkeypatch):
    from app.core import security
    from app.core.database import Base, get_db
    from app.api.routes import kis as kis_route
    from app.api.routes.auth import get_admin
    from app.models import user as user_model, kis as _k  # noqa: F401
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as s:
            u = user_model.User(username="boss", hashed_password="x", is_admin=True, totp_enabled=True, totp_secret=SECRET)
            s.add(u)
            await s.commit()
            return u.id
    uid = run(setup())
    clock = {"t": dt.datetime(2026, 11, 24, 10, 0, tzinfo=KST)}   # 화요일 장중
    monkeypatch.setattr(kis_trade, "_kst", lambda: clock["t"])
    monkeypatch.setattr(kis_trade, "time", SimpleNamespace(time=lambda: clock["t"].timestamp()))
    monkeypatch.setattr(security, "_now", lambda: clock["t"].timestamp())
    monkeypatch.setattr(kis_trade, "AsyncSessionLocal", Session)
    monkeypatch.setattr(kis_trade, "_alert_admins", lambda *a, **k: None)
    b = FakeBroker()
    for name in ("balance", "order", "executions", "cancel"):
        monkeypatch.setattr(kis_order, name, getattr(b, name))
    monkeypatch.setattr(kis_order, "creds", lambda: ("k", "s", "50123456-01"))

    async def price_now(symbol, bal):
        return float(b.prices[symbol])

    async def quote(symbol):
        return {"price": float(b.prices[symbol]), "vi": symbol in b.vi, "halted": False}

    async def index_change():
        return b.index

    async def fetch_prices(symbols):
        return {s: (float(b.prices[s]), "ws") for s in symbols if s in b.prices and s not in b.no_price}
    monkeypatch.setattr(kis_trade, "_price_now", price_now)
    monkeypatch.setattr(kis_trade, "_quote", quote)
    monkeypatch.setattr(kis_trade, "_index_change", index_change)
    monkeypatch.setattr(kis_trade, "_fetch_prices", fetch_prices)
    kis_trade._balance_cache.update(at=0.0, data=None, error=None)
    for d in (kis_trade._hist, kis_trade._next_try, kis_trade._wait_kind):
        d.clear()
    kis_trade._intraday.update(running=False, last=None, result=None, error=None, task=None, notes=[], waiting=[], took=None)

    async def _db():
        async with Session() as s:
            yield s

    async def _admin(db=Depends(get_db)):
        return await db.get(user_model.User, uid)
    app = FastAPI()
    app.include_router(kis_route.router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_admin] = _admin
    steps = {"n": 0}

    def code():
        """매번 새 30초 칸의 코드 (같은 코드는 재사용 불가라 시계를 30초씩 옮김)"""
        steps["n"] += 1
        clock["t"] += dt.timedelta(seconds=30)
        return pyotp.TOTP(SECRET).at(clock["t"].timestamp())
    with TestClient(app) as c:
        yield SimpleNamespace(c=c, b=b, Session=Session, clock=clock, code=code, uid=uid)
    run(engine.dispose())


def add_order(env, **kw):
    from app.models.kis import KisOrder

    async def go():
        async with env.Session() as s:
            k = KisOrder(created_at=env.clock["t"].timestamp(), base_date="2026-11-23", source="ai", status="proposed",
                         expires_at=kis_trade.expiry_for("2026-11-23"), **kw)
            s.add(k)
            await s.commit()
            return k.id
    return run(go())


def order(env, oid):
    from app.models.kis import KisOrder

    async def go():
        async with env.Session() as s:
            return await s.get(KisOrder, oid)
    return run(go())


def buy(env, sym="005930", budget=1_000_000, ref=70_000):
    return add_order(env, side="buy", symbol=sym, name=f"종목{sym}", budget=budget, ref_price=ref, reason="AI 점수 70")


def approve(env, *ids, code=None):
    return env.c.post("/api/kis/orders/approve", json={"ids": list(ids), "totp_code": code or env.code()})


# ---------------- 승인 · 주문 ----------------

def test_approve_needs_totp_and_places_order(kenv):
    oid = buy(kenv)
    r = approve(kenv, oid, code="000000")
    assert r.status_code == 400 and "2단계" in r.json()["detail"]
    assert kenv.b.orders == [] and order(kenv, oid).status == "proposed"
    r = approve(kenv, oid)
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["status"] == "submitted"
    assert kenv.b.orders[0]["qty"] == 14   # 1,000,000 / (70,000 × 1.003) → 14주
    k = order(kenv, oid)
    assert k.status == "submitted" and k.odno == "0000000001" and k.decided_by == kenv.uid
    # 체결 반영 → 앱 기록(보유 수량)·손절/목표
    assert run(kis_trade.refresh_fills()) == 1
    k = order(kenv, oid)
    assert k.status == "filled" and k.filled_qty == 14 and k.filled_price == 70_000
    st = run(kis_trade.overview())
    assert st["mismatches"] == [] and st["orders_today"] == 1
    h = st["balance"]["holdings"][0]
    assert h["stop"] == pytest.approx(70_000 * 0.93) and h["target"] == pytest.approx(70_000 * 1.15)
    # 같은 코드 재사용 불가 · 이미 처리된 제안은 다시 승인 안 됨
    r = approve(kenv, oid)
    assert r.json()["results"][0]["status"] is None and len(kenv.b.orders) == 1


def test_admin_without_totp_cannot_approve(kenv):
    from app.models.user import User

    async def off():
        async with kenv.Session() as s:
            u = await s.get(User, kenv.uid)
            u.totp_enabled = False
            await s.commit()
    run(off())
    r = approve(kenv, buy(kenv), code="123456")
    assert r.status_code == 403 and kenv.b.orders == []


def test_approved_outside_hours_waits_for_open(kenv):
    kenv.clock["t"] = dt.datetime(2026, 11, 23, 18, 0, tzinfo=KST)   # 월요일 장 마감 뒤
    oid = add_order(kenv, side="buy", symbol="005930", name="삼성", budget=1_000_000, ref_price=70_000, reason="x")
    r = approve(kenv, oid)
    assert r.json()["results"][0]["status"] == "approved" and kenv.b.orders == []
    sell = add_order(kenv, side="sell", symbol="000660", name="하이닉스", qty=2, ref_price=200_000, reason="x")
    kenv.b.holdings["000660"] = [2, 190_000]
    assert approve(kenv, sell).json()["results"][0]["status"] == "approved"
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 9, 0, 30, tzinfo=KST)   # 개장 1분 전엔 아무것도 안 보냄
    run(kis_trade.tick())
    assert kenv.b.orders == []
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 9, 1, 10, tzinfo=KST)   # 매도는 개장 1분 뒤, 매수는 5분 뒤부터
    run(kis_trade.tick())
    assert [o["side"] for o in kenv.b.orders] == ["sell"] and order(kenv, oid).status == "approved"
    assert "개장 5분 뒤" in order(kenv, oid).message
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 9, 5, 10, tzinfo=KST)
    run(kis_trade.tick())
    assert [o["side"] for o in kenv.b.orders] == ["sell", "buy"] and order(kenv, oid).status == "filled"
    assert kenv.b.orders[1]["limit"] == 70_300    # 지정가 = 현재가 70,000 × 1.003 → 호가 단위(100원) 올림


def test_proposal_expires_after_next_close(kenv):
    oid = buy(kenv)   # 기준일 11/23 → 11/24 15:30 까지
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 15, 31, tzinfo=KST)
    run(kis_trade.expire_old())
    assert order(kenv, oid).status == "expired"
    assert approve(kenv, oid).json()["results"][0]["status"] is None and kenv.b.orders == []


def test_reject(kenv):
    oid = buy(kenv)
    assert kenv.c.post("/api/kis/orders/reject", json={"ids": [oid]}).json()["message"] == "1건 거절했습니다"
    assert order(kenv, oid).status == "rejected"
    assert approve(kenv, oid).json()["results"][0]["status"] is None


# ---------------- 안전장치 ----------------

def test_per_order_limit_caps_quantity(kenv):
    run(kis_trade.set_config(kenv.uid, {"max_order_krw": 500_000}, None))
    approve(kenv, buy(kenv, budget=5_000_000))
    assert kenv.b.orders[0]["qty"] == 7    # 500,000 / 70,210 → 7주 (제안 금액 5백만이어도 한도까지만)


def test_one_share_too_expensive_is_blocked(kenv):
    run(kis_trade.set_config(kenv.uid, {"max_order_krw": 100_000}, None))
    oid = buy(kenv, sym="000660", ref=200_000)
    r = approve(kenv, oid).json()["results"][0]
    assert r["status"] == "blocked" and "1주" in r["message"] and kenv.b.orders == []


def test_daily_order_count_limit(kenv):
    run(kis_trade.set_config(kenv.uid, {"max_orders_day": 1}, None))
    approve(kenv, buy(kenv))
    r = approve(kenv, buy(kenv, sym="000660", ref=200_000)).json()["results"][0]
    assert r["status"] == "blocked" and "횟수" in r["message"] and len(kenv.b.orders) == 1


def test_price_rise_waits_then_buys_when_back_in_range(kenv):
    """비싸지면 막아 버리지 않고 기다림 (쫓아가서 안 삼) → 허용 안으로 내려오면 그때 지정가로 삼"""
    kenv.b.prices["005930"] = 73_000      # 제안 70,000 → +4.3% (허용 3%)
    oid = buy(kenv)
    r = approve(kenv, oid).json()["results"][0]
    assert r["status"] == "approved" and "비싸서 기다림" in r["message"] and kenv.b.orders == []
    run(kis_trade.watch())                # 아직 비쌈 → 그대로
    assert kenv.b.orders == [] and order(kenv, oid).status == "approved"
    kenv.b.prices["005930"] = 71_500      # +2.1% — 허용 안
    kenv.clock["t"] += dt.timedelta(seconds=31)
    assert run(kis_trade.watch())["sent"] == 1
    k = order(kenv, oid)
    assert k.status == "submitted" and k.limit_price == 71_800 and kenv.b.orders[0]["limit"] == 71_800   # 71,500 × 1.003 = 71,714.5 → 71,800
    log = [l["action"] for l in run(kis_trade.list_log())]
    assert log.count("wait") == 1         # 기다림은 이유가 바뀔 때만 기록 (매번 안 쌓음)


def test_price_crash_cancels_buy(kenv):
    kenv.b.prices["005930"] = 65_000      # 제안 70,000 → −7.1% (허용 −6%) — 판단 때와 상황이 다름
    oid = buy(kenv)
    r = approve(kenv, oid).json()["results"][0]
    assert r["status"] == "cancelled" and "급락" in r["message"] and kenv.b.orders == []
    assert order(kenv, oid).message.startswith("급변으로 자동 취소")
    kenv.b.prices["005930"] = 67_000      # −4.3% 는 괜찮음
    assert approve(kenv, buy(kenv)).json()["results"][0]["status"] == "submitted"


def test_duplicate_order_same_symbol_blocked(kenv):
    kenv.b.fill = False   # 첫 주문이 아직 안 체결 → 같은 종목 두 번째 주문은 막음
    a, b = buy(kenv), buy(kenv)
    res = approve(kenv, a, b).json()["results"]
    assert [x["status"] for x in res] == ["submitted", "blocked"] and "두 번" in res[1]["message"]
    assert len(kenv.b.orders) == 1


def test_daily_loss_limit_halts_and_cancels(kenv):
    kenv.b.prev_total = 10_600_000     # 전날 총자산 대비 −60만원 (한도 50만)
    a, b = buy(kenv), buy(kenv, sym="000660", ref=200_000)
    r = approve(kenv, a).json()["results"][0]
    assert r["status"] == "blocked" and "손실 한도" in r["message"] and kenv.b.orders == []
    st = run(kis_trade.overview())
    assert st["halted"] and "손실 한도" in st["halted_reason"]
    assert order(kenv, b).status == "cancelled"
    # 정지 중엔 승인도 안 됨 → 다시 시작은 2단계 코드
    assert approve(kenv, buy(kenv)).status_code == 400
    assert kenv.c.post("/api/kis/resume", json={"totp_code": "000000"}).status_code == 400
    assert kenv.c.post("/api/kis/resume", json={"totp_code": kenv.code()}).status_code == 200
    assert not run(kis_trade.overview())["halted"]


def test_mismatch_blocks_buy_until_rebaseline(kenv):
    run(kis_trade.rebaseline(kenv.uid))           # 앱 기록 = 지금 KIS 잔고 (없음)
    kenv.b.holdings["000660"] = [3, 190_000]      # HTS 에서 직접 삼
    kis_trade._balance_cache["data"] = None       # (화면 잔고는 20초 캐시)
    st = run(kis_trade.overview())
    assert st["mismatches"] == [{"symbol": "000660", "name": "종목000660", "app": 0, "kis": 3, "pending": False}]
    r = approve(kenv, buy(kenv)).json()["results"][0]
    assert r["status"] == "blocked" and "기록이 다름" in r["message"]
    assert kenv.c.post("/api/kis/baseline").status_code == 200   # 주문을 안 보내는 일이라 2단계 코드 없음 (사용자 결정 2026-11-26)
    kis_trade._balance_cache["data"] = None
    assert run(kis_trade.overview())["mismatches"] == []
    assert approve(kenv, buy(kenv)).json()["results"][0]["status"] == "submitted"


def _part_fill(b, o, n):
    """보낸 주문 o 를 n 주까지 체결된 것으로 (KIS 잔고·체결 내역 둘 다)"""
    add = n - o["filled"]
    q, _a = b.holdings.get(o["symbol"], [0, 0])
    b.holdings[o["symbol"]] = [q + add, o["px"]]
    b.cash -= add * o["px"]
    o["filled"] = n


def test_rebaseline_during_fill_does_not_double_count(kenv):
    """사용자 화면: 삼립 앱 36 / KIS 24, 인크로스 앱 185 / KIS 183 — 체결 중에 '기준 다시 맞추기'를 누르면
    이미 잔고에 들어간 체결이 다음 체결 확인 때 또 더해졌음 (36 = 12 + 24)"""
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.fill = False
    assert approve(kenv, buy(kenv)).json()["results"][0]["status"] == "submitted"
    o = kenv.b.orders[0]
    qty = o["qty"]
    _part_fill(kenv.b, o, qty // 2)                    # 일부만 체결된 사이에
    kis_trade._balance_cache["data"] = None
    run(kis_trade.rebaseline(kenv.uid))                # 기준 다시 맞추기
    _part_fill(kenv.b, o, qty)                         # 나머지 체결
    run(kis_trade.refresh_fills())
    kis_trade._balance_cache["data"] = None
    st = run(kis_trade.overview())
    assert st["mismatches"] == [], st["mismatches"]
    assert {h["symbol"]: h["qty"] for h in st["balance"]["holdings"]} == {"005930": qty}


def test_overview_applies_fills_before_comparing(kenv):
    """체결 직후 1분 체결 확인 전에 화면을 열어도 '다름' 경고가 안 뜸 (전엔 떠서 기준 맞추기를 누르게 됐음)"""
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.fill = False
    approve(kenv, buy(kenv))
    o = kenv.b.orders[0]
    _part_fill(kenv.b, o, o["qty"])
    kis_trade._balance_cache["data"] = None
    assert run(kis_trade.overview())["mismatches"] == []
    assert order(kenv, 1).status == "filled"


def test_mismatch_while_order_in_flight_is_pending(kenv):
    """KIS 잔고엔 들어왔는데 체결 내역엔 아직 없음 → '체결 중'(pending) 으로 표시, 매수는 그래도 막음"""
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.fill = False
    approve(kenv, buy(kenv))
    o = kenv.b.orders[0]
    kenv.b.holdings["005930"] = [5, 70_000]       # 잔고만 먼저 바뀜
    kis_trade._balance_cache["data"] = None
    mm = run(kis_trade.overview())["mismatches"]
    assert mm == [{"symbol": "005930", "name": "종목005930", "app": 0, "kis": 5, "pending": True}]
    kenv.b.holdings["000660"] = [1, 200_000]      # 직접 산 종목은 pending 아님
    kis_trade._balance_cache["data"] = None
    mm = {m["symbol"]: m["pending"] for m in run(kis_trade.overview())["mismatches"]}
    assert mm == {"005930": True, "000660": False}
    assert o["filled"] == 0


def test_submit_applies_previous_fills_before_mismatch_check(kenv):
    """앞 주문이 막 체결됐는데 체결 확인(1분) 전이라도 다음 매수가 '기록 다름'으로 막히지 않음"""
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.fill = False
    approve(kenv, buy(kenv))
    _part_fill(kenv.b, kenv.b.orders[0], kenv.b.orders[0]["qty"])
    kis_trade._balance_cache["data"] = None
    r = approve(kenv, buy(kenv, sym="000660", ref=200_000)).json()["results"][0]
    assert r["status"] == "submitted", r


def test_sell_only_sellable_quantity(kenv):
    kenv.b.holdings["005930"] = [5, 60_000]
    oid = add_order(kenv, side="sell", symbol="005930", name="삼성", qty=10, ref_price=70_000, reason="AI 점수 40")
    assert approve(kenv, oid).json()["results"][0]["status"] == "submitted"
    assert kenv.b.orders[0] == {**kenv.b.orders[0], "side": "sell", "qty": 5}
    run(kis_trade.refresh_fills())
    assert "005930" not in kenv.b.holdings and order(kenv, oid).status == "filled"


def test_kis_rejects_order(kenv):
    kenv.b.fail = "KIS VTTC0012U 실패 (HTTP 200, APBK0919): 주문가능금액을 초과"
    r = approve(kenv, buy(kenv)).json()["results"][0]
    assert r["status"] == "failed" and "주문가능금액" in r["message"]


def test_emergency_halt_cancels_unfilled(kenv):
    kenv.b.fill = False
    sent = buy(kenv)
    approve(kenv, sent)
    waiting = buy(kenv, sym="000660", ref=200_000)
    r = kenv.c.post("/api/kis/halt", json={"reason": "이상함"})   # 2단계 코드 없이 바로
    assert r.status_code == 200 and "1건 취소" in r.json()["message"]
    assert order(kenv, sent).status == "cancelled" and order(kenv, waiting).status == "cancelled"
    assert kenv.b.orders[0]["cancelled"]
    assert "cancel" in [l["action"] for l in run(kis_trade.list_log())]


def test_interrupted_submit_is_not_resent(kenv):
    """주문을 보내다 서버가 꺼지면 '결과 모름' — 다시 보내지 않음 (두 번 주문 방지)"""
    from app.models.kis import KisOrder
    oid = buy(kenv)

    async def mark():
        async with kenv.Session() as s:
            (await s.get(KisOrder, oid)).status = "submitting"
            await s.commit()
    run(mark())
    run(kis_trade.mark_interrupted())
    assert order(kenv, oid).status == "unknown"
    run(kis_trade.tick())
    assert kenv.b.orders == []


def test_unfilled_after_close(kenv):
    kenv.b.fill = False
    oid = buy(kenv)
    approve(kenv, oid)
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 15, 50, tzinfo=KST)
    run(kis_trade.refresh_fills(final=True))
    assert order(kenv, oid).status == "unfilled"


def test_config_validation_and_audit(kenv):
    r = kenv.c.put("/api/kis/config", json={"limits": {"max_orders_day": 999}, "totp_code": "000000"})
    assert r.status_code == 422      # 값이 틀리면 2단계 코드를 쓰기 전에 거절
    r = kenv.c.put("/api/kis/config", json={"limits": {"max_orders_day": 5}, "params": {"stop_pct": 5},
                                            "totp_code": kenv.code()})
    assert r.status_code == 200 and r.json()["limits"]["max_orders_day"] == 5 and r.json()["params"]["stop_pct"] == 5
    log = kenv.c.get("/api/kis/log").json()["items"]
    assert log[0]["action"] == "config" and "하루 주문 횟수 10→5" in log[0]["detail"] and log[0]["by"] == "boss"


# ---------------- 제안 ----------------

def test_propose_from_kis_balance(kenv, monkeypatch):
    from app.services import papertrade
    kenv.b.holdings["000660"] = [3, 190_000]
    seen = {}

    def row(sym, name, score, prob, close):
        return {"name": name, "score": score, "prob": prob, "close": close, "quant": 80, "grade": "A", "accum": 30,
                "accum_ok": False, "ma50": close * 0.9}

    async def fake_analyze(market, user_id, positions, params):
        seen.update(positions=positions, user=user_id)
        return {"rows": {"005930": row("005930", "삼성", 75, 62, 70_000), "000660": row("000660", "하이닉스", 30, 35, 200_000)},
                "regime": "상승 추세", "events": [], "aw": None, "last": "2026-11-23", "errors": [], "index": []}
    monkeypatch.setattr(papertrade, "analyze_live", fake_analyze)
    old = buy(kenv)
    kenv.clock["t"] = dt.datetime(2026, 11, 23, 15, 46, tzinfo=KST)
    run(kis_trade.tick())     # 장 마감 15분 뒤 자동 제안
    assert seen["user"] == kenv.uid and seen["positions"]["000660"]["qty"] == 3
    items = kenv.c.get("/api/kis/orders").json()["items"]
    sides = {(i["side"], i["symbol"]): i for i in items}
    assert set(sides) == {("buy", "005930"), ("sell", "000660")}
    assert sides[("sell", "000660")]["qty"] == 3 and sides[("buy", "005930")]["status"] == "proposed"
    assert order(kenv, old).status == "expired"
    assert kenv.b.orders == []          # 제안만 — 승인 전엔 주문 없음
    run(kis_trade.tick())               # 오늘은 이미 제안함
    assert len(kenv.c.get("/api/kis/orders").json()["items"]) == 2


def test_stop_loss_sells_automatically(kenv, monkeypatch):
    """손절가에 닿으면 승인 없이 바로 시장가 매도 + 휴대폰 알림 (사용자 결정 2026-11-26)"""
    pushed = []
    monkeypatch.setattr(kis_trade, "_push", lambda title, body, priority=3, tags=None, **kw: pushed.append((title, priority)))
    kenv.b.holdings["005930"] = [10, 70_000]
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.prices["005930"] = 64_000      # 손절가 65,100 아래
    assert run(kis_trade.watch())["stops"] == 1
    assert kenv.b.orders[0] == {**kenv.b.orders[0], "side": "sell", "qty": 10, "limit": None}   # 시장가
    items = kenv.c.get("/api/kis/orders?kind=all").json()["items"]
    assert items[0]["source"] == "stop" and items[0]["status"] in ("submitted", "filled") and "자동 매도" in items[0]["reason"]
    assert ("자동 손절 매도 — 종목005930", 5) in pushed
    run(kis_trade.refresh_fills())
    assert run(kis_trade.watch()).get("stops", 0) == 0 and len(kenv.b.orders) == 1   # 다 팔렸음 — 두 번 안 팖
    assert "auto_stop" in [l["action"] for l in run(kis_trade.list_log())]


def test_stop_loss_while_order_in_flight_not_doubled(kenv):
    kenv.b.holdings["005930"] = [10, 70_000]
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.fill = False
    kenv.b.prices["005930"] = 64_000
    run(kis_trade.watch())
    kenv.clock["t"] += dt.timedelta(seconds=300)
    run(kis_trade.watch())                 # 아직 접수 중(안 체결) — 다시 안 보냄
    assert len(kenv.b.orders) == 1


def test_stop_loss_runs_during_loss_halt_not_manual_halt(kenv):
    kenv.b.holdings["005930"] = [10, 70_000]
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.prices["005930"] = 64_000
    assert kenv.c.post("/api/kis/halt", json={"reason": ""}).status_code == 200   # 긴급 정지 = 모두 멈춤
    run(kis_trade.watch())
    assert kenv.b.orders == []
    kenv.c.post("/api/kis/resume", json={"totp_code": kenv.code()})
    kenv.b.prev_total = kenv.b.cash + 10 * 64_000 + 600_000      # 하루 손실 60만 (한도 50만) → 자동 정지
    run(kis_trade.check_exits())           # 5분 확인(잔고) — 손실 한도 정지 + 손절은 계속
    st = run(kis_trade.overview())
    assert st["halted"] and "손실 한도" in st["halted_reason"] and st["watch"]["stops_ok"]
    assert [o["side"] for o in kenv.b.orders] == ["sell"]


def test_stop_loss_ignores_daily_count_and_retries_limited(kenv):
    run(kis_trade.set_config(kenv.uid, {"max_orders_day": 1}, None))
    approve(kenv, buy(kenv, sym="000660", ref=200_000))   # 오늘 주문 1건 = 한도
    run(kis_trade.refresh_fills())
    kenv.b.holdings["005930"] = [10, 70_000]
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.prices["005930"] = 64_000
    kenv.b.fail = "KIS VTTC0011U 실패: 잠깐 오류"
    run(kis_trade.watch())
    assert len(kenv.b.orders) == 1        # 횟수 한도에 안 막히고 보냄 → KIS 거부(failed)
    run(kis_trade.watch())                # 2분 안엔 다시 안 함
    kenv.b.fail = None
    kenv.clock["t"] += dt.timedelta(seconds=121)
    run(kis_trade.watch())
    assert [o["side"] for o in kenv.b.orders] == ["buy", "sell"]
    stops = [o for o in run(kis_trade.list_orders("all")) if o["source"] == "stop"]
    assert [o["status"] for o in stops] == ["submitted", "failed"]


def test_target_reached_is_proposal_not_auto(kenv):
    kenv.b.holdings["005930"] = [10, 70_000]
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.prices["005930"] = 81_000      # 목표 80,500 위
    run(kis_trade.watch())
    items = kenv.c.get("/api/kis/orders").json()["items"]
    assert len(items) == 1 and items[0]["source"] == "exit" and items[0]["status"] == "proposed" and kenv.b.orders == []
    kenv.c.post("/api/kis/orders/reject", json={"ids": [items[0]["id"]]})
    kenv.clock["t"] += dt.timedelta(seconds=60)
    run(kis_trade.watch())                # 거절했으면 오늘은 다시 안 물음
    assert kenv.c.get("/api/kis/orders").json()["items"] == []


# ---------------- 장중 실시간 감시 · 급변 ----------------

def _feed(env, *prices, sym="005930", step=60):
    for p in prices:
        env.b.prices[sym] = p
        run(kis_trade.watch())
        env.clock["t"] += dt.timedelta(seconds=step)


def test_fast_drop_cancels_waiting_and_resting_buys(kenv, monkeypatch):
    pushed = []
    monkeypatch.setattr(kis_trade, "_push", lambda title, body, priority=3, tags=None, **kw: pushed.append(title))
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 9, 1, 30, tzinfo=KST)
    waiting = buy(kenv)                                   # 개장 5분 전 — 조건 대기
    assert approve(kenv, waiting).json()["results"][0]["status"] == "approved"
    _feed(kenv, 70_000, 69_800)
    kenv.b.prices["005930"] = 67_800                      # 10분 최고 70,000 대비 −3.1%
    run(kis_trade.watch())
    k = order(kenv, waiting)
    assert k.status == "cancelled" and "10분 안에" in k.message and kenv.b.orders == []
    assert "매수 자동 취소 — 종목005930" in pushed
    # 접수된(지정가가 안 체결) 매수도 KIS 에서 취소
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 11, 0, tzinfo=KST)
    kis_trade._hist.clear()
    kenv.b.prices["000660"] = 200_000
    resting = buy(kenv, sym="000660", ref=200_000)
    approve(kenv, resting)
    kenv.b.orders[0]["filled"] = 0
    kenv.b.holdings.pop("000660", None)                   # (안 체결로 되돌림 — 가짜 계좌)
    kenv.b.cash = 10_000_000

    async def unfilled(day=None):
        return [{**e, "filled": 0, "remain": e["qty"], "avg_price": 0} if not e["cancelled"] else {**e, "filled": 0, "avg_price": 0}
                for e in await FakeBroker.executions(kenv.b)]
    monkeypatch.setattr(kis_order, "executions", unfilled)
    assert order(kenv, resting).status == "submitted"
    _feed(kenv, 200_000, sym="000660")
    kenv.b.prices["000660"] = 193_000                     # −3.5%
    assert run(kis_trade.watch())["cancelled"] == 1
    k = order(kenv, resting)
    assert kenv.b.orders[0]["cancelled"] and k.cancel_req and k.status == "cancelled" and "10분 안에" in k.message
    run(kis_trade.watch())
    assert sum(1 for t in pushed if t == "매수 자동 취소 — 종목000660") == 1     # 한 번만


def test_slow_drop_over_10_minutes_is_not_shock(kenv):
    oid = buy(kenv)
    kenv.b.fill = False
    _feed(kenv, 70_000, 69_500, 69_000, sym="005930", step=300)   # 15분에 걸쳐 −1.4%
    kenv.b.prices["005930"] = 68_000                     # 10분 안 최고 69,500 대비 −2.2% (15분 전 70,000 은 안 봄)
    assert kis_trade.fast_drop("005930", 68_000)[1] == 69_500
    approve(kenv, oid)
    assert order(kenv, oid).status == "submitted"


def test_vi_and_index_drop_make_buy_wait(kenv):
    kenv.b.vi.add("005930")
    oid = buy(kenv)
    r = approve(kenv, oid).json()["results"][0]
    assert r["status"] == "approved" and "VI" in r["message"] and kenv.b.orders == []
    kenv.b.vi.clear()
    kenv.b.index = -2.4                    # 코스닥 −2.4% (기준 −2%)
    kenv.clock["t"] += dt.timedelta(seconds=31)
    run(kis_trade.watch())
    k = order(kenv, oid)
    assert k.status == "approved" and "지수 -2.4% 하락" in k.message and kenv.b.orders == []
    kenv.b.index = None                    # 지수를 못 받으면 사지 않고 기다림 (이유 표시)
    kenv.clock["t"] += dt.timedelta(seconds=31)
    run(kis_trade.watch())
    assert "지수를 못 받아" in order(kenv, oid).message and kenv.b.orders == []
    kenv.b.index = -0.5
    kenv.clock["t"] += dt.timedelta(seconds=31)
    run(kis_trade.watch())
    assert order(kenv, oid).status == "submitted"


def test_no_price_no_action(kenv):
    """가격을 못 받은 종목은 판단하지 않음 (지어내지 않음) — 상태에 몇 종목 못 받았는지 표시"""
    oid = buy(kenv)
    kenv.b.no_price.add("005930")
    approve(kenv, oid)    # 승인 순간 submit 은 REST 로 확인 — 여기선 정상이라 바로 감
    assert order(kenv, oid).status == "submitted"
    kenv.b.holdings["000660"] = [5, 200_000]
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.no_price.add("000660")
    kenv.b.prices["000660"] = 150_000      # 손절가 아래지만 가격을 못 받음
    run(kis_trade.watch())
    st = run(kis_trade.overview())
    assert st["watch"]["missing"] == 2 and len(kenv.b.orders) == 1


def test_halt_cancels_resting_buy_via_watch(kenv):
    """하루 손실 한도로 자동 정지되면 걸려 있는(안 체결) 매수도 취소"""
    kenv.b.fill = False
    oid = buy(kenv)
    approve(kenv, oid)
    kenv.b.cash -= 600_000                 # 오늘 60만원 손실 (한도 50만)
    kis_trade._balance_cache["data"] = None
    run(kis_trade.check_exits())
    assert run(kis_trade.overview())["halted"]
    run(kis_trade.watch())
    assert kenv.b.orders[0]["cancelled"] and order(kenv, oid).status == "cancelled"


def test_partial_fill_then_cancel_keeps_filled_shares(kenv):
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.fill = False
    oid = buy(kenv)
    approve(kenv, oid)
    o = kenv.b.orders[0]
    _part_fill(kenv.b, o, 5)                 # 5주만 체결된 상태에서 취소
    kis_trade._balance_cache["data"] = None
    assert "취소 요청" in kenv.c.post(f"/api/kis/orders/{oid}/cancel").json()["message"]
    k = order(kenv, oid)
    assert k.status == "partial" and k.filled_qty == 5
    kis_trade._balance_cache["data"] = None
    st = run(kis_trade.overview())
    assert st["mismatches"] == [] and st["balance"]["holdings"][0]["qty"] == 5


def test_old_limits_row_gets_new_defaults(kenv):
    """업데이트 전 DB(한도 4개만 저장) → 새 항목은 기본값"""
    from app.models.kis import KisTrade

    async def old():
        async with kenv.Session() as s:
            s.add(KisTrade(id=1, halted=False, limits=json.dumps({"max_order_krw": 1_000_000, "max_orders_day": 10,
                                                                  "max_loss_krw": 500_000, "max_gap_pct": 3.0}), params="{}", state="{}"))
            await s.commit()
    run(old())
    st = kenv.c.get("/api/kis/status").json()
    assert st["limits"]["fast_drop_pct"] == 3.0 and st["limits"]["index_drop_pct"] == 2.0 and st["limits"]["max_order_krw"] == 1_000_000
    assert st["limit_meta"]["limit_slip_pct"]["label"] == "매수 지정가 여유 (%)"
    assert st["watch"]["every"] == 5 and st["watch"]["buy_after_open"] == 5


# ---------------- KIS 주문 API 래퍼 ----------------

def test_order_client_refuses_real_server(monkeypatch):
    monkeypatch.setattr(kis_order, "creds", lambda: ("k", "s", "50123456-01"))
    real = KISClient(app_key="k", app_secret="s", base_url=KIS_REAL_BASE)
    monkeypatch.setattr(kis_order, "client", lambda: real)
    with pytest.raises(KISError, match="실거래"):
        run(kis_order.order("buy", "005930", 1))


def test_order_request_shape_and_tr_fallback(monkeypatch):
    monkeypatch.setattr(kis_order, "creds", lambda: ("k", "s", "50123456-01"))
    kis_order._tr_ok.clear()
    cl = KISClient(app_key="k", app_secret="s", base_url=KIS_MOCK_BASE)
    sent = []

    async def post(path, tr, body):
        sent.append((path, tr, body))
        if tr == "VTTC0012U":
            raise KISError("KIS VTTC0012U 실패 (HTTP 500, OPSQ0002): 없는 서비스 코드")
        return {"rt_cd": "0", "msg1": "주문 전송 완료", "output": {"ODNO": "0000123", "KRX_FWDG_ORD_ORGNO": "00950", "ORD_TMD": "090101"}}
    monkeypatch.setattr(cl, "_post", post)
    monkeypatch.setattr(kis_order, "client", lambda: cl)
    r = run(kis_order.order("buy", "005930", 3))
    assert r["odno"] == "0000123" and [t for _, t, _ in sent] == ["VTTC0012U", "VTTC0802U"]
    assert sent[-1][2] == {"CANO": "50123456", "ACNT_PRDT_CD": "01", "PDNO": "005930", "ORD_DVSN": "01", "ORD_QTY": "3", "ORD_UNPR": "0"}
    run(kis_order.order("buy", "005930", 1))
    assert sent[-1][1] == "VTTC0802U"     # 한 번 된 번호를 계속 씀
    run(kis_order.order("buy", "005930", 2, 70_300))   # 지정가
    assert sent[-1][2]["ORD_DVSN"] == "00" and sent[-1][2]["ORD_UNPR"] == "70300" and sent[-1][2]["ORD_QTY"] == "2"
    for bad in (70_250, 0, 70_300.5):                  # 호가 단위(100원)에 안 맞음 · 0 · 소수
        with pytest.raises(ValueError):
            run(kis_order.order("buy", "005930", 1, bad))
    with pytest.raises(ValueError):
        run(kis_order.order("buy", "../x", 1))


def test_tick_size_and_round_up():
    assert [kis_order.tick_size(p) for p in (1_999, 2_000, 4_999, 5_000, 19_990, 20_000, 49_950, 50_000, 199_900, 200_000, 499_500, 500_000)] == \
        [1, 5, 5, 10, 10, 50, 50, 100, 100, 500, 500, 1_000]
    assert kis_order.tick_up(70_210) == 70_300 and kis_order.tick_up(70_300) == 70_300 and kis_order.tick_up(1_234.2) == 1_235
    assert kis_order.tick_up(4_999.1) == 5_000 and kis_order.tick_up(200_001) == 200_500


def test_order_not_retried_on_other_errors(monkeypatch):
    monkeypatch.setattr(kis_order, "creds", lambda: ("k", "s", "50123456-01"))
    kis_order._tr_ok.clear()
    cl = KISClient(app_key="k", app_secret="s", base_url=KIS_MOCK_BASE)
    calls = []

    async def post(path, tr, body):
        calls.append(tr)
        raise KISError("KIS 실패 (APBK0919): 주문가능금액 초과")
    monkeypatch.setattr(cl, "_post", post)
    monkeypatch.setattr(kis_order, "client", lambda: cl)
    with pytest.raises(KISError):
        run(kis_order.order("sell", "005930", 1))
    assert calls == ["VTTC0011U"]     # 주문은 한 번만 보냄


def test_creds_and_account(monkeypatch):
    monkeypatch.setattr(settings, "kis_mock_app_key", "")
    monkeypatch.setattr(settings, "kis_mock_app_secret", "")
    monkeypatch.setattr(settings, "kis_mock_account_no", "")
    monkeypatch.setattr(settings, "kis_is_real", True)
    assert kis_order.creds() is None and kis_order.masked_account() is None
    with pytest.raises(kis_order.NotConfigured):
        kis_order.client()
    monkeypatch.setattr(settings, "kis_is_real", False)     # 시세용 키가 모의투자 키면 그대로 씀
    assert kis_order.creds() == (settings.kis_app_key, settings.kis_app_secret, settings.kis_account_no)
    monkeypatch.setattr(settings, "kis_is_real", True)
    monkeypatch.setattr(settings, "kis_mock_app_key", "mk")
    monkeypatch.setattr(settings, "kis_mock_app_secret", "ms")
    monkeypatch.setattr(settings, "kis_mock_account_no", "50123456-01")
    assert kis_order.masked_account() == "****3456-01"
    assert kis_order.client().base_url == KIS_MOCK_BASE
    assert kis_order.split_account("5012345601") == ("50123456", "01")
    with pytest.raises(kis_order.NotConfigured):
        kis_order.split_account("123")


def test_balance_parsing(monkeypatch):
    monkeypatch.setattr(kis_order, "creds", lambda: ("k", "s", "50123456-01"))

    async def call(kind, method, path, payload):
        assert kind == "balance" and payload["CANO"] == "50123456"
        return {"output1": [{"pdno": "005930", "prdt_name": "삼성전자", "hldg_qty": "10", "ord_psbl_qty": "10",
                             "pchs_avg_pric": "70000.0000", "prpr": "71000", "evlu_amt": "710000", "evlu_pfls_amt": "10000",
                             "evlu_pfls_rt": "1.43"}, {"pdno": "000660", "hldg_qty": "0"}],
                "output2": [{"dnca_tot_amt": "9300000", "prvs_rcdl_excc_amt": "9290000", "tot_evlu_amt": "10010000",
                             "scts_evlu_amt": "710000", "bfdy_tot_asst_evlu_amt": "10000000", "evlu_pfls_smtl_amt": "10000"}]}
    monkeypatch.setattr(kis_order, "_call", call)
    b = run(kis_order.balance())
    assert b["d2_cash"] == 9_290_000 and b["total"] == 10_010_000 and b["prev_total"] == 10_000_000
    assert b["holdings"] == [{"symbol": "005930", "name": "삼성전자", "qty": 10, "sellable": 10, "avg": 70000.0, "price": 71000,
                              "value": 710000, "pnl": 10000, "pnl_pct": 1.43}]


def test_status_not_configured(kenv, monkeypatch):
    monkeypatch.setattr(kis_order, "creds", lambda: None)
    st = kenv.c.get("/api/kis/status").json()
    assert st["configured"] is False and st["balance"] is None and st["server"].startswith("모의투자")
    assert kenv.c.post("/api/kis/propose").status_code == 400
    run(kis_trade.tick())    # 키가 없으면 아무것도 안 함


def test_account_rejected_gives_clear_help(monkeypatch):
    """실제 사용자 오류 (2026-11-25): 'KIS VTTC8434R 실패 (HTTP 200, OPSQ2000): ERROR : INPUT INVALID_CHECK_ACNO'
    → 계좌번호·앱키 설정을 고치라는 설명. 시세용 계좌를 빌려 쓰는 중이면 그 사실을 알려 줌. 주문은 예전 TR 로 다시 보내지 않음"""
    real_err = "KIS VTTC8434R 실패 (HTTP 200, OPSQ2000): ERROR : INPUT INVALID_CHECK_ACNO"
    cl = KISClient(app_key="k", app_secret="s", base_url=KIS_MOCK_BASE)
    calls = []

    async def get(path, tr, params):
        calls.append(tr)
        raise KISError(real_err.replace("VTTC8434R", tr))
    monkeypatch.setattr(cl, "_get", get)
    monkeypatch.setattr(cl, "_post", lambda path, tr, body: get(path, tr, body))
    monkeypatch.setattr(kis_order, "client", lambda: cl)
    kis_order._tr_ok.clear()
    # 1) KIS_MOCK_* 비어 있고 KIS_IS_REAL=false → 시세용 계좌번호를 빌려 씀
    for k in ("kis_mock_app_key", "kis_mock_app_secret", "kis_mock_account_no"):
        monkeypatch.setattr(settings, k, "")
    monkeypatch.setattr(settings, "kis_is_real", False)
    monkeypatch.setattr(settings, "kis_account_no", "12345678-01")
    assert kis_order.account_source() == "KIS_ACCOUNT_NO"
    with pytest.raises(kis_order.AccountRejected) as e:
        run(kis_order.balance())
    assert "KIS_ACCOUNT_NO" in str(e.value) and "KIS_MOCK_ACCOUNT_NO" in str(e.value) and "****5678-01" in str(e.value)
    # 2) 모의투자 키·계좌를 넣었는데 거부 → 계좌·앱키 짝 확인 안내
    monkeypatch.setattr(settings, "kis_mock_app_key", "mk")
    monkeypatch.setattr(settings, "kis_mock_app_secret", "ms")
    monkeypatch.setattr(settings, "kis_mock_account_no", "50123456-01")
    assert kis_order.account_source() == "KIS_MOCK_ACCOUNT_NO"
    calls.clear()
    with pytest.raises(kis_order.AccountRejected) as e:
        run(kis_order.order("buy", "005930", 1))
    assert "모의투자 계좌번호인지" in str(e.value) and "****3456-01" in str(e.value) and "INVALID_CHECK_ACNO" in str(e.value)
    assert calls == ["VTTC0012U"]      # 입력값 오류(OPSQ2000)는 예전 TR 로 다시 보내지 않음


def test_status_shows_account_error(kenv, monkeypatch):
    async def bad():
        raise kis_order.AccountRejected("모의투자 서버가 계좌번호 ****3456-01 를 거부했습니다 (INVALID_CHECK_ACNO) — ① KIS_MOCK_ACCOUNT_NO 가 모의투자 계좌번호인지")
    monkeypatch.setattr(kis_order, "balance", bad)
    st = kenv.c.get("/api/kis/status").json()
    assert "INVALID_CHECK_ACNO" in st["balance_error"] and "KIS_MOCK_ACCOUNT_NO" in st["balance_error"] and st["balance"] is None


def _fake_analyze(monkeypatch):
    from app.services import papertrade

    async def fake(market, user_id, positions, params):
        r = {"name": "삼성", "score": 75, "prob": 62, "close": 70_000, "quant": 80, "grade": "A", "accum": 30, "accum_ok": False, "ma50": 60_000}
        return {"rows": {"005930": r}, "regime": "상승 추세", "events": [], "aw": None, "last": "2026-11-23", "errors": [], "index": []}
    monkeypatch.setattr(papertrade, "analyze_live", fake)


def test_auto_propose_retries_after_failure(kenv, monkeypatch):
    """자동 제안이 실패하면(예: 계좌번호 오류) 그날은 끝이 아니라 30분 뒤 다시 — 매분은 아님"""
    _fake_analyze(monkeypatch)
    good = kenv.b.balance
    calls = {"n": 0}

    async def bad():
        calls["n"] += 1
        raise kis_order.AccountRejected("모의투자 서버가 계좌번호 ****3456-01 를 거부했습니다 (INVALID_CHECK_ACNO)")
    monkeypatch.setattr(kis_order, "balance", bad)
    kenv.clock["t"] = dt.datetime(2026, 11, 23, 15, 46, tzinfo=KST)
    with pytest.raises(kis_order.AccountRejected):
        run(kis_trade.tick())
    kenv.clock["t"] += dt.timedelta(minutes=1)
    run(kis_trade.tick())                       # 1분 뒤엔 다시 안 함
    assert calls["n"] == 1
    monkeypatch.setattr(kis_order, "balance", good)   # 사용자가 .env 를 고침
    kenv.clock["t"] += dt.timedelta(minutes=30)
    run(kis_trade.tick())                       # 30분 뒤 다시 → 성공
    st = run(kis_trade.overview())
    assert st["last_error"] is None and st["last_proposal_day"] == "2026-11-23"
    assert [o["symbol"] for o in run(kis_trade.list_orders())] == ["005930"]


def test_account_error_cleared_when_balance_ok(kenv, monkeypatch):
    """실제 사용자 화면 (2026-11-25): .env 를 고친 뒤 잔고는 받아지는데 '제안 실패: INVALID_CHECK_ACNO' 가 남아 있음
    → 잔고가 받아지면 지난 계좌 오류를 지우고 오늘 제안을 다시 함"""
    from app.models.kis import KisTrade
    _fake_analyze(monkeypatch)
    kenv.clock["t"] = dt.datetime(2026, 11, 23, 17, 30, tzinfo=KST)

    async def stale():
        async with kenv.Session() as s:
            s.add(KisTrade(id=1, halted=False, limits=json.dumps(kis_trade.clean_limits({})),
                           params=json.dumps(kis_trade.pe.clean_params({})), state="{}", last_proposal_day="2026-11-23",
                           last_error="2026-11-23T17:24:51+09:00 제안 실패: KIS VTTC8434R 실패 (HTTP 200, OPSQ2000): ERROR : INPUT INVALID_CHECK_ACNO"))
            await s.commit()
    run(stale())
    st = kenv.c.get("/api/kis/status").json()
    assert st["balance"] and st["last_error"] is None and st["last_proposal_day"] is None
    run(kis_trade.tick())                       # 다음 1분 → 바로 제안
    assert len(run(kis_trade.list_orders())) == 1
    assert any(l["action"] == "account_ok" for l in run(kis_trade.list_log()))


def test_order_results_pushed_to_phone(kenv, monkeypatch):
    """승인한 주문의 결과(체결·막힘)가 휴대폰 푸시로 감"""
    pushed = []
    monkeypatch.setattr(kis_trade, "_push", lambda title, body, priority=3, tags=None, **kw: pushed.append((title, priority)))
    approve(kenv, buy(kenv))
    run(kis_trade.refresh_fills())
    kenv.b.prices["000660"] = 180_000     # 제안 때보다 −10% → 급변 자동 취소
    approve(kenv, buy(kenv, sym="000660", ref=200_000))
    run(kis_trade.set_config(kenv.uid, {"max_order_krw": 100_000}, None))
    approve(kenv, buy(kenv, sym="000660", ref=180_000))
    assert pushed == [("체결 — 매수 종목005930", 3), ("매수 자동 취소 — 종목000660", 4), ("주문 안 보냄 — 종목000660", 4)]


def test_notify_test_endpoint(kenv, monkeypatch):
    from app.services import notify
    monkeypatch.setattr(settings, "ntfy_topic", "")
    assert kenv.c.post("/api/kis/notify-test").status_code == 503
    assert kenv.c.get("/api/kis/status").json()["notify"]["configured"] is False
    monkeypatch.setattr(settings, "ntfy_topic", "stockapp-test-topic-123")
    sent = []

    async def fake(title, msg, priority=3, tags=None, click=None):
        sent.append(title)
    monkeypatch.setattr(notify, "send", fake)
    r = kenv.c.post("/api/kis/notify-test")
    assert r.status_code == 200 and sent == ["StockApp 알림 시험"]
    st = kenv.c.get("/api/kis/status").json()
    assert st["notify"]["configured"] is True and "stockapp-test-topic-123" not in json.dumps(st)

    async def boom(*a, **k):
        raise notify.NotifyError("ntfy 거부 (HTTP 403) forbidden")
    monkeypatch.setattr(notify, "send", boom)
    assert kenv.c.post("/api/kis/notify-test").status_code == 502


def test_network_error_message_and_maybe_sent(monkeypatch):
    """KIS 에 연결 못 하면 httpx 오류 문구가 비어 '처리 실패: ' 만 보였음 (2026-11-25 점검) → 이유를 적음.
    연결 자체가 안 됨 = 주문 안 들어감 / 보낸 뒤 응답 시간 초과 = 들어갔을 수 있음"""
    import httpx
    from app.services.kis_api import KISConnectionError
    cl = KISClient(app_key="k", app_secret="s", base_url=KIS_MOCK_BASE)
    cl._access_token, cl._token_expires = "t", dt.datetime.now() + dt.timedelta(hours=1)
    for exc, sent in ((httpx.ConnectError(""), False), (httpx.ConnectTimeout(""), False), (httpx.ReadTimeout(""), True),
                      (httpx.RemoteProtocolError(""), True)):
        def handler(req, exc=exc):
            raise exc
        cl._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(KISConnectionError) as e:
            run(cl._post("/uapi/domestic-stock/v1/trading/order-cash", "VTTC0012U", {}))
        assert e.value.maybe_sent is sent and "VTTC0012U" in str(e.value) and type(exc).__name__ in str(e.value)


def test_order_timeout_after_send_is_unknown_not_failed(kenv):
    """주문 요청을 보낸 뒤 응답을 못 받으면 '결과 모름' — KIS 거부로 기록하면 실제로 들어간 주문을 놓침. 같은 종목 다음 주문도 막음"""
    from app.services.kis_api import KISConnectionError

    async def lost(side, symbol, qty, price=None):
        raise KISConnectionError("KIS VTTC0012U 응답 시간 초과 (ReadTimeout)", maybe_sent=True)
    kenv_order = kis_order.order
    kis_order.order = lost
    try:
        r = approve(kenv, buy(kenv)).json()["results"][0]
        assert r["status"] == "unknown" and "KIS 앱에서" in r["message"]
        r2 = approve(kenv, buy(kenv)).json()["results"][0]
        assert r2["status"] == "blocked" and "결과를 모름" in r2["message"]

        async def refused(side, symbol, qty, price=None):
            raise KISConnectionError("KIS VTTC0012U 연결 실패 (ConnectError)", maybe_sent=False)
        kis_order.order = refused
        r3 = approve(kenv, buy(kenv, sym="000660", ref=200_000)).json()["results"][0]
        assert r3["status"] == "failed" and "안 들어감" in r3["message"]
    finally:
        kis_order.order = kenv_order


def test_fetch_prices_realtime_first_then_rest(monkeypatch):
    """실시간 체결가(웹소켓)가 있으면 그것, 없는 종목만 REST 멀티종목 시세 — REST 는 15초에 한 번, 실패한 종목은 빠짐"""
    from app.services import kis_ws
    from app.services.kis_api import kis_client
    clock = {"t": 1_000.0}
    monkeypatch.setattr(kis_trade, "time", SimpleNamespace(time=lambda: clock["t"]))
    monkeypatch.setattr(kis_ws, "want", lambda syms: None)
    monkeypatch.setattr(kis_ws, "get", lambda sym: {"price": 70_100} if sym == "005930" else None)
    calls = []

    async def multi(syms):
        calls.append(list(syms))
        if clock["t"] > 1_100:
            raise KISError("KIS FHKST11300006 실패: 점검")
        return {"000660": {"price": 201_000, "change_rate": 0.5, "volume": 1}}
    monkeypatch.setattr(kis_client, "get_kr_multi_price", multi)
    kis_trade._rest.update(at=0.0, data={}, error=None)
    assert run(kis_trade._fetch_prices(["005930", "000660", "035720"])) == {"005930": (70_100.0, "ws"), "000660": (201_000.0, "rest")}
    assert calls == [["000660", "035720"]]
    clock["t"] += 5                        # 15초 안 — REST 다시 안 부르고 받아 둔 값
    assert run(kis_trade._fetch_prices(["000660"]))["000660"] == (201_000.0, "rest") and len(calls) == 1
    clock["t"] += 200                      # REST 실패 + 받아 둔 값이 오래됨 → 그 종목은 빠짐 (지어내지 않음)
    assert run(kis_trade._fetch_prices(["000660"])) == {} and "점검" in kis_trade._rest["error"]


def test_index_change_takes_worse_and_caches(monkeypatch):
    from app.services.kis_api import kis_client
    clock = {"t": 5_000.0}
    monkeypatch.setattr(kis_trade, "time", SimpleNamespace(time=lambda: clock["t"]))
    rates = {"0001": -0.8, "1001": -2.3}
    n = {"calls": 0}

    async def idx(code):
        n["calls"] += 1
        if rates is None:
            raise KISError("x")
        return {"price": 1.0, "change": 0.0, "change_rate": rates[code]}
    monkeypatch.setattr(kis_client, "get_kr_index", idx)
    kis_trade._index.update(at=0.0, change=None, error=None)
    assert run(kis_trade._index_change()) == -2.3 and n["calls"] == 2
    assert run(kis_trade._index_change()) == -2.3 and n["calls"] == 2    # 60초 캐시

    async def boom(code):
        raise KISError("KIS FHPUP02100000 실패")
    monkeypatch.setattr(kis_client, "get_kr_index", boom)
    clock["t"] += 61
    assert run(kis_trade._index_change()) is None and "FHPUP02100000" in kis_trade._index["error"]


def test_buy_wait_reason_boundaries():
    from app.models.kis import KisOrder
    lim = kis_trade.clean_limits({})
    k = KisOrder(symbol="005930", ref_price=70_000)
    at = dt.datetime(2026, 11, 24, 10, 0, tzinfo=KST)
    assert kis_trade.buy_wait_reason(k, 72_100, lim, 0.0, at) is None            # +3.0% 는 허용 (넘어야 기다림)
    assert kis_trade.buy_wait_reason(k, 72_200, lim, 0.0, at)[0] == "gap"
    assert kis_trade.buy_wait_reason(k, 70_000, lim, -2.0, at)[0] == "index"     # −2.0% 이면 보류
    assert kis_trade.buy_wait_reason(k, 70_000, lim, -1.99, at) is None
    assert kis_trade.buy_wait_reason(k, 70_000, lim, 0.0, at.replace(hour=9, minute=4))[0] == "open"
    assert kis_trade.buy_wait_reason(k, 70_000, lim, 0.0, at.replace(hour=9, minute=5)) is None
    kis_trade._hist.clear()
    assert kis_trade.shock_reason(k, 65_800, lim) is None                       # −6.0% 는 아직
    assert "급락" in kis_trade.shock_reason(k, 65_700, lim)


def test_ledger_rate_limit_retried_for_reads_not_orders(monkeypatch):
    """EGW00215(원장 초당 건수 초과 — 모의투자 잔고 조회에서 실제로 나옴, 2026-11-26 화면) → 조회는 기다렸다 다시, 주문은 다시 안 보냄"""
    import httpx
    from app.services import kis_api
    cl = KISClient(app_key="k", app_secret="s", base_url=KIS_MOCK_BASE)
    cl._access_token, cl._token_expires = "t", dt.datetime.now() + dt.timedelta(hours=1)
    waits = []

    async def no_wait(attempt):
        waits.append(attempt)
    monkeypatch.setattr(cl, "_rate_limited", no_wait)
    n = {"calls": 0}

    def handler(req):
        n["calls"] += 1
        if n["calls"] == 1:
            return httpx.Response(500, json={"rt_cd": "1", "msg_cd": "EGW00215", "msg1": "원장에서 허용 가능한 초당 거래건수를 초과하였습니다."})
        return httpx.Response(200, json={"rt_cd": "0", "output1": []})
    cl._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert run(cl._get("/uapi/domestic-stock/v1/trading/inquire-balance", "VTTC8434R", {}))["rt_cd"] == "0"
    assert n["calls"] == 2 and waits == [0]
    n["calls"] = 0
    with pytest.raises(KISError) as e:
        run(cl._post("/uapi/domestic-stock/v1/trading/order-cash", "VTTC0012U", {}))
    assert "EGW00215" in str(e.value) and n["calls"] == 1


def test_overview_shows_ws_status_and_param_ranges(kenv, monkeypatch):
    from app.services import kis_ws
    monkeypatch.setattr(kis_ws, "status", lambda: {"connected": False, "subscribed": 0, "last_error": "연결 거부", "last_message": None,
                                                   "reconnects": 2, "watching": 3, "session": True})
    st = kenv.c.get("/api/kis/status").json()
    assert st["watch"]["ws"] == {"connected": False, "subscribed": 0, "last_error": "연결 거부", "last_message": None, "reconnects": 2}
    assert st["param_meta"]["max_positions"] == {"default": 5, "min": 1, "max": 15, "label": "최대 보유 종목 수"}


# ---------------- 장중 AI 제안 (사용자 결정 2026-11-26) ----------------

def test_intraday_due_every_minutes():
    lim = kis_trade.clean_limits({})
    assert lim["intraday_every_min"] == 5
    at = lambda h, m, d=24: dt.datetime(2026, 11, d, h, m, tzinfo=KST)   # noqa: E731
    assert not kis_trade.intraday_due({}, lim, at(9, 29))                 # 09:30 부터
    assert kis_trade.intraday_due({}, lim, at(9, 30))
    assert kis_trade.intraday_due({}, lim, at(15, 0)) and not kis_trade.intraday_due({}, lim, at(15, 1))   # 15:00 까지
    st = lambda ts, d="2026-11-24": {"intraday": {"date": d, "last_start": ts}}   # noqa: E731
    t0 = at(10, 0).timestamp()
    assert not kis_trade.intraday_due(st(t0), lim, at(10, 4))
    assert kis_trade.intraday_due(st(t0), lim, at(10, 5))                 # 5분 지남
    assert kis_trade.intraday_due(st(t0, "2026-11-23"), lim, at(10, 1))   # 어제 기록은 무시
    assert not kis_trade.intraday_due({}, lim, at(10, 0, d=28))           # 토요일
    assert not kis_trade.intraday_due({}, {**lim, "intraday_every_min": 0}, at(11, 0))   # 0 = 끔
    assert kis_trade.intraday_due(st(t0), {**lim, "intraday_every_min": 3}, at(10, 3))
    assert kis_trade.clean_limits({"intraday_every_min": 0})["intraday_every_min"] == 0
    for bad in (1, 2, 61):
        with pytest.raises(ValueError):
            kis_trade.clean_limits({"intraday_every_min": bad})
    assert kis_trade.clean_limits({}, base={"intraday_runs": 3})["intraday_every_min"] == 5   # 예전 설정 이름은 무시


def test_intraday_chase_bounds():
    lim = kis_trade.clean_limits({})   # 허용 3%
    r = lambda c: {"name": "A", "close": c}   # noqa: E731
    assert kis_trade.intraday_chase(r(103), 100, lim) is None              # 딱 +3% 는 괜찮음
    assert "쫓아가서" in kis_trade.intraday_chase(r(103.5), 100, lim)
    assert kis_trade.intraday_chase(r(94), 100, lim) is None               # −6% 까지
    assert "급락" in kis_trade.intraday_chase(r(93.9), 100, lim)
    assert kis_trade.intraday_chase(r(150), None, lim) is None             # 전날 종가 모름 → 막지 않음 (decide 가 판단)


def test_project_today_scales_partial_volume():
    from app.services import papertrade
    cs = [{"date": "2026-11-23", "close": 100, "volume": 1000}, {"date": "2026-11-24", "close": 101, "volume": 300}]
    noon = dt.datetime(2026, 11, 24, 12, 15, tzinfo=KST)    # 09:00~15:30 중 195/390 분 = 절반
    out = papertrade.project_today("KR", cs, noon)
    assert out[-1]["volume"] == 600 and out[-1]["close"] == 101 and out[0] == cs[0]
    assert cs[-1]["volume"] == 300                                         # 원본은 그대로
    early = papertrade.project_today("KR", cs, dt.datetime(2026, 11, 24, 9, 5, tzinfo=KST))
    assert early[-1]["volume"] == 3000                                     # 최소 10% 로 (개장 직후 몇 분으로 부풀리지 않게)
    assert papertrade.project_today("KR", cs, dt.datetime(2026, 11, 24, 15, 40, tzinfo=KST)) == cs   # 장 끝남 → 그대로
    assert papertrade.project_today("KR", cs, dt.datetime(2026, 11, 25, 10, 0, tzinfo=KST)) == cs    # 오늘 봉 없음
    assert papertrade.project_today("KR", [], noon) == []


def _intraday_env(kenv, monkeypatch):
    """보유 005930 · 어제 저녁 제안(승인 대기) 000660 · 어제 저녁 거절한 068270 + 장중 판단 결과 5종목"""
    from app.services import papertrade
    kenv.b.holdings["005930"] = [10, 65_000]
    kenv.clock["t"] = dt.datetime(2026, 11, 23, 15, 50, tzinfo=KST)        # 월요일 장 마감 뒤
    pend = buy(kenv, sym="000660", budget=2_000_000, ref=200_000)
    rej = buy(kenv, sym="068270", budget=1_000_000, ref=150_000)
    kenv.c.post("/api/kis/orders/reject", json={"ids": [rej]})
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 10, 0, tzinfo=KST)          # 화요일 장중
    seen = {}

    def row(name, score, prob, close):
        return {"name": name, "score": score, "prob": prob, "close": close, "quant": 80, "grade": "A", "accum": 30,
                "accum_ok": False, "ma50": close * 0.9}

    async def fake(market, user_id, positions, params, intraday=False):
        seen.update(intraday=intraday, positions=dict(positions))
        rows = {"005930": row("삼성", 80, 65, 70_000), "000660": row("하이닉스", 80, 65, 200_000),
                "068270": row("셀트리온", 80, 65, 150_000), "035420": row("네이버", 75, 62, 101_000),
                "051910": row("LG화학", 90, 70, 105_000), "035720": row("카카오", 40, 50, 40_000)}
        prev = {"005930": 69_000, "000660": 199_000, "068270": 150_000, "035420": 100_000, "051910": 100_000, "035720": 40_000}
        return {"rows": rows, "regime": "상승 추세", "events": [], "aw": None, "last": "2026-11-24", "errors": [], "index": [],
                "prev_close": prev}
    monkeypatch.setattr(papertrade, "analyze_live", fake)
    return SimpleNamespace(pend=pend, rej=rej, seen=seen)


def test_propose_intraday_new_buys_only(kenv, monkeypatch):
    e = _intraday_env(kenv, monkeypatch)
    alerts = []
    monkeypatch.setattr(kis_trade, "_alert_admins", lambda *a, **k: alerts.append(a[0]))
    r = run(kis_trade.propose_intraday())                                # 자동 판단 첫 통과 → 확인 대기 (제안 안 함)
    assert r["proposed"] == 0 and r["waiting"] == ["네이버"] and any("확인 대기: 네이버" in n for n in r["notes"])
    assert run(kis_trade.list_log())[:1] == [] or run(kis_trade.list_log())[0]["action"] != "propose_intraday"   # 제안 없으면 감사 로그 안 쌓음
    assert not any(l.get("intraday") for l in run(kis_trade.overview(with_balance=False))["log"])
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 10, 5, tzinfo=KST)        # 5분 뒤 다시 통과 → 제안
    r = run(kis_trade.propose_intraday())
    assert r["intraday"] and r["proposed"] == 1
    assert e.seen["intraday"] is True
    assert e.seen["positions"]["000660"].get("pending") and e.seen["positions"]["005930"]["qty"] == 10   # 승인 대기 매수 = 산 것으로
    items = run(kis_trade.list_orders())
    new = [i for i in items if i["source"] == "intraday"]
    assert [i["symbol"] for i in new] == ["035420"]                      # 보유·제안 중·거절·+5%·점수 낮음은 제외
    k = new[0]
    assert k["side"] == "buy" and k["status"] == "proposed" and k["ref_price"] == 101_000 and k["reason"].startswith("장중 판단 10:05")
    assert k["expires_at"] == dt.datetime(2026, 11, 24, 15, 30, tzinfo=KST).timestamp()   # 오늘 장 마감까지
    assert order(kenv, e.pend).status == "proposed"                      # 장 마감 후 제안은 그대로 (만료 안 함)
    assert kenv.b.orders == [] and alerts and "장중" in alerts[0]       # 제안만 — 주문 없음
    st = run(kis_trade.overview())
    lg = st["log"][0]
    assert lg["intraday"] and any("LG화학" in n and "쫓아가서" in n for n in lg["notes"])
    assert any("승인 대기·진행 중 매수 1건" in n for n in lg["notes"])
    assert st["intraday"]["every"] == 5 and st["intraday"]["from"] == "09:30" and "새 매수 제안 1건" in st["intraday"]["result"]
    assert any(l["action"] == "propose_intraday" for l in run(kis_trade.list_log()))
    # 다음 장중 판단 — 방금 제안한 종목은 다시 안 묻음
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 10, 10, tzinfo=KST)
    assert run(kis_trade.propose_intraday())["proposed"] == 0
    # 승인 → 장중 조건이 맞으면 지정가 매수 (기존 매수와 같은 흐름)
    kenv.b.prices["035420"] = 101_000
    res = approve(kenv, k["id"]).json()["results"][0]
    assert res["status"] == "submitted" and kenv.b.orders[-1]["symbol"] == "035420" and kenv.b.orders[-1]["limit"]


def test_intraday_confirm_needs_consecutive_pass(kenv, monkeypatch):
    """두 번 '연속' 이어야 함 — 사이에 한 번 통과 못 하거나 오래 비면 처음부터. 손으로 누른 판단은 바로 제안"""
    from app.services import papertrade
    _intraday_env(kenv, monkeypatch)
    orig = papertrade.analyze_live
    flags = {"low": False}

    async def maybe_low(*a, **k):
        r = await orig(*a, **k)
        if flags["low"]:
            r["rows"]["035420"] = {**r["rows"]["035420"], "score": 50}
        return r
    monkeypatch.setattr(papertrade, "analyze_live", maybe_low)
    at = lambda m: dt.datetime(2026, 11, 24, 10, m, tzinfo=KST)   # noqa: E731
    kenv.clock["t"] = at(0)
    assert run(kis_trade.propose_intraday())["waiting"] == ["네이버"]
    flags["low"] = True
    kenv.clock["t"] = at(5)
    assert run(kis_trade.propose_intraday())["waiting"] == []            # 이번엔 통과 못 함 → 끊김
    flags["low"] = False
    kenv.clock["t"] = at(10)
    assert run(kis_trade.propose_intraday())["proposed"] == 0            # 다시 첫 통과
    kenv.clock["t"] = at(30)                                               # 20분 비었음 (간격 5분 × 2.5 넘음)
    assert run(kis_trade.propose_intraday())["proposed"] == 0
    assert kenv.c.post("/api/kis/propose?intraday=true").json()["proposed"] == 1   # 손으로 = 바로


def test_propose_intraday_reserves_cash(kenv, monkeypatch):
    """현금이 승인 대기 매수 몫밖에 없으면 장중 제안 안 함 (같은 돈을 두 번 쓰지 않게)"""
    _intraday_env(kenv, monkeypatch)
    kenv.b.cash = 2_000_000                                              # = 000660 승인 대기 매수 예산
    r = run(kis_trade.propose_intraday())
    assert r["proposed"] == 0 and any("더 못 삼" in n for n in r["notes"])


def test_propose_intraday_refuses_outside_market_and_halted(kenv, monkeypatch):
    _intraday_env(kenv, monkeypatch)
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 15, 25, tzinfo=KST)
    with pytest.raises(kis_trade.TradeError):
        run(kis_trade.propose_intraday())
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 10, 0, tzinfo=KST)
    kenv.c.post("/api/kis/halt", json={"reason": ""})
    r = kenv.c.post("/api/kis/propose?intraday=true")
    assert r.status_code == 400 and "정지" in r.json()["detail"]
    assert kis_trade._intraday["running"] is False                       # 실패해도 '진행 중'이 남지 않음


def test_propose_route_intraday(kenv, monkeypatch):
    _intraday_env(kenv, monkeypatch)
    r = kenv.c.post("/api/kis/propose?intraday=true")          # 손으로 누른 판단은 확인 대기 없이 바로
    assert r.status_code == 200, r.text
    assert r.json()["intraday"] is True and r.json()["proposed"] == 1
    assert run(kis_trade.list_log())[0]["action"] == "propose_intraday"


def test_schedule_intraday_every_interval(kenv, monkeypatch):
    calls = []

    async def fake(user_id=None):
        calls.append(kis_trade._kst())
        return {"proposed": 0}
    monkeypatch.setattr(kis_trade, "propose_intraday", fake)

    async def go():
        a = await kis_trade.schedule_intraday()
        if a:
            await kis_trade._intraday["task"]
        return a
    at = lambda h, m, s=0: dt.datetime(2026, 11, 24, h, m, s, tzinfo=KST)   # noqa: E731
    kenv.clock["t"] = at(9, 20)
    assert run(go()) is False                                              # 09:30 전
    kenv.clock["t"] = at(9, 31)
    assert run(go()) is True and run(go()) is False                       # 한 번 시작하면 5분 뒤까지 안 함
    kenv.clock["t"] = at(9, 35, 58)                                        # (몇 초 일찍은 됨 — 5초 감시 주기)
    assert run(go()) is True and len(calls) == 2
    v = run(kis_trade.overview(with_balance=False))["intraday"]
    assert v["runs"] == 2 and v["every"] == 5 and v["next"] == "09:40"
    kis_trade._intraday["running"] = True                                  # 앞 판단이 아직 진행 중이면 안 겹침
    kenv.clock["t"] = at(9, 45)
    assert run(go()) is False
    kis_trade._intraday["running"] = False
    kenv.c.put("/api/kis/config", json={"limits": {"intraday_every_min": 0}, "totp_code": kenv.code()})
    kenv.clock["t"] = at(10, 0)
    assert run(go()) is False                                              # 0 = 끔


# ---------------- 미국 (해외주식 모의투자, 사용자 결정 2026-11-26) ----------------

ET = _TZ["US"]


class FakeUSBroker:
    """KIS 해외주식 모의투자 흉내 — 지정가만, 현재가 이상 매수·이하 매도 지정가는 바로 현재가로 체결"""

    def __init__(self):
        self.cash = 10_000.0
        self.prices = {"AAPL": 200.0, "NVDA": 150.0}
        self.holdings, self.orders = {}, []

    async def us_balance(self):
        hs = [{"symbol": s, "name": s, "qty": q, "sellable": q, "avg": a, "price": self.prices[s], "value": q * self.prices[s],
               "pnl": 0.0, "pnl_pct": 0.0, "exchange": "NASD"} for s, (q, a) in self.holdings.items()]
        st = sum(h["value"] for h in hs)
        return {"cash": self.cash, "d2_cash": self.cash, "total": self.cash + st, "stock_value": st, "prev_total": 0, "pnl": 0,
                "holdings": hs, "currency": "USD"}

    async def us_order(self, side, symbol, qty, price, exchange=None):
        assert price is not None, "미국은 지정가만"
        odno = f"US{len(self.orders) + 1:08d}"
        px = self.prices[symbol]
        o = {"odno": odno, "side": side, "symbol": symbol, "qty": qty, "px": px, "limit": price, "filled": 0, "exchange": exchange}
        self.orders.append(o)
        if (side == "buy" and price >= px) or (side == "sell" and price <= px):
            q, a = self.holdings.get(symbol, [0, 0])
            if side == "buy":
                self.cash -= qty * px
                self.holdings[symbol] = [q + qty, px]
            else:
                self.cash += qty * px
                if q - qty:
                    self.holdings[symbol] = [q - qty, a]
                else:
                    self.holdings.pop(symbol)
            o["filled"] = qty
        return {"odno": odno, "orgno": "", "time": "100000", "msg": "해외 주문 완료"}

    async def us_executions(self, day=None):
        return [{"odno": o["odno"], "side": o["side"], "symbol": o["symbol"], "name": "", "qty": o["qty"], "filled": o["filled"],
                 "avg_price": o["px"] if o["filled"] else 0, "amount": 0, "remain": o["qty"] - o["filled"],
                 "cancelled": o.get("cancelled", False), "cancel_qty": 0, "rejected": False, "time": ""} for o in self.orders]

    async def us_cancel(self, odno, symbol, qty, exchange=None):
        for o in self.orders:
            if o["odno"] == odno:
                o["cancelled"] = True
        return {"msg": "취소"}


@pytest.fixture
def usenv(kenv, monkeypatch):
    ub = FakeUSBroker()
    kenv.b.prices.update(ub.prices)
    ub.prices = kenv.b.prices          # kenv 가 바꿔 둔 현재가·지수 함수(_quote·_fetch_prices 등)가 미국 가격도 보게
    for name in ("us_balance", "us_order", "us_executions", "us_cancel"):
        monkeypatch.setattr(kis_order, name, getattr(ub, name))
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 10, 30, tzinfo=ET).astimezone(KST)   # 뉴욕 화요일 10:30 (한국 수요일 00:30)
    kis_trade._US["_balance_cache"].update(at=0.0, data=None, error=None)
    kenv.ub = ub
    return kenv


def us_get(env, path, **kw):
    return env.c.get(path, params={"market": "US", **kw.pop("params", {})}, **kw)


def us_post(env, path, **kw):
    return env.c.post(path, params={"market": "US", **kw.pop("params", {})}, **kw)


def add_us(env, **kw):
    from app.models.kis import KisOrder

    async def go():
        with kis_trade.market("US"):
            exp = kis_trade.expiry_for("2026-11-23")
        async with env.Session() as s:
            k = KisOrder(market="US", created_at=env.clock["t"].timestamp(), base_date="2026-11-23", source="ai", status="proposed",
                         expires_at=exp, **kw)
            s.add(k)
            await s.commit()
            return k.id
    return run(go())


def test_us_local_time_market_window_and_money():
    with kis_trade.market("US"):
        t = dt.datetime(2026, 11, 24, 10, 30, tzinfo=ET)
        assert kis_trade.market_window(t) == "open"
        assert kis_trade.market_window(dt.datetime(2026, 11, 24, 15, 55, tzinfo=ET)) == "closing"
        assert kis_trade.market_window(dt.datetime(2026, 11, 26, 11, 0, tzinfo=ET)) == "closed"   # 추수감사절 휴장
        assert kis_trade._m(1234.5) == "$1,234.50" and kis_trade._m(-3, True) == "-$3.00"
        assert kis_trade.clean_limits({})["max_order_krw"] == 1500                       # 미국 한도 = 달러
        with pytest.raises(ValueError, match="달러"):
            kis_trade.clean_limits({"max_order_krw": 1_000_000})
    assert kis_trade.mk() == "KR" and kis_trade._m(1234.6) == "1,235원"
    with pytest.raises(ValueError):
        with kis_trade.market("JP"):
            pass


def test_us_starts_off_then_resume_and_orders_separate(usenv):
    st = us_get(usenv, "/api/kis/status").json()
    assert st["market"] == "US" and st["currency"] == "USD" and st["us_off"] is True and st["halted"] is True
    assert st["limit_meta"]["max_order_krw"]["label"] == "1회 매수 한도 (달러)"
    r = us_post(usenv, "/api/kis/propose")
    assert r.status_code == 400 and "꺼져" in r.json()["detail"]
    assert us_post(usenv, "/api/kis/resume", json={"totp_code": usenv.code()}).status_code == 200
    assert us_get(usenv, "/api/kis/status").json()["us_off"] is False
    assert usenv.c.get("/api/kis/status").json()["market"] == "KR"                     # 국내는 따로 (그대로 켜져 있음)
    add_us(usenv, side="buy", symbol="AAPL", name="애플", budget=1000, ref_price=200.0, reason="AI")
    assert us_get(usenv, "/api/kis/orders").json()["items"][0]["symbol"] == "AAPL"
    assert usenv.c.get("/api/kis/orders").json()["items"] == []                         # 국내 목록엔 안 보임


def test_us_buy_limit_usd_budget_and_stop_sell_limit(usenv, monkeypatch):
    us_post(usenv, "/api/kis/resume", json={"totp_code": usenv.code()})
    oid = add_us(usenv, side="buy", symbol="AAPL", name="애플", budget=5_000, ref_price=200.0, reason="AI 점수 70")
    with kis_trade.market("US"):
        assert kis_trade._quote is not None
    r = us_post(usenv, "/api/kis/orders/approve", json={"ids": [oid], "totp_code": usenv.code()})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["status"] == "submitted", res
    o = usenv.ub.orders[0]
    assert o["limit"] == 200.6 and o["qty"] == 7          # 지정가 = 200 × 1.003 · 1회 한도 $1,500 → 7주
    assert usenv.b.orders == []                            # 국내 주문은 안 나감
    with kis_trade.market("US"):
        assert run(kis_trade.refresh_fills()) == 1
        st = run(kis_trade.overview())
    assert st["mismatches"] == [] and st["balance"]["holdings"][0]["stop"] == pytest.approx(200 * 0.93)
    # 손절가 아래로 → 자동 매도 = 현재가 −1% 지정가 (모의투자 해외는 시장가 없음)
    usenv.ub.prices["AAPL"] = 180.0
    with kis_trade.market("US"):
        n = run(kis_trade.check_exits({"AAPL": 180.0}))
    assert n == 1 and usenv.ub.orders[-1]["side"] == "sell" and usenv.ub.orders[-1]["limit"] == 178.2
    assert usenv.ub.orders[-1]["filled"] == 7
    log = us_get(usenv, "/api/kis/log").json()["items"]
    assert any("$178.20" in (x["detail"] or "") for x in log)
    assert not any(x["action"] == "auto_stop" for x in usenv.c.get("/api/kis/log").json()["items"])   # 국내 로그엔 없음


def test_us_order_api_payloads(monkeypatch):
    """kis_order 미국 주문·잔고·체결 — 보내는 값·받은 값 해석 (가짜 _call)"""
    sent = []

    async def fake_call(kind, method, path, payload):
        sent.append((kind, path, payload))
        if kind == "us_buy":
            return {"output": {"ODNO": "0030001", "ORD_TMD": "103000"}, "msg1": "ok"}
        if kind == "us_balance":
            if payload["OVRS_EXCG_CD"] == "NASD":
                return {"output1": [{"ovrs_pdno": "AAPL", "ovrs_item_name": "애플", "ovrs_cblc_qty": "3", "ord_psbl_qty": "3",
                                     "pchs_avg_pric": "190.5", "now_pric2": "200.25", "ovrs_stck_evlu_amt": "600.75",
                                     "frcr_evlu_pfls_amt": "29.25", "evlu_pfls_rt": "5.1", "ovrs_excg_cd": "NASD"}]}
            return {"output1": [{"ovrs_pdno": "BRK/B", "ovrs_item_name": "버크셔", "ovrs_cblc_qty": "1", "ord_psbl_qty": "1",
                                 "pchs_avg_pric": "500", "now_pric2": "510", "ovrs_stck_evlu_amt": "510", "frcr_evlu_pfls_amt": "10",
                                 "evlu_pfls_rt": "2", "ovrs_excg_cd": "NYSE"}]} if payload["OVRS_EXCG_CD"] == "NYSE" else {"output1": []}
        if kind == "us_cash":
            return {"output": {"ord_psbl_frcr_amt": "8888.12"}}
        if kind == "us_ccld":
            return {"output": [
                {"odno": "0030001", "sll_buy_dvsn_cd": "02", "pdno": "AAPL", "ft_ord_qty": "5", "ft_ccld_qty": "2",
                 "ft_ccld_unpr3": "200.1", "nccs_qty": "0", "rvse_cncl_dvsn": "00", "prcs_stat_name": "완료"},
                {"odno": "0030002", "orgn_odno": "0030001", "rvse_cncl_dvsn": "02", "ft_ord_qty": "3", "ft_ccld_qty": "3"},
                {"odno": "0030003", "sll_buy_dvsn_cd": "01", "pdno": "NVDA", "ft_ord_qty": "1", "ft_ccld_qty": "0",
                 "nccs_qty": "0", "rvse_cncl_dvsn": "00", "prcs_stat_name": "거부"}]}
        return {}
    monkeypatch.setattr(kis_order, "_call", fake_call)
    monkeypatch.setattr(kis_order, "creds", lambda: ("k", "s", "50123456-01"))
    r = run(kis_order.us_order("buy", "AAPL", 5, 200.6, "NAS"))
    assert r["odno"] == "0030001"
    body = sent[0][2]
    assert body["OVRS_EXCG_CD"] == "NASD" and body["OVRS_ORD_UNPR"] == "200.60" and body["ORD_DVSN"] == "00" and body["CANO"] == "50123456"
    with pytest.raises(ValueError):
        run(kis_order.us_order("buy", "AAPL", 1, 200.605))      # 호가 단위($0.01) 안 맞음
    with pytest.raises(ValueError):
        run(kis_order.us_order("buy", "AAPL", 1, None))         # 지정가만
    b = run(kis_order.us_balance())
    assert b["d2_cash"] == 8888.12 and {h["symbol"] for h in b["holdings"]} == {"AAPL", "BRK-B"}
    assert b["total"] == pytest.approx(8888.12 + 600.75 + 510) and b["prev_total"] == 0
    ex = {e["odno"]: e for e in run(kis_order.us_executions(dt.date(2026, 11, 24)))}
    assert set(ex) == {"0030001", "0030003"}                    # 취소 줄은 원주문에 합침
    assert ex["0030001"]["cancelled"] and ex["0030001"]["cancel_qty"] == 3 and ex["0030001"]["filled"] == 2
    assert ex["0030003"]["rejected"] and ex["0030003"]["side"] == "sell"
    assert kis_order.us_tick_up(10.001) == 10.01 and kis_order.us_tick_down(10.009) == 10.0


def test_us_guard_refuses_real_server(monkeypatch):
    from app.services import kis_order as ko
    monkeypatch.setattr(ko, "creds", lambda: ("k", "s", "50123456-01"))
    cl = KISClient(app_key="k", app_secret="s", base_url=KIS_REAL_BASE)
    monkeypatch.setattr(ko, "client", lambda: cl)
    with pytest.raises(KISError, match="실거래"):
        run(ko.us_order("buy", "AAPL", 1, 100.0))
