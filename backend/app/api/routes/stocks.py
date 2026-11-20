from fastapi import APIRouter, Depends, Query
import yfinance as yf
import asyncio
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services.kis_api import kis_client
from app.services.market_data import get_us_stock_history, get_news_naver
from app.services.analysis import calc_technical_indicators, predict_next_day, classify_investment_style


async def _get_us_price_yfinance(symbol: str) -> dict:
    """yfinance로 미국 주식 현재가 조회 (KIS 실패시 fallback)"""
    def _fetch():
        t = yf.Ticker(symbol)
        hist = t.history(period="2d")
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            curr = float(hist["Close"].iloc[-1])
            change = curr - prev
            change_rate = (change / prev) * 100
        elif len(hist) == 1:
            curr = float(hist["Close"].iloc[-1])
            change, change_rate = 0, 0
        else:
            return {"symbol": symbol, "market": "US", "price": 0, "change": 0, "change_rate": 0}
        return {
            "symbol": symbol, "market": "US",
            "price": round(curr, 2),
            "change": round(change, 2),
            "change_rate": round(change_rate, 2),
        }
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/kr/{symbol}")
async def get_kr_stock(symbol: str, current_user: User = Depends(get_current_user)):
    price = await kis_client.get_kr_stock_price(symbol)
    candles = await kis_client.get_kr_stock_history(symbol, count=120)
    indicators = calc_technical_indicators(candles)
    prediction = predict_next_day(candles, indicators)
    style = classify_investment_style(candles, indicators, price.get("per", 0), price.get("pbr", 0))
    news = await get_news_naver(symbol, market="KR")
    return {
        "price": price,
        "candles": candles,
        "indicators": indicators,
        "prediction": prediction,
        "style": style,
        "news": news,
    }


@router.get("/us/{symbol}")
async def get_us_stock(
    symbol: str,
    exchange: str = Query("NAS", description="NAS/NYS/AMS"),
    current_user: User = Depends(get_current_user),
):
    price = await kis_client.get_us_stock_price(symbol, exchange)
    candles = await get_us_stock_history(symbol, period="6mo")
    indicators = calc_technical_indicators(candles)
    prediction = predict_next_day(candles, indicators)
    style = classify_investment_style(candles, indicators)
    news = await get_news_naver(symbol, name=symbol, market="US")
    return {
        "price": price,
        "candles": candles,
        "indicators": indicators,
        "prediction": prediction,
        "style": style,
        "news": news,
    }


@router.get("/volume-surge")
async def get_volume_surge(current_user: User = Depends(get_current_user)):
    return await kis_client.get_volume_surge_kr()


@router.get("/recommendations/longterm")
async def get_longterm_recommendations(current_user: User = Depends(get_current_user)):
    """장기투자 추천 종목 (안정적 우량주 위주)"""
    candidates = [
        {"symbol": "005930", "name": "삼성전자", "market": "KR", "exchange": None},
        {"symbol": "000660", "name": "SK하이닉스", "market": "KR", "exchange": None},
        {"symbol": "051910", "name": "LG화학", "market": "KR", "exchange": None},
        {"symbol": "AAPL", "name": "애플", "market": "US", "exchange": "NAS"},
        {"symbol": "MSFT", "name": "마이크로소프트", "market": "US", "exchange": "NAS"},
        {"symbol": "KO", "name": "코카콜라", "market": "US", "exchange": "NYS"},
        {"symbol": "JNJ", "name": "존슨앤존슨", "market": "US", "exchange": "NYS"},
    ]
    results = []
    for c in candidates:
        try:
            if c["market"] == "KR":
                candles = await kis_client.get_kr_stock_history(c["symbol"], count=120)
                price_data = await kis_client.get_kr_stock_price(c["symbol"])
                per = price_data.get("per", 0)
                pbr = price_data.get("pbr", 0)
                price = price_data.get("price", 0)
                change_rate = price_data.get("change_rate", 0)
            else:
                candles = await get_us_stock_history(c["symbol"], period="6mo")
                try:
                    price_data = await kis_client.get_us_stock_price(c["symbol"], c["exchange"])
                except Exception:
                    price_data = await _get_us_price_yfinance(c["symbol"])
                per, pbr = 0, 0
                price = price_data.get("price", 0)
                change_rate = price_data.get("change_rate", 0)

            indicators = calc_technical_indicators(candles)
            style = classify_investment_style(candles, indicators, per, pbr)
            prediction = predict_next_day(candles, indicators)

            results.append({
                **c,
                "price": price,
                "change_rate": change_rate,
                "long_term_score": style.get("long_term_score", 0),
                "trend_6m": style.get("trend_6m", 0),
                "volatility": style.get("volatility", 0),
                "prediction": prediction,
                "per": per,
                "pbr": pbr,
            })
        except Exception as e:
            results.append({**c, "error": str(e)})

    results.sort(key=lambda x: x.get("long_term_score", 0), reverse=True)
    return results


@router.get("/recommendations/shortterm")
async def get_shortterm_recommendations(current_user: User = Depends(get_current_user)):
    """단기/스윙 추천 종목"""
    surge = await kis_client.get_volume_surge_kr()
    results = []
    for item in surge[:10]:
        try:
            candles = await kis_client.get_kr_stock_history(item["symbol"], count=60)
            indicators = calc_technical_indicators(candles)
            prediction = predict_next_day(candles, indicators)
            style = classify_investment_style(candles, indicators)
            results.append({
                **item,
                "market": "KR",
                "indicators": {
                    "rsi": indicators.get("rsi"),
                    "macd_hist": indicators.get("macd_hist"),
                },
                "prediction": prediction,
                "short_term_score": style.get("short_term_score", 0),
            })
        except Exception:
            pass

    results.sort(key=lambda x: x.get("prediction", {}).get("probability", 0), reverse=True)
    return results[:5]
