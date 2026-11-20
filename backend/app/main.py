from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.database import init_db
from app.core.config import settings
from app.api.routes import auth, stocks, market, watchlist, portfolio
from app.services import stock_master


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 종목마스터(KIS 공식 종목코드) — 없으면 검색·종목 검증이 안 되므로 시작 시 로드
    await stock_master.load()
    yield


app = FastAPI(title="StockApp API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(stocks.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
