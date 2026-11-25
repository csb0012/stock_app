"""보안: 유출 비밀번호 차단(HIBP k-익명성) · 계정별 잠금 · 새 IP 로그인 알림 · X-Forwarded-For 위조 · 2단계 코드 재사용 · KIS 토큰 노출"""
import hashlib
import time

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from tests.conftest import run
from app.services import pwned

LEAKED = "password123"
LEAKED_HASH = hashlib.sha1(LEAKED.encode()).hexdigest().upper()
LEAKED2 = "sunshine777"
LEAKED2_HASH = hashlib.sha1(LEAKED2.encode()).hexdigest().upper()


class FakeHIBP:
    """가짜 api.pwnedpasswords.com — 받은 주소·헤더를 기록하고 range 응답을 줌"""
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def client(self, *a, **k):
        fake = self

        class C:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *e):
                return False

            async def get(self, url, headers=None):
                fake.calls.append((url, headers))
                if fake.fail:
                    raise ConnectionError("차단됨")
                prefix = url.rsplit("/", 1)[1]
                lines = ["0000000000000000000000000000000000A:0"]      # 패딩 줄 (횟수 0)
                if prefix == LEAKED_HASH[:5]:
                    lines.append(f"{LEAKED_HASH[5:]}:2254650")
                if prefix == LEAKED2_HASH[:5]:
                    lines.append(f"{LEAKED2_HASH[5:]}:1234")
                lines.append("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:3")

                class R:
                    status_code = 200
                    text = "\r\n".join(lines)
                return R()
        return C()


@pytest.fixture
def hibp(monkeypatch):
    from app.core.config import settings
    fake = FakeHIBP()
    monkeypatch.setattr(settings, "pwned_check", True)
    monkeypatch.setattr(pwned.httpx, "AsyncClient", fake.client)
    pwned._cache.clear()
    return fake


def test_pwned_sends_only_5_char_prefix(hibp):
    assert run(pwned.leak_count(LEAKED)) == 2254650
    url, headers = hibp.calls[0]
    assert url.endswith("/range/" + LEAKED_HASH[:5]) and LEAKED_HASH[5:] not in url and LEAKED not in url
    assert headers.get("Add-Padding") == "true"
    assert run(pwned.leak_count("Zq9-unique-Passw0rd-xyz")) == 0
    assert run(pwned.leak_count(LEAKED)) == 2254650 and len(hibp.calls) == 2     # 같은 앞자리는 캐시


def test_pwned_fail_open_and_disabled(monkeypatch):
    from app.core.config import settings
    fake = FakeHIBP(fail=True)
    monkeypatch.setattr(settings, "pwned_check", True)
    monkeypatch.setattr(pwned.httpx, "AsyncClient", fake.client)
    pwned._cache.clear()
    assert run(pwned.leak_count(LEAKED)) is None                                # 확인 못 하면 막지 않음
    monkeypatch.setattr(settings, "pwned_check", False)
    assert run(pwned.leak_count(LEAKED)) is None and len(fake.calls) == 1


# ---------------- 로그인 API ----------------

@pytest.fixture
def client(monkeypatch):
    from app.core.database import Base, get_db
    from app.core.security import get_password_hash
    from app.api.routes import auth, stocks
    from app.models import user as user_model, watchlist as _w, portfolio as _p, prediction as _pr, flow as _f, paper as _pp  # noqa: F401
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as s:
            s.add(user_model.User(username="me", hashed_password=get_password_hash(LEAKED), email="me@example.com",
                                  email_verified=True))
            s.add(user_model.User(username="other", hashed_password=get_password_hash("Other-pass-77")))
            await s.commit()
    run(setup())

    async def _db():
        async with Session() as s:
            yield s
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(stocks.router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    sent = []

    async def fake_send(to, subject, body):
        sent.append((to, subject, body))
    monkeypatch.setattr(auth.mailer, "configured", lambda: True)
    monkeypatch.setattr(auth.mailer, "send", fake_send)
    with TestClient(app) as c:
        yield c, sent, Session
    run(engine.dispose())


def login(c, user="me", pw=LEAKED, ip="10.0.0.1", code=None):
    return c.post("/api/auth/login", json={"username": user, "password": pw, "totp_code": code},
                  headers={"X-Forwarded-For": ip, "User-Agent": "pytest-browser"})


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_leaked_password_warns_on_login_and_blocks_change(client, hibp):
    c, sent, Session = client
    r = login(c).json()
    assert r["password_leaked"] is True                                          # 로그인은 되지만 경고
    tok = r["access_token"]
    assert c.get("/api/auth/me", headers=H(tok)).json()["password_leaked"] is True
    # 유출 목록의 비밀번호로는 못 바꿈
    r = c.post("/api/auth/password/change", json={"current_password": LEAKED, "new_password": LEAKED2}, headers=H(tok))
    assert r.status_code == 400 and "유출된 비밀번호 목록에 1,234번" in r.json()["detail"]
    # 목록에 없는 비밀번호로 바꾸면 경고가 꺼짐
    r = c.post("/api/auth/password/change", json={"current_password": LEAKED, "new_password": "Zq9-unique-Passw0rd"}, headers=H(tok))
    assert r.status_code == 200
    assert c.get("/api/auth/me", headers=H(r.json()["access_token"])).json()["password_leaked"] is False
    assert login(c, pw="Zq9-unique-Passw0rd", ip="10.0.0.1").json()["password_leaked"] is False


def test_leak_check_unreachable_does_not_block_login(client, monkeypatch):
    from app.core.config import settings
    c, sent, Session = client
    monkeypatch.setattr(settings, "pwned_check", True)
    monkeypatch.setattr(pwned.httpx, "AsyncClient", FakeHIBP(fail=True).client)
    pwned._cache.clear()
    r = login(c)
    assert r.status_code == 200 and r.json()["password_leaked"] is False


def test_account_lock_across_ips(client, monkeypatch):
    """IP 를 바꿔 가며 한 계정에 대입해도 10번 틀리면 그 계정은 15분 잠김 (맞는 비밀번호도) + 알림 메일"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "login_alert", True)
    c, sent, Session = client
    for i in range(10):
        r = login(c, pw="wrong", ip=f"10.1.{i}.1")
        assert r.status_code == 401
    r = login(c, ip="10.2.0.1")                                       # 맞는 비밀번호·새 IP 여도
    assert r.status_code == 429 and "이 계정에 로그인 실패가 많아" in r.json()["detail"]
    assert any("잠갔습니다" in s for _, s, _ in sent) and sent[0][0] == "me@example.com"
    assert login(c, user="other", pw="Other-pass-77", ip="10.2.0.1").status_code == 200   # 다른 계정은 영향 없음
    from app.api.routes import auth
    from app.models.user import User
    from sqlalchemy import update
    auth._acct_locked.clear()                                         # 서버를 다시 켠 것처럼 메모리 기록을 지워도
    assert login(c, ip="10.2.0.1").status_code == 429                 # DB(locked_until)에 남아 계속 잠김

    async def unlock():
        async with Session() as s:
            await s.execute(update(User).where(User.username == "me").values(locked_until=time.time() - 1))
            await s.commit()
    run(unlock())
    assert login(c, ip="10.2.0.1").status_code == 200                 # 잠금 시간이 지나면 로그인


def test_spoofed_forwarded_for_cannot_dodge_ip_block(client):
    """X-Forwarded-For 맨 앞 값은 접속자가 마음대로 넣을 수 있음 → 맨 뒤(프록시가 본 IP) 기준으로 차단"""
    c, sent, Session = client
    for i in range(5):
        assert login(c, user="other", pw="x", ip=f"6.6.6.{i}, 203.0.113.9").status_code == 401
    r = login(c, user="other", pw="Other-pass-77", ip="7.7.7.7, 203.0.113.9")
    assert r.status_code == 429 and "차단" in r.json()["detail"]


def test_new_ip_login_alert(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "login_alert", True)
    c, sent, Session = client
    assert login(c, ip="10.0.0.1").status_code == 200                 # 첫 로그인 — 비교할 기록 없음 → 알림 없음
    assert login(c, ip="10.0.0.1").status_code == 200                 # 같은 IP → 없음
    assert sent == []
    assert login(c, ip="198.51.100.7").status_code == 200             # 처음 보는 IP → 알림
    assert len(sent) == 1 and "새 IP" in sent[0][1] and "198.51.100.7" in sent[0][2] and "pytest-browser" in sent[0][2]
    assert login(c, ip="198.51.100.7").status_code == 200 and len(sent) == 1
    monkeypatch.setattr(settings, "login_alert", False)                # 끄면 안 보냄
    assert login(c, ip="192.0.2.1").status_code == 200 and len(sent) == 1


def test_totp_code_cannot_be_reused(client, monkeypatch):
    from app.core import security
    t0 = 1_800_000_000.0
    monkeypatch.setattr(security, "_now", lambda: t0)
    c, sent, Session = client
    tok = login(c, user="other", pw="Other-pass-77").json()["access_token"]
    sec = c.post("/api/auth/setup-totp", headers=H(tok)).json()["secret"]
    T = pyotp.TOTP(sec)
    assert c.post("/api/auth/enable-totp", json={"totp_code": T.at(t0)}, headers=H(tok)).status_code == 200
    assert login(c, user="other", pw="Other-pass-77", code=T.at(t0)).status_code == 401           # 같은 코드
    assert login(c, user="other", pw="Other-pass-77", code=T.at(t0 - 30)).status_code == 401      # 이전 코드
    assert login(c, user="other", pw="Other-pass-77", code=T.at(t0 + 30)).status_code == 200      # 다음 코드
    assert login(c, user="other", pw="Other-pass-77", code=T.at(t0 + 30)).status_code == 401


def test_totp_step_window():
    from app.core.security import totp_step
    sec = pyotp.random_base32()
    T, t = pyotp.TOTP(sec), 1_800_000_015.0
    s = int(t // 30)
    assert totp_step(sec, T.at(t), t) == s
    assert totp_step(sec, T.at(t - 30), t) == s - 1 and totp_step(sec, T.at(t + 30), t) == s + 1
    assert totp_step(sec, T.at(t - 60), t) is None
    for bad in ("", "12345", "abcdef", "1234567", None):
        assert totp_step(sec, bad, t) is None


def test_kis_test_endpoint_hides_token(client, monkeypatch):
    from app.services.kis_api import kis_client
    c, sent, Session = client

    async def tok():
        return "SECRET-TOKEN-abcdefghijklmnopqrstuvwxyz"
    monkeypatch.setattr(kis_client, "_get_token", tok)
    r = c.get("/api/stocks/test/kis").json()
    assert r["status"] == "ok" and "SECRET" not in str(r) and "token_preview" not in r


def test_token_header_works_behind_caddy_basic_auth(client):
    """클라우드: 브라우저가 Authorization 에 Caddy 접속 비밀번호(Basic)를 실어 보냄 → 앱 토큰은 X-Access-Token 으로.
    예전엔 화면이 Authorization 에 토큰을 넣어 Basic 이 지워지고 Caddy 가 모든 요청을 401 로 막았음 (로그인 직후 다시 로그인 화면)"""
    import base64
    c, sent, Session = client
    tok = login(c).json()["access_token"]
    basic = "Basic " + base64.b64encode(b"gate:gate-pass").decode()
    r = c.get("/api/auth/me", headers={"Authorization": basic, "X-Access-Token": tok})
    assert r.status_code == 200 and r.json()["username"] == "me"
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 200      # 예전 방식도 됨
    r = c.get("/api/auth/me", headers={"Authorization": basic})                                       # 토큰 없음
    assert r.status_code == 401 and "로그인이 필요" in r.json()["detail"]
    assert c.get("/api/auth/me", headers={"X-Access-Token": "garbage"}).status_code == 401
