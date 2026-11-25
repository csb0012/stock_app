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
    """KIS 모의투자 계좌 흉내: 시장가 주문은 바로 현재가로 체결"""

    def __init__(self):
        self.cash = 10_000_000
        self.prev_total = 10_000_000
        self.prices = {"005930": 70_000, "000660": 200_000}
        self.holdings = {}      # 종목 → [수량, 평균가]
        self.orders = []        # 보낸 주문
        self.fill = True
        self.fail = None

    async def balance(self):
        hs = [{"symbol": s, "name": f"종목{s}", "qty": q, "sellable": q, "avg": a, "price": self.prices[s],
               "value": q * self.prices[s], "pnl": 0, "pnl_pct": 0.0} for s, (q, a) in self.holdings.items()]
        stock = sum(h["value"] for h in hs)
        return {"cash": self.cash, "d2_cash": self.cash, "total": self.cash + stock, "stock_value": stock,
                "prev_total": self.prev_total, "pnl": 0, "holdings": hs}

    async def order(self, side, symbol, qty):
        if self.fail:
            raise KISError(self.fail)
        odno = f"{len(self.orders) + 1:010d}"
        px = self.prices[symbol]
        self.orders.append({"odno": odno, "side": side, "symbol": symbol, "qty": qty, "px": px, "filled": 0})
        if self.fill:
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
    monkeypatch.setattr(kis_trade, "_price_now", price_now)
    kis_trade._balance_cache.update(at=0.0, data=None, error=None)

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
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 9, 0, 30, tzinfo=KST)   # 개장 직후 1분 전엔 안 보냄
    run(kis_trade.tick())
    assert kenv.b.orders == []
    kenv.clock["t"] = dt.datetime(2026, 11, 24, 9, 1, 10, tzinfo=KST)
    run(kis_trade.tick())
    assert len(kenv.b.orders) == 1 and order(kenv, oid).status == "filled"


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


def test_price_gap_blocks_buy(kenv):
    kenv.b.prices["005930"] = 73_000      # 제안 70,000 → +4.3% (허용 3%)
    r = approve(kenv, buy(kenv)).json()["results"][0]
    assert r["status"] == "blocked" and "비싸져서" in r["message"] and kenv.b.orders == []


def test_price_crash_blocks_buy(kenv):
    kenv.b.prices["005930"] = 65_000      # 제안 70,000 → −7.1% (허용 −6%) — 판단 때와 상황이 다름
    r = approve(kenv, buy(kenv)).json()["results"][0]
    assert r["status"] == "blocked" and "급락" in r["message"] and kenv.b.orders == []
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
    assert st["mismatches"] == [{"symbol": "000660", "name": "종목000660", "app": 0, "kis": 3}]
    r = approve(kenv, buy(kenv)).json()["results"][0]
    assert r["status"] == "blocked" and "기록이 다름" in r["message"]
    assert kenv.c.post("/api/kis/baseline", json={"totp_code": kenv.code()}).status_code == 200
    kis_trade._balance_cache["data"] = None
    assert run(kis_trade.overview())["mismatches"] == []
    assert approve(kenv, buy(kenv)).json()["results"][0]["status"] == "submitted"


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
    assert run(kis_trade.list_log())[0]["action"] in ("cancel", "halt")


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


def test_exit_proposal_on_stop(kenv):
    kenv.b.holdings["005930"] = [10, 70_000]
    run(kis_trade.rebaseline(kenv.uid))
    kenv.b.prices["005930"] = 64_000      # 손절가 65,100 아래
    kis_trade._balance_cache["data"] = None
    assert run(kis_trade.check_exits()) == 1
    items = kenv.c.get("/api/kis/orders").json()["items"]
    assert items[0]["side"] == "sell" and items[0]["source"] == "exit" and "손절가" in items[0]["reason"]
    assert run(kis_trade.check_exits()) == 0   # 같은 종목 매도 제안 중복 없음
    assert kenv.b.orders == []


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
    with pytest.raises(ValueError):
        run(kis_order.order("buy", "../x", 1))


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
