"""가치·재무 (PER·PBR·ROE·영업이익률·성장률·배당) — 가치주 찾기 화면, 퀀트 점수의 가치·수익성 요인, AI 추천 근거

국내: 네이버 증권 모바일 API 의 분기 실적(m.stock.naver.com/api/stock/{코드}/finance/quarter, 최근 실적 5분기 + 예상치)
      → 예상치(컨센서스)는 안 씀. 종목마다 7일에 한 번 다시 받음 (app/data/fundamentals_kr.json).
      비공식 API 라 형식이 바뀌면 '재무 데이터를 읽지 못함' 오류로 표시 (가짜 값으로 채우지 않음)
미국: Yahoo 시세(v7 quote — PER·PBR·배당수익률·시가총액·52주 등락) + Yahoo 스크리너 조건 검색

**미래 데이터 미사용 (퀀트 요인·검증용)**: 분기 실적은 법정 공시 기한이 지난 뒤에 '알려진 것'으로 봄
  (1·2·3분기 = 분기 끝 + 45일, 4분기(사업보고서) = + 90일). 그날 알려진 최근 4분기 합(TTM)과 그날 종가로 PER·PBR·ROE 를 계산.
  실제로는 더 일찍 발표하는 회사가 많아서 보수적인 기준 (늦게 반영 = 미래를 보지 않음).
한계: 업종 차이(은행 PBR 이 원래 낮음 등)를 따로 보정하지 않음. 액면분할이 있으면 주당 값이 잠깐 어긋날 수 있음.
"""
import asyncio
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

_DATA = Path(__file__).resolve().parents[1] / "data"
_KR_FILE = _DATA / "fundamentals_kr.json"
KR_REFRESH_DAYS = 7
_UA = {"User-Agent": "Mozilla/5.0 (StockApp)", "Referer": "https://m.stock.naver.com/"}

_kr: dict | None = None          # symbol -> {"q": [분기...], "fetched": "YYYY-MM-DD"} 또는 {"error":..., "fetched":...}
_status = {"running": False, "done": 0, "total": 0, "errors": 0, "error_samples": [], "started_at": None,
           "finished_at": None, "message": None}
_lock = asyncio.Lock()


# ---------------- 국내: 네이버 분기 실적 파싱 (순수 함수) ----------------

def _num(v):
    if v in (None, "", "-", "N/A"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


ROW_KEYS = {"매출액": "sales", "영업이익": "op", "당기순이익": "ni", "지배주주순이익": "ni_ctl", "EPS": "eps", "BPS": "bps",
            "주당배당금": "dps", "부채비율": "debt", "ROE": "roe_q", "영업이익률": "opm_q"}


def parse_quarter(data: dict) -> list:
    """네이버 분기 실적 응답 → 실적 분기만 [{q:'202609', sales, op, ni, eps, bps, dps, debt, ...}] 오래된 순"""
    fi = (data or {}).get("financeInfo") or {}
    titles = fi.get("trTitleList") or []
    rows = fi.get("rowList") or []
    if not titles or not rows:
        raise ValueError("재무 표 형식이 예상과 다름 (financeInfo.trTitleList/rowList 없음)")
    actual = [t["key"] for t in titles if t.get("isConsensus") == "N" and re.fullmatch(r"\d{6}", str(t.get("key", "")))]
    out = {k: {"q": k} for k in actual}
    for r in rows:
        name = ROW_KEYS.get(r.get("title"))
        if not name:
            continue
        for k in actual:
            out[k][name] = _num(((r.get("columns") or {}).get(k) or {}).get("value"))
    return [out[k] for k in sorted(out)]


def known_from(q: str) -> date:
    """분기 실적이 '알려진 것'으로 보는 날 — 공시 기한 (1~3분기 +45일, 4분기 +90일)"""
    y, m = int(q[:4]), int(q[4:6])
    end = (date(y, m, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return end + timedelta(days=90 if m == 12 else 45)


def metrics(quarters: list, on: date) -> dict | None:
    """그날(on) 알려진 실적만으로 TTM 지표. 알려진 분기가 4개 미만이면 None"""
    known = [x for x in quarters if known_from(x["q"]) <= on]
    if len(known) < 4:
        return None
    last4 = known[-4:]
    eps = [x.get("eps") for x in last4]
    if any(v is None for v in eps):
        return None
    latest = known[-1]
    sales = [x.get("sales") for x in last4]
    ops = [x.get("op") for x in last4]
    out = {"q": latest["q"], "eps_ttm": sum(eps), "bps": latest.get("bps"), "debt": latest.get("debt"),
           "dps_ttm": sum(x.get("dps") or 0 for x in last4)}
    bps = out["bps"]
    out["roe"] = round(out["eps_ttm"] / bps * 100, 2) if bps and bps > 0 else None
    out["op_margin"] = round(sum(ops) / sum(sales) * 100, 2) if all(v is not None for v in sales + ops) and sum(sales) > 0 else None
    # 전년 같은 분기 대비 성장률 (5분기가 다 알려졌을 때만)
    yo = [x for x in known if x["q"] == f"{int(latest['q'][:4]) - 1}{latest['q'][4:]}"]
    if yo:
        def g(a, b):
            return round((a / b - 1) * 100, 1) if a is not None and b is not None and b > 0 else None
        out["sales_yoy"], out["op_yoy"] = g(latest.get("sales"), yo[0].get("sales")), g(latest.get("op"), yo[0].get("op"))
        if latest.get("op") is not None and yo[0].get("op") is not None and yo[0]["op"] <= 0 < latest["op"]:
            out["turnaround"] = True     # 적자 → 흑자 전환
    return out


def with_price(m: dict | None, price: float | None) -> dict | None:
    """TTM 지표 + 가격 → PER·PBR·배당수익률 (적자면 PER None)"""
    if not m or not price or price <= 0:
        return m
    eps, bps = m.get("eps_ttm"), m.get("bps")
    return {**m, "price": price,
            "per": round(price / eps, 2) if eps and eps > 0 else None,
            "pbr": round(price / bps, 2) if bps and bps > 0 else None,
            "div_yield": round(m.get("dps_ttm", 0) / price * 100, 2) if m.get("dps_ttm") else 0.0}


def factor_rows(quarters: list, frame: pd.DataFrame) -> pd.DataFrame:
    """종목 1개: 날짜별 종가(frame: date, close) → 그날 알려진 실적 기준 E/P·B/P·ROE·영업이익률 (퀀트 요인 원값)"""
    rows = []
    cache: dict = {}
    for d, c in zip(frame["date"], frame["close"]):
        day = date.fromisoformat(str(d)[:10])
        known_q = tuple(x["q"] for x in quarters if known_from(x["q"]) <= day)
        if known_q not in cache:
            cache[known_q] = metrics(quarters, day)
        m = cache[known_q]
        if not m or not c:
            rows.append((d, np.nan, np.nan, np.nan, np.nan))
            continue
        rows.append((d, m["eps_ttm"] / c, (m["bps"] / c) if m.get("bps") else np.nan,
                     m["roe"] if m.get("roe") is not None else np.nan,
                     m["op_margin"] if m.get("op_margin") is not None else np.nan))
    return pd.DataFrame(rows, columns=["date", "ep", "bp", "roe", "opm"])


# ---------------- 국내: 받기·저장 ----------------

def _load() -> dict:
    global _kr
    if _kr is None:
        try:
            _kr = json.loads(_KR_FILE.read_text(encoding="utf-8")) if _KR_FILE.exists() else {}
        except (OSError, ValueError):
            _kr = {}
    return _kr


def _save():
    try:
        _KR_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _KR_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_load(), ensure_ascii=False), encoding="utf-8")
        tmp.replace(_KR_FILE)
    except OSError as e:
        print(f"[fundamentals] 저장 실패: {e}")


async def _fetch_kr(client: httpx.AsyncClient, sym: str) -> list:
    r = await client.get(f"https://m.stock.naver.com/api/stock/{sym}/finance/quarter")
    if r.status_code == 404:
        return []          # 재무 정보가 없는 종목 (신규 상장 등)
    if r.status_code != 200:
        raise RuntimeError(f"네이버 HTTP {r.status_code}")
    return parse_quarter(r.json())


async def refresh_kr(symbols: list, force: bool = False) -> dict:
    """국내 종목 분기 실적 받기 (7일 지난 종목만). 이미 실행 중이면 상태만"""
    if _lock.locked():
        return status()
    async with _lock:
        data = _load()
        cutoff = (date.today() - timedelta(days=KR_REFRESH_DAYS)).isoformat()
        todo = [s for s in symbols if force or (data.get(s) or {}).get("fetched", "") < cutoff]
        _status.update(running=True, done=0, total=len(todo), errors=0, error_samples=[], message=None,
                       started_at=datetime.now().isoformat(timespec="seconds"), finished_at=None)
        sem = asyncio.Semaphore(4)
        today = date.today().isoformat()

        async def one(client, s):
            async with sem:
                try:
                    data[s] = {"q": await _fetch_kr(client, s), "fetched": today}
                except Exception as e:
                    _status["errors"] += 1
                    if len(_status["error_samples"]) < 5:
                        _status["error_samples"].append(f"{s}: {str(e)[:120]}")
                    data.setdefault(s, {})["error"] = str(e)[:120]
                finally:
                    _status["done"] += 1
                    if _status["done"] % 200 == 0:
                        _save()
                    await asyncio.sleep(0.1)

        try:
            async with httpx.AsyncClient(headers=_UA, timeout=10.0, follow_redirects=True) as client:
                await asyncio.gather(*[one(client, s) for s in todo])
            _save()
            ok = _status["done"] - _status["errors"]
            _status["message"] = f"{ok}/{len(todo)}종목 재무 갱신" + (f" · 실패 {_status['errors']}건" if _status["errors"] else "")
            if todo and ok == 0:
                _status["message"] = "실패: 재무 데이터를 하나도 못 받음 — " + " / ".join(_status["error_samples"][:2])
            print(f"[fundamentals] {_status['message']}")
        finally:
            _status.update(running=False, finished_at=datetime.now().isoformat(timespec="seconds"))
        return status()


def status() -> dict:
    d = _load()
    return {**_status, "kr_symbols": sum(1 for v in d.values() if v.get("q")),
            "kr_last": max((v.get("fetched", "") for v in d.values()), default=None)}


def kr_quarters(symbol: str) -> list:
    return (_load().get(symbol) or {}).get("q") or []


def kr_now(symbol: str, price: float | None) -> dict | None:
    """국내 종목의 오늘 기준 가치·재무 지표 (화면·AI 근거). 재무가 없으면 None"""
    q = kr_quarters(symbol)
    return with_price(metrics(q, date.today()), price) if q else None


def kr_factor_frame(frames: dict) -> pd.DataFrame | None:
    """퀀트용: {종목: DataFrame(date, close)} → [date, symbol, value, quality] (요인 원값, 그날 알려진 실적만)"""
    parts = []
    for sym, f in frames.items():
        q = kr_quarters(sym)
        if not q or f is None or f.empty:
            continue
        r = factor_rows(q, f[["date", "close"]])
        r["symbol"] = sym
        parts.append(r)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    # 같은 날 안에서 E/P·B/P 백분위 평균 = 가치, ROE·영업이익률 백분위 평균 = 수익성 (단위가 달라 백분위로 합침)
    g = df.groupby("date")
    df["value"] = (g["ep"].rank(pct=True) + g["bp"].rank(pct=True)) / 2
    df["quality"] = (g["roe"].rank(pct=True) + g["opm"].rank(pct=True)) / 2
    return df[["date", "symbol", "value", "quality"]]


# ---------------- 국내 가치주 찾기 (토스 방식 조건) ----------------

def _f(x, k):
    v = x.get(k)
    return v if v is not None else None


KR_SCREENS = [
    # key, 이름, 설명, 조건 함수, 정렬 키(큰 값 먼저)
    ("undervalued_growth", "저평가 성장주", "PER 15배 이하인데 매출·영업이익이 전년보다 10% 넘게 늘어난 회사",
     lambda x: (x.get("per") or 99) <= 15 and (x.get("sales_yoy") or -1) >= 10 and (x.get("op_yoy") or -1) >= 10, "op_yoy"),
    ("growth", "성장 기대주", "영업이익이 전년 같은 분기보다 30% 넘게, 매출이 15% 넘게 늘어난 회사",
     lambda x: (x.get("op_yoy") or -1) >= 30 and (x.get("sales_yoy") or -1) >= 15, "op_yoy"),
    ("steady_growth", "안정 성장주", "매출이 꾸준히(5~30%) 늘고 영업이익률 10%↑·ROE 8%↑·부채비율 100% 이하",
     lambda x: 5 <= (x.get("sales_yoy") or -1) <= 30 and (x.get("op_margin") or 0) >= 10 and (x.get("roe") or 0) >= 8
     and (x.get("debt") if x.get("debt") is not None else 999) <= 100, "roe"),
    ("cheap_value", "아직 저렴한 가치주", "순자산보다 싸게 거래되는(PBR 0.8배 이하) 흑자 회사",
     lambda x: 0 < (x.get("pbr") or 99) <= 0.8 and (x.get("eps_ttm") or 0) > 0, "-pbr"),
    ("high_roe_cheap", "고수익 저평가", "ROE 15% 이상인데 PER 10배 이하 (돈은 잘 버는데 싼 회사)",
     lambda x: (x.get("roe") or 0) >= 15 and 0 < (x.get("per") or 99) <= 10, "roe"),
    ("value_breakout", "저평가 탈출", "PER 12배 또는 PBR 1배 이하인데 주가가 오르는 추세(퀀트 추세 등급 B+ 이상)",
     lambda x: ((0 < (x.get("per") or 99) <= 12) or (0 < (x.get("pbr") or 99) <= 1)) and (x.get("trend_pct") or 0) >= 65, "trend_pct"),
    ("cash_cow", "돈 잘 버는 회사", "영업이익률 20%↑·ROE 15%↑",
     lambda x: (x.get("op_margin") or 0) >= 20 and (x.get("roe") or 0) >= 15, "op_margin"),
    ("dividend", "고배당주", "최근 1년 배당수익률 4% 이상 흑자 회사",
     lambda x: (x.get("div_yield") or 0) >= 4 and (x.get("eps_ttm") or 0) > 0, "div_yield"),
    ("turnaround", "흑자 전환", "전년 같은 분기 적자 → 이번 분기 흑자",
     lambda x: bool(x.get("turnaround")), "op_yoy"),
]


def kr_table(prices: dict, extra: dict | None = None) -> list:
    """재무가 있는 국내 종목 전체 지표 행. prices: {종목: 종가}, extra: {종목: 붙일 값(퀀트 등)}"""
    from app.services import stock_master
    rows = []
    for sym in _load():
        p = prices.get(sym)
        m = kr_now(sym, p)
        if not m or "per" not in m:
            continue
        rows.append({"symbol": sym, "market": "KR", "name": (stock_master.get("KR", sym) or {}).get("name", sym),
                     **m, **((extra or {}).get(sym) or {})})
    return rows


def run_screen(rows: list, key: str, limit: int = 100) -> list:
    sc = next((s for s in KR_SCREENS if s[0] == key), None)
    if not sc:
        raise KeyError(key)
    _, _, _, cond, sort = sc
    out = [r for r in rows if cond(r)]
    desc = not sort.startswith("-")
    k = sort.lstrip("-")
    out.sort(key=lambda r: (r.get(k) is None, -(r.get(k) or 0) if desc else (r.get(k) or 0)))
    return out[:limit]


# ---------------- 미국: Yahoo ----------------

_yq: dict = {}         # symbol -> (ts, 값)
_YQ_TTL = 3600


def _yahoo_quotes_sync(symbols: list) -> dict:
    from yfinance.data import YfData
    yd = YfData()
    out = {}
    for i in range(0, len(symbols), 150):
        part = symbols[i:i + 150]
        j = yd.get_raw_json("https://query1.finance.yahoo.com/v7/finance/quote",
                            params={"symbols": ",".join(part), "formatted": "false", "lang": "en-US", "region": "US"})
        for q in (j.get("quoteResponse") or {}).get("result") or []:
            out[q["symbol"]] = quote_row(q)
    return out


def quote_row(q: dict) -> dict:
    """Yahoo 시세 한 줄 → 공통 형식 (없는 값은 None)"""
    def r(v, n=2):
        return round(float(v), n) if isinstance(v, (int, float)) and np.isfinite(v) else None
    pe = r(q.get("trailingPE"))
    return {"price": r(q.get("regularMarketPrice")), "change_rate": r(q.get("regularMarketChangePercent")),
            "change_52w": r(q.get("fiftyTwoWeekChangePercent"), 1),
            "per": pe if pe and pe > 0 else None, "forward_per": r(q.get("forwardPE")),
            "pbr": r(q.get("priceToBook")), "div_yield": r(q.get("dividendYield")),
            "market_cap": q.get("marketCap"), "eps_ttm": r(q.get("epsTrailingTwelveMonths")),
            "name_en": q.get("shortName") or q.get("longName")}


async def yahoo_quotes(symbols: list) -> dict:
    """미국 종목 여러 개 시세·가치 지표 (1시간 캐시). 실패하면 예외 (가짜 값 없음)"""
    now = time.time()
    need = [s for s in symbols if s not in _yq or now - _yq[s][0] > _YQ_TTL]
    if need:
        got = await asyncio.get_event_loop().run_in_executor(None, _yahoo_quotes_sync, need)
        for s, v in got.items():
            _yq[s] = (now, v)
    return {s: _yq[s][1] for s in symbols if s in _yq}


def _us_screens():
    from yfinance import EquityQuery as Q
    base = [Q("eq", ["region", "us"]), Q("is-in", ["exchange", "NMS", "NYQ", "ASE"]), Q("gt", ["intradaymarketcap", 2e9])]
    return [
        ("undervalued_growth", "저평가 성장주", "Yahoo '저평가 성장주' — 이익이 25%↑ 늘 것으로 예상되는데 PEG·PER 이 낮은 회사", "undervalued_growth_stocks"),
        ("growth", "성장 기대주", "최근 1년 매출 15%↑·주당순이익 25%↑ 성장 (시가총액 20억 달러↑)",
         Q("and", base + [Q("gt", ["totalrevenues1yrgrowth.lasttwelvemonths", 15]), Q("gt", ["epsgrowth.lasttwelvemonths", 25])])),
        ("steady_growth", "안정 성장주", "매출 5~30% 성장·ROE 15%↑·부채비율 100% 이하 (시가총액 100억 달러↑)",
         Q("and", base + [Q("btwn", ["totalrevenues1yrgrowth.lasttwelvemonths", 5, 30]), Q("gt", ["returnonequity.lasttwelvemonths", 15]),
                          Q("btwn", ["totaldebtequity.lasttwelvemonths", 0, 100]), Q("gt", ["intradaymarketcap", 1e10])])),
        ("cheap_value", "아직 저렴한 가치주", "PBR 1.5배 이하·PER 15배 이하 흑자 회사",
         Q("and", base + [Q("btwn", ["pricebookratio.quarterly", 0, 1.5]), Q("btwn", ["peratio.lasttwelvemonths", 0, 15])])),
        ("high_roe_cheap", "고수익 저평가", "ROE 20% 이상인데 PER 15배 이하",
         Q("and", base + [Q("gt", ["returnonequity.lasttwelvemonths", 20]), Q("btwn", ["peratio.lasttwelvemonths", 0, 15])])),
        ("value_breakout", "저평가 탈출", "PER 15배 이하인데 최근 1년 주가 +10% 넘게 오른 회사",
         Q("and", base + [Q("btwn", ["peratio.lasttwelvemonths", 0, 15]), Q("gt", ["fiftytwowkpercentchange", 10])])),
        ("cash_cow", "돈 잘 버는 회사", "순이익률 20%↑·ROE 20%↑ (시가총액 100억 달러↑)",
         Q("and", base + [Q("gt", ["netincomemargin.lasttwelvemonths", 20]), Q("gt", ["returnonequity.lasttwelvemonths", 20]),
                          Q("gt", ["intradaymarketcap", 1e10])])),
        ("dividend", "미래의 배당왕", "배당을 3년 넘게 연속으로 늘렸고 주당순이익도 늘고 있는 회사",
         Q("and", base + [Q("gte", ["consecutive_years_of_dividend_growth_count", 3]), Q("gt", ["epsgrowth.lasttwelvemonths", 0])])),
    ]


US_SCREEN_KEYS = ["undervalued_growth", "growth", "steady_growth", "cheap_value", "high_roe_cheap", "value_breakout", "cash_cow", "dividend"]


def us_screen_meta() -> list:
    return [{"key": k, "name": n, "about": a} for k, n, a, _ in _us_screens()]


def us_screen_sync(key: str, limit: int = 100) -> dict:
    """Yahoo 스크리너 조건 검색 (시가총액 큰 순). 우선주(-P…)는 뺌"""
    import yfinance as yf
    from app.services import stock_master
    sc = next((s for s in _us_screens() if s[0] == key), None)
    if not sc:
        raise KeyError(key)
    q = sc[3]
    resp = yf.screen(q, count=limit) if isinstance(q, str) else \
        yf.screen(q, size=min(limit, 250), sortField="intradaymarketcap", sortAsc=False)
    quotes = (resp or {}).get("quotes")
    if quotes is None:
        raise RuntimeError(f"Yahoo 스크리너({key}) 응답에 결과가 없음")
    rows = []
    for x in quotes:
        sym = x.get("symbol") or ""
        if not sym or re.search(r"-P[A-Z]?$", sym) or x.get("quoteType", "EQUITY") != "EQUITY":
            continue
        m = stock_master.get("US", sym) or stock_master.get("US", sym.replace("-", "/")) or {}
        rows.append({"symbol": sym, "market": "US", "name": m.get("name") or x.get("shortName") or sym,
                     "exchange": m.get("exchange"), **quote_row(x)})
    return {"items": rows, "total": (resp or {}).get("total")}

