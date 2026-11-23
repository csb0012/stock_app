from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.database import init_db
from app.core.config import settings
from app.api.routes import auth, stocks, market, watchlist, portfolio, predictions, chat, themes as themes_route, accumulation as accumulation_route
import asyncio
from app.services import stock_master, prediction_log, extras, backtest, ml_model, scheduler, flows
from app.services.repair import repair_symbols
from app.services.kis_api import mark_background


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 종목마스터(KIS 공식 종목코드) — 없으면 검색·종목 검증이 안 되므로 시작 시 로드
    await stock_master.load()
    # 예전 코드표 때문에 잘못 저장된 종목코드 자동 복구
    await repair_symbols()
    # 쌓아둔 외국인·기관 수급 불러오기 (학습 모델·카드 표시용)
    await flows.load_all()
    # 장이 끝난 예측을 30분마다 채점 (예측 검증 화면을 안 열어도 결과가 쌓이도록)
    task = asyncio.create_task(_evaluate_loop())
    # FRED·Finnhub·DART 추가 데이터는 호출 제한 때문에 백그라운드 큐로 수집 (.env 에 키가 있을 때만)
    extras_task = asyncio.create_task(extras.worker())
    asyncio.get_event_loop().call_later(1.0, _warm_extras)
    # 최근 90일 과거 예측 백테스트 — 하루 한 번 (이미 계산한 날짜는 건너뜀)
    bt_task = asyncio.create_task(_backtest_loop())
    # 학습 모델의 실시간 예측에 쓰는 지수 일봉 (10분마다)
    ctx_task = asyncio.create_task(_model_ctx_loop())
    # 정해진 시각 자동 예측 기록 (국내 장 시작 전·장 마감 후, 미국 장 마감 후) — scheduler.py
    preopen_task = asyncio.create_task(scheduler.loop())
    # AI 추천 기본 데이터 미리 계산 (첫 화면 대기 없애기)
    warm_task = asyncio.create_task(scheduler.warm_recommendations())
    # 테마 구성(네이버) 하루 1번 갱신 + 매집 탐지 결과가 없으면 시작 2분 뒤 전 종목 스캔
    from app.services import themes as themes_svc, accumulation
    theme_task = asyncio.create_task(themes_svc.loop())
    accum_task = asyncio.create_task(accumulation.startup())
    # 대시보드 데이터 미리 받기 (첫 화면 대기 줄이기)
    asyncio.get_event_loop().call_later(2.0, market.warm_overview)
    yield
    ctx_task.cancel()
    preopen_task.cancel()
    warm_task.cancel()
    theme_task.cancel()
    accum_task.cancel()
    task.cancel()
    extras_task.cancel()
    bt_task.cancel()


def _warm_extras():
    """추천 후보 종목의 추가 데이터를 미리 수집 예약"""
    from app.api.routes.stocks import KR_LONGTERM, US_LONGTERM, US_SHORTTERM_EXTRA
    extras.warm([(c["market"], c["symbol"]) for c in KR_LONGTERM + US_LONGTERM + US_SHORTTERM_EXTRA])


async def _evaluate_loop():
    mark_background()  # 화면 요청보다 KIS 호출 순서를 뒤로
    while True:
        try:
            await prediction_log.evaluate_pending()
        except Exception as e:
            print(f"[prediction] 채점 실패: {e}")
        await asyncio.sleep(1800)


async def _model_ctx_loop():
    mark_background()  # 화면 요청보다 KIS 호출 순서를 뒤로
    while True:
        await ml_model.refresh_ctx()
        await asyncio.sleep(600)


async def _backtest_loop():
    mark_background()  # 화면 요청보다 KIS 호출 순서를 뒤로
    await asyncio.sleep(20)  # 시작 직후 KIS 호출이 몰리지 않게
    while True:
        if backtest.due():
            await backtest.run()
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
app.include_router(chat.router, prefix="/api")
app.include_router(themes_route.router, prefix="/api")
app.include_router(accumulation_route.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
