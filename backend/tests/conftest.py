"""테스트 공통 설정

- 실제 KIS·Yahoo·FRED 등 외부 API 는 부르지 않는다 (가짜 함수·가짜 응답으로 흐름만 검증).
- .env 가 없어도 앱 import 가 되도록 가짜 KIS 값을 넣는다 (이미 있으면 그대로).
- DB 는 실제 backend/stock_app.db 를 건드리지 않도록 API 테스트마다 메모리 SQLite 를 쓴다 (api_client 픽스처).
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("KIS_APP_KEY", "test")
os.environ.setdefault("KIS_APP_SECRET", "test")
os.environ.setdefault("KIS_ACCOUNT_NO", "00000000-01")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _no_external_security_calls(monkeypatch):
    """유출 비밀번호 확인(HIBP)·새 IP 로그인 알림 메일은 테스트에서 끔 — 그 기능 테스트는 직접 켜고 가짜로 바꿈.
    초대 코드 가입(INVITE_ONLY)·2단계 필수(REQUIRE_TOTP)도 기존 가입·계정 테스트를 위해 끄고, test_invite_totp.py 가 켜서 검사"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "pwned_check", False)
    monkeypatch.setattr(settings, "login_alert", False)
    monkeypatch.setattr(settings, "ntfy_topic", "")      # PC 의 .env 에 NTFY_TOPIC 이 있어도 테스트가 진짜 휴대폰 알림을 보내지 않게
    monkeypatch.setattr(settings, "invite_only", False)
    monkeypatch.setattr(settings, "require_totp", False)
    # 한국은행 홈페이지·Google 뉴스는 테스트에서 실제로 부르지 않음 (필요한 테스트가 직접 가짜로 바꿈)
    from app.services import bok, news

    async def _no_bok(client, url):
        raise RuntimeError("테스트: 한국은행 홈페이지에 접속하지 않음")

    async def _no_google(query, lang="ko"):
        raise RuntimeError("테스트: Google 뉴스에 접속하지 않음")
    monkeypatch.setattr(bok, "_get", _no_bok)
    monkeypatch.setattr(bok, "_cache", {"schedule": {}, "rates": None, "latest": None, "ts": {}})
    monkeypatch.setattr(news, "_fetch_google", _no_google)
    # 미국 가치주 후보(Yahoo 스크리너)도 실제로 안 부름 — 판단 후보 테스트가 직접 가짜로 바꿈
    from app.services import fundamentals, signals

    def _no_yahoo_screen(key, limit=100):
        raise RuntimeError("테스트: Yahoo 스크리너에 접속하지 않음")
    monkeypatch.setattr(fundamentals, "us_screen_sync", _no_yahoo_screen)
    monkeypatch.setattr(signals, "_us_value_cache", {"at": 0.0, "rows": None, "error": None})
    from app.api.routes import auth   # 로그인 실패·잠금 기록은 모듈에 남으므로 테스트마다 비움
    for d in (auth._fails, auth._locked, auth._acct_fails, auth._acct_locked):
        d.clear()


def run(coro):
    """async 함수를 테스트 안에서 실행 (pytest-asyncio 없이)"""
    return asyncio.run(coro)


@pytest.fixture
def api_client(monkeypatch):
    """라우터만 올린 FastAPI 테스트 앱 + 메모리 DB + 로그인 사용자 1명.
    반환: (TestClient, 세션 팩토리, 사용자)"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import StaticPool

    from app.core.database import Base, get_db
    from app.api.routes import watchlist, portfolio, stocks, market, signals as signals_route
    from app.api.routes.auth import get_current_user
    from app.models import user as user_model, watchlist as _w, portfolio as _p, prediction as _pr, flow as _f  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as s:
            u = user_model.User(username="tester", hashed_password="x")
            s.add(u)
            await s.commit()
            await s.refresh(u)
            return u
    user = run(setup())

    async def _db():
        async with Session() as s:
            yield s

    app = FastAPI()
    for r in (watchlist.router, portfolio.router, stocks.router, market.router, signals_route.router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    # 예측 기록은 부가 기능 — 테스트에선 DB 에 안 씀
    from app.services import prediction_log

    async def _no_record(*a, **k):
        return None
    monkeypatch.setattr(prediction_log, "record", _no_record)

    async def _no_tracks():
        return {}
    monkeypatch.setattr(prediction_log, "tracks", _no_tracks)   # 실제 DB 파일을 열지 않게
    with TestClient(app) as client:
        yield client, Session, user
    run(engine.dispose())
