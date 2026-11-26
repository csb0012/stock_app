import asyncio

from fastapi import APIRouter, Depends, Query

from app.core.bg import spawn
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services import prediction_log, backtest, ml_model

router = APIRouter(prefix="/predictions", tags=["predictions"])


_eval_task: asyncio.Task | None = None


async def _evaluate_briefly(wait: float = 2.0):
    """채점을 시작(이미 하는 중이면 그것)하고 최대 wait 초만 기다림. 못 끝나면 None (뒤에서 계속)"""
    global _eval_task
    if _eval_task is None or _eval_task.done():
        _eval_task = asyncio.create_task(prediction_log.evaluate_pending())
        _eval_task.add_done_callback(lambda t: t.cancelled() or t.exception() and print(f"[prediction] 채점 실패: {t.exception()}"))
    try:
        return await asyncio.wait_for(asyncio.shield(_eval_task), wait)
    except asyncio.TimeoutError:
        return None
    except Exception as e:  # 부가 기능 — 채점 실패가 기록 조회를 막지 않음
        print(f"[prediction] 채점 실패: {e}")
        return None


@router.get("/review")
async def review_predictions(
    days: int = Query(30, ge=1, le=365),
    market: str = Query("ALL"),
    kind: str = Query("all", pattern="^(all|live|backtest)$"),
    outcome: str = Query("all", pattern="^(all|hit|miss|pending)$"),
    limit: int = Query(200, ge=1, le=5000),
    current_user: User = Depends(get_current_user),
):
    """예측 복기 — 대상일 장이 끝난 예측을 채점한 뒤 적중률·이유 반환.
    채점(종목마다 일봉 조회)이 오래 걸리면 기다리지 않고 지금까지의 기록을 먼저 보여줌 → 다음 조회 때 반영"""
    evaluated = await _evaluate_briefly()
    data = await prediction_log.review(days, market, kind, outcome, limit)
    data["newly_evaluated"] = evaluated
    data["backtest"] = backtest.status()
    data["model"] = ml_model.status()
    from app.services import flows
    data["flows"] = flows.status()
    return data


async def _bg_backtest(force: bool):
    from app.services.kis_api import mark_background
    mark_background()  # 화면 요청보다 KIS 호출 순서를 뒤로
    await backtest.run(force)


@router.post("/backtest")
async def run_backtest(force: bool = Query(False), current_user: User = Depends(get_current_user)):
    """최근 1년 백테스트 시작 (백그라운드). force=true 면 기존 백테스트 기록을 지우고 다시 계산"""
    if not backtest.status()["running"]:
        spawn(_bg_backtest(force))
        await asyncio.sleep(0)
    return backtest.status()


@router.get("/backtest/status")
async def backtest_status(current_user: User = Depends(get_current_user)):
    return backtest.status()
