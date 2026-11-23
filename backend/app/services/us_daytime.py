"""미국 주간거래 가격 (한국 낮 10:00 ~ 18:00(서머타임 17:00), 블루오션 ATS) — KIS 해외 현재가 EXCD=BAQ/BAY/BAA

- 토스·증권사 앱이 낮에 보여주는 미국 주식 가격. Yahoo 에는 없어서 이 시간엔 금요일 종가 등이 그대로 보였음.
- 표시 전용: 예측 확률·추천 매입가 계산에는 쓰지 않음 (거래량이 적은 시장이라 정규장 가격이 기준).
- 주간거래 시간에만 조회, 종목별 30초 캐시. 실패는 그 종목에 error 로 붙이고 주 응답은 막지 않음 (부가 정보).
"""
import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services import stock_master
from app.services.kis_api import kis_client
from app.services.market_calendar import us_daytime_session

_TTL = 30.0
_cache: dict = {}   # symbol -> (ts, result)
_KST = ZoneInfo("Asia/Seoul")


def build(raw: dict, session: dict, fetched: float) -> dict | None:
    """KIS 응답 → 화면용. 체결이 없으면(가격 0) None"""
    price = raw.get("price") or 0
    if price <= 0:
        return None
    base = raw.get("base") or 0
    if base > 0:   # 기준가(직전 정규장 종가) 대비로 직접 계산 — KIS 부호 표기에 기대지 않음
        change, rate = price - base, (price / base - 1) * 100
    else:
        change, rate = raw.get("change") or 0.0, raw.get("change_rate") or 0.0
    return {
        "label": "주간거래",
        "price": round(price, 4 if price < 1 else 2),
        "base": round(base, 2) if base else None,
        "change": round(change, 2),
        "change_rate": round(0.0 if abs(rate) < 0.005 else rate, 2),
        "volume": raw.get("volume") or 0,
        "time": datetime.fromtimestamp(fetched, _KST).strftime("%H:%M"),
        "hours_kst": session["hours_kst"],
        "source": "KIS 주간거래",
    }


async def get_many(symbols: list) -> dict:
    """{symbol: 주간거래 정보 | {"error"}} — 주간거래 시간이 아니면 빈 dict. 체결 없는 종목은 빠짐"""
    session = us_daytime_session()
    if not session["open"] or not symbols:
        return {}
    now = time.time()
    out, todo = {}, []
    for s in dict.fromkeys(symbols):
        hit = _cache.get(s)
        if hit and now - hit[0] < _TTL:
            if hit[1] is not None:
                out[s] = hit[1]
        else:
            todo.append(s)

    async def one(s):
        ex = (stock_master.get("US", s) or {}).get("exchange") or "NAS"
        try:
            raw = await kis_client.get_us_daytime_price(s, ex)
            v = build(raw, session, time.time())
            _cache[s] = (time.time(), v)
            if v is not None:
                out[s] = v
        except Exception as e:
            # 실패는 캐시하지 않음 (다음 요청 때 다시)
            out[s] = {"label": "주간거래", "error": f"주간거래 시세 조회 실패: {e}"}

    await asyncio.gather(*(one(s) for s in todo))
    return out


async def attach(rows: list, symbol_key: str = "symbol", market_key: str | None = "market") -> list:
    """목록의 미국 종목에 daytime 필드를 붙인 **새 목록** (캐시된 원본 행은 건드리지 않음 —
    주간거래가 끝난 뒤에도 예전 가격이 캐시에 남아 보이는 일이 없게)"""
    def is_us(r):
        return isinstance(r, dict) and r.get(symbol_key) and (market_key is None or r.get(market_key) == "US")
    got = await get_many([r[symbol_key] for r in rows if is_us(r)])
    out = []
    for r in rows:
        if isinstance(r, dict):
            r = {k: v for k, v in r.items() if k != "daytime"}
            if is_us(r) and r[symbol_key] in got:
                r["daytime"] = got[r[symbol_key]]
        out.append(r)
    return out
