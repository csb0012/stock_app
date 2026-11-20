from fastapi import APIRouter, Depends
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services.market_data import get_index_data, get_bigtech_data, get_economic_calendar, get_us_etf_data

router = APIRouter(prefix="/market", tags=["market"])


_overview_cache: dict = {"ts": 0.0, "data": None}


@router.get("/overview")
async def get_market_overview(current_user: User = Depends(get_current_user)):
    """대시보드 - 주요 지수 + 매크로 한번에 (60초 캐시)"""
    import asyncio, time
    if _overview_cache["data"] and time.time() - _overview_cache["ts"] < 60:
        return _overview_cache["data"]
    indices, bigtech, etfs = await asyncio.gather(
        get_index_data(),
        get_bigtech_data(),
        get_us_etf_data(),
    )
    data = {"indices": indices, "bigtech": bigtech, "etfs": etfs}
    _overview_cache.update(ts=time.time(), data=data)
    return data


@router.get("/indices")
async def get_indices(current_user: User = Depends(get_current_user)):
    return await get_index_data()


@router.get("/bigtech")
async def get_bigtech(current_user: User = Depends(get_current_user)):
    return await get_bigtech_data()


@router.get("/calendar")
async def get_calendar(current_user: User = Depends(get_current_user)):
    return await get_economic_calendar()
