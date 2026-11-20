from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
import asyncio
import yfinance as yf

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.models.portfolio import PortfolioItem
from app.services.kis_api import kis_client
from app.services.analysis import calc_technical_indicators, predict_next_day

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
        raise HTTPException(status_code=400, detail="Already in portfolio")

    item = PortfolioItem(
        user_id=current_user.id,
        symbol=req.symbol,
        market=req.market,
        name=req.name,
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


async def _fetch_price_and_predict(item: dict) -> dict:
    """보유 종목 현재가 + 예측 조회"""
    symbol = item["symbol"]
    market = item["market"]

    def _yf_fetch():
        yf_sym = f"{symbol}.KS" if market == "KR" else symbol
        t = yf.Ticker(yf_sym)
        hist = t.history(period="6mo")
        if market == "KR" and len(hist) < 20:
            t2 = yf.Ticker(f"{symbol}.KQ")
            hist2 = t2.history(period="6mo")
            if len(hist2) >= 20:
                hist = hist2
        return hist

    try:
        hist = await asyncio.get_event_loop().run_in_executor(None, _yf_fetch)
        if len(hist) < 20:
            return {**item, "current_price": 0, "change_rate": 0, "prediction": None, "error": "데이터 부족"}

        candles = []
        for ts, row in hist.iterrows():
            import pandas as pd
            c = float(row["Close"])
            if pd.isna(c) or c <= 0:
                continue
            candles.append({
                "date": str(ts.date()),
                "open": float(row["Open"]) if not pd.isna(row["Open"]) else c,
                "high": float(row["High"]) if not pd.isna(row["High"]) else c,
                "low": float(row["Low"]) if not pd.isna(row["Low"]) else c,
                "close": c,
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            })

        current_price = candles[-1]["close"] if candles else 0
        prev_price = candles[-2]["close"] if len(candles) >= 2 else current_price
        change_rate = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0

        indicators = calc_technical_indicators(candles)
        prediction = predict_next_day(candles, indicators)

        # 수익/손실 계산
        avg_price = item.get("avg_price", 0)
        quantity = item.get("quantity", 0)
        pnl_pct = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
        pnl_amount = (current_price - avg_price) * quantity if avg_price > 0 and quantity > 0 else 0

        return {
            **item,
            "current_price": current_price,
            "change_rate": round(change_rate, 2),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_amount": round(pnl_amount, 2),
            "prediction": prediction,
        }
    except Exception as e:
        return {**item, "current_price": 0, "change_rate": 0, "prediction": None, "error": str(e)}


@router.get("/analysis")
async def analyze_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목별 현재가 + 예측"""
    result = await db.execute(
        select(PortfolioItem).where(PortfolioItem.user_id == current_user.id)
    )
    items = result.scalars().all()
    if not items:
        return []

    item_dicts = [
        {"id": i.id, "symbol": i.symbol, "market": i.market, "name": i.name,
         "quantity": i.quantity, "avg_price": i.avg_price}
        for i in items
    ]

    results = await asyncio.gather(*[_fetch_price_and_predict(item) for item in item_dicts])
    return list(results)
