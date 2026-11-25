from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import BACKEND_DIR

# backend/stock_app.db 로 고정 (실행 위치가 달라도 같은 DB 사용)
SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'stock_app.db').as_posix()}"

# timeout: 다른 연결이 쓰는 중이면 이만큼(초)까지 기다렸다가 진행 (기본 5초 — 느린 디스크·Docker 의 Windows 폴더에서는
# 큰 저장이 5초를 넘겨 'database is locked' 로 실패했음)
DB_TIMEOUT = 30
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False, connect_args={"timeout": DB_TIMEOUT})
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        from app.models import user, watchlist, portfolio, prediction, flow, paper, kis  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
        await conn.run_sync(_ensure_owner)


def _add_missing_columns(sync_conn):
    """create_all 은 기존 테이블에 새 컬럼을 추가하지 않으므로, 모델에 새로 생긴 컬럼을 ALTER TABLE 로 추가.
    (기존 stock_app.db 데이터를 유지한 채 업데이트하기 위함)"""
    from sqlalchemy import inspect, text
    insp = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(dialect=sync_conn.dialect)
                sync_conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'))


def _ensure_owner(sync_conn):
    """관리자가 한 명도 없으면 가장 먼저 만든 계정(가장 작은 id)을 관리자로 — 업데이트 전 기존 DB 용.
    (관리자를 바꾸려면 서버에서 create_admin.py --admin <아이디>)"""
    from sqlalchemy import text
    if sync_conn.execute(text("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1")).first():
        return
    row = sync_conn.execute(text("SELECT id, username FROM users ORDER BY id LIMIT 1")).first()
    if row:
        sync_conn.execute(text("UPDATE users SET is_admin = 1 WHERE id = :i"), {"i": row[0]})
        print(f"[db] 관리자가 없어 처음 만든 계정 '{row[1]}' 을 관리자로 정했습니다")
