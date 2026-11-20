"""종목 뉴스 + 호재/악재 키워드 분위기 (예측 '뉴스' 요인)

국내: 네이버 증권 모바일 뉴스 API (m.stock.naver.com) — 예전 finance.naver.com 종목뉴스 페이지는 410(폐지)
      네이버가 실패하면 Google 뉴스 RSS(종목명 검색)로 받고, 어디서 받았는지 source 에 남긴다.
미국: yfinance Ticker.news
종목별 10분 캐시 — 뉴스는 초 단위로 바뀌지 않으므로 실시간 갱신 때도 캐시 사용
"""
import asyncio
import html
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx
import yfinance as yf

from app.services import stock_master

_TTL = 600.0
_cache: dict = {}
_sem = asyncio.Semaphore(8)
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# 문구 단위 판단을 먼저 한다 — "하락 우려 해소" 를 '하락'·'우려' 때문에 악재로 세지 않도록
PHRASE_POS_KR = ["우려 해소", "우려해소", "적자 축소", "적자폭 축소", "흑자 전환", "흑자전환", "적자 탈출", "반등", "저점 매수",
                 "낙폭 과대", "목표가 상향", "투자의견 상향", "어닝 서프라이즈", "최대 실적", "사상 최대"]
PHRASE_NEG_KR = ["흑자 축소", "적자 전환", "적자전환", "목표가 하향", "투자의견 하향", "어닝 쇼크", "상장 폐지", "상장폐지",
                 "거래 정지", "거래정지", "실적 부진", "하락 전환"]
POS_KR = ["급등", "상승", "강세", "신고가", "호실적", "흑자", "수주", "계약 체결", "공급계약", "상향", "매수", "호재",
          "돌파", "증가", "성장", "승인", "협력", "투자 유치", "배당 확대", "자사주", "최고"]
NEG_KR = ["급락", "하락", "약세", "신저가", "적자", "소송", "리콜", "하향", "매도", "악재", "감소", "부진", "우려",
          "조사", "제재", "유상증자", "횡령", "손실", "최저", "경고"]
POS_EN = ["surge", "soar", "jump", "rally", "beat", "record", "upgrade", "raises", "strong", "gain", "bullish",
          "outperform", "buy", "approval", "partnership", "growth", "profit", "tops", "rebound"]
NEG_EN = ["plunge", "sink", "drop", "fall", "slump", "miss", "downgrade", "cut", "weak", "loss", "bearish",
          "lawsuit", "probe", "recall", "underperform", "sell", "warning", "decline", "layoff"]


def _tone(title: str, market: str) -> str | None:
    t = title.lower()
    p = n = 0
    if market == "KR":
        for ph in PHRASE_POS_KR:
            if ph in t:
                p += 2
                t = t.replace(ph, " ")
        for ph in PHRASE_NEG_KR:
            if ph in t:
                n += 2
                t = t.replace(ph, " ")
        p += sum(1 for w in POS_KR if w in t)
        n += sum(1 for w in NEG_KR if w in t)
    else:
        p += sum(1 for w in POS_EN if re.search(rf"\b{w}", t))
        n += sum(1 for w in NEG_EN if re.search(rf"\b{w}", t))
    return "pos" if p > n else "neg" if n > p else None


def _collect_titled(obj, out: list):
    """네이버 응답 구조가 바뀌어도 title 이 있는 기사 객체를 모두 찾는다"""
    if isinstance(obj, dict):
        if obj.get("title") and (obj.get("datetime") or obj.get("officeName") or obj.get("articleId")):
            out.append(obj)
        for v in obj.values():
            _collect_titled(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_titled(v, out)


async def _fetch_kr_naver(symbol: str) -> list:
    url = f"https://m.stock.naver.com/api/news/stock/{symbol}?pageSize=20&page=1"
    async with httpx.AsyncClient(headers={**_UA, "Referer": f"https://m.stock.naver.com/domestic/stock/{symbol}/news"},
                                 follow_redirects=True, timeout=6.0) as c:
        resp = await c.get(url)
    resp.raise_for_status()
    raw: list = []
    _collect_titled(resp.json(), raw)
    out = []
    for a in raw:
        dt = str(a.get("datetime") or "")
        date = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) >= 8 and dt[:8].isdigit() else ""
        link = (f"https://n.news.naver.com/mnews/article/{a['officeId']}/{a['articleId']}"
                if a.get("officeId") and a.get("articleId") else "")
        out.append({"title": html.unescape(re.sub(r"<[^>]+>", "", a["title"])), "date": date,
                    "url": link, "press": a.get("officeName", "")})
    return out[:15]


async def _fetch_google(query: str, lang: str = "ko") -> list:
    gl, ceid = ("KR", "KR:ko") if lang == "ko" else ("US", "US:en")
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl={lang}&gl={gl}&ceid={ceid}"
    async with httpx.AsyncClient(headers=_UA, follow_redirects=True, timeout=6.0) as c:
        resp = await c.get(url)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    out = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            date = ""
        src = item.find("source")
        out.append({"title": html.unescape(title), "date": date, "url": item.findtext("link") or "",
                    "press": src.text if src is not None else ""})
    return out[:15]


def _fetch_us_sync(symbol: str) -> list:
    out = []
    for n in (yf.Ticker(symbol).news or [])[:15]:
        c = n.get("content") or n  # yfinance 버전에 따라 구조가 다름
        title = c.get("title") or ""
        date = c.get("pubDate") or c.get("providerPublishTime") or ""
        if isinstance(date, (int, float)):
            date = time.strftime("%Y-%m-%d", time.localtime(date))
        url = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link", "")
        if title:
            out.append({"title": title, "date": str(date)[:10], "url": url or "",
                        "press": (c.get("provider") or {}).get("displayName", "") if isinstance(c.get("provider"), dict) else ""})
    return out


async def fetch_headlines(market: str, symbol: str) -> tuple[list, str]:
    """→ (기사 목록, 출처). 국내는 네이버 → 실패 시 Google 뉴스. 둘 다 실패하면 예외."""
    if market == "KR":
        try:
            items = await _fetch_kr_naver(symbol)
            if items:
                return items, "네이버 증권"
            naver_err = "기사 0건"
        except Exception as e:
            naver_err = f"{type(e).__name__}: {e}"
        name = (stock_master.get("KR", symbol) or {}).get("name") or symbol
        try:
            return await _fetch_google(f"{name} 주가"), f"Google 뉴스 (네이버 실패: {naver_err[:80]})"
        except Exception as e:
            raise RuntimeError(f"네이버({naver_err[:80]}) · Google 뉴스({type(e).__name__}: {str(e)[:80]}) 모두 실패")
    items = await asyncio.get_event_loop().run_in_executor(None, _fetch_us_sync, symbol)
    return items, "Yahoo Finance"


async def get_news_tone(market: str, symbol: str) -> dict:
    key = (market, symbol)
    hit = _cache.get(key)
    if hit and time.time() - hit["ts"] < _TTL:
        return hit["data"]
    async with _sem:
        try:
            items, source = await fetch_headlines(market, symbol)
            for h in items:
                h["tone"] = _tone(h["title"], market)
            data = {
                "total": len(items),
                "pos": sum(1 for h in items if h["tone"] == "pos"),
                "neg": sum(1 for h in items if h["tone"] == "neg"),
                "headlines": items,
                "source": source,
            }
        except Exception as e:
            data = {"total": 0, "pos": 0, "neg": 0, "headlines": [], "error": str(e)}
    _cache[key] = {"ts": time.time(), "data": data}
    return data


async def get_news_many(keys: list) -> dict:
    res = await asyncio.gather(*[get_news_tone(m, s) for m, s in keys])
    return dict(zip(keys, res))
