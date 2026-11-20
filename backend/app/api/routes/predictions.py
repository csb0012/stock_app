from fastapi import APIRouter, Depends, Query

from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services import prediction_log

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/review")
async def review_predictions(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("ALL"),
    current_user: User = Depends(get_current_user),
):
    """예측 복기 — 대상일 장이 끝난 예측을 채점한 뒤 적중률·이유 반환"""
    evaluated = await prediction_log.evaluate_pending()
    data = await prediction_log.review(days, market)
    data["newly_evaluated"] = evaluated
    return data
