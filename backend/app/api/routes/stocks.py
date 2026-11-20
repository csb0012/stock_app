from fastapi import APIRouter, Depends, Query
import yfinance as yf
import asyncio
import json
import os
import time
import pandas as pd
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services.kis_api import kis_client
from app.services.market_data import get_us_stock_history, get_news_naver
from app.services.analysis import calc_technical_indicators, predict_next_day, classify_investment_style

router = APIRouter(prefix="/stocks", tags=["stocks"])

_STOCK_LIST_PATH = os.path.join(os.path.dirname(__file__), "../../data/stock_list.json")
_stock_list_cache: list = []

# --- 추천 캐시 (15분 TTL) ---
_rec_cache: dict = {
    "longterm": {"data": None, "ts": 0.0},
    "shortterm": {"data": None, "ts": 0.0},
}
_CACHE_TTL = 900.0

# --- 추천 후보 종목 목록 ---
KR_LONGTERM = [
    {"symbol": "005930", "name": "삼성전자",        "market": "KR", "yf": "005930.KS"},
    {"symbol": "000660", "name": "SK하이닉스",       "market": "KR", "yf": "000660.KS"},
    {"symbol": "051910", "name": "LG화학",           "market": "KR", "yf": "051910.KS"},
    {"symbol": "035420", "name": "NAVER",            "market": "KR", "yf": "035420.KS"},
    {"symbol": "005380", "name": "현대자동차",        "market": "KR", "yf": "005380.KS"},
    {"symbol": "068270", "name": "셀트리온",          "market": "KR", "yf": "068270.KQ"},
    {"symbol": "035720", "name": "카카오",            "market": "KR", "yf": "035720.KQ"},
    {"symbol": "006400", "name": "삼성SDI",          "market": "KR", "yf": "006400.KS"},
    {"symbol": "066570", "name": "LG전자",           "market": "KR", "yf": "066570.KS"},
    {"symbol": "017670", "name": "SK텔레콤",         "market": "KR", "yf": "017670.KS"},
    {"symbol": "030200", "name": "KT",               "market": "KR", "yf": "030200.KS"},
    {"symbol": "009150", "name": "삼성전기",          "market": "KR", "yf": "009150.KS"},
    {"symbol": "000270", "name": "기아",              "market": "KR", "yf": "000270.KS"},
    {"symbol": "207940", "name": "삼성바이오로직스",   "market": "KR", "yf": "207940.KS"},
    {"symbol": "096770", "name": "SK이노베이션",      "market": "KR", "yf": "096770.KS"},
    {"symbol": "028260", "name": "삼성물산",          "market": "KR", "yf": "028260.KS"},
    {"symbol": "018260", "name": "삼성에스디에스",     "market": "KR", "yf": "018260.KS"},
    {"symbol": "010130", "name": "고려아연",          "market": "KR", "yf": "010130.KS"},
    {"symbol": "032830", "name": "삼성생명",          "market": "KR", "yf": "032830.KS"},
    {"symbol": "034020", "name": "두산에너빌리티",    "market": "KR", "yf": "034020.KS"},
    {"symbol": "005490", "name": "POSCO홀딩스",      "market": "KR", "yf": "005490.KS"},
    {"symbol": "055550", "name": "신한지주",          "market": "KR", "yf": "055550.KS"},
    {"symbol": "105560", "name": "KB금융",            "market": "KR", "yf": "105560.KS"},
    {"symbol": "086790", "name": "하나금융지주",      "market": "KR", "yf": "086790.KS"},
    {"symbol": "003490", "name": "대한항공",          "market": "KR", "yf": "003490.KS"},
]

US_LONGTERM = [
    {"symbol": "AAPL",  "name": "애플",           "market": "US", "exchange": "NAS"},
    {"symbol": "MSFT",  "name": "마이크로소프트",   "market": "US", "exchange": "NAS"},
    {"symbol": "NVDA",  "name": "엔비디아",         "market": "US", "exchange": "NAS"},
    {"symbol": "GOOGL", "name": "알파벳",           "market": "US", "exchange": "NAS"},
    {"symbol": "AMZN",  "name": "아마존",           "market": "US", "exchange": "NAS"},
    {"symbol": "META",  "name": "메타",             "market": "US", "exchange": "NAS"},
    {"symbol": "TSLA",  "name": "테슬라",           "market": "US", "exchange": "NAS"},
    {"symbol": "AVGO",  "name": "브로드컴",         "market": "US", "exchange": "NAS"},
    {"symbol": "AMD",   "name": "AMD",              "market": "US", "exchange": "NAS"},
    {"symbol": "NFLX",  "name": "넷플릭스",         "market": "US", "exchange": "NAS"},
    {"symbol": "COST",  "name": "코스트코",         "market": "US", "exchange": "NAS"},
    {"symbol": "JPM",   "name": "JP모건",           "market": "US", "exchange": "NYS"},
    {"symbol": "V",     "name": "비자",             "market": "US", "exchange": "NYS"},
    {"symbol": "JNJ",   "name": "존슨앤존슨",       "market": "US", "exchange": "NYS"},
    {"symbol": "KO",    "name": "코카콜라",         "market": "US", "exchange": "NYS"},
    {"symbol": "WMT",   "name": "월마트",           "market": "US", "exchange": "NYS"},
    {"symbol": "XOM",   "name": "엑슨모빌",         "market": "US", "exchange": "NYS"},
    {"symbol": "LLY",   "name": "일라이릴리",       "market": "US", "exchange": "NYS"},
    {"symbol": "PG",    "name": "P&G",              "market": "US", "exchange": "NYS"},
    {"symbol": "HD",    "name": "홈디포",           "market": "US", "exchange": "NYS"},
    {"symbol": "ABBV",  "name": "애브비",           "market": "US", "exchange": "NYS"},
    {"symbol": "BRK-B", "name": "버크셔해서웨이",   "market": "US", "exchange": "NYS"},
    {"symbol": "MRK",   "name": "머크",             "market": "US", "exchange": "NYS"},
    {"symbol": "SPY",   "name": "S&P500 ETF",       "market": "US", "exchange": "AMS"},
    {"symbol": "QQQ",   "name": "나스닥100 ETF",    "market": "US", "exchange": "NAS"},
]

US_SHORTTERM_EXTRA = [
    {"symbol": "TSLA",  "name": "테슬라",    "market": "US", "exchange": "NAS"},
    {"symbol": "NVDA",  "name": "엔비디아",  "market": "US", "exchange": "NAS"},
    {"symbol": "AMD",   "name": "AMD",       "market": "US", "exchange": "NAS"},
    {"symbol": "COIN",  "name": "코인베이스","market": "US", "exchange": "NAS"},
    {"symbol": "PLTR",  "name": "팔란티어",  "market": "US", "exchange": "NYS"},
    {"symbol": "MSTR",  "name": "마이크로스트래티지","market": "US", "exchange": "NAS"},
    {"symbol": "IONQ",  "name": "아이온큐",  "market": "US", "exchange": "NYS"},
    {"symbol": "SMCI",  "name": "슈퍼마이크로","market": "US","exchange": "NAS"},
    {"symbol": "RIVN",  "name": "리비안",    "market": "US", "exchange": "NAS"},
    {"symbol": "SOFI",  "name": "소파이",    "market": "US", "exchange": "NAS"},
    {"symbol": "RKLB",  "name": "로켓랩",    "market": "US", "exchange": "NAS"},
    {"symbol": "SOXL",  "name": "반도체 3배 ETF","market": "US", "exchange": "AMS"},
    {"symbol": "TQQQ",  "name": "나스닥 3배 ETF","market": "US", "exchange": "NAS"},
]

# 스크리너용 상위 KR 종목 (yfinance batch용)
KR_SCREENER_STOCKS = [
    ("005930", "삼성전자", ".KS"), ("000660", "SK하이닉스", ".KS"),
    ("051910", "LG화학", ".KS"),   ("035420", "NAVER", ".KS"),
    ("005380", "현대자동차", ".KS"),("068270", "셀트리온", ".KQ"),
    ("035720", "카카오", ".KQ"),   ("006400", "삼성SDI", ".KS"),
    ("066570", "LG전자", ".KS"),   ("017670", "SK텔레콤", ".KS"),
    ("030200", "KT", ".KS"),       ("009150", "삼성전기", ".KS"),
    ("000270", "기아", ".KS"),     ("207940", "삼성바이오로직스", ".KS"),
    ("096770", "SK이노베이션", ".KS"),("005490", "POSCO홀딩스", ".KS"),
    ("055550", "신한지주", ".KS"), ("105560", "KB금융", ".KS"),
    ("086790", "하나금융지주", ".KS"),("034020", "두산에너빌리티", ".KS"),
    ("003490", "대한항공", ".KS"), ("010130", "고려아연", ".KS"),
    ("028260", "삼성물산", ".KS"), ("018260", "삼성에스디에스", ".KS"),
    ("032830", "삼성생명", ".KS"), ("326030", "SK바이오팜", ".KS"),
    ("003550", "LG", ".KS"),       ("011200", "HMM", ".KS"),
    ("042700", "한미반도체", ".KS"),("000100", "유한양행", ".KS"),
]

# 스크리너용 상위 US 종목
US_SCREENER_STOCKS = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","BRK-B","JPM","V",
    "JNJ","KO","WMT","XOM","ABBV","LLY","PG","MRK","HD","AVGO",
    "COST","NFLX","AMD","COIN","PLTR","MSTR","IONQ","SMCI","RIVN","SOFI",
    "RKLB","BAC","MA","CVX","INTC","QCOM","TXN","CRM","ORCL","IBM",
    "SPY","QQQ","SOXL","TQQQ","TLT","GLD","SLV","ARKK","IWM","DIA",
]


def _load_stock_list() -> list:
    global _stock_list_cache
    if not _stock_list_cache:
        with open(_STOCK_LIST_PATH, encoding="utf-8") as f:
            _stock_list_cache = json.load(f)
    return _stock_list_cache


def _batch_yf_history_sync(tickers: list, period: str = "6mo") -> dict:
    """yfinance 배치 다운로드 → {ticker: [candles]}"""
    if not tickers:
        return {}
    try:
        data = yf.download(tickers, period=period, auto_adjust=True, progress=False, threads=True)
    except Exception:
        return {t: [] for t in tickers}

    if data.empty:
        return {t: [] for t in tickers}

    is_multi = isinstance(data.columns, pd.MultiIndex)
    results = {}

    for sym in tickers:
        try:
            if is_multi:
                if sym not in data.columns.get_level_values(1):
                    results[sym] = []
                    continue
                close = data["Close"][sym]
                open_ = data["Open"][sym]
                high = data["High"][sym]
                low = data["Low"][sym]
                volume = data["Volume"][sym]
            else:
                close = data["Close"]
                open_ = data["Open"]
                high = data["High"]
                low = data["Low"]
                volume = data["Volume"]

            candles = []
            for ts in close.dropna().index:
                c = float(close[ts])
                if c <= 0:
                    continue
                candles.append({
                    "date": str(ts.date()),
                    "open": float(open_[ts]) if not pd.isna(open_[ts]) else c,
                    "high": float(high[ts]) if not pd.isna(high[ts]) else c,
                    "low": float(low[ts]) if not pd.isna(low[ts]) else c,
                    "close": c,
                    "volume": int(volume[ts]) if not pd.isna(volume[ts]) else 0,
                })
            results[sym] = candles
        except Exception:
            results[sym] = []

    return results


async def _get_us_price_yfinance(symbol: str) -> dict:
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
            change, change_rate = 0.0, 0.0
        else:
            return {"symbol": symbol, "market": "US", "price": 0.0, "change": 0.0, "change_rate": 0.0}
        return {"symbol": symbol, "market": "US",
                "price": round(curr, 2), "change": round(change, 2), "change_rate": round(change_rate, 2)}
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def _build_longterm_recommendations() -> list:
    """배치 yfinance로 장기 추천 종목 분석"""
    kr_yf_tickers = [c["yf"] for c in KR_LONGTERM]
    us_yf_tickers = [c["symbol"] for c in US_LONGTERM]

    kr_hist, us_hist = await asyncio.gather(
        asyncio.get_event_loop().run_in_executor(None, lambda: _batch_yf_history_sync(kr_yf_tickers)),
        asyncio.get_event_loop().run_in_executor(None, lambda: _batch_yf_history_sync(us_yf_tickers)),
    )

    results = []

    for c in KR_LONGTERM:
        try:
            candles = kr_hist.get(c["yf"], [])
            if len(candles) < 20:
                continue
            price = candles[-1]["close"]
            prev = candles[-2]["close"] if len(candles) >= 2 else price
            change_rate = round((price - prev) / prev * 100, 2) if prev > 0 else 0.0
            indicators = calc_technical_indicators(candles)
            style = classify_investment_style(candles, indicators)
            prediction = predict_next_day(candles, indicators)
            results.append({
                **c, "price": int(price), "change_rate": change_rate,
                "long_term_score": style.get("long_term_score", 0),
                "trend_6m": style.get("trend_6m", 0),
                "volatility": style.get("volatility", 0),
                "prediction": prediction,
                "per": 0, "pbr": 0,
            })
        except Exception:
            pass

    for c in US_LONGTERM:
        try:
            candles = us_hist.get(c["symbol"], [])
            if len(candles) < 20:
                continue
            price = candles[-1]["close"]
            prev = candles[-2]["close"] if len(candles) >= 2 else price
            change_rate = round((price - prev) / prev * 100, 2) if prev > 0 else 0.0
            indicators = calc_technical_indicators(candles)
            style = classify_investment_style(candles, indicators)
            prediction = predict_next_day(candles, indicators)
            results.append({
                **c, "price": round(price, 2), "change_rate": change_rate,
                "long_term_score": style.get("long_term_score", 0),
                "trend_6m": style.get("trend_6m", 0),
                "volatility": style.get("volatility", 0),
                "prediction": prediction,
                "per": 0, "pbr": 0,
            })
        except Exception:
            pass

    results.sort(key=lambda x: x.get("long_term_score", 0), reverse=True)
    return results


async def _build_shortterm_recommendations() -> list:
    """거래량 급증(국내) + 모멘텀 미국주 단기 추천"""
    # KIS에서 거래량 급증 목록 가져오기
    try:
        surge = await kis_client.get_volume_surge_kr()
        kr_candidates = surge[:20]
    except Exception:
        kr_candidates = []

    kr_yf_tickers = [f"{c['symbol']}.KS" for c in kr_candidates]
    us_yf_tickers = [c["symbol"] for c in US_SHORTTERM_EXTRA]

    kr_hist, us_hist = await asyncio.gather(
        asyncio.get_event_loop().run_in_executor(None, lambda: _batch_yf_history_sync(kr_yf_tickers, period="3mo")),
        asyncio.get_event_loop().run_in_executor(None, lambda: _batch_yf_history_sync(us_yf_tickers, period="3mo")),
    )

    results = []

    for c in kr_candidates:
        yf_key = f"{c['symbol']}.KS"
        try:
            candles = kr_hist.get(yf_key, [])
            if len(candles) < 20:
                # KOSDAQ fallback
                kq_key = f"{c['symbol']}.KQ"
                kq_hist = _batch_yf_history_sync([kq_key], period="3mo")
                candles = kq_hist.get(kq_key, [])
            if len(candles) < 20:
                continue
            # 현재가는 KIS 데이터 우선, 없으면 yfinance
            price = c.get("price", 0) or int(candles[-1]["close"])
            change_rate = c.get("change_rate", 0)
            indicators = calc_technical_indicators(candles)
            prediction = predict_next_day(candles, indicators)
            style = classify_investment_style(candles, indicators)
            results.append({
                "symbol": c["symbol"], "name": c["name"], "market": "KR",
                "price": price, "change_rate": change_rate,
                "volume": c.get("volume", 0),
                "volume_ratio": c.get("volume_ratio", 0),
                "indicators": {"rsi": indicators.get("rsi"), "macd_hist": indicators.get("macd_hist")},
                "prediction": prediction,
                "short_term_score": style.get("short_term_score", 0),
            })
        except Exception:
            pass

    for c in US_SHORTTERM_EXTRA:
        try:
            candles = us_hist.get(c["symbol"], [])
            if len(candles) < 20:
                continue
            price = round(candles[-1]["close"], 2)
            prev = candles[-2]["close"] if len(candles) >= 2 else price
            change_rate = round((price - prev) / prev * 100, 2) if prev > 0 else 0.0
            indicators = calc_technical_indicators(candles)
            prediction = predict_next_day(candles, indicators)
            style = classify_investment_style(candles, indicators)
            results.append({
                **c, "price": price, "change_rate": change_rate,
                "volume": candles[-1]["volume"],
                "volume_ratio": 0,
                "indicators": {"rsi": indicators.get("rsi"), "macd_hist": indicators.get("macd_hist")},
                "prediction": prediction,
                "short_term_score": style.get("short_term_score", 0),
            })
        except Exception:
            pass

    results.sort(key=lambda x: x.get("prediction", {}).get("probability", 0), reverse=True)
    return results


def _yf_screener_sync(yf_tickers: list, name_map: dict) -> list:
    """yfinance 배치로 스크리너 데이터 계산"""
    if not yf_tickers:
        return []
    try:
        data = yf.download(yf_tickers, period="6d", auto_adjust=True, progress=False, threads=True)
    except Exception:
        return []
    if data.empty:
        return []

    is_multi = isinstance(data.columns, pd.MultiIndex)
    results = []

    for sym in yf_tickers:
        try:
            if is_multi:
                if sym not in data.columns.get_level_values(1):
                    continue
                close = data["Close"][sym].dropna()
                volume = data["Volume"][sym].dropna()
            else:
                close = data["Close"].dropna()
                volume = data["Volume"].dropna()

            if len(close) < 2:
                continue
            curr = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            if curr <= 0 or prev <= 0:
                continue
            vol_today = int(volume.iloc[-1]) if len(volume) > 0 else 0
            vol_avg = int(volume.iloc[:-1].mean()) if len(volume) > 1 else 1
            volume_ratio = round(vol_today / vol_avg * 100, 1) if vol_avg > 0 else 0
            trading_value = int(curr * vol_today)
            change_rate = round((curr - prev) / prev * 100, 2)
            # Strip yfinance suffix for original symbol
            orig = sym.replace(".KS", "").replace(".KQ", "")
            results.append({
                "symbol": orig,
                "name": name_map.get(sym, orig),
                "price": int(curr) if ".KS" in sym or ".KQ" in sym else round(curr, 2),
                "change_rate": change_rate,
                "volume": vol_today,
                "volume_ratio": volume_ratio,
                "trading_value": trading_value,
                "trading_value_display": f"{trading_value // 100_000_000}억" if trading_value >= 100_000_000 else f"{trading_value // 1_000_000}백만",
                "market": "KR" if (".KS" in sym or ".KQ" in sym) else "US",
            })
        except Exception:
            pass

    return results


# ==================== ROUTES ====================

@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1),
    market: str = Query("ALL"),
):
    stocks = _load_stock_list()
    q_lower = q.lower()
    results = []
    for s in stocks:
        if market != "ALL" and s["market"] != market:
            continue
        if (q_lower in s["name"].lower()
                or q_lower in s.get("name_en", "").lower()
                or q_lower in s["symbol"].lower()):
            results.append(s)
    return results[:25]


@router.get("/test/kis")
async def test_kis_connection():
    try:
        token = await kis_client._get_token()
        return {"status": "ok", "token_preview": token[:20] + "..."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/kr/{symbol}")
async def get_kr_stock(symbol: str, current_user: User = Depends(get_current_user)):
    price = await kis_client.get_kr_stock_price(symbol)
    candles = await kis_client.get_kr_stock_history(symbol, count=120)
    indicators = calc_technical_indicators(candles)
    prediction = predict_next_day(candles, indicators)
    style = classify_investment_style(candles, indicators, price.get("per", 0), price.get("pbr", 0))
    news = await get_news_naver(symbol, market="KR")
    return {"price": price, "candles": candles, "indicators": indicators,
            "prediction": prediction, "style": style, "news": news}


@router.get("/us/{symbol}")
async def get_us_stock(
    symbol: str,
    exchange: str = Query("NAS"),
    current_user: User = Depends(get_current_user),
):
    price = await kis_client.get_us_stock_price(symbol, exchange)
    candles = await get_us_stock_history(symbol, period="6mo")
    indicators = calc_technical_indicators(candles)
    prediction = predict_next_day(candles, indicators)
    style = classify_investment_style(candles, indicators)
    news = await get_news_naver(symbol, name=symbol, market="US")
    return {"price": price, "candles": candles, "indicators": indicators,
            "prediction": prediction, "style": style, "news": news}


@router.get("/volume-surge")
async def get_volume_surge(current_user: User = Depends(get_current_user)):
    return await kis_client.get_volume_surge_kr()


@router.get("/recommendations/longterm")
async def get_longterm_recommendations(current_user: User = Depends(get_current_user)):
    cache = _rec_cache["longterm"]
    if cache["data"] and (time.time() - cache["ts"]) < _CACHE_TTL:
        return cache["data"]
    data = await _build_longterm_recommendations()
    cache["data"] = data
    cache["ts"] = time.time()
    return data


@router.get("/recommendations/shortterm")
async def get_shortterm_recommendations(current_user: User = Depends(get_current_user)):
    cache = _rec_cache["shortterm"]
    if cache["data"] and (time.time() - cache["ts"]) < _CACHE_TTL:
        return cache["data"]
    data = await _build_shortterm_recommendations()
    cache["data"] = data
    cache["ts"] = time.time()
    return data


@router.get("/screener/kr/{mode}")
async def screener_kr(
    mode: str,
    current_user: User = Depends(get_current_user),
):
    """국내 종목 스크리너: volume_surge | trading_value | gainers | losers"""
    if mode == "volume_surge":
        try:
            return await kis_client.get_volume_surge_kr()
        except Exception:
            pass
    elif mode == "trading_value":
        try:
            return await kis_client.get_trading_value_kr()
        except Exception:
            pass
    elif mode == "gainers":
        try:
            return await kis_client.get_gainers_kr()
        except Exception:
            pass
    elif mode == "losers":
        try:
            return await kis_client.get_losers_kr()
        except Exception:
            pass

    # yfinance fallback
    yf_tickers = [sym + sfx for sym, name, sfx in KR_SCREENER_STOCKS]
    name_map = {sym + sfx: name for sym, name, sfx in KR_SCREENER_STOCKS}

    def _fetch():
        rows = _yf_screener_sync(yf_tickers, name_map)
        if mode == "trading_value":
            rows.sort(key=lambda x: x.get("trading_value", 0), reverse=True)
        elif mode == "gainers":
            rows.sort(key=lambda x: x.get("change_rate", 0), reverse=True)
        elif mode == "losers":
            rows.sort(key=lambda x: x.get("change_rate", 0))
        else:
            rows.sort(key=lambda x: x.get("volume_ratio", 0), reverse=True)
        return rows[:30]

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


@router.get("/screener/us/{mode}")
async def screener_us(
    mode: str,
    current_user: User = Depends(get_current_user),
):
    """미국 종목 스크리너: volume_surge | trading_value | gainers | losers"""
    name_map = {
        "AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아",
        "GOOGL": "알파벳", "AMZN": "아마존", "META": "메타",
        "TSLA": "테슬라", "BRK-B": "버크셔해서웨이", "JPM": "JP모건",
        "V": "비자", "JNJ": "존슨앤존슨", "KO": "코카콜라",
        "WMT": "월마트", "XOM": "엑슨모빌", "ABBV": "애브비",
        "LLY": "일라이릴리", "PG": "P&G", "MRK": "머크",
        "HD": "홈디포", "AVGO": "브로드컴", "COST": "코스트코",
        "NFLX": "넷플릭스", "AMD": "AMD", "COIN": "코인베이스",
        "PLTR": "팔란티어", "MSTR": "마이크로스트래티지", "IONQ": "아이온큐",
        "SMCI": "슈퍼마이크로", "RIVN": "리비안", "SOFI": "소파이",
        "RKLB": "로켓랩", "BAC": "뱅크오브아메리카", "MA": "마스터카드",
        "CVX": "쉐브론", "INTC": "인텔", "QCOM": "퀄컴",
        "TXN": "텍사스인스트루먼트", "CRM": "세일즈포스", "ORCL": "오라클",
        "IBM": "IBM", "SPY": "S&P500 ETF", "QQQ": "나스닥100 ETF",
        "SOXL": "반도체 3배 ETF", "TQQQ": "나스닥 3배 ETF", "TLT": "미국 20년 국채",
        "GLD": "금 ETF", "SLV": "은 ETF", "ARKK": "ARK 혁신 ETF",
        "IWM": "러셀2000 ETF", "DIA": "다우존스 ETF",
    }

    def _fetch():
        rows = _yf_screener_sync(US_SCREENER_STOCKS, name_map)
        if mode == "trading_value":
            rows.sort(key=lambda x: x.get("trading_value", 0), reverse=True)
        elif mode == "gainers":
            rows.sort(key=lambda x: x.get("change_rate", 0), reverse=True)
        elif mode == "losers":
            rows.sort(key=lambda x: x.get("change_rate", 0))
        else:
            rows.sort(key=lambda x: x.get("volume_ratio", 0), reverse=True)
        return rows[:30]

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)
