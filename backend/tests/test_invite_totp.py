"""초대 코드로만 가입 · 2단계 인증(Google Authenticator) 필수 · 관리자(초대 코드·회원 차단) · 계정 잠금 DB 유지"""
import re
import time

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.conftest import run
from app.core.config import settings
from app.services import mailer, email_codes, invites

T0 = 1_800_000_000.0
PW = "Boss-pass-2026"


@pytest.fixture
def env(monkeypatch):
    from app.core import security
    from app.core.database import Base, get_db
    from app.core.security import get_password_hash
    from app.api.routes import auth, admin, watchlist
    from app.models import user as user_model, watchlist as _w, portfolio as _p, prediction as _pr, flow as _f, paper as _pp  # noqa: F401
    monkeypatch.setattr(settings, "invite_only", True)
    monkeypatch.setattr(settings, "require_totp", True)
    monkeypatch.setattr(settings, "signup_open", True)
    clock = {"t": T0}
    monkeypatch.setattr(security, "_now", lambda: clock["t"])
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as s:
            s.add(user_model.User(username="boss", hashed_password=get_password_hash(PW), is_admin=True))
            await s.commit()
    run(setup())

    async def _db():
        async with Session() as s:
            yield s
    app = FastAPI()
    for r in (auth.router, admin.router, watchlist.router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[get_db] = _db
    email_codes._ip_sent.clear()
    monkeypatch.setattr(email_codes, "COOLDOWN", 0)
    sent = []

    async def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
    monkeypatch.setattr(mailer, "send", fake_send)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    with TestClient(app) as c:
        yield c, sent, Session, clock
    run(engine.dispose())


def H(tok):
    return {"X-Access-Token": tok}


def login(c, user="boss", pw=PW, code=None, ip="10.0.0.1"):
    return c.post("/api/auth/login", json={"username": user, "password": pw, "totp_code": code},
                  headers={"X-Forwarded-For": ip})


def turn_on_totp(c, tok, clock):
    sec = c.post("/api/auth/setup-totp", headers=H(tok)).json()["secret"]
    T = pyotp.TOTP(sec)
    clock["t"] += 30
    r = c.post("/api/auth/enable-totp", json={"totp_code": T.at(clock["t"])}, headers=H(tok))
    assert r.status_code == 200, r.text
    return T


def next_code(T, clock):
    clock["t"] += 30   # 한 번 쓴 코드는 다시 못 쓰므로 다음 30초 칸으로
    return T.at(clock["t"])


def admin_session(c, clock):
    """관리자 로그인 + 2단계 켜기 → (토큰, TOTP)"""
    tok = login(c).json()["access_token"]
    T = turn_on_totp(c, tok, clock)
    return tok, T


def test_totp_required_blocks_everything_until_enabled(env):
    c, sent, Session, clock = env
    r = login(c).json()
    assert r["totp_setup_required"] is True and r["totp_enabled"] is False
    tok = r["access_token"]
    # 비밀번호만으로 받은 토큰 → 다른 기능은 전부 403 + 화면이 2단계 설정으로 보낼 수 있는 헤더
    r = c.get("/api/watchlist/", headers=H(tok))
    assert r.status_code == 403 and r.headers.get("X-Totp-Required") == "1" and "2단계" in r.json()["detail"]
    assert c.get("/api/admin/invites", headers=H(tok)).status_code == 403
    assert c.post("/api/auth/delete-account", json={"password": PW}, headers=H(tok)).status_code == 403
    me = c.get("/api/auth/me", headers=H(tok)).json()            # 내 정보·2단계 설정은 됨
    assert me["totp_required"] is True and me["totp_enabled"] is False and me["is_admin"] is True
    T = turn_on_totp(c, tok, clock)
    assert c.get("/api/watchlist/", headers=H(tok)).status_code == 200          # 켜면 같은 토큰으로 바로 됨
    # 이후 로그인은 코드 필요
    assert login(c).json() == {"requires_totp": True}
    r = login(c, code=next_code(T, clock)).json()
    assert r["totp_setup_required"] is False
    # 휴대폰 바꾸기: 지금 코드로 해제 → 다시 등록 전까지 다시 막힘
    r = c.post("/api/auth/disable-totp", json={"totp_code": next_code(T, clock)}, headers=H(tok)).json()
    assert r["totp_setup_required"] is True
    assert c.get("/api/watchlist/", headers=H(tok)).status_code == 403


def test_totp_optional_when_setting_off(env, monkeypatch):
    c, sent, Session, clock = env
    monkeypatch.setattr(settings, "require_totp", False)
    r = login(c).json()
    assert r["totp_setup_required"] is False
    assert c.get("/api/watchlist/", headers=H(r["access_token"])).status_code == 200


def signup_send(c, email="friend@naver.com", invite=None, ip="10.9.9.9"):
    return c.post("/api/auth/signup/send-code", json={"email": email, "invite_code": invite}, headers={"X-Forwarded-For": ip})


def register(c, sent, invite, username="friend", email="friend@naver.com"):
    code = re.search(r"인증 코드: (\d{6})", sent[-1]["body"]).group(1)
    return c.post("/api/auth/register", json={"username": username, "password": "Pal-pw-8812", "email": email,
                                              "code": code, "invite_code": invite})


def test_invite_only_signup(env):
    c, sent, Session, clock = env
    tok, T = admin_session(c, clock)
    assert c.get("/api/auth/options").json()["invite_required"] is True
    # 초대 코드 없이 / 틀린 코드 → 메일도 안 보냄
    r = signup_send(c)
    assert r.status_code == 400 and "초대 코드가 필요" in r.json()["detail"] and sent == []
    assert signup_send(c, invite="AAAA-BBBB-CCCC").status_code == 400 and sent == []
    # 초대 코드 만들기: 2단계 코드 다시 확인
    r = c.post("/api/admin/invites", json={"memo": "동생", "totp_code": "000000"}, headers=H(tok))
    assert r.status_code == 400
    r = c.post("/api/admin/invites", json={"memo": "동생", "days": 3, "totp_code": next_code(T, clock)}, headers=H(tok)).json()
    code = r["code"]
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code)
    # 원문은 DB 에 없음 (해시 + 끝 4글자만)
    async def stored():
        async with Session() as s:
            return (await s.execute(select(invites.Invite))).scalars().all()
    rows = run(stored())
    assert len(rows) == 1 and code not in rows[0].code_hash and invites.normalize(code) not in rows[0].code_hash
    lst = c.get("/api/admin/invites", headers=H(tok)).json()["items"]
    assert lst[0]["status"] == "active" and lst[0]["hint"] == code[-4:] and lst[0]["memo"] == "동생" and "code" not in lst[0]
    # 소문자·하이픈 없이 쳐도 됨
    loose = code.replace("-", "").lower()
    assert signup_send(c, invite=loose).status_code == 200 and len(sent) == 1
    r = register(c, sent, loose)
    assert r.status_code == 200, r.text
    assert r.json()["totp_setup_required"] is True
    new_tok = r.json()["access_token"]
    assert c.get("/api/watchlist/", headers=H(new_tok)).status_code == 403          # 가입해도 2단계부터
    # 1회용: 같은 코드로 또 가입 못 함
    assert signup_send(c, email="third@naver.com", invite=code).status_code == 400
    lst = c.get("/api/admin/invites", headers=H(tok)).json()["items"]
    assert lst[0]["status"] == "used" and lst[0]["used_by"] == "friend"
    users = c.get("/api/admin/users", headers=H(tok)).json()["items"]
    friend = next(u for u in users if u["username"] == "friend")
    assert friend["invited_by"] == "boss" and friend["totp_enabled"] is False and friend["is_admin"] is False
    # 관리자가 아니면 관리 API 못 씀
    T2 = turn_on_totp(c, new_tok, clock)
    assert c.get("/api/admin/invites", headers=H(new_tok)).status_code == 403
    assert c.post("/api/admin/invites", json={"totp_code": next_code(T2, clock)}, headers=H(new_tok)).status_code == 403


def test_invite_expired_revoked_and_register_needs_invite(env, monkeypatch):
    c, sent, Session, clock = env
    tok, T = admin_session(c, clock)
    a = c.post("/api/admin/invites", json={"days": 1, "totp_code": next_code(T, clock)}, headers=H(tok)).json()
    b = c.post("/api/admin/invites", json={"days": 2, "totp_code": next_code(T, clock)}, headers=H(tok)).json()
    assert c.post("/api/admin/invites", json={"days": 30, "totp_code": next_code(T, clock)}, headers=H(tok)).status_code == 400
    # 취소한 코드
    assert c.delete(f"/api/admin/invites/{b['id']}", headers=H(tok)).status_code == 200
    assert signup_send(c, invite=b["code"]).status_code == 400
    # 메일 코드를 받은 뒤 초대 코드 없이 register 만 직접 불러도 안 됨
    assert signup_send(c, invite=a["code"]).status_code == 200
    code = re.search(r"인증 코드: (\d{6})", sent[-1]["body"]).group(1)
    r = c.post("/api/auth/register", json={"username": "friend", "password": "Pal-pw-8812", "email": "friend@naver.com", "code": code})
    assert r.status_code == 400 and "초대 코드" in r.json()["detail"]
    # 만료 (1일 뒤)
    real = time.time
    monkeypatch.setattr(invites.time, "time", lambda: real() + 2 * 86400)
    r = register(c, sent, a["code"])
    assert r.status_code == 400 and "만료" in r.json()["detail"]
    statuses = {i["id"]: i["status"] for i in c.get("/api/admin/invites", headers=H(tok)).json()["items"]}
    assert statuses == {a["id"]: "expired", b["id"]: "revoked"}


def test_wrong_invite_codes_get_ip_blocked(env):
    c, sent, Session, clock = env
    for i in range(5):
        assert signup_send(c, invite=f"AAAA-BBBB-CCC{i + 2}", ip="203.0.113.5").status_code == 400
    r = signup_send(c, invite="AAAA-BBBB-CCCZ", ip="203.0.113.5")
    assert r.status_code == 429 and "차단" in r.json()["detail"]
    assert sent == []


def test_invite_limit_and_open_mode(env, monkeypatch):
    c, sent, Session, clock = env
    tok, T = admin_session(c, clock)
    for _ in range(invites.MAX_ACTIVE):
        assert c.post("/api/admin/invites", json={"totp_code": next_code(T, clock)}, headers=H(tok)).status_code == 200
    r = c.post("/api/admin/invites", json={"totp_code": next_code(T, clock)}, headers=H(tok))
    assert r.status_code == 400 and "취소" in r.json()["detail"]
    monkeypatch.setattr(settings, "invite_only", False)       # INVITE_ONLY=false → 인증만으로 가입 (예전 방식)
    assert signup_send(c).status_code == 200


def test_admin_block_user(env):
    c, sent, Session, clock = env
    tok, T = admin_session(c, clock)
    inv = c.post("/api/admin/invites", json={"totp_code": next_code(T, clock)}, headers=H(tok)).json()["code"]
    signup_send(c, invite=inv)
    ftok = register(c, sent, inv).json()["access_token"]
    fid = next(u["id"] for u in c.get("/api/admin/users", headers=H(tok)).json()["items"] if u["username"] == "friend")
    boss_id = next(u["id"] for u in c.get("/api/admin/users", headers=H(tok)).json()["items"] if u["me"])
    assert c.put(f"/api/admin/users/{boss_id}/active", json={"active": False, "totp_code": next_code(T, clock)}, headers=H(tok)).status_code == 400
    assert c.put(f"/api/admin/users/{fid}/active", json={"active": False, "totp_code": "123"}, headers=H(tok)).status_code == 400
    r = c.put(f"/api/admin/users/{fid}/active", json={"active": False, "totp_code": next_code(T, clock)}, headers=H(tok))
    assert r.status_code == 200
    assert c.get("/api/auth/me", headers=H(ftok)).status_code == 401                 # 바로 끊김
    assert login(c, user="friend", pw="Pal-pw-8812").status_code == 401             # 로그인도 안 됨
    assert c.put(f"/api/admin/users/{fid}/active", json={"active": True, "totp_code": next_code(T, clock)}, headers=H(tok)).status_code == 200
    assert login(c, user="friend", pw="Pal-pw-8812").status_code == 200


def test_admin_summary_detail_and_security_log(env):
    """관리자 페이지: 요약 숫자 · 회원 상세(연락처는 가림, 비밀값 없음) · 전체 보안 기록. 일반 회원은 못 봄"""
    c, sent, Session, clock = env
    tok, T = admin_session(c, clock)
    inv = c.post("/api/admin/invites", json={"memo": "친구", "totp_code": next_code(T, clock)}, headers=H(tok)).json()["code"]
    signup_send(c, invite=inv)
    ftok = register(c, sent, inv).json()["access_token"]
    login(c, user="friend", pw="wrong-pass-1", ip="10.7.7.7")
    s = c.get("/api/admin/summary", headers=H(tok)).json()
    assert s["users"] == 2 and s["admins"] == 1 and s["blocked"] == 0 and s["totp_missing"] == 1
    assert s["login_fail_7d"] == 1 and s["invites_active"] == 0
    fid = next(u["id"] for u in c.get("/api/admin/users", headers=H(tok)).json()["items"] if u["username"] == "friend")
    d = c.get(f"/api/admin/users/{fid}", headers=H(tok)).json()
    assert d["username"] == "friend" and d["invited_by"] == "boss" and d["email"] == "fr***@naver.com"
    assert d["login_fail_7d"] == 1 and d["usage"] == {"watchlist": 0, "portfolio": 0, "paper_accounts": 0, "paper_sims": 0}
    assert [e["kind"] for e in d["events"]][:2] == ["login_fail", "signup"]
    assert not any(k in d for k in ("hashed_password", "totp_secret", "phone_full"))
    assert c.get("/api/admin/users/999", headers=H(tok)).status_code == 404
    ev = c.get("/api/admin/events", headers=H(tok)).json()["items"]
    kinds = [(e["user"], e["kind"]) for e in ev]
    assert ("friend", "login_fail") in kinds and ("boss", "invite_create") in kinds and ("boss", "totp_on") in kinds
    assert all(e["kind"] != "login" for e in ev)        # 보통 로그인은 회원 상세에서만
    # 일반 회원(2단계 등록 후에도)은 관리자 API 403
    FT = turn_on_totp(c, ftok, clock)
    for path in ("/api/admin/summary", f"/api/admin/users/{fid}", "/api/admin/events"):
        assert c.get(path, headers=H(ftok)).status_code == 403
    assert FT


def test_first_user_becomes_admin_on_upgrade():
    """업데이트 전 DB(관리자 없음) → 처음 만든 계정이 관리자. 이미 관리자가 있으면 그대로"""
    from sqlalchemy import create_engine, text
    from app.core.database import Base, _add_missing_columns, _ensure_owner
    from app.models import user as _u  # noqa: F401
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR, hashed_password VARCHAR)"))
        conn.execute(text("INSERT INTO users (id, username, hashed_password) VALUES (3, 'later', 'x'), (1, 'owner', 'x')"))
        Base.metadata.create_all(conn)
        _add_missing_columns(conn)
        _ensure_owner(conn)
        rows = dict(conn.execute(text("SELECT username, is_admin FROM users")).all())
        assert rows == {"owner": 1, "later": None}
        conn.execute(text("UPDATE users SET is_admin = 0 WHERE id = 1"))
        conn.execute(text("UPDATE users SET is_admin = 1 WHERE id = 3"))
        _ensure_owner(conn)
        assert dict(conn.execute(text("SELECT username, is_admin FROM users")).all()) == {"owner": 0, "later": 1}


def test_invite_code_helpers():
    codes = {invites.new_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(not set(c.replace("-", "")) & set("01OIL") for c in codes)
    assert invites.normalize(" abcd-efgh-jkmn ") == "ABCDEFGHJKMN"
    assert invites._hash("abcd-efgh-jkmn") == invites._hash("ABCDEFGHJKMN")
