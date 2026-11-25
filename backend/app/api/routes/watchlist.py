from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel, field_validator

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.services import stock_master
from app.services.quote import analyze_items
from app.services import prediction_log
from app.core.swr import SWRCache
from app.services import us_daytime, accumulation

# 같은 목록을 15초 안에 다시 요청하면(화면 이동·새로고침 연타) 다시 분석하지 않음, 동시에 와도 분석은 한 번
_analysis_cache = SWRCache("watchlist_analysis", fresh=15, max_stale=15)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistAddRequest(BaseModel):
    symbol: str
    market: str  # KR / US
    name: str = ""

    @field_validator("market")
    @classmethod
    def _market(cls, v):
        if v not in ("KR", "US"):
            raise ValueError("market 은 KR 또는 US")
        return v


class WatchlistUpdateRequest(BaseModel):
    memo: Optional[str] = None
    target_price: Optional[float] = None  # 0 이하를 보내면 목표가 삭제


def _to_dict(i: WatchlistItem) -> dict:
    return {
        "id": i.id, "symbol": i.symbol, "market": i.market, "name": i.name,
        "memo": i.memo, "target_price": i.target_price,
        "added_at": i.added_at.isoformat() if i.added_at else None,
    }


async def _get_owned(db: AsyncSession, item_id: int, user: User) -> WatchlistItem:
    result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.id == item_id, WatchlistItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


@router.get("/")
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == current_user.id)
    )
    return [_to_dict(i) for i in result.scalars().all()]


@router.post("/")
async def add_to_watchlist(
    req: WatchlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.symbol == req.symbol,
            WatchlistItem.market == req.market,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 관심종목에 있습니다")

    master = stock_master.get(req.market, req.symbol)
    if not master:
        raise HTTPException(status_code=400, detail=f"종목마스터에 없는 종목입니다: {req.market} {req.symbol}")

    item = WatchlistItem(user_id=current_user.id, symbol=req.symbol, market=req.market, name=master["name"])
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _to_dict(item)


@router.put("/{item_id}")
async def update_watchlist_item(
    item_id: int,
    req: WatchlistUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await _get_owned(db, item_id, current_user)
    if req.memo is not None:
        item.memo = req.memo.strip() or None
    if req.target_price is not None:
        item.target_price = req.target_price if req.target_price > 0 else None
    await db.commit()
    await db.refresh(item)
    return _to_dict(item)


@router.delete("/{item_id}")
async def remove_from_watchlist(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == current_user.id,
        )
    )
    await db.commit()
    if not res.rowcount:
        raise HTTPException(status_code=404, detail="이미 없는 종목입니다")
    return {"message": "Removed"}


@router.get("/analysis")
async def analyze_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관심종목별 현재가·등락률·내일 전망·목표가 도달 여부"""
    result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == current_user.id)
    )
    items = [_to_dict(i) for i in result.scalars().all()]
    key = (current_user.id, tuple((i["id"], i["symbol"], i["market"], i["memo"], i["target_price"]) for i in items))
    rows = await _analysis_cache.get(key, lambda: _analyze(items), wrap=False)
    rows = await us_daytime.attach(rows)   # 미국 주간거래 가격 (한국 낮 시간만, 표시 전용)
    return await prediction_log.attach_tracks(rows)   # 종목별 최근 90일 예측 적중 기록


async def _analyze(items: list) -> list:
    analyzed = await analyze_items(items)
    await prediction_log.record(list(analyzed.values()), "관심종목")
    rows = []
    for item in items:
        r = analyzed.get((item["market"], item["symbol"]), {"error": "분석 결과 없음"})
        if "error" in r:
            rows.append({**item, "error": r["error"]})
            continue
        ind = r["indicators"]
        candles = r["candles"]
        closes = [c["close"] for c in candles]
        tp = item["target_price"]
        rows.append({
            **item,
            "current_price": r["price"],
            "change_rate": r["change_rate"],
            "price_source": r.get("price_source"),   # 미국: KIS / Yahoo (KIS 실패 시 — 최대 15분 지연)
            "prediction": r["prediction"],
            "rsi": ind.get("rsi"),
            "high_period": max(closes),
            "low_period": min(closes),
            "period_days": len(closes),
            "change_5d": round((closes[-1] / closes[-6] - 1) * 100, 2) if len(closes) >= 6 else None,
            "change_20d": round((closes[-1] / closes[-21] - 1) * 100, 2) if len(closes) >= 21 else None,
            "target_gap_pct": round((r["price"] - tp) / tp * 100, 2) if tp else None,
            "target_reached": bool(tp and r["price"] <= tp),
            "quant": accumulation.quant_of(item["symbol"]) if item["market"] == "KR" else None,
        })
    return rows
