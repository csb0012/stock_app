from fastapi import APIRouter, Depends, Query, HTTPException
import yfinance as yf
import asyncio
import time

from app.api.routes.auth import get_current_user
from app.models.user import User
from app.services.kis_api import kis_client, KISError
from app.services import stock_master
from app.services.quote import (analyze_kr, analyze_kr_many, analyze_us_many, strip_candles,
                                live_prices, patch_candles, analyze_candles)
from app.services.news import get_news_many
from app.services import prediction_log
from app.services.market_data import get_news_naver

router = APIRouter(prefix="/stocks", tags=["stocks"])

# --- 추천 캐시 (15분 TTL) ---
_rec_cache: dict = {
    "longterm": {"data": None, "ts": 0.0},
    "shortterm": {"data": None, "ts": 0.0},
}
_CACHE_TTL = 900.0

# --- 스크리너 캐시 (1분 TTL) — 1분마다 화면이 갱신되므로 KIS 호출 수 절약 ---
_screener_cache: dict = {}
_SCREENER_TTL = 60.0

# --- 추천 후보 종목 목록 ---
KR_LONGTERM = [
    {"symbol": "005930", "name": "삼성전자",        "market": "KR"},
    {"symbol": "000660", "name": "SK하이닉스",       "market": "KR"},
    {"symbol": "051910", "name": "LG화학",           "market": "KR"},
    {"symbol": "035420", "name": "NAVER",            "market": "KR"},
    {"symbol": "005380", "name": "현대자동차",        "market": "KR"},
    {"symbol": "068270", "name": "셀트리온",          "market": "KR"},
    {"symbol": "035720", "name": "카카오",            "market": "KR"},
    {"symbol": "006400", "name": "삼성SDI",          "market": "KR"},
    {"symbol": "066570", "name": "LG전자",           "market": "KR"},
    {"symbol": "017670", "name": "SK텔레콤",         "market": "KR"},
    {"symbol": "030200", "name": "KT",               "market": "KR"},
    {"symbol": "009150", "name": "삼성전기",          "market": "KR"},
    {"symbol": "000270", "name": "기아",              "market": "KR"},
    {"symbol": "207940", "name": "삼성바이오로직스",   "market": "KR"},
    {"symbol": "096770", "name": "SK이노베이션",      "market": "KR"},
    {"symbol": "028260", "name": "삼성물산",          "market": "KR"},
    {"symbol": "018260", "name": "삼성에스디에스",     "market": "KR"},
    {"symbol": "010130", "name": "고려아연",          "market": "KR"},
    {"symbol": "032830", "name": "삼성생명",          "market": "KR"},
    {"symbol": "034020", "name": "두산에너빌리티",    "market": "KR"},
    {"symbol": "005490", "name": "POSCO홀딩스",      "market": "KR"},
    {"symbol": "055550", "name": "신한지주",          "market": "KR"},
    {"symbol": "105560", "name": "KB금융",            "market": "KR"},
    {"symbol": "086790", "name": "하나금융지주",      "market": "KR"},
    {"symbol": "003490", "name": "대한항공",          "market": "KR"},
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


def _fail(e: Exception):
    """KIS/yfinance 오류를 그대로 화면에 전달 (빈 목록으로 숨기지 않음)"""
    raise HTTPException(status_code=502, detail=str(e))


def _rec_row(r: dict, extra: dict) -> dict:
    return {
        "symbol": r["symbol"], "name": r["name"], "market": r["market"],
        "exchange": r.get("exchange"), "category": r.get("category", "stock"),
        "price": r["price"], "change_rate": r["change_rate"],
        "per": r.get("per", 0), "pbr": r.get("pbr", 0),
        "prediction": r["prediction"],
        "news": r.get("news"),
        "long_term_score": r["style"].get("long_term_score", 0),
        "short_term_score": r["style"].get("short_term_score", 0),
        "trend_6m": r["style"].get("trend_6m", 0),
        "volatility": r["style"].get("volatility", 0),
        "indicators": {"rsi": r["indicators"].get("rsi"), "macd_hist": r["indicators"].get("macd_hist")},
        **extra,
    }


async def _build_longterm() -> dict:
    kr, us = await asyncio.gather(
        analyze_kr_many([c["symbol"] for c in KR_LONGTERM], count=130),
        analyze_us_many([c["symbol"] for c in US_LONGTERM], period="6mo"),
    )
    return {"raw": {**kr, **us}, "extra": {}}


async def _build_shortterm() -> dict:
    surge = (await kis_client.get_volume_surge_kr())[:30]
    extra = {c["symbol"]: {"volume": c["volume"], "volume_ratio": c["volume_ratio"]} for c in surge}
    kr, us = await asyncio.gather(
        analyze_kr_many([c["symbol"] for c in surge], count=100),
        analyze_us_many([c["symbol"] for c in US_SHORTTERM_EXTRA], period="3mo"),
    )
    return {"raw": {**kr, **us}, "extra": extra}


_BUILDERS = {"longterm": _build_longterm, "shortterm": _build_shortterm}
_LIVE_TTL = 10.0
_build_locks = {k: asyncio.Lock() for k in _BUILDERS}


async def _base(kind: str) -> dict:
    """일봉·뉴스 등 무거운 데이터 (15분 캐시)"""
    cache = _rec_cache[kind]
    async with _build_locks[kind]:
        if cache["data"] and (time.time() - cache["ts"]) < _CACHE_TTL:
            return cache["data"]
        try:
            data = await _BUILDERS[kind]()
        except Exception as e:
            _fail(e)
        ok = [r for r in data["raw"].values() if "error" not in r]
        if not ok:
            errs = "; ".join(f"{r['symbol']}: {r['error']}" for r in list(data["raw"].values())[:3])
            _fail(RuntimeError("추천 분석 실패: " + errs))
        cache["data"], cache["ts"] = data, time.time()
        cache["live"] = None
        return data


def _rows_from(raw: dict, extra: dict, kind: str) -> dict:
    rows, errors = [], []
    for sym, r in raw.items():
        if "error" in r:
            errors.append({"market": r.get("market"), "symbol": sym, "error": r["error"]})
        else:
            rows.append(_rec_row(r, extra.get(sym, {})))
    key = (lambda x: x["long_term_score"]) if kind == "longterm" else (lambda x: x["prediction"].get("probability", 0))
    rows.sort(key=key, reverse=True)
    return {"items": rows, "errors": errors}


async def _live(kind: str) -> dict:
    """현재가 + 뉴스(10분 캐시)로 상승 확률을 다시 계산 (10초 캐시)"""
    base = await _base(kind)
    cache = _rec_cache[kind]
    live = cache.get("live")
    if live and time.time() - live["ts"] < _LIVE_TTL:
        return live["data"]

    ok = {s: r for s, r in base["raw"].items() if "error" not in r}
    keys = [(r["market"], s) for s, r in ok.items()]
    prices, news = await asyncio.gather(
        live_prices([{"market": m, "symbol": s} for m, s in keys]),
        get_news_many(keys),
    )

    def recompute():
        out = {}
        for s, r in base["raw"].items():
            if "error" in r:
                out[s] = r
                continue
            lp = prices.get((r["market"], s), {})
            candles = patch_candles(r["market"], r["candles"], lp) if "price" in lp else r["candles"]
            prev = candles[-2]["close"] if len(candles) >= 2 else candles[-1]["close"]
            price = lp.get("price", r["price"])
            change = lp.get("change_rate")
            if change is None:
                change = round((price / prev - 1) * 100, 2) if prev else 0.0
            n = news.get((r["market"], s))
            out[s] = {**r, "price": price, "change_rate": change, "candles": candles,
                      "news": n and {k: n.get(k) for k in ("total", "pos", "neg", "error")} | {"headlines": n.get("headlines", [])[:5]},
                      "live_error": lp.get("error"),
                      **analyze_candles(r["market"], candles, r.get("per", 0), r.get("pbr", 0), n)}
        return out

    raw = await asyncio.get_event_loop().run_in_executor(None, recompute)
    data = _rows_from(raw, base["extra"], kind)

    prev_probs = {(x["market"], x["symbol"]): x["prediction"]["probability"] for x in (live["data"]["items"] if live else [])}
    for x in data["items"]:
        x["prev_probability"] = prev_probs.get((x["market"], x["symbol"]))
    data["updated_at"] = time.strftime("%H:%M:%S")
    data["live_errors"] = sorted({r["live_error"] for r in raw.values() if r.get("live_error")})[:3]
    cache["live"] = {"ts": time.time(), "data": data}

    await prediction_log.record(list(raw.values()), "AI추천")
    return data


# ---------- 미국 스크리너 (Yahoo 전체 시장 스크리너) ----------

def _us_screener_sync(mode: str) -> list:
    query = {"gainers": "day_gainers", "losers": "day_losers"}.get(mode, "most_actives")
    resp = yf.screen(query, count=200)
    quotes = (resp or {}).get("quotes") or []
    if not quotes:
        raise RuntimeError(f"Yahoo 스크리너({query}) 결과 없음")
    rows = []
    for q in quotes:
        sym = q.get("symbol")
        price = q.get("regularMarketPrice")
        if not sym or not price:
            continue
        vol = int(q.get("regularMarketVolume") or 0)
        avg = int(q.get("averageDailyVolume3Month") or 0)
        tv = int(price * vol)
        master = stock_master.get("US", sym) or {}
        rows.append({
            "symbol": sym,
            "name": master.get("name") or q.get("shortName") or q.get("longName") or sym,
            "market": "US",
            "price": round(float(price), 2),
            "change_rate": round(float(q.get("regularMarketChangePercent") or 0), 2),
            "volume": vol,
            "volume_ratio": round((vol / avg - 1) * 100, 1) if avg > 0 else 0,  # 3개월 평균 대비 증가율(%)
            "trading_value": tv,
            "trading_value_display": f"${tv / 1e9:.2f}B" if tv >= 1e9 else f"${tv / 1e6:.0f}M",
        })
    if mode == "trading_value":
        rows.sort(key=lambda x: x["trading_value"], reverse=True)
    elif mode == "gainers":
        rows.sort(key=lambda x: x["change_rate"], reverse=True)
    elif mode == "losers":
        rows.sort(key=lambda x: x["change_rate"])
    else:
        rows.sort(key=lambda x: x["volume_ratio"], reverse=True)
    return rows


_MODES = ("volume_surge", "trading_value", "gainers", "losers")


async def _cached_screener(key: str, fn):
    hit = _screener_cache.get(key)
    if hit and time.time() - hit["ts"] < _SCREENER_TTL:
        return hit["data"]
    try:
        data = await fn()
    except Exception as e:
        _fail(e)
    _screener_cache[key] = {"data": data, "ts": time.time()}
    return data


# ==================== ROUTES ====================

@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1),
    market: str = Query("ALL"),
    limit: int = Query(30, le=100),
):
    """종목 검색 — KIS 공식 종목마스터 (국내 주식·ETF·ETN 전체 + 미국 NAS/NYS/AMS)"""
    try:
        await stock_master.load()
    except Exception as e:
        _fail(e)
    return stock_master.search(q, market, limit)


@router.get("/test/kis")
async def test_kis_connection():
    try:
        token = await kis_client._get_token()
        return {"status": "ok", "token_preview": token[:20] + "..."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/quote/{market}/{symbol}")
async def get_quote(market: str, symbol: str, current_user: User = Depends(get_current_user)):
    """종목 1개 시세 + 내일 전망 (종목탐색 검색 결과용)"""
    market = market.upper()
    try:
        if market == "KR":
            r = await analyze_kr(symbol)
        elif market == "US":
            r = (await analyze_us_many([symbol]))[symbol]
            if "error" in r:
                raise RuntimeError(r["error"])
        else:
            raise HTTPException(status_code=400, detail="market 은 KR 또는 US")
    except HTTPException:
        raise
    except Exception as e:
        _fail(e)
    await prediction_log.record([r], "검색")
    return strip_candles(r)


@router.get("/kr/{symbol}")
async def get_kr_stock(symbol: str, current_user: User = Depends(get_current_user)):
    try:
        price, r = await asyncio.gather(kis_client.get_kr_stock_price(symbol), analyze_kr(symbol))
    except KISError as e:
        _fail(e)
    news = await get_news_naver(symbol, market="KR")
    return {"price": price, "candles": r["candles"], "indicators": r["indicators"],
            "prediction": r["prediction"], "style": r["style"], "news": news}


@router.get("/us/{symbol}")
async def get_us_stock(
    symbol: str,
    exchange: str = Query("NAS"),
    current_user: User = Depends(get_current_user),
):
    try:
        price = await kis_client.get_us_stock_price(symbol, exchange)
    except KISError as e:
        _fail(e)
    r = (await analyze_us_many([symbol]))[symbol]
    if "error" in r:
        _fail(RuntimeError(r["error"]))
    news = await get_news_naver(symbol, name=symbol, market="US")
    return {"price": price, "candles": r["candles"], "indicators": r["indicators"],
            "prediction": r["prediction"], "style": r["style"], "news": news}


@router.get("/volume-surge")
async def get_volume_surge(current_user: User = Depends(get_current_user)):
    try:
        return await kis_client.get_volume_surge_kr()
    except KISError as e:
        _fail(e)


@router.get("/recommendations/{kind}")
async def get_recommendations(kind: str, current_user: User = Depends(get_current_user)):
    """AI 추천 (kind: longterm | shortterm) — 호출할 때마다 현재가·뉴스로 상승 확률 재계산 (10초 캐시)"""
    if kind not in _BUILDERS:
        raise HTTPException(status_code=404, detail="kind 는 longterm 또는 shortterm")
    try:
        return await _live(kind)
    except HTTPException:
        raise
    except Exception as e:
        _fail(e)


@router.get("/screener/kr/{mode}")
async def screener_kr(mode: str, current_user: User = Depends(get_current_user)):
    """국내 스크리너 (KIS 순위 API, KOSPI+KOSDAQ 합산 최대 60종목)"""
    if mode not in _MODES:
        raise HTTPException(status_code=400, detail=f"mode 는 {_MODES} 중 하나")
    fn = {
        "volume_surge": kis_client.get_volume_surge_kr,
        "trading_value": kis_client.get_trading_value_kr,
        "gainers": kis_client.get_gainers_kr,
        "losers": kis_client.get_losers_kr,
    }[mode]
    return await _cached_screener(f"kr:{mode}", fn)


@router.get("/screener/us/{mode}")
async def screener_us(mode: str, current_user: User = Depends(get_current_user)):
    """미국 스크리너 (Yahoo 전체 시장 스크리너, 최대 200종목)"""
    if mode not in _MODES:
        raise HTTPException(status_code=400, detail=f"mode 는 {_MODES} 중 하나")

    async def fn():
        return await asyncio.get_event_loop().run_in_executor(None, lambda: _us_screener_sync(mode))
    return await _cached_screener(f"us:{mode}", fn)
