"""종목 시세 + 분석 공통 모듈 (투자종목·관심종목·종목탐색·AI추천이 같이 사용)

- 국내(KR): KIS 일봉/현재가 (실시간, 공식 종목코드 기준)
- 미국(US): yfinance 배치 다운로드
- USD/KRW 환율: yfinance KRW=X
"""
import asyncio

import pandas as pd
import yfinance as yf

from app.services.kis_api import kis_client
from app.services import stock_master
from app.services.analysis import calc_technical_indicators, predict_next_day, classify_investment_style


def batch_yf_history_sync(tickers: list, period: str = "6mo") -> dict:
    """yfinance 배치 다운로드 → {ticker: [candles]} (날짜 오름차순)"""
    if not tickers:
        return {}
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False, threads=True)
    if data is None or data.empty:
        return {t: [] for t in tickers}

    is_multi = isinstance(data.columns, pd.MultiIndex)
    results = {}
    for sym in tickers:
        if is_multi:
            if sym not in data.columns.get_level_values(1):
                results[sym] = []
                continue
            cols = {k: data[k][sym] for k in ("Close", "Open", "High", "Low", "Volume")}
        else:
            cols = {k: data[k] for k in ("Close", "Open", "High", "Low", "Volume")}
        close = cols["Close"]
        candles = []
        for ts in close.dropna().index:
            c = float(close[ts])
            if c <= 0:
                continue

            def v(k, default):
                x = cols[k][ts]
                return default if pd.isna(x) else float(x)

            candles.append({
                "date": str(ts.date()),
                "open": v("Open", c), "high": v("High", c), "low": v("Low", c),
                "close": c, "volume": int(v("Volume", 0)),
            })
        results[sym] = candles
    return results


async def batch_yf_history(tickers: list, period: str = "6mo") -> dict:
    return await asyncio.get_event_loop().run_in_executor(None, lambda: batch_yf_history_sync(tickers, period))


def _analyze(candles: list, per: float = 0, pbr: float = 0) -> dict:
    indicators = calc_technical_indicators(candles)
    return {
        "indicators": indicators,
        "prediction": predict_next_day(candles, indicators),
        "style": classify_investment_style(candles, indicators, per, pbr),
    }


async def analyze_kr(symbol: str, count: int = 120) -> dict:
    """국내 종목 1개: KIS 현재가 + 일봉 + 분석"""
    chart = await kis_client.get_kr_chart(symbol, count)
    master = stock_master.get("KR", symbol) or {}
    candles = chart["candles"]
    return {
        "symbol": symbol,
        "market": "KR",
        "name": master.get("name") or chart["name"],
        "type": master.get("type", "stock"),
        "price": chart["price"],
        "change_rate": chart["change_rate"],
        "per": chart["per"],
        "pbr": chart["pbr"],
        "volume": candles[-1]["volume"],
        "candles": candles,
        **_analyze(candles, chart["per"], chart["pbr"]),
    }


def _us_from_candles(symbol: str, candles: list) -> dict:
    master = stock_master.get("US", symbol) or {}
    price = candles[-1]["close"]
    prev = candles[-2]["close"] if len(candles) >= 2 else price
    return {
        "symbol": symbol,
        "market": "US",
        "name": master.get("name") or symbol,
        "type": master.get("type", "stock"),
        "exchange": master.get("exchange", "NAS"),
        "price": round(price, 2),
        "change_rate": round((price - prev) / prev * 100, 2) if prev > 0 else 0.0,
        "per": 0, "pbr": 0,
        "volume": candles[-1]["volume"],
        "candles": candles,
        **_analyze(candles),
    }


async def analyze_us_many(symbols: list, period: str = "6mo") -> dict:
    """미국 종목 여러 개 (yfinance 배치 1회) → {symbol: 결과 또는 {"error": ...}}"""
    hist = await batch_yf_history(symbols, period)
    out = {}
    for s in symbols:
        candles = hist.get(s, [])
        if len(candles) < 20:
            out[s] = {"symbol": s, "market": "US", "error": f"yfinance 가격 데이터 부족 ({len(candles)}일)"}
        else:
            out[s] = _us_from_candles(s, candles)
    return out


async def analyze_kr_many(symbols: list, count: int = 120) -> dict:
    """국내 종목 여러 개 (KIS 호출은 kis_client 가 초당 제한에 맞춰 순서대로 보냄)"""
    async def one(s):
        try:
            return s, await analyze_kr(s, count)
        except Exception as e:
            return s, {"symbol": s, "market": "KR", "error": str(e)}
    return dict(await asyncio.gather(*[one(s) for s in symbols]))


async def analyze_items(items: list, period: str = "6mo") -> dict:
    """[{market, symbol}, ...] → {(market, symbol): 결과}"""
    kr = [i["symbol"] for i in items if i["market"] == "KR"]
    us = [i["symbol"] for i in items if i["market"] == "US"]
    kr_res, us_res = await asyncio.gather(analyze_kr_many(kr), analyze_us_many(us, period) if us else _empty())
    out = {("KR", k): v for k, v in kr_res.items()}
    out.update({("US", k): v for k, v in us_res.items()})
    return out


async def _empty():
    return {}


def strip_candles(d: dict) -> dict:
    """응답 크기 줄이기 — 목록 화면에는 캔들 전체가 필요 없음"""
    return {k: v for k, v in d.items() if k != "candles"}


async def get_usdkrw() -> float:
    def _fetch():
        hist = yf.Ticker("KRW=X").history(period="5d")
        if hist.empty:
            raise RuntimeError("USD/KRW 환율 데이터 없음 (yfinance KRW=X)")
        return float(hist["Close"].dropna().iloc[-1])
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)
