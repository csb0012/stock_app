from fastapi import APIRouter, Depends
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services.market_data import get_index_data, get_bigtech_data, get_economic_calendar

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview")
async def get_market_overview(current_user: User = Depends(get_current_user)):
    """대시보드 - 주요 지수 + 매크로 한번에"""
    indices, bigtech = await __import__("asyncio").gather(
        get_index_data(),
        get_bigtech_data(),
    )
    return {"indices": indices, "bigtech": bigtech}


@router.get("/indices")
async def get_indices(current_user: User = Depends(get_current_user)):
    return await get_index_data()


@router.get("/bigtech")
async def get_bigtech(current_user: User = Depends(get_current_user)):
    return await get_bigtech_data()


@router.get("/calendar")
async def get_calendar(current_user: User = Depends(get_current_user)):
    return await get_economic_calendar()
