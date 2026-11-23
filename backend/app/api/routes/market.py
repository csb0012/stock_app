import asyncio

from fastapi import APIRouter, Depends, HTTPException
from app.api.routes.auth import get_current_user
from app.core.swr import SWRCache
from app.models.user import User
from app.services.market_data import (get_kr_indices, get_global_indices, get_bigtech_data,
                                      get_us_etf_data, INDEX_TICKERS, KIS_INDEX)
from app.services.econ_calendar import get_economic_calendar
from app.services import us_daytime

router = APIRouter(prefix="/market", tags=["market"])

# 대시보드 구역별 캐시: 60초 안이면 그대로, 6시간 안이면 기존 값을 바로 보여주고 뒤에서 갱신
# (구역마다 따로 받으므로 느린 Yahoo 가 KIS 국내 지수 표시를 막지 않음)
_overview = SWRCache("overview", fresh=60, max_stale=6 * 3600)
_SECTIONS = {
    "kr_indices": lambda: get_kr_indices(),
    "global_indices": lambda: get_global_indices(),
    "bigtech": lambda: _list(get_bigtech_data()),
    "etfs": lambda: _list(get_us_etf_data()),
}
# 일부 출처가 일시적으로 실패한 결과(retry)는 5분 뒤 다시 받음
_calendar = SWRCache("calendar", fresh=3600, max_stale=24 * 3600,
                     fresh_for=lambda v: 300 if isinstance(v, dict) and v.get("retry") else 3600)


async def _list(coro) -> dict:
    return {"items": await coro}


async def overview_section(section: str) -> dict:
    return await _overview.get(section, _SECTIONS[section])


def warm_overview():
    """서버 시작 직후 대시보드 데이터를 미리 받아 둠 (첫 화면 대기 줄이기)"""
    for name, fn in _SECTIONS.items():
        _overview.warm(name, fn)


@router.get("/overview/{section}")
async def get_overview_section(section: str, current_user: User = Depends(get_current_user)):
    """대시보드 한 구역 (kr_indices | global_indices | bigtech | etfs) — 화면이 구역별로 따로 받아 먼저 온 것부터 표시"""
    if section not in _SECTIONS:
        raise HTTPException(status_code=404, detail=f"section 은 {list(_SECTIONS)} 중 하나")
    try:
        data = await overview_section(section)
        if section in ("bigtech", "etfs"):   # 미국 주간거래 가격 (한국 낮 시간만, 캐시와 별개로 30초마다)
            data = {**data, "items": await us_daytime.attach(data.get("items") or [], market_key=None)}
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{section} 조회 실패 — {e}")


@router.get("/overview")
async def get_market_overview(current_user: User = Depends(get_current_user)):
    """대시보드 전체 한번에 (예전 화면·점검용). 구역별 캐시를 같이 씀"""
    kr, gl, big, etf = await asyncio.gather(*[overview_section(s) for s in _SECTIONS])
    return {"indices": {k: (kr if k in KIS_INDEX else gl)[k] for k in INDEX_TICKERS},
            "bigtech": big["items"], "etfs": etf["items"]}


@router.get("/status")
async def get_market_status(current_user: User = Depends(get_current_user)):
    """국내·미국 장 운영 상태 (휴장일 반영)"""
    from app.services.market_calendar import market_status
    return {"KR": market_status("KR"), "US": market_status("US")}


@router.get("/extras-status")
async def get_extras_status(current_user: User = Depends(get_current_user)):
    """점검용: FRED·Finnhub·DART 키 설정 여부와 수집 현황"""
    from app.services import extras
    return extras.status()


@router.get("/scheduler-status")
async def get_scheduler_status(current_user: User = Depends(get_current_user)):
    """점검용: 자동 예측 기록(장 시작 전·장 마감 후) 마지막 실행 결과"""
    from app.services import scheduler
    return scheduler.status()


@router.get("/calendar")
async def get_calendar(current_user: User = Depends(get_current_user)):
    """경제 캘린더 (1시간 캐시, 하루 안이면 기존 값을 바로 보여주고 뒤에서 갱신)"""
    try:
        return await _calendar.get("calendar", get_economic_calendar)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"경제 캘린더 조회 실패 — {e}")
