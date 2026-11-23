"""미국 거시경제 데이터 (yfinance, FRED 등 무료 소스)"""
import yfinance as yf
import asyncio
from datetime import datetime
from typing import Optional
from functools import lru_cache
import httpx
from app.core.config import settings

# 주요 티커 매핑
INDEX_TICKERS = {
    "kospi": "^KS11",      # 코스피
    "kosdaq": "^KQ11",     # 코스닥
    "dow": "^DJI",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "sox": "^SOX",
    "vix": "^VIX",
    "us10y": "^TNX",
    "dxy": "DX-Y.NYB",
    "wti": "CL=F",
    "usdkrw": "KRW=X",
}

BIGTECH_TICKERS = {
    "NVDA": "엔비디아",
    "AAPL": "애플",
    "TSLA": "테슬라",
    "MSFT": "마이크로소프트",
    "AMZN": "아마존",
    "META": "메타",
    "GOOGL": "구글",
}

US_ETF_TICKERS = {
    "SPY": "S&P500 ETF",
    "QQQ": "나스닥100 ETF",
    "SOXL": "반도체 3배 (SOXL)",
    "TQQQ": "나스닥 3배 (TQQQ)",
    "TLT": "미국 20년 국채",
}


# 국내 지수는 KIS 공식 실시간 지수 (Yahoo 의 ^KS11·^KQ11 은 하루 늦게 갱신되는 경우가 있어 쓰지 않음)
KIS_INDEX = {"kospi": ("0001", "^KS11"), "kosdaq": ("1001", "^KQ11")}
# 24시간 거래(환율·원유)는 거래일 개념이 없어 날짜 지연 검사를 하지 않음
_NO_SESSION = {"usdkrw", "wti", "dxy"}


def _yf_closes(data, ticker):
    """yf.download 결과에서 한 종목의 종가 시리즈"""
    try:
        return data["Close"][ticker].dropna()
    except KeyError:
        return data["Close"].dropna() if "Close" in data else None


def _daily_item(closes, expect_date=None) -> dict:
    """마지막 두 종가로 등락 계산 + 기준일. expect_date 보다 오래된 날짜면 stale 표시"""
    if closes is None or len(closes) < 2:
        raise ValueError("데이터 부족")
    prev_close, curr_close = float(closes.iloc[-2]), float(closes.iloc[-1])
    as_of = closes.index[-1].date()
    item = {
        "price": round(curr_close, 2),
        "change": round(curr_close - prev_close, 2),
        "change_rate": round((curr_close - prev_close) / prev_close * 100, 2),
        "as_of": as_of.isoformat(),
        "source": "Yahoo Finance",
    }
    if expect_date and as_of < expect_date:
        item["stale"] = f"Yahoo 데이터가 {as_of.month}/{as_of.day} 기준 — 최신 거래일({expect_date.month}/{expect_date.day}) 아님"
    return item


def _global_indices_sync() -> dict:
    """해외 지수·매크로 (Yahoo Finance 일봉 5일)"""
    from app.services.market_calendar import last_session_date
    us_day = last_session_date("US")
    keys = [k for k in INDEX_TICKERS if k not in KIS_INDEX]
    data = yf.download([INDEX_TICKERS[k] for k in keys], period="5d", progress=False, auto_adjust=True, threads=True)
    results = {}
    for key in keys:
        ticker = INDEX_TICKERS[key]
        try:
            item = _daily_item(_yf_closes(data, ticker), None if key in _NO_SESSION else us_day)
            results[key] = {"ticker": ticker, **item}
        except Exception as e:
            results[key] = {"ticker": ticker, "price": 0, "change": 0, "change_rate": 0, "error": str(e)}
    return results


async def get_global_indices() -> dict:
    return await asyncio.get_event_loop().run_in_executor(None, _global_indices_sync)


async def get_kr_indices() -> dict:
    """코스피·코스닥 = KIS 실시간 업종지수 (실패하면 Yahoo 로 대체하지 않고 오류 표시)"""
    from app.services.kis_api import kis_client
    from app.services.market_calendar import last_session_date
    kr_day = last_session_date("KR")

    async def kr(key, code):
        try:
            v = await kis_client.get_kr_index(code)
            return key, {"ticker": KIS_INDEX[key][1], **v, "as_of": kr_day.isoformat(), "source": "KIS 실시간"}
        except Exception as e:
            return key, {"ticker": KIS_INDEX[key][1], "price": 0, "change": 0, "change_rate": 0,
                         "error": f"KIS 지수 조회 실패: {e}"}

    return dict(await asyncio.gather(*[kr(k, code) for k, (code, _) in KIS_INDEX.items()]))


async def get_index_data() -> dict:
    """주요 지수/매크로: 국내 지수 = KIS 실시간, 나머지 = Yahoo Finance(yfinance) 일봉 (화면 순서대로)"""
    kr, gl = await asyncio.gather(get_kr_indices(), get_global_indices())
    return {key: kr[key] if key in KIS_INDEX else gl[key] for key in INDEX_TICKERS}


def _extended_prices(tickers: list) -> dict:
    """미국 시간외(프리마켓·애프터마켓) 마지막 가격 — 5분봉 prepost. 정규장 시간이면 빈 값"""
    from zoneinfo import ZoneInfo
    try:
        data = yf.download(tickers, period="1d", interval="5m", prepost=True, progress=False, auto_adjust=False)
    except Exception as e:
        return {"_error": str(e)}
    out = {}
    ny = ZoneInfo("America/New_York")
    for t in tickers:
        s = _yf_closes(data, t)
        if s is None or s.empty:
            continue
        ts = s.index[-1]
        ts = ts.tz_convert(ny) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(ny)
        hm = ts.hour * 60 + ts.minute
        if hm >= 16 * 60 or hm < 9 * 60 + 30:
            out[t] = {"price": round(float(s.iloc[-1]), 2), "label": "애프터마켓" if hm >= 16 * 60 else "프리마켓",
                      "time": ts.strftime("%m/%d %H:%M") + " ET"}
    return out


def _us_rows(names: dict) -> list:
    """미국 종목: 정규장 종가(기준일) + 시간외 가격"""
    from app.services.market_calendar import last_session_date
    us_day = last_session_date("US")
    tickers = list(names)
    # 일봉과 시간외 5분봉을 동시에 받음 (순서대로 받으면 두 배 걸림)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as pool:
        f_daily = pool.submit(yf.download, tickers, period="5d", progress=False, auto_adjust=True)
        f_ext = pool.submit(_extended_prices, tickers)
        data, ext = f_daily.result(), f_ext.result()
    results = []
    for symbol, name in names.items():
        row = {"symbol": symbol, "name": name}
        try:
            row.update(_daily_item(_yf_closes(data, symbol), us_day))
        except Exception as e:
            row.update({"price": 0, "change": 0, "change_rate": 0, "error": str(e)})
        x = ext.get(symbol)
        if x and row.get("price"):
            row["ext"] = {**x, "change_rate": round((x["price"] / row["price"] - 1) * 100, 2)}
        if "_error" in ext:
            row["ext_error"] = ext["_error"]
        results.append(row)
    return results


async def get_bigtech_data() -> list:
    """빅테크: 정규장 종가 + 시간외 (Yahoo Finance)"""
    return await asyncio.get_event_loop().run_in_executor(None, _us_rows, BIGTECH_TICKERS)


async def get_us_etf_data() -> list:
    """주요 미국 ETF: 정규장 종가 + 시간외 (Yahoo Finance)"""
    return await asyncio.get_event_loop().run_in_executor(None, _us_rows, US_ETF_TICKERS)


async def get_us_stock_history(symbol: str, period: str = "6mo") -> list:
    """미국 개별 종목 차트 데이터"""
    def _fetch():
        t = yf.Ticker(symbol)
        hist = t.history(period=period)
        candles = []
        for idx, row in hist.iterrows():
            candles.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return candles

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


# FRED 발표 일정에서 고를 주요 지표 (FRED 의 release_name 그대로 비교 — 이름이 다르면 그 지표는 그냥 안 보임)
FRED_RELEASES = {
    "consumer price index": ("미국 CPI (소비자물가)", "high"),
    "employment situation": ("미국 고용보고서 (비농업)", "high"),
    "gross domestic product": ("미국 GDP", "high"),
    "personal income and outlays": ("미국 PCE (개인소비지출)", "high"),
    "fomc press release": ("FOMC 금리결정", "high"),
    "producer price index": ("미국 PPI (생산자물가)", "medium"),
    "advance monthly sales for retail and food services": ("미국 소매판매", "medium"),
    "job openings and labor turnover survey": ("JOLTS 구인건수", "medium"),
    "unemployment insurance weekly claims report": ("미국 신규 실업수당 청구", "medium"),
    "surveys of consumers": ("미시간대 소비자심리", "low"),
}


def _result(actual, estimate):
    """발표치 vs 예상치 (둘 다 숫자일 때만)"""
    try:
        a, e = float(actual), float(estimate)
    except (TypeError, ValueError):
        return None
    return "예상 상회" if a > e else "예상 하회" if a < e else "예상 부합"


async def _finnhub_calendar(start: str, end: str) -> list:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://finnhub.io/api/v1/calendar/economic",
                                params={"from": start, "to": end, "token": settings.finnhub_api_key})
    if resp.status_code in (401, 403):
        raise RuntimeError(f"HTTP {resp.status_code} — 경제 캘린더는 Finnhub 유료 기능일 수 있음 ({resp.text[:80]})")
    resp.raise_for_status()
    events = []
    for e in (resp.json().get("economicCalendar") or []):
        events.append({
            "date": e.get("time", ""), "event": e.get("event", ""), "country": e.get("country", ""),
            "actual": e.get("actual"), "estimate": e.get("estimate"), "prev": e.get("prev"),
            "impact": e.get("impact", "low"), "result": _result(e.get("actual"), e.get("estimate")),
        })
    return events


async def _fred_calendar(start: str, end: str) -> list:
    """FRED 발표 일정 (실제 공식 일정, 예상치·발표치는 없음)"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://api.stlouisfed.org/fred/releases/dates", params={
            "api_key": settings.fred_api_key, "file_type": "json", "realtime_start": start, "realtime_end": end,
            "include_release_dates_with_no_data": "true", "limit": 1000, "sort_order": "asc",
        })
    resp.raise_for_status()
    seen, events = set(), []
    for r in resp.json().get("release_dates") or []:
        key = (r.get("release_name") or "").strip().lower()
        if key not in FRED_RELEASES or (key, r.get("date")) in seen:
            continue
        seen.add((key, r.get("date")))
        name, impact = FRED_RELEASES[key]
        events.append({"date": r.get("date", ""), "event": name, "country": "US", "impact": impact,
                       "actual": None, "estimate": None, "prev": None, "result": None})
    return events


async def get_economic_calendar() -> dict:
    """경제 캘린더 (최근 2주 + 앞으로 4주): Finnhub → 안 되면 FRED 공식 발표 일정. 둘 다 안 되면 오류.
    (예전엔 실패하면 손으로 적은 가짜 일정·가짜 발표치를 보여줬음 → 삭제)"""
    from datetime import timedelta
    today = datetime.now().date()
    start, end = (today - timedelta(days=14)).isoformat(), (today + timedelta(days=28)).isoformat()
    errors = []
    if settings.finnhub_api_key:
        try:
            return {"source": "Finnhub", "events": await _finnhub_calendar(start, end), "errors": []}
        except Exception as e:
            errors.append(f"Finnhub: {e}")
    else:
        errors.append("Finnhub: FINNHUB_API_KEY 없음")
    if settings.fred_api_key:
        try:
            return {"source": "FRED 공식 발표 일정 (예상치·발표치 없음)", "events": await _fred_calendar(start, end),
                    "errors": errors}
        except Exception as e:
            errors.append(f"FRED: {e}")
    else:
        errors.append("FRED: FRED_API_KEY 없음")
    raise RuntimeError(" / ".join(errors))
