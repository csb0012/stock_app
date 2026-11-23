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
    from app.api.routes import watchlist, portfolio, stocks, market
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
    for r in (watchlist.router, portfolio.router, stocks.router, market.router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    # 예측 기록은 부가 기능 — 테스트에선 DB 에 안 씀
    from app.services import prediction_log

    async def _no_record(*a, **k):
        return None
    monkeypatch.setattr(prediction_log, "record", _no_record)
    with TestClient(app) as client:
        yield client, Session, user
    run(engine.dispose())
