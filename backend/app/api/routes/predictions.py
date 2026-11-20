import asyncio

from fastapi import APIRouter, Depends, Query

from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services import prediction_log, backtest, ml_model

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/review")
async def review_predictions(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("ALL"),
    kind: str = Query("all", pattern="^(all|live|backtest)$"),
    outcome: str = Query("all", pattern="^(all|hit|miss|pending)$"),
    limit: int = Query(200, ge=1, le=5000),
    current_user: User = Depends(get_current_user),
):
    """예측 복기 — 대상일 장이 끝난 예측을 채점한 뒤 적중률·이유 반환"""
    evaluated = await prediction_log.evaluate_pending()
    data = await prediction_log.review(days, market, kind, outcome, limit)
    data["newly_evaluated"] = evaluated
    data["backtest"] = backtest.status()
    data["model"] = ml_model.status()
    return data


@router.post("/backtest")
async def run_backtest(force: bool = Query(False), current_user: User = Depends(get_current_user)):
    """최근 90일 백테스트 시작 (백그라운드). force=true 면 기존 백테스트 기록을 지우고 다시 계산"""
    if not backtest.status()["running"]:
        asyncio.create_task(backtest.run(force))
        await asyncio.sleep(0)
    return backtest.status()


@router.get("/backtest/status")
async def backtest_status(current_user: User = Depends(get_current_user)):
    return backtest.status()
