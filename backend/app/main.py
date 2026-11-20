from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.database import init_db
from app.core.config import settings
from app.api.routes import auth, stocks, market, watchlist, portfolio, predictions
import asyncio
from app.services import stock_master, prediction_log
from app.services.repair import repair_symbols


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 종목마스터(KIS 공식 종목코드) — 없으면 검색·종목 검증이 안 되므로 시작 시 로드
    await stock_master.load()
    # 예전 코드표 때문에 잘못 저장된 종목코드 자동 복구
    await repair_symbols()
    # 장이 끝난 예측을 30분마다 채점 (예측 검증 화면을 안 열어도 결과가 쌓이도록)
    task = asyncio.create_task(_evaluate_loop())
    yield
    task.cancel()


async def _evaluate_loop():
    while True:
        try:
            await prediction_log.evaluate_pending()
        except Exception as e:
            print(f"[prediction] 채점 실패: {e}")
        await asyncio.sleep(1800)


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
app.include_router(predictions.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
