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
    "dow": "^DJI",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "sox": "^SOX",
    "vix": "^VIX",
    "us10y": "^TNX",       # 미국 10년물 국채
    "dxy": "DX-Y.NYB",     # 달러인덱스
    "wti": "CL=F",         # WTI 원유
    "usdkrw": "KRW=X",     # 원달러 환율
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


async def get_index_data() -> dict:
    """주요 지수/매크로 데이터 조회"""
    def _fetch():
        results = {}
        for key, ticker in INDEX_TICKERS.items():
            try:
                t = yf.Ticker(ticker)
                info = t.fast_info
                hist = t.history(period="2d")
                if len(hist) >= 2:
                    prev_close = float(hist["Close"].iloc[-2])
                    curr_close = float(hist["Close"].iloc[-1])
                    change = curr_close - prev_close
                    change_rate = (change / prev_close) * 100
                else:
                    curr_close = float(info.last_price) if hasattr(info, 'last_price') else 0
                    change = 0
                    change_rate = 0

                results[key] = {
                    "ticker": ticker,
                    "price": round(curr_close, 2),
                    "change": round(change, 2),
                    "change_rate": round(change_rate, 2),
                }
            except Exception as e:
                results[key] = {"ticker": ticker, "price": 0, "change": 0, "change_rate": 0, "error": str(e)}
        return results

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def get_bigtech_data() -> list:
    """빅테크 종목 현재가"""
    def _fetch():
        results = []
        tickers = list(BIGTECH_TICKERS.keys())
        data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
        for symbol, name in BIGTECH_TICKERS.items():
            try:
                closes = data["Close"][symbol].dropna()
                if len(closes) >= 2:
                    prev = float(closes.iloc[-2])
                    curr = float(closes.iloc[-1])
                    change = curr - prev
                    change_rate = (change / prev) * 100
                else:
                    curr, change, change_rate = 0, 0, 0
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "price": round(curr, 2),
                    "change": round(change, 2),
                    "change_rate": round(change_rate, 2),
                })
            except Exception:
                results.append({"symbol": symbol, "name": name, "price": 0, "change": 0, "change_rate": 0})
        return results

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


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


async def get_news_naver(symbol: str, name: str = "", market: str = "KR") -> list:
    """네이버 금융 뉴스 스크래핑"""
    from bs4 import BeautifulSoup

    async def _fetch():
        results = []
        try:
            if market == "KR":
                url = f"https://finance.naver.com/item/news_news.naver?code={symbol}&page=1"
            else:
                query = name or symbol
                url = f"https://finance.naver.com/search/searchList.naver?query={query}&page=1"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
                resp = await client.get(url, timeout=10)
                soup = BeautifulSoup(resp.text, "lxml")

                if market == "KR":
                    rows = soup.select("table.type5 tbody tr")
                    for row in rows[:10]:
                        a_tag = row.select_one("td.title a")
                        date_td = row.select_one("td.date")
                        if a_tag and date_td:
                            results.append({
                                "title": a_tag.get_text(strip=True),
                                "url": "https://finance.naver.com" + a_tag.get("href", ""),
                                "date": date_td.get_text(strip=True),
                                "source": "네이버 금융",
                            })
                else:
                    items = soup.select("dl.newsList dd.articleSubject")
                    dates = soup.select("dl.newsList dd.articleDate")
                    for i, item in enumerate(items[:10]):
                        a_tag = item.select_one("a")
                        if a_tag:
                            results.append({
                                "title": a_tag.get_text(strip=True),
                                "url": "https://finance.naver.com" + a_tag.get("href", ""),
                                "date": dates[i].get_text(strip=True) if i < len(dates) else "",
                                "source": "네이버 금융",
                            })
        except Exception as e:
            results = [{"error": str(e)}]
        return results

    return await _fetch()


async def get_economic_calendar() -> list:
    """Finnhub 경제 캘린더"""
    if not settings.finnhub_api_key:
        return _get_mock_calendar()

    from datetime import timedelta
    today = datetime.now()
    from_date = today.strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=14)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://finnhub.io/api/v1/calendar/economic",
                params={"from": from_date, "to": to_date, "token": settings.finnhub_api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            events = []
            for e in (data.get("economicCalendar") or []):
                events.append({
                    "date": e.get("time", ""),
                    "event": e.get("event", ""),
                    "country": e.get("country", ""),
                    "actual": e.get("actual"),
                    "estimate": e.get("estimate"),
                    "prev": e.get("prev"),
                    "impact": e.get("impact", "low"),
                })
            return events
        except Exception:
            return _get_mock_calendar()


def _get_mock_calendar() -> list:
    """Finnhub 키 없을 때 주요 일정 (현재 날짜 기준 동적 생성)"""
    from datetime import timedelta
    today = datetime.now()

    def next_weekday(d, weekday):
        days_ahead = weekday - d.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return d + timedelta(days=days_ahead)

    def nth_weekday_of_month(year, month, weekday, n):
        import calendar
        first_day = datetime(year, month, 1)
        days_ahead = weekday - first_day.weekday()
        if days_ahead < 0:
            days_ahead += 7
        first_occurrence = first_day + timedelta(days=days_ahead)
        return first_occurrence + timedelta(weeks=n - 1)

    # 이번달 / 다음달 주요 일정 계산
    y, m = today.year, today.month
    next_m = m + 1 if m < 12 else 1
    next_y = y if m < 12 else y + 1

    events = []

    # 매월 첫째 금요일 - 미국 고용보고서
    for yr, mo in [(y, m), (next_y, next_m)]:
        d = nth_weekday_of_month(yr, mo, 4, 1)  # 4=금요일
        if d >= today:
            events.append({"date": d.strftime("%Y-%m-%d"), "event": "미국 고용보고서 (비농업)", "country": "US", "impact": "high", "estimate": None, "prev": None})

    # 매월 둘째 목요일 - 옵션만기일
    for yr, mo in [(y, m), (next_y, next_m)]:
        d = nth_weekday_of_month(yr, mo, 3, 2)  # 3=목요일
        if d >= today:
            events.append({"date": d.strftime("%Y-%m-%d"), "event": "옵션 만기일", "country": "KR", "impact": "medium", "estimate": None, "prev": None})

    # CPI - 보통 매월 10~15일 사이
    for yr, mo in [(y, m), (next_y, next_m)]:
        d = datetime(yr, mo, 12)
        if d >= today:
            events.append({"date": d.strftime("%Y-%m-%d"), "event": "미국 CPI (소비자물가)", "country": "US", "impact": "high", "estimate": None, "prev": None})

    # FOMC - 연 8회 (대략 6~7주 간격, 간략히 다음 예상일 표시)
    fomc_dates_2026 = ["2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17", "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16"]
    fomc_dates_2027 = ["2027-01-27", "2027-03-17", "2027-05-05", "2027-06-16"]
    for ds in fomc_dates_2026 + fomc_dates_2027:
        d = datetime.strptime(ds, "%Y-%m-%d")
        if today <= d <= today + timedelta(days=90):
            events.append({"date": ds, "event": "FOMC 금리결정", "country": "US", "impact": "high", "estimate": None, "prev": None})

    # 한국은행 금통위
    bok_dates_2026 = ["2026-01-16", "2026-02-27", "2026-04-17", "2026-05-29", "2026-07-17", "2026-08-28", "2026-10-16", "2026-11-27"]
    for ds in bok_dates_2026:
        d = datetime.strptime(ds, "%Y-%m-%d")
        if today <= d <= today + timedelta(days=90):
            events.append({"date": ds, "event": "한국은행 금통위", "country": "KR", "impact": "high", "estimate": None, "prev": None})

    events.sort(key=lambda x: x["date"])
    return events[:10]
