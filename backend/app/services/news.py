"""종목 뉴스 + 호재/악재 키워드 분위기 (예측 '뉴스' 요인)

국내: 네이버 금융 종목 뉴스, 미국: yfinance Ticker.news
종목별 10분 캐시 — 뉴스는 초 단위로 바뀌지 않으므로 실시간 갱신 때도 캐시 사용
"""
import asyncio
import re
import time

import httpx
import yfinance as yf
from bs4 import BeautifulSoup

_TTL = 600.0
_cache: dict = {}
_sem = asyncio.Semaphore(8)

POS_KR = ["급등", "상승", "강세", "신고가", "호실적", "흑자", "최대 실적", "어닝 서프라이즈", "수주", "계약 체결",
          "목표가 상향", "상향", "매수", "호재", "돌파", "증가", "성장", "승인", "협력", "투자 유치", "배당 확대", "자사주"]
NEG_KR = ["급락", "하락", "약세", "신저가", "적자", "실적 부진", "어닝 쇼크", "소송", "리콜", "목표가 하향", "하향",
          "매도", "악재", "감소", "부진", "우려", "조사", "제재", "유상증자", "횡령", "상장폐지", "거래정지", "손실"]
POS_EN = ["surge", "soar", "jump", "rally", "beat", "record", "upgrade", "raises", "strong", "gain", "bullish",
          "outperform", "buy", "approval", "partnership", "growth", "profit", "tops"]
NEG_EN = ["plunge", "sink", "drop", "fall", "slump", "miss", "downgrade", "cut", "weak", "loss", "bearish",
          "lawsuit", "probe", "recall", "underperform", "sell", "warning", "decline", "layoff"]


def _tone(title: str, market: str) -> str | None:
    t = title.lower()
    pos_words, neg_words = (POS_KR, NEG_KR) if market == "KR" else (POS_EN, NEG_EN)
    p = sum(1 for w in pos_words if (w in t if market == "KR" else re.search(rf"\b{w}", t)))
    n = sum(1 for w in neg_words if (w in t if market == "KR" else re.search(rf"\b{w}", t)))
    return "pos" if p > n else "neg" if n > p else None


async def _fetch_kr(symbol: str) -> list:
    url = f"https://finance.naver.com/item/news_news.naver?code={symbol}&page=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://finance.naver.com/item/news.naver?code={symbol}",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=6.0) as c:
        resp = await c.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    out = []
    for row in soup.select("table.type5 tbody tr"):
        a = row.select_one("td.title a")
        d = row.select_one("td.date")
        if a:
            out.append({"title": a.get_text(strip=True), "date": d.get_text(strip=True) if d else ""})
    return out[:15]


def _fetch_us_sync(symbol: str) -> list:
    out = []
    for n in (yf.Ticker(symbol).news or [])[:15]:
        c = n.get("content") or n  # yfinance 버전에 따라 구조가 다름
        title = c.get("title") or ""
        date = c.get("pubDate") or c.get("providerPublishTime") or ""
        if title:
            out.append({"title": title, "date": str(date)[:10]})
    return out


async def get_news_tone(market: str, symbol: str) -> dict:
    key = (market, symbol)
    hit = _cache.get(key)
    if hit and time.time() - hit["ts"] < _TTL:
        return hit["data"]
    async with _sem:
        try:
            if market == "KR":
                items = await _fetch_kr(symbol)
            else:
                items = await asyncio.get_event_loop().run_in_executor(None, _fetch_us_sync, symbol)
            for h in items:
                h["tone"] = _tone(h["title"], market)
            data = {
                "total": len(items),
                "pos": sum(1 for h in items if h["tone"] == "pos"),
                "neg": sum(1 for h in items if h["tone"] == "neg"),
                "headlines": items,
            }
        except Exception as e:
            data = {"total": 0, "pos": 0, "neg": 0, "headlines": [], "error": str(e)}
    _cache[key] = {"ts": time.time(), "data": data}
    return data


async def get_news_many(keys: list) -> dict:
    res = await asyncio.gather(*[get_news_tone(m, s) for m, s in keys])
    return dict(zip(keys, res))
