from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.auth import get_current_user
from app.core.swr import SWRCache
from app.models.user import User
from app.services import themes

router = APIRouter(prefix="/themes", tags=["themes"])

# 테마 등락은 KIS 시세 60여 번 호출 → 60초 안이면 그대로, 1시간 안이면 이전 값을 먼저 주고 뒤에서 갱신
_overview = SWRCache("themes", fresh=60, max_stale=3600)
_detail = SWRCache("theme_detail", fresh=20, max_stale=600)


@router.get("")
async def theme_list(current_user: User = Depends(get_current_user)):
    """테마 전체 (오늘 평균 등락률 높은 순) + 테마 구성 갱신 상태"""
    try:
        data = await _overview.get("all", themes.overview)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"테마 조회 실패 — {e}")
    return {**data, "status": themes.status()}


@router.get("/status")
async def theme_status(current_user: User = Depends(get_current_user)):
    return themes.status()


@router.post("/refresh")
async def theme_refresh(current_user: User = Depends(get_current_user)):
    """네이버 테마 구성 지금 다시 받기 (백그라운드)"""
    import asyncio
    if not themes.status()["running"]:
        asyncio.create_task(themes.refresh())
        await asyncio.sleep(0)
    return themes.status()


@router.get("/{no}")
async def theme_detail(no: str, current_user: User = Depends(get_current_user)):
    """테마 하나의 종목 (현재가·등락률·거래량·매집 점수·다른 테마)"""
    if not themes.get(no):
        raise HTTPException(status_code=404, detail=f"테마 {no} 없음")
    try:
        return await _detail.get(no, lambda: themes.detail(no))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"테마 종목 조회 실패 — {e}")
