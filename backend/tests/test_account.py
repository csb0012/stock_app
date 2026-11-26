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
from app.services import mailer, email_codes, sms


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

    async def fake_sms(to, text):   # 문자도 같은 목록에 (body 에 코드)
        sent.append({"to": to, "subject": "SMS", "body": text.replace("인증번호", "인증 코드:")})
    monkeypatch.setattr(sms, "send", fake_sms)
    monkeypatch.setattr(sms, "configured", lambda: True)
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
    o = c.get("/api/auth/options").json()
    assert {k: o[k] for k in ("signup_open", "mail_configured", "sms_configured")} == {"signup_open": True, "mail_configured": False, "sms_configured": True}
    assert "invite_required" in o and "totp_required" in o
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


def test_delete_account(env, monkeypatch):
    from app.core import security
    t0 = 1_800_000_000.0
    monkeypatch.setattr(security, "_now", lambda: t0)
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
    c.post("/api/auth/enable-totp", json={"totp_code": pyotp.TOTP(sec).at(t0)}, headers=h(tok))
    r = c.post("/api/auth/delete-account", json={"password": "byebye123"}, headers=h(tok))
    assert r.status_code == 400 and "2단계" in r.json()["detail"]
    r = c.post("/api/auth/delete-account", json={"password": "byebye123", "totp_code": pyotp.TOTP(sec).at(t0)}, headers=h(tok))
    assert r.status_code == 400                                                   # 켤 때 쓴 코드 재사용 불가
    r = c.post("/api/auth/delete-account", json={"password": "byebye123", "totp_code": pyotp.TOTP(sec).at(t0 + 30)}, headers=h(tok))
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


# ---------------- 휴대폰(문자) 본인인증 ----------------

def phone_signup(c, sent, username="phoneman", phone="010-1234-5678", pw="abcd1234", nickname=None):
    r = c.post("/api/auth/signup/send-code", json={"phone": phone})
    assert r.status_code == 200, r.text
    body = {"username": username, "password": pw, "phone": phone, "code": code_of(sent)}
    if nickname is not None:
        body["nickname"] = nickname
    return c.post("/api/auth/register", json=body)


@pytest.mark.parametrize("raw, norm", [
    ("010-1234-5678", "01012345678"), ("01012345678", "01012345678"), ("+82 10-1234-5678", "01012345678"),
    ("821012345678", "01012345678"), ("011-123-4567", "0111234567"), (" 010 9999 0000 ", "01099990000"),
])
def test_normalize_phone(raw, norm):
    assert email_codes.normalize_phone(raw) == norm


@pytest.mark.parametrize("bad", ["", "02-123-4567", "010-123", "1234567890", "010-1234-56789", "abc"])
def test_normalize_phone_bad(bad):
    with pytest.raises(email_codes.CodeError):
        email_codes.normalize_phone(bad)


def test_phone_signup_login_and_forgot(env):
    c, sent, _ = env
    r = phone_signup(c, sent)
    assert r.status_code == 200, r.text
    assert sent[0]["to"] == "01012345678" and sent[0]["subject"] == "SMS"
    me = c.get("/api/auth/me", headers=h(r.json()["access_token"])).json()
    assert me["phone"] == "010-1234-5678" and me["phone_verified"] and me["email"] is None and me["verified"]
    # 휴대폰 번호로 로그인 (하이픈 있든 없든)
    assert c.post("/api/auth/login", json={"username": "01012345678", "password": "abcd1234"}).json()["username"] == "phoneman"
    assert c.post("/api/auth/login", json={"username": "010-1234-5678", "password": "abcd1234"}).status_code == 200
    # 같은 번호로 다시 가입 불가
    r = c.post("/api/auth/signup/send-code", json={"phone": "01012345678"})
    assert r.status_code == 400 and "휴대폰" in r.json()["detail"]
    # 비밀번호 찾기 — 없는 번호도 같은 답, 문자는 안 감
    n = len(sent)
    r1 = c.post("/api/auth/password/forgot", json={"phone": "010-0000-0000"})
    assert r1.status_code == 200 and len(sent) == n
    r2 = c.post("/api/auth/password/forgot", json={"phone": "010-1234-5678"})
    assert len(sent) == n + 1 and r1.json()["message"].split(" 가 ")[1] == r2.json()["message"].split(" 가 ")[1]
    r = c.post("/api/auth/password/reset", json={"phone": "01012345678", "code": code_of(sent), "new_password": "newone123"})
    assert r.status_code == 200 and r.json()["username"] == "phoneman"
    assert c.post("/api/auth/login", json={"username": "phoneman", "password": "newone123"}).status_code == 200


def test_contact_must_be_exactly_one(env):
    c, sent, _ = env
    for body in ({}, {"email": "a@naver.com", "phone": "01012345678"}, {"email": "", "phone": ""}):
        r = c.post("/api/auth/signup/send-code", json=body)
        assert r.status_code == 400 and "하나" in r.json()["detail"]
    assert c.post("/api/auth/signup/send-code", json={"phone": "02-123-4567"}).status_code == 400


def test_sms_not_configured(env, monkeypatch):
    c, _, _ = env
    monkeypatch.setattr(sms, "configured", lambda: False)
    r = c.post("/api/auth/signup/send-code", json={"phone": "01012345678"})
    assert r.status_code == 503 and "SMS" in r.json()["detail"]
    r = c.post("/api/auth/password/forgot", json={"phone": "01012345678"})
    assert r.status_code == 503
    assert c.post("/api/auth/signup/send-code", json={"email": "a@naver.com"}).status_code == 200   # 메일은 그대로


def test_sms_failure_allows_retry(env, monkeypatch):
    c, sent, _ = env
    monkeypatch.setattr(email_codes, "COOLDOWN", 60)

    async def boom(to, text):
        raise sms.SmsError("문자 접수 실패 — 발신번호 미등록")
    monkeypatch.setattr(sms, "send", boom)
    r = c.post("/api/auth/signup/send-code", json={"phone": "01012345678"})
    assert r.status_code == 502 and "발신번호" in r.json()["detail"]

    async def ok(to, text):
        sent.append({"to": to, "subject": "SMS", "body": text.replace("인증번호", "인증 코드:")})
    monkeypatch.setattr(sms, "send", ok)
    assert c.post("/api/auth/signup/send-code", json={"phone": "01012345678"}).status_code == 200


def test_phone_register_on_mypage_and_remove_contact(env):
    c, sent, _ = env
    tok = signup(c, sent, "both", "both@naver.com", "zz9876qq").json()["access_token"]
    # 이메일만 있으면 이메일은 못 지움 (본인인증 수단이 하나는 남아야)
    r = c.post("/api/auth/contact/remove", json={"kind": "email", "password": "zz9876qq"}, headers=h(tok))
    assert r.status_code == 400 and "하나는 남아야" in r.json()["detail"]
    assert c.post("/api/auth/phone/send-code", json={"phone": "010-5555-6666"}, headers=h(tok)).status_code == 200
    assert "휴대폰 인증" in sent[-1]["body"]
    bad = c.post("/api/auth/phone/verify", json={"phone": "01055556666", "code": "000000" if code_of(sent) != "000000" else "111111"}, headers=h(tok))
    assert bad.status_code == 400
    r = c.post("/api/auth/phone/verify", json={"phone": "01055556666", "code": code_of(sent)}, headers=h(tok))
    assert r.status_code == 200 and r.json()["phone"] == "010-5555-6666"
    me = c.get("/api/auth/me", headers=h(tok)).json()
    assert me["phone"] == "010-5555-6666" and me["email"] == "both@naver.com"
    # 이미 인증된 같은 번호 다시 / 다른 계정이 가져가기 불가
    assert c.post("/api/auth/phone/send-code", json={"phone": "01055556666"}, headers=h(tok)).status_code == 400
    other = phone_signup(c, sent, "other1", "010-7777-8888").json()["access_token"]
    r = c.post("/api/auth/phone/send-code", json={"phone": "01055556666"}, headers=h(other))
    assert r.status_code == 400 and "다른 계정" in r.json()["detail"]
    # 이제 이메일 삭제 가능 (비밀번호 필요)
    assert c.post("/api/auth/contact/remove", json={"kind": "email", "password": "wrong"}, headers=h(tok)).status_code == 400
    assert c.post("/api/auth/contact/remove", json={"kind": "email", "password": "zz9876qq"}, headers=h(tok)).status_code == 200
    me = c.get("/api/auth/me", headers=h(tok)).json()
    assert me["email"] is None and me["phone"] and me["verified"]
    assert c.post("/api/auth/login", json={"username": "both@naver.com", "password": "zz9876qq"}).status_code == 401
    assert c.post("/api/auth/contact/remove", json={"kind": "email", "password": "zz9876qq"}, headers=h(tok)).status_code == 400
    assert c.post("/api/auth/contact/remove", json={"kind": "fax", "password": "zz9876qq"}, headers=h(tok)).status_code == 400


# ---------------- 닉네임 ----------------

def test_nickname(env):
    c, sent, _ = env
    tok = signup(c, sent, "nick1", "n1@naver.com", "pass9876", ).json()["access_token"]
    me = c.get("/api/auth/me", headers=h(tok)).json()
    assert me["nickname"] is None and me["display_name"] == "nick1"
    r = c.put("/api/auth/profile", json={"nickname": "주식왕_1"}, headers=h(tok))
    assert r.status_code == 200 and r.json()["display_name"] == "주식왕_1"
    assert c.get("/api/auth/me", headers=h(tok)).json()["display_name"] == "주식왕_1"
    for bad, msg in [("a", "2~12자"), ("띄어 쓰기", "2~12자"), ("열세글자가넘는닉네임입니다", "2~12자"), ("관리자", "쓸 수 없는"),
                     ("old", "이미"), ("OLD", "이미")]:   # old = 다른 사람의 아이디
        r = c.put("/api/auth/profile", json={"nickname": bad}, headers=h(tok))
        assert r.status_code == 400 and msg in r.json()["detail"], (bad, r.json())
    # 다른 사람이 같은 닉네임(대소문자 무시) 불가, 가입할 때 아이디로도 불가
    r = phone_signup(c, sent, "nick2", "010-2222-3333", nickname="주식왕_1")
    assert r.status_code == 400 and "닉네임" in r.json()["detail"]
    tok2 = phone_signup(c, sent, "nick2", "010-2222-3333", nickname="Trader").json()["access_token"]
    assert c.get("/api/auth/me", headers=h(tok2)).json()["display_name"] == "Trader"
    r = c.put("/api/auth/profile", json={"nickname": "trader"}, headers=h(tok))
    assert r.status_code == 400
    c.post("/api/auth/signup/send-code", json={"email": "t@naver.com"})
    r = c.post("/api/auth/register", json={"username": "TRADER", "password": "abcd1234", "email": "t@naver.com", "code": code_of(sent)})
    assert r.status_code == 400 and "아이디" in r.json()["detail"]
    # 내 닉네임 그대로 저장은 됨, 비우면 아이디
    assert c.put("/api/auth/profile", json={"nickname": "주식왕_1"}, headers=h(tok)).status_code == 200
    r = c.put("/api/auth/profile", json={"nickname": "  "}, headers=h(tok))
    assert r.status_code == 200 and r.json()["display_name"] == "nick1"


# ---------------- 모든 기기 로그아웃 · 활동 기록 ----------------

def test_logout_all(env):
    c, sent, _ = env
    a = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"}).json()["access_token"]
    b = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"}).json()["access_token"]
    r = c.post("/api/auth/logout-all", headers=h(a))
    assert r.status_code == 200
    new = r.json()["access_token"]
    assert c.get("/api/auth/me", headers=h(new)).status_code == 200
    for t in (a, b):
        r = c.get("/api/auth/me", headers=h(t))
        assert r.status_code == 401 and "모든 기기" in r.json()["detail"]
    # 그 뒤 새로 로그인한 토큰은 정상
    t2 = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"}).json()["access_token"]
    assert c.get("/api/auth/me", headers=h(t2)).status_code == 200


def test_activity_log(env):
    c, sent, _ = env
    c.post("/api/auth/login", json={"username": "old", "password": "wrongpw1"}, headers={"User-Agent": "Mozilla/5.0 (iPhone)"})
    c.post("/api/auth/login", json={"username": "nobody", "password": "x"})          # 없는 아이디는 기록 없음
    tok = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"},
                 headers={"X-Forwarded-For": "1.2.3.4", "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130"}).json()["access_token"]
    tok = c.post("/api/auth/password/change", json={"current_password": "oldpass123", "new_password": "newpass123"}, headers=h(tok)).json()["access_token"]
    r = c.get("/api/auth/activity", headers=h(tok)).json()
    kinds = [i["kind"] for i in r["items"]]
    assert kinds == ["password_change", "login", "login_fail"], kinds          # 최신순
    assert r["recent_failures"] == 1
    login = r["items"][1]
    assert login["ip"] == "1.2.3.4" and "Windows" in login["user_agent"] and login["ok"]
    assert r["items"][2]["ok"] is False and r["items"][2]["detail"] == "비밀번호 틀림"


def test_activity_keeps_recent_only(env, monkeypatch):
    c, sent, Session = env
    from app.api.routes import auth
    monkeypatch.setattr(auth, "EVENT_KEEP", 5)
    for _ in range(8):
        tok = c.post("/api/auth/login", json={"username": "old", "password": "oldpass123"}).json()["access_token"]

    async def count():
        from sqlalchemy import select, func
        from app.models.user import AccountEvent
        async with Session() as s:
            return (await s.execute(select(func.count()).select_from(AccountEvent))).scalar()
    assert run(count()) == 5
    assert len(c.get("/api/auth/activity?limit=100", headers=h(tok)).json()["items"]) == 5


def test_delete_account_removes_activity(env):
    c, sent, Session = env
    tok = phone_signup(c, sent, "gone1", "010-3333-4444").json()["access_token"]
    c.post("/api/auth/login", json={"username": "gone1", "password": "abcd1234"})
    uid = c.get("/api/auth/me", headers=h(tok)).json()["id"]

    async def add_paper():   # AI 모의투자 계좌·거래·자산·시뮬레이션도 탈퇴 때 같이 지워져야 함
        from app.models.paper import PaperAccount, PaperTrade, PaperEquity, PaperSim
        async with Session() as s:
            a = PaperAccount(user_id=uid, market="KR", capital=1e7, params="{}", state="{}")
            s.add(a)
            await s.flush()
            s.add(PaperTrade(account_id=a.id, ts="t", symbol="005930", side="buy", qty=1, price=1, amount=1))
            s.add(PaperEquity(account_id=a.id, date="2026-11-20", equity=1, cash=1))
            s.add(PaperSim(user_id=uid, market="KR", capital=1e7, months=1, params="{}"))
            await s.commit()
    run(add_paper())
    assert c.post("/api/auth/delete-account", json={"password": "abcd1234"}, headers=h(tok)).status_code == 200

    async def count():
        from sqlalchemy import select, func
        from app.models.user import AccountEvent
        async with Session() as s:
            return (await s.execute(select(func.count()).select_from(AccountEvent))).scalar()
    assert run(count()) == 0

    async def paper_left():
        from sqlalchemy import select, func
        from app.models.paper import PaperAccount, PaperTrade, PaperEquity, PaperSim
        async with Session() as s:
            return [(await s.execute(select(func.count()).select_from(m))).scalar()
                    for m in (PaperAccount, PaperTrade, PaperEquity, PaperSim)]
    assert run(paper_left()) == [0, 0, 0, 0]
    assert phone_signup(c, sent, "gone2", "010-3333-4444").status_code == 200    # 같은 번호로 다시 가입 가능


# ---------------- 문자 발송 (가짜 솔라피 서버) ----------------

@pytest.fixture
def solapi(monkeypatch):
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    state = {"reqs": [], "reply": None}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["reqs"].append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
            status, data = state["reply"] or (200, {"groupInfo": {"count": {"total": 1, "registeredFailed": 0, "registeredSuccess": 1}},
                                                    "failedMessageList": []})
            raw = json.dumps(data).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(sms, "API_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(settings, "sms_api_key", "KEY123")
    monkeypatch.setattr(settings, "sms_api_secret", "SECRET456")
    monkeypatch.setattr(settings, "sms_from", "010-9876-5432")
    monkeypatch.setattr(settings, "sms_daily_limit", 50)
    sms._sent_day.clear()
    yield state
    srv.shutdown()


def test_sms_send_request_format(solapi):
    import hashlib, hmac as _hmac
    assert sms.configured()
    run(sms.send("01012345678", email_codes.sms_text("signup", "123456")))
    req = solapi["reqs"][0]
    assert req["path"] == "/messages/v4/send-many/detail"
    assert req["body"]["messages"] == [{"to": "01012345678", "from": "01098765432", "text": "[StockApp] 회원가입 인증번호 123456 (10분 유효)"}]
    m = re.fullmatch(r"HMAC-SHA256 ApiKey=KEY123, Date=(\S+), salt=(\w+), signature=([0-9a-f]{64})", req["auth"])
    assert m, req["auth"]
    date, salt, sig = m.groups()
    assert sig == _hmac.new(b"SECRET456", (date + salt).encode(), hashlib.sha256).hexdigest()
    assert len(email_codes.sms_text("reset", "123456").encode("euc-kr")) <= 90    # 단문 요금


def test_sms_errors(solapi, monkeypatch):
    solapi["reply"] = (401, {"errorCode": "InvalidApiKey", "errorMessage": "Invalid API Key"})
    with pytest.raises(sms.SmsError) as e:
        run(sms.send("01012345678", "t"))
    assert "계정 인증 실패" in str(e.value) and "SECRET456" not in str(e.value) and "KEY123" not in str(e.value)
    solapi["reply"] = (200, {"groupInfo": {"count": {"total": 1, "registeredFailed": 1}},
                             "failedMessageList": [{"statusCode": "1062", "statusMessage": "발신번호 미등록"}]})
    with pytest.raises(sms.SmsError, match="발신번호 미등록"):
        run(sms.send("01012345678", "t"))
    solapi["reply"] = (400, {"errorCode": "ValidationError", "errorMessage": "to 형식 오류"})
    with pytest.raises(sms.SmsError, match="ValidationError"):
        run(sms.send("01012345678", "t"))
    # 하루 한도
    solapi["reply"] = None
    monkeypatch.setattr(settings, "sms_daily_limit", 2)
    run(sms.send("01012345678", "t")); run(sms.send("01012345678", "t"))
    with pytest.raises(sms.SmsError, match="오늘 보낼 수 있는"):
        run(sms.send("01012345678", "t"))
    monkeypatch.setattr(settings, "sms_api_key", "")
    with pytest.raises(sms.SmsError, match="설정이 없습니다"):
        run(sms.send("01012345678", "t"))
    monkeypatch.setattr(settings, "sms_api_key", "KEY123")
    monkeypatch.setattr(sms, "API_BASE", "http://127.0.0.1:1")
    monkeypatch.setattr(settings, "sms_daily_limit", 0)
    with pytest.raises(sms.SmsError, match="연결하지 못했습니다"):
        run(sms.send("01012345678", "t"))


def test_old_token_cannot_enter_new_account_with_same_username(env):
    """탈퇴 뒤 다른 사람이 같은 아이디로 가입 → 예전 토큰(아직 12시간 안)으로 새 계정에 못 들어감 (2026-11-26 점검에서 발견)"""
    c, sent, Session = env
    old_tok = signup(c, sent, "samename", "first@naver.com", "firstpw12").json()["access_token"]
    assert c.post("/api/auth/delete-account", json={"password": "firstpw12"}, headers=h(old_tok)).status_code == 200
    new_tok = signup(c, sent, "samename", "second@naver.com", "secondpw34").json()["access_token"]
    assert c.get("/api/auth/me", headers=h(new_tok)).status_code == 200
    r = c.get("/api/auth/me", headers=h(old_tok))
    assert r.status_code == 401, r.text


def test_login_unknown_user_still_checks_password(env, monkeypatch):
    """없는 아이디도 비밀번호 확인(bcrypt)을 한 번 해서 응답 시간으로 가입 여부가 드러나지 않게"""
    from app.api.routes import auth
    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda pw, hashed: calls.append(hashed) or real(pw, hashed))
    c, sent, Session = env
    r = c.post("/api/auth/login", json={"username": "nobody-here", "password": "whatever1"})
    assert r.status_code == 401 and calls == [auth._DUMMY_HASH]
