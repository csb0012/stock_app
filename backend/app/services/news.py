"""종목 뉴스 + 호재/악재 키워드 분위기 (예측 '뉴스' 요인)

국내 종목:
  - **해외 영문 기사 = 확률에 반영** (weighted): Yahoo Finance 종목 뉴스(005930.KS) + Google 뉴스 영문 검색(영문 회사명).
    TRUSTED_FOREIGN 에 있는 매체(Reuters·Bloomberg·CNBC·FT·WSJ·Nikkei Asia 등)만 남김. 대형주 위주라 중소형주는 0건 → 뉴스 요인 미반영
  - **국내 기사 = 가져와서 보여주기만** (확률 반영 안 함): 네이버 증권 모바일 뉴스 API → 실패 시 Google 뉴스(한국어).
    TRUSTED_KR 언론사만 남김 (작은 매체·기사형 광고 제외)
미국 종목: yfinance Ticker.news (전부 반영, 기존과 같음)
국내 기사 10분 / 해외 기사 30분 캐시. 국내 종목 영문 회사명은 Yahoo 에서 한 번 받아 app/data/kr_en_names.json 에 저장
"""
import asyncio
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import yfinance as yf

from app.services import stock_master

_TTL = 600.0
_FOREIGN_TTL = 1800.0
_cache: dict = {}
_foreign_cache: dict = {}   # symbol -> {"ts", "data"}
_sem = asyncio.Semaphore(8)
_foreign_sem = asyncio.Semaphore(4)   # Google·Yahoo 에 한꺼번에 몰리지 않게

# 국내 기사: 이 언론사만 남김 (네이버 officeName / Google 출처 이름에 포함되면 통과). 고치려면 이 목록만 수정
TRUSTED_KR = ["연합뉴스", "연합인포맥스", "한국경제", "매일경제", "서울경제", "머니투데이", "이데일리", "뉴스1", "뉴시스", "조선비즈"]
# 해외 기사: 이 매체만 남김 (출처 이름을 소문자로 바꿔 포함 여부로 비교)
TRUSTED_FOREIGN = {
    "reuters": "Reuters", "bloomberg": "Bloomberg", "cnbc": "CNBC", "financial times": "Financial Times",
    "wall street journal": "WSJ", "wsj": "WSJ", "nikkei": "Nikkei Asia", "associated press": "AP", "ap news": "AP",
    "barron": "Barron's", "marketwatch": "MarketWatch", "economist": "The Economist", "investing.com": "Investing.com",
    "yahoo finance": "Yahoo Finance", "korea herald": "Korea Herald", "joongang": "Korea JoongAng Daily",
    "korea times": "Korea Times", "yonhap": "Yonhap",
}
_EN_NAME_FILE = Path(__file__).resolve().parents[1] / "data" / "kr_en_names.json"
_en_names: dict | None = None
_en_fail: dict = {}   # symbol -> 실패 시각 (하루 동안 다시 안 물어봄)
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
          "outperform", "buy", "approval", "partnership", "growth", "profit", "tops", "rebound",
          "climb", "rise", "rises", "record high", "upbeat", "boost", "wins", "expands"]
NEG_EN = ["plunge", "sink", "drop", "fall", "slump", "miss", "downgrade", "cut", "weak", "loss", "bearish",
          "lawsuit", "probe", "recall", "underperform", "sell", "warning", "decline", "layoff",
          "falls short", "misses", "tumble", "slide", "plummet", "weaker"]


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


def _trusted_kr(press: str) -> bool:
    return any(t in (press or "") for t in TRUSTED_KR)


def _trusted_foreign(press: str) -> str | None:
    p = (press or "").lower()   # 단어 경계로 비교 ("Yonhap News" 안의 "ap news" 를 AP 로 보지 않게)
    return next((label for key, label in TRUSTED_FOREIGN.items() if re.search(rf"\b{re.escape(key)}", p)), None)


def _clean_en_name(name: str) -> str:
    """'Samsung Electronics Co., Ltd.' → 'Samsung Electronics' (검색어용)"""
    n = re.sub(r"[,.]?\s*(co\.?,?\s*ltd\.?|company|corporation|corp\.?|inc\.?|limited|ltd\.?|plc)\s*$", "", name.strip(), flags=re.I)
    return re.sub(r"[,.]?\s*(co\.?,?\s*ltd\.?|corp\.?|inc\.?)\s*$", "", n, flags=re.I).strip(" ,.")


def _en_name_sync(symbol: str, yf_ticker: str) -> str:
    """국내 종목 영문 회사명 (Yahoo) — 파일에 저장해 두고 재사용"""
    global _en_names
    if _en_names is None:
        try:
            _en_names = json.loads(_EN_NAME_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            _en_names = {}
    if symbol in _en_names:
        return _en_names[symbol]
    if time.time() - _en_fail.get(symbol, 0) < 86400:
        return ""
    try:
        info = yf.Ticker(yf_ticker).get_info() or {}
    except Exception:
        _en_fail[symbol] = time.time()
        return ""
    name = _clean_en_name(info.get("longName") or info.get("shortName") or "")
    if not name:
        _en_fail[symbol] = time.time()
        return ""
    _en_names[symbol] = name
    try:
        _EN_NAME_FILE.parent.mkdir(parents=True, exist_ok=True)
        _EN_NAME_FILE.write_text(json.dumps(_en_names, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return name


def _yahoo_news_sync(ticker: str) -> list:
    return _fetch_us_sync(ticker)


async def _fetch_foreign_kr(symbol: str) -> dict:
    """국내 종목의 해외 영문 기사 (신뢰 매체만). → {"items", "errors", "en_name"}  (30분 캐시)"""
    hit = _foreign_cache.get(symbol)
    if hit and time.time() - hit["ts"] < _FOREIGN_TTL:
        return hit["data"]
    m = stock_master.get("KR", symbol) or {}
    yf_ticker = m.get("yf") or f"{symbol}.KS"
    loop = asyncio.get_event_loop()
    errors, raw = [], []
    async with _foreign_sem:
        try:
            raw += await loop.run_in_executor(None, _yahoo_news_sync, yf_ticker)
        except Exception as e:
            errors.append(f"Yahoo: {type(e).__name__}: {str(e)[:80]}")
        en = await loop.run_in_executor(None, _en_name_sync, symbol, yf_ticker)
        if en:
            # 짧은 이름(KT, HLB 등)은 엉뚱한 기사가 섞이지 않게 Korea 를 같이 검색
            q = f'"{en}"' + (" Korea" if len(en) <= 4 else "") + " when:14d"
            try:
                for it in await _fetch_google(q, "en"):
                    # Google 제목 끝의 " - Reuters" 제거
                    if it["press"] and it["title"].endswith(f" - {it['press']}"):
                        it["title"] = it["title"][: -len(it["press"]) - 3]
                    raw.append(it)
            except Exception as e:
                errors.append(f"Google 뉴스(영문): {type(e).__name__}: {str(e)[:80]}")
    items, seen = [], set()
    for it in sorted(raw, key=lambda x: x.get("date", ""), reverse=True):
        label = _trusted_foreign(it.get("press", ""))
        key = re.sub(r"\W+", "", it["title"].lower())[:60]
        if not label or key in seen:
            continue
        seen.add(key)
        items.append({**it, "press": label, "lang": "en", "weighted": True})
    data = {"items": items[:10], "errors": errors, "en_name": en}
    # 둘 다 실패면 짧게만 캐시 (10분)
    _foreign_cache[symbol] = {"ts": time.time() - (_FOREIGN_TTL - _TTL if errors and not raw else 0), "data": data}
    return data


async def _fetch_kr_domestic(symbol: str) -> tuple[list, str]:
    """국내 기사 (신뢰 언론사만, 확률 반영 안 함): 네이버 → 실패 시 Google 뉴스(한국어)"""
    try:
        items = await _fetch_kr_naver(symbol)
        if items:
            return [i for i in items if _trusted_kr(i.get("press", ""))], "네이버 증권"
        naver_err = "기사 0건"
    except Exception as e:
        naver_err = f"{type(e).__name__}: {e}"
    name = (stock_master.get("KR", symbol) or {}).get("name") or symbol
    try:
        items = await _fetch_google(f"{name} 주가")
        return [i for i in items if _trusted_kr(i.get("press", ""))], f"Google 뉴스 (네이버 실패: {naver_err[:60]})"
    except Exception as e:
        raise RuntimeError(f"네이버({naver_err[:80]}) · Google 뉴스({type(e).__name__}: {str(e)[:80]}) 모두 실패")


async def _get_kr(symbol: str) -> dict:
    """국내 종목 뉴스: 해외 영문(반영) + 국내(참고) → get_news_tone 형식"""
    async def domestic():
        try:
            return await _fetch_kr_domestic(symbol), None
        except Exception as e:
            return ([], ""), str(e)
    foreign, ((kr_items, kr_src), kr_err) = await asyncio.gather(_fetch_foreign_kr(symbol), domestic())
    for h in kr_items:
        h["tone"] = _tone(h["title"], "KR")
        h["lang"], h["weighted"] = "ko", False
    fi = [dict(h) for h in foreign["items"]]
    for h in fi:
        h["tone"] = _tone(h["title"], "US")
    presses = sorted({h["press"] for h in fi})
    src = (f"해외 {len(fi)}건 ({'·'.join(presses[:4])})" if fi else
           "해외 기사 조회 실패" if foreign["errors"] else "해외 기사 없음") + \
          (f" · 국내 {len(kr_items)}건 참고 ({kr_src})" if kr_src else "")
    data = {
        "weight_source": "foreign",          # analysis.py: 해외 기사만 확률에 반영
        "total": len(fi),
        "pos": sum(1 for h in fi if h["tone"] == "pos"),
        "neg": sum(1 for h in fi if h["tone"] == "neg"),
        "kr_total": len(kr_items),
        "headlines": fi + kr_items,          # 해외(반영) 먼저, 국내(참고) 다음
        "source": src,
    }
    if foreign["errors"] and not fi:
        data["foreign_error"] = " / ".join(foreign["errors"])
    if kr_err:
        data["kr_error"] = kr_err
    return data


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
        if market == "KR":
            data = await _get_kr(symbol)
            _cache[key] = {"ts": time.time(), "data": data}
            return data
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
