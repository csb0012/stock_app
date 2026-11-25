"""회원가입(이메일 인증) · 비밀번호 찾기/변경 · 이메일 인증 · 탈퇴 · 토큰 무효화 · 메일 발송(가짜 SMTP 서버)"""
import base64
import re
import socketserver
import threading
import time

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.conftest import run
from app.core.config import settings
from app.services import mailer, email_codes


@pytest.fixture
def env(monkeypatch):
    """인증 라우터 + 메모리 DB + 보낸 메일 수집 (실제 메일은 안 보냄)"""
    from app.core.database import Base, get_db
    from app.core.security import get_password_hash
    from app.api.routes import auth, watchlist
    from app.models import user as user_model, watchlist as wl_model, portfolio as _p, prediction as _pr, flow as _f  # noqa: F401
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as s:   # 이메일 없는 예전 계정
            s.add(user_model.User(username="old", hashed_password=get_password_hash("oldpass123")))
            await s.commit()
    run(setup())

    async def _db():
        async with Session() as s:
            yield s
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(watchlist.router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    auth._fails.clear(); auth._locked.clear(); email_codes._ip_sent.clear()

    sent = []

    async def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
    monkeypatch.setattr(mailer, "send", fake_send)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(settings, "signup_open", True)
    monkeypatch.setattr(email_codes, "COOLDOWN", 0)
    with TestClient(app) as c:
        yield c, sent, Session
    run(engine.dispose())


def code_of(sent):
    return re.search(r"인증 코드: (\d{6})", sent[-1]["body"]).group(1)


def signup(c, sent, username="newbie", email="Me@Naver.com", pw="abcd1234"):
    r = c.post("/api/auth/signup/send-code", json={"email": email})
    assert r.status_code == 200, r.text
    return c.post("/api/auth/register", json={"username": username, "password": pw, "email": email, "code": code_of(sent)})


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- 회원가입 ----------------

def test_signup_flow(env):
    c, sent, _ = env
    r = signup(c, sent)
    assert r.status_code == 200 and r.json()["username"] == "newbie" and r.json()["access_token"]
    assert sent[0]["to"] == "me@naver.com" and "회원가입" in sent[0]["subject"]
    me = c.get("/api/auth/me", headers=h(r.json()["access_token"])).json()
    assert me["email"] == "me@naver.com" and me["email_verified"] is True
    # 아이디·이메일로 둘 다 로그인
    assert "access_token" in c.post("/api/auth/login", json={"username": "newbie", "password": "abcd1234"}).json()
    assert c.post("/api/auth/login", json={"username": "ME@naver.com", "password": "abcd1234"}).json()["username"] == "newbie"
    # 같은 이메일·같은 아이디(대소문자 무시)로는 다시 못 함
    assert c.post("/api/auth/signup/send-code", json={"email": "me@naver.com"}).status_code == 400
    c.post("/api/auth/signup/send-code", json={"email": "other@naver.com"})
    r = c.post("/api/auth/register", json={"username": "NEWBIE", "password": "abcd1234", "email": "other@naver.com", "code": code_of(sent)})
    assert r.status_code == 400 and "아이디" in r.json()["detail"]


@pytest.mark.parametrize("username, pw, msg", [
    ("ab", "abcd1234", "아이디"), ("bad name", "abcd1234", "아이디"), ("가나다", "abcd1234", "아이디"),
    ("good_1", "short1", "8자"), ("good_1", "abcdefgh", "영문과 숫자"), ("good_1", "12345678", "영문과 숫자"),
    ("good_1", "good_1abc9", "아이디"),
])
def test_signup_rules(env, username, pw, msg):
    c, sent, _ = env
    c.post("/api/auth/signup/send-code", json={"email": "x@naver.com"})
    r = c.post("/api/auth/register", json={"username": username, "password": pw, "email": "x@naver.com", "code": code_of(sent)})
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_signup_code_errors(env, monkeypatch):
    c, sent, _ = env
    assert c.post("/api/auth/signup/send-code", json={"email": "not-an-email"}).status_code == 400
    c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"})
    good = code_of(sent)
    wrong = "000000" if good != "000000" else "111111"
    for i in range(5):
        r = c.post("/api/auth/register", json={"username": "kimtest", "password": "zxcv5678", "email": "a@naver.com", "code": wrong})
        assert r.status_code == 400
    assert "남은 기회" not in r.json()["detail"]
    # 5번 틀리면 맞는 코드도 무효
    r = c.post("/api/auth/register", json={"username": "kimtest", "password": "zxcv5678", "email": "a@naver.com", "code": good})
    assert r.status_code == 400 and "5번" in r.json()["detail"]
    # 다른 메일 주소의 코드로는 안 됨
    c.post("/api/auth/signup/send-code", json={"email": "b@naver.com"})
    r = c.post("/api/auth/register", json={"username": "kimtest", "password": "zxcv5678", "email": "c@naver.com", "code": code_of(sent)})
    assert r.status_code == 400
    # 만료
    c.post("/api/auth/signup/send-code", json={"email": "d@naver.com"})
    code = code_of(sent)
    monkeypatch.setattr(email_codes.time, "time", lambda: time.monotonic() + 10 ** 10)
    r = c.post("/api/auth/register", json={"username": "kimtest", "password": "zxcv5678", "email": "d@naver.com", "code": code})
    assert r.status_code == 400 and "만료" in r.json()["detail"]


def test_signup_closed_and_no_mail(env, monkeypatch):
    c, _, _ = env
    monkeypatch.setattr(mailer, "configured", lambda: False)
    r = c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"})
    assert r.status_code == 503 and "SMTP" in r.json()["detail"]
    assert c.get("/api/auth/options").json() == {"signup_open": True, "mail_configured": False}
    monkeypatch.setattr(settings, "signup_open", False)
    assert c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"}).status_code == 403
    assert c.post("/api/auth/register", json={"username": "kimtest", "password": "zxcv5678", "email": "a@naver.com", "code": "123456"}).status_code == 403


def test_cooldown_and_ip_limit(env, monkeypatch):
    c, sent, _ = env
    monkeypatch.setattr(email_codes, "COOLDOWN", 60)
    assert c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"}).status_code == 200
    r = c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"})
    assert r.status_code == 429 and "초 뒤" in r.json()["detail"]
    monkeypatch.setattr(email_codes, "COOLDOWN", 0)
    for i in range(9):
        c.post("/api/auth/signup/send-code", json={"email": f"u{i}@naver.com"})
    r = c.post("/api/auth/signup/send-code", json={"email": "z@naver.com"})
    assert r.status_code == 429 and "1시간" in r.json()["detail"]


def test_mail_failure_allows_retry(env, monkeypatch):
    c, sent, _ = env
    monkeypatch.setattr(email_codes, "COOLDOWN", 60)

    async def boom(*a):
        raise mailer.MailError("메일 계정 로그인 실패 — 테스트")
    monkeypatch.setattr(mailer, "send", boom)
    r = c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"})
    assert r.status_code == 502 and "로그인 실패" in r.json()["detail"]

    async def ok(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
    monkeypatch.setattr(mailer, "send", ok)
    assert c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"}).status_code == 200   # 60초 안 기다려도 됨


# ---------------- 비밀번호 찾기 · 변경 ----------------

def test_forgot_and_reset(env):
    c, sent, _ = env
    signup(c, sent, "kim", "kim@naver.com", "first1234")
    old_tok = c.post("/api/auth/login", json={"username": "kim", "password": "first1234"}).json()["access_token"]
    n = len(sent)
    # 없는 이메일도 같은 답 (가입 여부 노출 안 함), 메일은 안 보냄
    r1 = c.post("/api/auth/password/forgot", json={"email": "nobody@naver.com"})
    assert r1.status_code == 200 and len(sent) == n
    r2 = c.post("/api/auth/password/forgot", json={"email": "KIM@naver.com"})
    assert r2.status_code == 200 and len(sent) == n + 1 and "비밀번호 찾기" in sent[-1]["subject"]
    assert r1.json()["message"].split(" 가 ")[1] == r2.json()["message"].split(" 가 ")[1]
    code = code_of(sent)
    assert c.post("/api/auth/password/reset", json={"email": "kim@naver.com", "code": code, "new_password": "weak"}).status_code == 400
    r = c.post("/api/auth/password/reset", json={"email": "kim@naver.com", "code": code, "new_password": "second1234"})
    assert r.status_code == 200 and r.json()["username"] == "kim"
    assert c.post("/api/auth/login", json={"username": "kim", "password": "first1234"}).status_code == 401
    assert "access_token" in c.post("/api/auth/login", json={"username": "kim", "password": "second1234"}).json()
    # 바꾸기 전 토큰은 무효 (다른 기기 로그아웃)
    r = c.get("/api/auth/me", headers=h(old_tok))
    assert r.status_code == 401 and "비밀번호가 바뀌어" in r.json()["detail"]
    # 같은 코드 재사용 불가
    assert c.post("/api/auth/password/reset", json={"email": "kim@naver.com", "code": code, "new_password": "third1234"}).status_code == 400


def test_forgot_ignores_unverified_email(env):
    c, sent, _ = env
    # 예전 계정(이메일 없음)은 비밀번호 찾기 불가 → 서버 명령(--reset-password) 안내는 화면에서
    assert c.post("/api/auth/password/forgot", json={"email": "old@naver.com"}).status_code == 200
    assert sent == []


def test_change_password(env):
    c, sent, _ = env
    tok = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"}).json()["access_token"]
    other = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"}).json()["access_token"]
    bad = c.post("/api/auth/password/change", json={"current_password": "nope", "new_password": "newpass123"}, headers=h(tok))
    assert bad.status_code == 400 and "현재 비밀번호" in bad.json()["detail"]
    same = c.post("/api/auth/password/change", json={"current_password": "oldpass123", "new_password": "oldpass123"}, headers=h(tok))
    assert same.status_code == 400
    weak = c.post("/api/auth/password/change", json={"current_password": "oldpass123", "new_password": "old12345678"}, headers=h(tok))
    assert weak.status_code == 400 and "아이디" in weak.json()["detail"]
    r = c.post("/api/auth/password/change", json={"current_password": "oldpass123", "new_password": "newpass123"}, headers=h(tok))
    assert r.status_code == 200
    new_tok = r.json()["access_token"]
    assert c.get("/api/auth/me", headers=h(new_tok)).status_code == 200          # 지금 화면은 계속
    assert c.get("/api/auth/me", headers=h(other)).status_code == 401           # 다른 기기는 끊김
    assert c.post("/api/auth/login", json={"username": "old", "password": "newpass123"}).status_code == 200


# ---------------- 이메일 등록 · 탈퇴 ----------------

def test_email_register_for_old_account(env):
    c, sent, _ = env
    tok = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"}).json()["access_token"]
    assert c.get("/api/auth/me", headers=h(tok)).json()["email"] is None
    assert c.post("/api/auth/email/send-code", json={"email": "old@naver.com"}, headers=h(tok)).status_code == 200
    assert "이메일 인증" in sent[-1]["subject"]
    r = c.post("/api/auth/email/verify", json={"email": "old@naver.com", "code": code_of(sent)}, headers=h(tok))
    assert r.status_code == 200
    me = c.get("/api/auth/me", headers=h(tok)).json()
    assert me["email"] == "old@naver.com" and me["email_verified"]
    # 이제 비밀번호 찾기 메일이 감
    n = len(sent)
    c.post("/api/auth/password/forgot", json={"email": "old@naver.com"})
    assert len(sent) == n + 1
    # 다른 계정이 이 이메일을 가져갈 수 없음
    other = signup(c, sent, "second", "second@naver.com").json()["access_token"]
    assert c.post("/api/auth/email/send-code", json={"email": "old@naver.com"}, headers=h(other)).status_code == 400
    assert c.post("/api/auth/signup/send-code", json={"email": "old@naver.com"}).status_code == 400


def test_delete_account(env):
    c, sent, Session = env
    tok = signup(c, sent, "leaver", "bye@naver.com", "byebye123").json()["access_token"]
    from app.services import stock_master
    stock_master._by_key[("KR", "005930")] = {"name": "삼성전자"}
    try:
        assert c.post("/api/watchlist/", json={"symbol": "005930", "market": "KR"}, headers=h(tok)).status_code == 200
    finally:
        stock_master._by_key.pop(("KR", "005930"), None)
    assert c.post("/api/auth/delete-account", json={"password": "wrong"}, headers=h(tok)).status_code == 400
    # 2단계 인증이 켜져 있으면 코드도 필요
    sec = c.post("/api/auth/setup-totp", headers=h(tok)).json()["secret"]
    c.post("/api/auth/enable-totp", json={"totp_code": pyotp.TOTP(sec).now()}, headers=h(tok))
    r = c.post("/api/auth/delete-account", json={"password": "byebye123"}, headers=h(tok))
    assert r.status_code == 400 and "2단계" in r.json()["detail"]
    r = c.post("/api/auth/delete-account", json={"password": "byebye123", "totp_code": pyotp.TOTP(sec).now()}, headers=h(tok))
    assert r.status_code == 200
    assert c.get("/api/auth/me", headers=h(tok)).status_code == 401
    assert c.post("/api/auth/login", json={"username": "leaver", "password": "byebye123"}).status_code == 401

    async def left():
        from sqlalchemy import select, func
        from app.models.watchlist import WatchlistItem
        async with Session() as s:
            return (await s.execute(select(func.count()).select_from(WatchlistItem))).scalar()
    assert run(left()) == 0
    # 탈퇴한 이메일로 다시 가입 가능
    assert signup(c, sent, "leaver2", "bye@naver.com", "byebye123").status_code == 200


# ---------------- 실제 SMTP 발송 (가짜 SMTP 서버) ----------------

class _SMTP(socketserver.StreamRequestHandler):
    def handle(self):
        srv = self.server
        w = lambda s: self.wfile.write((s + "\r\n").encode())   # noqa: E731
        w("220 fake ESMTP")
        data_mode, buf = False, []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            t = line.decode(errors="replace").rstrip("\r\n")
            if data_mode:
                if t == ".":
                    srv.messages.append("\n".join(buf)); data_mode, buf = False, []
                    w("250 queued")
                else:
                    buf.append(t)
                continue
            cmd = t.split(" ")[0].upper()
            if cmd == "EHLO":
                self.wfile.write(b"250-fake\r\n250 AUTH PLAIN LOGIN\r\n")
            elif cmd == "AUTH":
                parts = t.split(" ")
                creds = base64.b64decode(parts[2]).split(b"\0") if len(parts) > 2 else []
                ok = len(creds) == 3 and creds[1] == srv.user and creds[2] == srv.password
                w("235 ok" if ok else "535 bad credentials")
            elif cmd in ("MAIL", "RCPT", "RSET", "NOOP"):
                if cmd == "RCPT":
                    srv.rcpts.append(t)
                w("250 ok")
            elif cmd == "DATA":
                data_mode = True; w("354 go")
            elif cmd == "QUIT":
                w("221 bye"); return
            else:
                w("502 no")


@pytest.fixture
def smtp_server(monkeypatch):
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SMTP)
    srv.daemon_threads = True
    srv.messages, srv.rcpts, srv.user, srv.password = [], [], b"me@naver.com", b"app-pass"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", srv.server_address[1])
    monkeypatch.setattr(settings, "smtp_user", "me@naver.com")
    monkeypatch.setattr(settings, "smtp_password", "app-pass")
    monkeypatch.setattr(settings, "smtp_from", "")
    yield srv
    srv.shutdown()


def test_mailer_sends_via_smtp(smtp_server):
    assert mailer.configured()
    run(mailer.send("you@naver.com", "[StockApp] 회원가입 인증 코드 123456", "인증 코드: 123456"))
    assert len(smtp_server.messages) == 1 and "you@naver.com" in smtp_server.rcpts[0]
    raw = smtp_server.messages[0]
    assert "me@naver.com" in raw                                    # 보내는 주소 = 로그인 계정 (네이버 규칙)


def test_mailer_bad_password_message(smtp_server, monkeypatch):
    monkeypatch.setattr(settings, "smtp_password", "wrong")
    with pytest.raises(mailer.MailError) as e:
        run(mailer.send("you@naver.com", "s", "b"))
    assert "로그인 실패" in str(e.value) and "wrong" not in str(e.value)   # 비밀번호는 문구에 안 넣음


def test_mailer_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "")
    with pytest.raises(mailer.MailError, match="설정이 없습니다"):
        run(mailer.send("a@b.co", "s", "b"))
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1"); monkeypatch.setattr(settings, "smtp_user", "x")
    monkeypatch.setattr(settings, "smtp_password", "y"); monkeypatch.setattr(settings, "smtp_port", 1)   # 닫힌 포트
    with pytest.raises(mailer.MailError, match="메일 발송 실패"):
        run(mailer.send("a@b.co", "s", "b"))
