from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import BACKEND_DIR

# backend/stock_app.db 로 고정 (실행 위치가 달라도 같은 DB 사용)
SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'stock_app.db').as_posix()}"

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)
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
        from app.models import user, watchlist, portfolio, prediction, flow, paper  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


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
