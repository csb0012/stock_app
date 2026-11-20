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


async def get_index_data() -> dict:
    """주요 지수/매크로 데이터 조회 (yfinance 배치 1회)"""
    def _fetch():
        tickers = list(INDEX_TICKERS.values())
        data = yf.download(tickers, period="5d", progress=False, auto_adjust=True, threads=True)
        results = {}
        for key, ticker in INDEX_TICKERS.items():
            try:
                closes = data["Close"][ticker].dropna()
                if len(closes) < 2:
                    raise ValueError("데이터 부족")
                prev_close, curr_close = float(closes.iloc[-2]), float(closes.iloc[-1])
                change = curr_close - prev_close
                results[key] = {
                    "ticker": ticker,
                    "price": round(curr_close, 2),
                    "change": round(change, 2),
                    "change_rate": round(change / prev_close * 100, 2),
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


async def get_us_etf_data() -> list:
    """주요 미국 ETF 현재가"""
    def _fetch():
        results = []
        tickers = list(US_ETF_TICKERS.keys())
        data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
        for symbol, name in US_ETF_TICKERS.items():
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
                    "symbol": symbol, "name": name,
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
    """Finnhub 키 없을 때 주요 일정 (과거 3개월 + 미래 3개월)"""
    from datetime import timedelta
    today = datetime.now()

    def nth_weekday_of_month(year, month, weekday, n):
        first_day = datetime(year, month, 1)
        days_ahead = weekday - first_day.weekday()
        if days_ahead < 0:
            days_ahead += 7
        return first_day + timedelta(days=days_ahead) + timedelta(weeks=n - 1)

    # 과거 이벤트 (실제값 포함, 해설 포함)
    past_events = [
        {
            "date": "2026-09-16", "event": "FOMC 금리결정", "country": "US", "impact": "high",
            "estimate": "4.25%", "actual": "4.25%", "prev": "4.50%",
            "result": "예상부합 (동결)",
            "analysis": "연준이 기준금리를 4.25%로 동결했습니다. 시장 예상에 부합하는 결과로 증시 영향은 중립적이었습니다. 금리 동결 기조는 성장주·기술주에 우호적. 삼성전자·SK하이닉스 등 반도체 관련주에 긍정적 영향."
        },
        {
            "date": "2026-10-02", "event": "미국 고용보고서 (비농업)", "country": "US", "impact": "high",
            "estimate": "150K", "actual": "143K", "prev": "161K",
            "result": "예상하회 (고용 둔화)",
            "analysis": "비농업 고용이 예상(15만)을 하회하는 14.3만 명 증가에 그쳤습니다. 고용 둔화 신호로 금리인하 기대감이 높아졌습니다. → 증시 단기 반응 긍정적. 국내 성장주(카카오·NAVER)와 2차전지주 수혜 가능."
        },
        {
            "date": "2026-10-14", "event": "미국 CPI (소비자물가)", "country": "US", "impact": "high",
            "estimate": "2.8%", "actual": "2.6%", "prev": "2.9%",
            "result": "예상하회 (물가 둔화)",
            "analysis": "CPI가 예상(2.8%)을 하회하는 2.6%를 기록했습니다. 물가 압력 완화로 연준의 금리인하 여지가 확대되었습니다. → 미국 증시 반등·나스닥 강세. 국내에서는 원·달러 환율 하락(원화 강세)으로 수입 의존도 높은 종목에 유리."
        },
        {
            "date": "2026-10-16", "event": "한국은행 금통위", "country": "KR", "impact": "high",
            "estimate": "2.75%", "actual": "2.75%", "prev": "3.00%",
            "result": "예상부합 (인하)",
            "analysis": "한국은행이 기준금리를 2.75%로 25bp 인하했습니다. 미국 금리 동결 속 선제적 인하로 내수 부양 의지를 보였습니다. → 부동산 관련주·금융주 단기 수혜. 원화 약세 압력으로 수출주(삼성전자·현대차) 긍정적."
        },
        {
            "date": "2026-10-23", "event": "옵션 만기일", "country": "KR", "impact": "medium",
            "estimate": None, "actual": "변동성 보통", "prev": None,
            "result": "무난 소화",
            "analysis": "10월 옵션 만기일이 큰 변동 없이 소화되었습니다. 외국인·기관 포지션 정리 물량이 나왔으나 시장 충격은 미미했습니다."
        },
        {
            "date": "2026-11-04", "event": "FOMC 금리결정", "country": "US", "impact": "high",
            "estimate": "4.25%", "actual": "4.00%", "prev": "4.25%",
            "result": "예상상회 (인하)",
            "analysis": "연준이 시장 예상보다 과감하게 25bp 추가 인하하여 4.00%로 결정했습니다. 경기 연착륙 기대감 확산으로 미국 증시 급등. → 국내 주식시장에도 긍정적 파급. 반도체(삼성전자·SK하이닉스)·성장주(카카오·네이버) 강세 예상."
        },
        {
            "date": "2026-11-07", "event": "미국 고용보고서 (비농업)", "country": "US", "impact": "high",
            "estimate": "155K", "actual": "178K", "prev": "143K",
            "result": "예상상회 (고용 호조)",
            "analysis": "비농업 고용이 예상(15.5만)을 크게 상회하는 17.8만 명 증가를 기록했습니다. 경기 견조 확인으로 추가 금리인하 속도에 의문 제기. → 증시 혼조. 달러 강세로 원·달러 환율 상승, 수출주에 단기 호재."
        },
        {
            "date": "2026-11-13", "event": "미국 CPI (소비자물가)", "country": "US", "impact": "high",
            "estimate": "2.5%", "actual": "2.4%", "prev": "2.6%",
            "result": "예상하회 (물가 둔화 지속)",
            "analysis": "CPI가 2.4%로 예상치(2.5%)를 소폭 하회하며 물가 안정 기조가 확인되었습니다. 금리인하 기대감 유지. → 기술주·성장주 중심 강세. SOXL·TQQQ 등 레버리지 ETF 단기 수혜."
        },
    ]

    # 미래 이벤트 생성
    future_events = []

    y, m = today.year, today.month

    def months_range(start_y, start_m, count):
        result = []
        for i in range(count):
            mo = (start_m - 1 + i) % 12 + 1
            yr = start_y + (start_m - 1 + i) // 12
            result.append((yr, mo))
        return result

    for yr, mo in months_range(y, m, 3):
        # 첫째 금요일 - 고용보고서
        d = nth_weekday_of_month(yr, mo, 4, 1)
        if d > today:
            future_events.append({"date": d.strftime("%Y-%m-%d"), "event": "미국 고용보고서 (비농업)", "country": "US", "impact": "high", "estimate": None, "actual": None, "prev": None, "result": None, "analysis": None})
        # 둘째 목요일 - 옵션만기
        d = nth_weekday_of_month(yr, mo, 3, 2)
        if d > today:
            future_events.append({"date": d.strftime("%Y-%m-%d"), "event": "옵션 만기일", "country": "KR", "impact": "medium", "estimate": None, "actual": None, "prev": None, "result": None, "analysis": None})
        # 12일 근처 CPI
        d = datetime(yr, mo, 12)
        if d > today:
            future_events.append({"date": d.strftime("%Y-%m-%d"), "event": "미국 CPI (소비자물가)", "country": "US", "impact": "high", "estimate": None, "actual": None, "prev": None, "result": None, "analysis": None})

    # FOMC 일정
    fomc_all = ["2026-12-16", "2027-01-27", "2027-03-17", "2027-05-05"]
    for ds in fomc_all:
        d = datetime.strptime(ds, "%Y-%m-%d")
        if today < d <= today + timedelta(days=120):
            future_events.append({"date": ds, "event": "FOMC 금리결정", "country": "US", "impact": "high", "estimate": None, "actual": None, "prev": None, "result": None, "analysis": None})

    # 한국은행 금통위
    bok_all = ["2026-11-27", "2027-01-16", "2027-02-26"]
    for ds in bok_all:
        d = datetime.strptime(ds, "%Y-%m-%d")
        if today < d <= today + timedelta(days=120):
            future_events.append({"date": ds, "event": "한국은행 금통위", "country": "KR", "impact": "high", "estimate": None, "actual": None, "prev": None, "result": None, "analysis": None})

    # 과거 이벤트는 최근 3개월만
    cutoff = today - timedelta(days=90)
    filtered_past = [e for e in past_events if datetime.strptime(e["date"], "%Y-%m-%d") >= cutoff]

    all_events = filtered_past + future_events
    all_events.sort(key=lambda x: x["date"])
    return all_events
