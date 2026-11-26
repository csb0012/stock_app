"""미국 정규장 밖 가격 — 응답의 daytime 필드 (label 로 구분). 세 시간대는 겹치지 않음:

- 주간거래 (한국 낮 10:00 ~ 18:00(서머타임 17:00), 블루오션 ATS) — KIS 해외 현재가 EXCD=BAQ/BAY/BAA, 종목별 30초 캐시
- 프리마켓 (04:00~09:30 ET) · 애프터마켓 (16:00~20:00 ET) — Yahoo 5분봉(prepost) 의 그 시간대 마지막 체결, 종목별 60초 캐시.
  KIS 해외 현재가(HHDFS00000300)는 정규장 마지막 가격만 줘서 애프터마켓에도 종가가 그대로 보였음.
  등락률은 행의 현재가(= 정규장 종가) 대비 (없으면 Yahoo 의 직전 정규장 마지막 봉)
- 표시 전용: 예측 확률·추천 매입가 계산에는 쓰지 않음 (거래량이 적은 시장이라 정규장 가격이 기준).
- 그 시간에만 조회. 실패는 그 종목에 error 로 붙이고 주 응답은 막지 않음 (부가 정보), 실패는 캐시 안 함.
"""
import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services import stock_master
from app.services.kis_api import kis_client
from app.services.market_calendar import us_daytime_session, us_ext_session

_TTL = 30.0
_EXT_TTL = 60.0
_cache: dict = {}       # symbol -> (ts, result)   주간거래
_ext_cache: dict = {}   # (symbol, 시간대, 날짜) -> (ts, result)   프리·애프터마켓
_KST = ZoneInfo("Asia/Seoul")
_NY = ZoneInfo("America/New_York")


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


def _yf_ext_sync(symbols: list, session: dict) -> dict:
    """Yahoo 5분봉(prepost) → {symbol: {price, base, at(datetime ET)}} — 지금 시간대(오늘 미국 날짜, 프리/애프터 구간)에 체결이 있는 종목만.
    base = 그 전 정규장(09:30~16:00) 마지막 봉 종가"""
    import yfinance as yf
    data = yf.download(symbols, period="5d", interval="5m", prepost=True, progress=False, auto_adjust=False, threads=True)
    out = {}
    if data is None or data.empty:   # yfinance 는 실패해도 예외 없이 빈 표를 줌 → 숨기지 않고 오류로
        raise RuntimeError("Yahoo 5분봉 응답 없음 (접속 실패 또는 차단)")
    day = session["session_date"]
    for s in symbols:
        close = data["Close"] if "Close" in data else None
        if hasattr(close, "columns"):   # 종목별 열 (한 종목만 물었는데 열 이름이 다르면 그 한 열)
            col = close[s] if s in close.columns else (close.iloc[:, 0] if len(symbols) == 1 and len(close.columns) == 1 else None)
        else:
            col = close if len(symbols) == 1 else None
        col = col.dropna() if col is not None else None
        if col is None or col.empty:   # 5일 동안 봉이 하나도 없음 = 이 종목 조회 실패 (체결 없음과 구분)
            out[s] = {"error": "Yahoo 5분봉 없음 (이 종목 조회 실패)"}
            continue
        idx = col.index.tz_convert(_NY) if col.index.tz is not None else col.index.tz_localize("UTC").tz_convert(_NY)
        ext_price, ext_at, base = None, None, None
        for ts, v in zip(idx, col.values):
            hm = ts.hour * 60 + ts.minute
            if ts.date().isoformat() == day and session["start_et"] <= hm < session["end_et"]:
                ext_price, ext_at = float(v), ts
            elif 9 * 60 + 30 <= hm < 16 * 60 and (ext_at is None) and ts.date().isoformat() <= day:
                base = float(v)
        if ext_price and ext_price > 0:
            out[s] = {"price": ext_price, "base": base, "at": ext_at}
    return out


def build_ext(raw: dict, session: dict, base: float | None = None) -> dict:
    """Yahoo 시간외 값 → 화면용 (daytime 과 같은 모양). base(정규장 종가)를 주면 그 대비 등락률"""
    price = raw["price"]
    base = base if base and base > 0 else (raw.get("base") or 0)
    rate = (price / base - 1) * 100 if base > 0 else 0.0
    at = raw["at"]
    return {
        "label": session["label"],
        "price": round(price, 4 if price < 1 else 2),
        "base": round(base, 2) if base else None,
        "change": round(price - base, 2) if base else 0.0,
        "change_rate": round(0.0 if abs(rate) < 0.005 else rate, 2),
        "volume": 0,
        "time": at.astimezone(_KST).strftime("%H:%M"),
        "et_time": at.strftime("%H:%M") + " ET",
        "hours_kst": session["hours_kst"],
        "source": "Yahoo 시간외",
    }


async def _ext_many(symbols: list, session: dict) -> dict:
    """프리·애프터마켓 Yahoo 원값 {symbol: raw | {"error"}} — 체결 없는 종목은 빠짐 (60초 캐시, 없음도 캐시)"""
    now = time.time()
    out, todo = {}, []
    for s in dict.fromkeys(symbols):
        hit = _ext_cache.get((s, session["label"], session["session_date"]))
        if hit and now - hit[0] < _EXT_TTL:
            if hit[1] is not None:
                out[s] = hit[1]
        else:
            todo.append(s)
    if todo:
        try:
            got = await asyncio.get_event_loop().run_in_executor(None, _yf_ext_sync, todo, session)
        except Exception as e:   # noqa: BLE001 — 부가 정보: 주 응답은 그대로
            msg = f"{session['label']} 시세 조회 실패 (Yahoo): {str(e)[:150] or type(e).__name__}"
            return {**out, **{s: {"error": msg} for s in todo}}
        t = time.time()
        for s in todo:
            v = got.get(s)
            if v and "error" in v:   # 실패는 캐시 안 함
                out[s] = {"error": f"{session['label']} 시세 조회 실패 (Yahoo): {v['error']}"}
                continue
            _ext_cache[(s, session["label"], session["session_date"])] = (t, v)
            if v:
                out[s] = v
    return out


async def get_many(symbols: list, extended: bool = True) -> dict:
    """{symbol: 주간거래 정보 | {"error"}} — 주간거래 시간이 아니면 빈 dict. 체결 없는 종목은 빠짐.
    extended=True 면 프리·애프터마켓 시간엔 그 가격 (raw — attach 가 행의 정규장 가격 대비로 바꿈)"""
    session = us_daytime_session()
    if not symbols:
        return {}
    if not session["open"]:
        ext = us_ext_session()
        if not (extended and ext["open"]):
            return {}
        raw = await _ext_many(symbols, ext)
        return {s: ({"label": ext["label"], **v} if "error" in v else {"ext_raw": v, "session": ext}) for s, v in raw.items()}
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


async def attach(rows: list, symbol_key: str = "symbol", market_key: str | None = "market", extended: bool = True) -> list:
    """목록의 미국 종목에 daytime 필드(주간거래 / 프리마켓 / 애프터마켓 — label)를 붙인 **새 목록** (캐시된 원본 행은 건드리지 않음 —
    그 시간이 끝난 뒤에도 예전 가격이 캐시에 남아 보이는 일이 없게). extended=False = 주간거래만 (대시보드는 따로 ext 가 있음)"""
    def is_us(r):
        return isinstance(r, dict) and r.get(symbol_key) and (market_key is None or r.get(market_key) == "US")
    got = await get_many([r[symbol_key] for r in rows if is_us(r)], extended)
    out = []
    for r in rows:
        if isinstance(r, dict):
            r = {k: v for k, v in r.items() if k != "daytime"}
            if is_us(r) and r[symbol_key] in got:
                v = got[r[symbol_key]]
                if "ext_raw" in v:   # 시간외: 이 행의 정규장 가격(KIS 종가) 대비
                    v = build_ext(v["ext_raw"], v["session"], r.get("current_price") or r.get("price"))
                r["daytime"] = v
        out.append(r)
    return out


async def attach_screener(rows: list, fallback_limit: int = 30) -> list:
    """미국 스크리너 행 → 프리·애프터마켓 시간이면 daytime(시간외 가격)을 붙인 **새 목록** (_ext 원값은 뺌).
    1) Yahoo 스크리너 시세의 pre/postMarketPrice·Time (추가 호출 없음) — 시각이 오늘 그 시간대일 때만
    2) 없으면 앞쪽 fallback_limit 종목만 5분봉으로 (종목이 최대 200개라 전부는 안 받음)"""
    out = [{k: v for k, v in r.items() if k not in ("_ext", "daytime")} for r in rows]
    ses = us_ext_session()
    if not ses["open"]:
        return out
    key = "post" if ses["label"] == "애프터마켓" else "pre"
    missing = []
    for r, raw in zip(out, rows):
        e = (raw.get("_ext") or {}).get(key) or {}
        at = None
        try:
            if e.get("price") and e.get("time"):
                at = datetime.fromtimestamp(float(e["time"]), _NY)
        except (TypeError, ValueError, OSError):
            at = None
        if at and at.date().isoformat() == ses["session_date"] and ses["start_et"] <= at.hour * 60 + at.minute < ses["end_et"]:
            r["daytime"] = build_ext({"price": float(e["price"]), "base": None, "at": at}, ses, r.get("price"))
        else:
            missing.append(r)
    missing = missing[:fallback_limit]
    if missing:
        got = await _ext_many([r["symbol"] for r in missing], ses)
        for r in missing:
            v = got.get(r["symbol"])
            if v:
                r["daytime"] = {"label": ses["label"], **v} if "error" in v else build_ext(v, ses, r.get("price"))
    return out
