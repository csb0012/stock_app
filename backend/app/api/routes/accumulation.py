import asyncio

from fastapi import APIRouter, Depends

from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services import accumulation, themes

router = APIRouter(prefix="/accumulation", tags=["accumulation"])


@router.get("")
async def accumulation_result(min_score: int = 50, current_user: User = Depends(get_current_user)):
    """매집·바닥 다지기 후보 (마지막 스캔 결과) + 검증 적중률 + 스캔 진행 상황"""
    r = accumulation.result()
    status = {**accumulation.status(), "stale": accumulation.stale()}
    if not r:
        return {"candidates": [], "validation": [], "status": status, "result": None}
    cands = [{**c, "themes": themes.themes_of(c["symbol"])[:4]} for c in r["candidates"] if c["score"] >= min_score]
    meta = {k: r.get(k) for k in ("base_date", "finished_at", "universe", "scanned", "errors", "error_samples", "rules")}
    return {"candidates": cands, "validation": r.get("validation", []), "status": status, "result": meta}


@router.post("/scan")
async def accumulation_scan(current_user: User = Depends(get_current_user)):
    """전 종목 다시 스캔 (백그라운드, 실서버 7~10분)"""
    if not accumulation.status()["running"]:
        asyncio.create_task(accumulation.scan())
        await asyncio.sleep(0)
    return accumulation.status()
