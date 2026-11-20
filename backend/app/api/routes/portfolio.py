from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
import asyncio

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.models.portfolio import PortfolioItem
from app.services import stock_master
from app.services.quote import analyze_items, get_usdkrw
from app.services import prediction_log

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class PortfolioAddRequest(BaseModel):
    symbol: str
    market: str
    name: str = ""
    quantity: float = 0.0
    avg_price: float = 0.0


class PortfolioUpdateRequest(BaseModel):
    quantity: Optional[float] = None
    avg_price: Optional[float] = None
    name: Optional[str] = None


@router.get("/")
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PortfolioItem).where(PortfolioItem.user_id == current_user.id)
    )
    items = result.scalars().all()
    return [
        {
            "id": i.id,
            "symbol": i.symbol,
            "market": i.market,
            "name": i.name,
            "quantity": i.quantity,
            "avg_price": i.avg_price,
        }
        for i in items
    ]


@router.post("/")
async def add_to_portfolio(
    req: PortfolioAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(PortfolioItem).where(
            PortfolioItem.user_id == current_user.id,
            PortfolioItem.symbol == req.symbol,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 투자종목에 있습니다")

    master = stock_master.get(req.market, req.symbol)
    if not master:
        raise HTTPException(status_code=400, detail=f"종목마스터에 없는 종목입니다: {req.market} {req.symbol}")

    item = PortfolioItem(
        user_id=current_user.id,
        symbol=req.symbol,
        market=req.market,
        name=master["name"],
        quantity=req.quantity,
        avg_price=req.avg_price,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {
        "id": item.id,
        "symbol": item.symbol,
        "market": item.market,
        "name": item.name,
        "quantity": item.quantity,
        "avg_price": item.avg_price,
    }


@router.put("/{item_id}")
async def update_portfolio_item(
    item_id: int,
    req: PortfolioUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PortfolioItem).where(
            PortfolioItem.id == item_id,
            PortfolioItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")

    if req.quantity is not None:
        item.quantity = req.quantity
    if req.avg_price is not None:
        item.avg_price = req.avg_price
    if req.name is not None:
        item.name = req.name

    await db.commit()
    await db.refresh(item)
    return {
        "id": item.id,
        "symbol": item.symbol,
        "market": item.market,
        "name": item.name,
        "quantity": item.quantity,
        "avg_price": item.avg_price,
    }


@router.delete("/{item_id}")
async def remove_from_portfolio(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(PortfolioItem).where(
            PortfolioItem.id == item_id,
            PortfolioItem.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"message": "Removed"}


def _norm(s: str) -> str:
    return (s or "").replace(" ", "").lower()


def _code_warning(item: dict) -> str | None:
    """저장된 종목코드가 실제로 그 종목인지 공식 종목마스터로 확인"""
    m = stock_master.get(item["market"], item["symbol"])
    if not m:
        return f"종목코드 {item['symbol']} 는 공식 종목마스터에 없습니다. 삭제 후 검색해서 다시 추가하세요."
    if item.get("name") and _norm(item["name"]) != _norm(m["name"]):
        return (f"종목코드 {item['symbol']} 의 실제 종목은 '{m['name']}' 입니다 (저장된 이름: '{item['name']}'). "
                f"삭제 후 검색해서 다시 추가하세요.")
    return None


def _with_pnl(item: dict, r: dict) -> dict:
    price = r["price"]
    avg, qty = item.get("avg_price", 0), item.get("quantity", 0)
    invested = avg * qty
    value = price * qty
    return {
        **item,
        "current_price": price,
        "change_rate": r["change_rate"],
        "invested": round(invested, 2),
        "value": round(value, 2),
        "pnl_pct": round((price - avg) / avg * 100, 2) if avg > 0 else 0,
        "pnl_amount": round(value - invested, 2) if avg > 0 else 0,
        "prediction": r["prediction"],
    }


@router.get("/analysis")
async def analyze_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목별 현재가·손익·내일 전망 + 통화별 합계 + 원화 환산 총합"""
    result = await db.execute(
        select(PortfolioItem).where(PortfolioItem.user_id == current_user.id)
    )
    items = [
        {"id": i.id, "symbol": i.symbol, "market": i.market, "name": i.name,
         "quantity": i.quantity, "avg_price": i.avg_price}
        for i in result.scalars().all()
    ]

    has_us = any(i["market"] == "US" for i in items)

    async def fx():
        if not has_us:
            return None, None
        try:
            return await get_usdkrw(), None
        except Exception as e:
            return None, str(e)

    analyzed, (usdkrw, fx_error) = await asyncio.gather(analyze_items(items), fx())
    await prediction_log.record(list(analyzed.values()), "투자종목")

    rows = []
    totals = {cur: {"invested": 0.0, "value": 0.0, "pnl": 0.0, "count": 0} for cur in ("KRW", "USD")}
    for item in items:
        r = analyzed.get((item["market"], item["symbol"]), {"error": "분석 결과 없음"})
        warning = _code_warning(item)
        if "error" in r:
            rows.append({**item, "error": r["error"], "warning": warning, "prediction": None})
            continue
        row = _with_pnl(item, r)
        row["warning"] = warning
        rows.append(row)
        t = totals["KRW" if item["market"] == "KR" else "USD"]
        t["invested"] += row["invested"]
        t["value"] += row["value"]
        t["pnl"] += row["pnl_amount"]
        t["count"] += 1

    for t in totals.values():
        t["pnl_pct"] = round(t["pnl"] / t["invested"] * 100, 2) if t["invested"] > 0 else 0
        for k in ("invested", "value", "pnl"):
            t[k] = round(t[k], 2)

    combined = None
    if usdkrw or not has_us:
        rate = usdkrw or 0
        k, u = totals["KRW"], totals["USD"]
        inv = k["invested"] + u["invested"] * rate
        val = k["value"] + u["value"] * rate
        combined = {
            "invested": round(inv), "value": round(val), "pnl": round(val - inv),
            "pnl_pct": round((val - inv) / inv * 100, 2) if inv > 0 else 0,
        }

    return {
        "items": rows,
        "totals": totals,
        "usdkrw": round(usdkrw, 2) if usdkrw else None,
        "fx_error": fx_error,
        "combined_krw": combined,
    }
