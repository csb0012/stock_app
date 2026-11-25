"""전체 점검(2026-11-25)에서 찾은 문제들의 재발 방지 테스트"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.conftest import run
from app.services import stock_master, market_regime


@pytest.fixture
def master(monkeypatch):
    known = {("KR", "005930"): {"name": "삼성전자"}, ("US", "AAPL"): {"name": "애플"}}
    monkeypatch.setattr(stock_master, "get", lambda m, s: known.get((m, s)))


# ---------------- 관심종목·투자종목 입력 검증 ----------------

def test_watchlist_validation_and_delete(api_client, master):
    client, _, _ = api_client
    assert client.post("/api/watchlist/", json={"symbol": "005930", "market": "XX"}).status_code == 422
    assert client.post("/api/watchlist/", json={"symbol": "005930", "market": "KR"}).status_code == 200
    r = client.post("/api/watchlist/", json={"symbol": "005930", "market": "KR"})
    assert r.status_code == 400 and "이미" in r.json()["detail"]
    r = client.delete("/api/watchlist/9999")
    assert r.status_code == 404 and "없는" in r.json()["detail"]


@pytest.mark.parametrize("body, ok", [
    ({"quantity": 10, "avg_price": 70000}, True),
    ({"quantity": 1.5}, True),                      # 평단가 모르면 0
    ({"quantity": 0}, False),
    ({"quantity": -3, "avg_price": 100}, False),
    ({"quantity": 5, "avg_price": -1}, False),
    ({"avg_price": 100}, False),                     # 수량 빠짐
])
def test_portfolio_add_validation(api_client, master, body, ok):
    client, _, _ = api_client
    r = client.post("/api/portfolio/", json={"symbol": "005930", "market": "KR", **body})
    assert (r.status_code == 200) is ok, r.text
    if not ok:
        assert r.status_code == 422


def test_portfolio_update_delete(api_client, master):
    client, _, _ = api_client
    pid = client.post("/api/portfolio/", json={"symbol": "AAPL", "market": "US", "quantity": 2, "avg_price": 150}).json()["id"]
    assert client.put(f"/api/portfolio/{pid}", json={"quantity": 0}).status_code == 422
    assert client.put(f"/api/portfolio/{pid}", json={"avg_price": -5}).status_code == 422
    r = client.put(f"/api/portfolio/{pid}", json={"quantity": 3, "avg_price": 0})
    assert r.json()["quantity"] == 3 and r.json()["avg_price"] == 0
    assert client.post("/api/portfolio/", json={"symbol": "AAPL", "market": "XX", "quantity": 1}).status_code == 422
    assert client.delete(f"/api/portfolio/{pid}").status_code == 200
    assert client.delete(f"/api/portfolio/{pid}").status_code == 404


def test_quote_unknown_symbol_404(api_client, master):
    client, _, _ = api_client
    r = client.get("/api/stocks/quote/KR/999999")
    assert r.status_code == 404 and "종목마스터" in r.json()["detail"]
    assert client.get("/api/stocks/quote/XX/005930").status_code == 400


# ---------------- 로그인 · 2단계 인증 ----------------

@pytest.fixture
def auth_client():
    """실제 로그인 토큰으로 인증 (setup-totp 가 사용자 행을 바꾸므로 get_current_user 를 가짜로 바꾸지 않음)"""
    from app.core.database import Base, get_db
    from app.core.security import get_password_hash
    from app.api.routes import auth
    from app.models import user as user_model, watchlist as _w, portfolio as _p, prediction as _pr, flow as _f  # noqa: F401
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as s:
            s.add(user_model.User(username="me", hashed_password=get_password_hash("pw123456")))
            await s.commit()
    run(setup())

    async def _db():
        async with Session() as s:
            yield s
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    auth._fails.clear(); auth._locked.clear()
    with TestClient(app) as c:
        yield c
    run(engine.dispose())


def login(c, pw="pw123456", code=None):
    return c.post("/api/auth/login", json={"username": "me", "password": pw, "totp_code": code},
                  headers={"X-Forwarded-For": "10.9.9.9"})


def test_login_messages_korean(auth_client):
    r = login(auth_client, pw="wrong")
    assert r.status_code == 401 and r.json()["detail"] == "아이디 또는 비밀번호가 틀렸습니다"


def test_totp_full_flow(auth_client, monkeypatch):
    from app.core import security
    t0 = 1_800_000_000.0
    monkeypatch.setattr(security, "_now", lambda: t0)    # 시각 고정 (30초 칸 경계에서 흔들리지 않게)
    c = auth_client
    tok = login(c).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    setup = c.post("/api/auth/setup-totp", headers=h).json()
    assert setup["qr_code"] and setup["secret"]
    assert c.post("/api/auth/enable-totp", json={"totp_code": "000000"}, headers=h).status_code == 400
    T = pyotp.TOTP(setup["secret"])
    code = T.at(t0 - 30)                                   # 앞 칸 코드 (허용 범위)
    assert c.post("/api/auth/enable-totp", json={"totp_code": code}, headers=h).status_code == 200
    assert c.get("/api/auth/me", headers=h).json()["totp_enabled"] is True
    # 켜진 상태에서 다시 등록하면 앱 코드가 안 맞게 되므로 거부
    r = c.post("/api/auth/setup-totp", headers=h)
    assert r.status_code == 400 and "이미 켜져" in r.json()["detail"]
    # 로그인: 코드 없으면 요청, 틀리면 한국어 오류, 맞으면 토큰
    assert login(c).json() == {"requires_totp": True}
    assert "인증 코드가 틀렸" in login(c, code="000000").json()["detail"]
    # 한 번 쓴 코드(켤 때 쓴 코드)는 다시 못 씀 — 엿본 코드로 로그인하는 것 방지
    assert "이미 쓴 코드" in login(c, code=code).json()["detail"]
    assert "access_token" in login(c, code=T.at(t0)).json()
    assert "이미 쓴 코드" in login(c, code=T.at(t0)).json()["detail"]                  # 같은 코드 두 번째
    # 끄기: 틀린 코드 거부, 맞으면 꺼짐 → 비밀번호만으로 로그인
    assert c.post("/api/auth/disable-totp", json={"totp_code": "000000"}, headers=h).status_code == 400
    assert c.post("/api/auth/disable-totp", json={"totp_code": T.at(t0)}, headers=h).status_code == 400   # 이미 씀
    assert c.post("/api/auth/disable-totp", json={"totp_code": T.at(t0 + 30)}, headers=h).status_code == 200
    assert c.get("/api/auth/me", headers=h).json()["totp_enabled"] is False
    assert "access_token" in login(c).json()
    assert c.post("/api/auth/disable-totp", json={"totp_code": "123456"}, headers=h).status_code == 400   # 이미 꺼짐


# ---------------- 시장 상태: 장중 '최신 아님' 경고 안 띄우기 ----------------

@pytest.mark.parametrize("market, when, expected", [
    ("KR", datetime(2026, 11, 25, 9, 15, tzinfo=ZoneInfo("Asia/Seoul")), "2026-11-24"),     # 장중 → 어제 종가가 최신
    ("KR", datetime(2026, 11, 25, 15, 40, tzinfo=ZoneInfo("Asia/Seoul")), "2026-11-25"),    # 장 마감 후 → 오늘
    ("KR", datetime(2026, 11, 23, 8, 0, tzinfo=ZoneInfo("Asia/Seoul")), "2026-11-20"),      # 월요일 개장 전 → 금요일
    ("US", datetime(2026, 11, 27, 12, 0, tzinfo=ZoneInfo("America/New_York")), "2026-11-25"),  # 추수감사절 다음 날 장중 → 수요일
])
def test_last_closed_session(market, when, expected):
    assert market_regime.last_closed_session(market, when).isoformat() == expected
