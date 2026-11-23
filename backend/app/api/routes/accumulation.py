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


# ---------- 퀀트 점수 (같은 스캔 결과) ----------
quant_router = APIRouter(prefix="/quant", tags=["quant"])


@quant_router.get("")
async def quant_result(limit: int = 100, min_score: int = 1, current_user: User = Depends(get_current_user)):
    """국내 퀀트 점수 상위 종목 + 요인 가중치 + 검증(뒤쪽 기간) + 스캔 상태"""
    r = accumulation.result() or {}
    q = r.get("quant")
    status = {**accumulation.status(), "stale": accumulation.stale()}
    if not q:
        return {"quant": None, "error": r.get("quant_error"), "status": status, "base_date": r.get("base_date")}
    top = [{**t, "themes": themes.themes_of(t["symbol"])[:3], "accum": (r.get("scores") or {}).get(t["symbol"])}
           for t in q.get("top", []) if t["score"] >= min_score][:max(1, min(limit, 150))]
    meta = {k: q.get(k) for k in ("date", "universe", "horizon_days", "weights", "ic", "useful", "validation", "factors")}
    return {"quant": {**meta, "top": top}, "error": None, "status": status, "base_date": r.get("base_date")}
