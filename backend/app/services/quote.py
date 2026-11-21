"""종목 시세 + 분석 공통 모듈 (투자종목·관심종목·종목탐색·AI추천이 같이 사용)

- 국내(KR): KIS 일봉/현재가 (실시간, 공식 종목코드 기준)
- 미국(US): yfinance 배치 다운로드
- 뉴스 분위기: news.py (10분 캐시)
- 예측 대상일: market_calendar.py (휴장일 반영한 다음 거래일)
- USD/KRW 환율: yfinance KRW=X

속도: 일봉은 60초 캐시 → 같은 종목을 여러 화면에서 봐도 KIS/yfinance 를 다시 부르지 않는다.
"""
import asyncio
import copy
import json
import time

import pandas as pd
import yfinance as yf

from app.services.kis_api import kis_client
from app.services import stock_master
from app.services.news import get_news_many
from app.services.extras import get_extra
from app.services import ml_model, flows, events
from app.services.market_calendar import prediction_target, market_today, is_market_open
from app.services.analysis import calc_technical_indicators, predict_next_day, classify_investment_style

_CHART_TTL = 60.0
_kr_chart_cache: dict = {}   # symbol -> {"ts", "count", "chart"}
_us_hist_cache: dict = {}    # (symbol, period) -> {"ts", "candles"}
_fx_cache: dict = {}


# ---------------- 원천 데이터 ----------------

def batch_yf_history_sync(tickers: list, period: str = "6mo") -> dict:
    """yfinance 배치 다운로드 → {ticker: [candles]} (날짜 오름차순)"""
    if not tickers:
        return {}
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False, threads=True)
    if data is None or data.empty:
        return {t: [] for t in tickers}

    is_multi = isinstance(data.columns, pd.MultiIndex)
    results = {}
    for sym in tickers:
        if is_multi:
            if sym not in data.columns.get_level_values(1):
                results[sym] = []
                continue
            cols = {k: data[k][sym] for k in ("Close", "Open", "High", "Low", "Volume")}
        else:
            cols = {k: data[k] for k in ("Close", "Open", "High", "Low", "Volume")}
        close = cols["Close"]
        candles = []
        for ts in close.dropna().index:
            c = float(close[ts])
            if c <= 0:
                continue

            def v(k, default):
                x = cols[k][ts]
                return default if pd.isna(x) else float(x)

            candles.append({
                "date": str(ts.date()),
                "open": v("Open", c), "high": v("High", c), "low": v("Low", c),
                "close": c, "volume": int(v("Volume", 0)),
            })
        results[sym] = candles
    return results


async def batch_yf_history(tickers: list, period: str = "6mo") -> dict:
    """캐시를 거친 yfinance 배치 다운로드 (캐시에 없는 종목만 받음)"""
    now = time.time()
    out, missing = {}, []
    for t in tickers:
        hit = _us_hist_cache.get((t, period))
        if hit and now - hit["ts"] < _CHART_TTL:
            out[t] = hit["candles"]
        else:
            missing.append(t)
    if missing:
        fetched = await asyncio.get_event_loop().run_in_executor(None, lambda: batch_yf_history_sync(missing, period))
        for t, c in fetched.items():
            _us_hist_cache[(t, period)] = {"ts": now, "candles": c}
            out[t] = c
    return out


async def kr_chart(symbol: str, count: int = 100) -> dict:
    hit = _kr_chart_cache.get(symbol)
    if hit and time.time() - hit["ts"] < _CHART_TTL and hit["count"] >= count:
        return hit["chart"]
    chart = await kis_client.get_kr_chart(symbol, count)
    _kr_chart_cache[symbol] = {"ts": time.time(), "count": count, "chart": chart}
    return chart


# ---------------- 분석 ----------------

_analysis_memo: dict = {}   # 입력이 같으면 다시 계산하지 않음 (장 마감 후·가격 그대로인 종목은 15초 갱신마다 재계산 불필요)


def _memo_key(market, candles, per, pbr, news, extra, symbol):
    last = tuple((c["date"], c["close"], c["high"], c["low"], c.get("volume")) for c in candles[-2:])
    n = (news or {})
    return (market, symbol, len(candles), candles[0]["date"], last, per, pbr,
            (n.get("pos"), n.get("neg"), n.get("total"), n.get("error")),
            json.dumps(extra, sort_keys=True, default=str) if extra else None,
            ml_model._ctx.get("ts"), tuple(id(ml_model.load(v)) for v in ml_model.VARIANT_FEATURES),
            len(flows.series(symbol)) if symbol and market == "KR" else 0, events.version(),
            market_today(market))  # 날짜가 바뀌면 대상일 라벨이 달라지므로


def analyze_candles(market: str, candles: list, per: float = 0, pbr: float = 0, news: dict | None = None,
                    extra: dict | None = None, symbol: str | None = None) -> dict:
    key = _memo_key(market, candles, per, pbr, news, extra, symbol)
    hit = _analysis_memo.get(key)
    if hit is not None:
        return copy.deepcopy(hit)
    out = _analyze_candles(market, candles, per, pbr, news, extra, symbol)
    if len(_analysis_memo) > 2000:
        _analysis_memo.clear()
    _analysis_memo[key] = copy.deepcopy(out)
    return out


def _analyze_candles(market: str, candles: list, per: float = 0, pbr: float = 0, news: dict | None = None,
                     extra: dict | None = None, symbol: str | None = None) -> dict:
    indicators = calc_technical_indicators(candles)
    model = None
    if symbol:
        try:
            model = ml_model.live_predict(market, symbol, candles)
        except Exception as e:  # 부가 기능 — 실패하면 규칙 점수로 (화면에 사유 표시)
            model = {"status": f"학습 모델 계산 실패: {e}"}
    prediction = predict_next_day(candles, indicators, news, extra, model)
    prediction.update(prediction_target(market, candles[-1]["date"]))
    # 대상일에 걸린 변동성 이벤트(FOMC·CPI 발표, 옵션 만기일) — 확률은 그대로, 경고만
    ev = events.warnings_for(market, prediction["target_date"])
    if ev:
        prediction["events"] = ev
        prediction["warnings"] = (prediction.get("warnings") or []) + ev
        prediction["summary"] = (prediction.get("summary") or "") + "".join(f" · ⚠ {w}" for w in ev)
    prediction["base_date"] = candles[-1]["date"][:10]
    return {
        "indicators": indicators,
        "prediction": prediction,
        "style": classify_investment_style(candles, indicators, per, pbr),
    }


def _kr_result(symbol: str, chart: dict, news: dict | None) -> dict:
    master = stock_master.get("KR", symbol) or {}
    candles = chart["candles"]
    item = {"market": "KR", "name": master.get("name") or chart["name"], "type": master.get("type", "stock")}
    return {
        "symbol": symbol,
        "market": "KR",
        "name": item["name"],
        "type": item["type"],
        "category": stock_master.category(item),
        "price": chart["price"],
        "change_rate": chart["change_rate"],
        "per": chart["per"],
        "pbr": chart["pbr"],
        "volume": candles[-1]["volume"],
        "candles": candles,
        "news": _news_brief(news),
        "flows": flows.summary(symbol),
        **analyze_candles("KR", candles, chart["per"], chart["pbr"], news, get_extra("KR", symbol), symbol),
    }


_US_VAL_TTL = 12 * 3600
_us_val_cache: dict = {}   # symbol -> {"ts", "data"}


async def us_valuations(symbols: list) -> dict:
    """미국 종목 PER·PBR (KIS 해외주식 현재가상세, 12시간 캐시). ETF 는 건너뜀.
    부가 정보라 실패하면 그 종목만 빠지고(PER 표시 안 함) 로그를 남긴다."""
    now = time.time()
    out, todo = {}, []
    for s in symbols:
        m = stock_master.get("US", s) or {}
        if m.get("type") == "etf":
            continue
        hit = _us_val_cache.get(s)
        if hit and now - hit["ts"] < _US_VAL_TTL:
            out[s] = hit["data"]
        else:
            todo.append((s, m.get("exchange") or "NAS"))

    async def one(s, ex):
        try:
            v = await kis_client.get_us_valuation(s, ex)
            _us_val_cache[s] = {"ts": time.time(), "data": v}
            out[s] = v
        except Exception as e:
            print(f"[quote] {s} PER/PBR 조회 실패: {e}")
    await asyncio.gather(*[one(s, ex) for s, ex in todo])
    return out


def _us_result(symbol: str, candles: list, news: dict | None, val: dict | None = None) -> dict:
    master = stock_master.get("US", symbol) or {}
    per, pbr = (val or {}).get("per", 0), (val or {}).get("pbr", 0)
    price = candles[-1]["close"]
    prev = candles[-2]["close"] if len(candles) >= 2 else price
    return {
        "symbol": symbol,
        "market": "US",
        "name": master.get("name") or symbol,
        "type": master.get("type", "stock"),
        "category": stock_master.category({"market": "US", **master}),
        "exchange": master.get("exchange", "NAS"),
        "price": round(price, 2),
        "change_rate": round((price - prev) / prev * 100, 2) if prev > 0 else 0.0,
        "per": per, "pbr": pbr,
        "volume": candles[-1]["volume"],
        "candles": candles,
        "news": _news_brief(news),
        **analyze_candles("US", candles, per, pbr, news=news, extra=get_extra("US", symbol), symbol=symbol),
    }


def _news_brief(news: dict | None) -> dict | None:
    if not news:
        return None
    return {k: news.get(k) for k in ("total", "pos", "neg", "error", "source")} | {"headlines": news.get("headlines", [])[:5]}


async def analyze_kr(symbol: str, count: int = 100, with_news: bool = True) -> dict:
    """국내 종목 1개: KIS 현재가 + 일봉 + 분석"""
    chart, news = await asyncio.gather(
        kr_chart(symbol, count),
        get_news_many([("KR", symbol)]) if with_news else _none(),
    )
    return _kr_result(symbol, chart, (news or {}).get(("KR", symbol)))


async def analyze_kr_many(symbols: list, count: int = 100, with_news: bool = True) -> dict:
    """국내 종목 여러 개 (KIS 호출은 kis_client 가 초당 제한에 맞춰 보냄)"""
    async def one(s):
        try:
            return s, await kr_chart(s, count)
        except Exception as e:
            return s, e
    charts, news = await asyncio.gather(
        asyncio.gather(*[one(s) for s in symbols]),
        get_news_many([("KR", s) for s in symbols]) if with_news else _none(),
    )
    out = {}
    for s, chart in charts:
        if isinstance(chart, Exception):
            out[s] = {"symbol": s, "market": "KR", "error": str(chart)}
        else:
            out[s] = _kr_result(s, chart, (news or {}).get(("KR", s)))
    return out


async def analyze_us_many(symbols: list, period: str = "6mo", with_news: bool = True) -> dict:
    """미국 종목 여러 개 (yfinance 배치 1회) → {symbol: 결과 또는 {"error": ...}}"""
    hist, news, vals = await asyncio.gather(
        batch_yf_history(symbols, period),
        get_news_many([("US", s) for s in symbols]) if with_news and symbols else _none(),
        us_valuations(symbols),
    )
    out = {}
    for s in symbols:
        candles = hist.get(s, [])
        if len(candles) < 20:
            out[s] = {"symbol": s, "market": "US", "error": f"yfinance 가격 데이터 부족 ({len(candles)}일)"}
        else:
            out[s] = _us_result(s, candles, (news or {}).get(("US", s)), vals.get(s))
    return out


async def analyze_items(items: list, period: str = "6mo") -> dict:
    """[{market, symbol}, ...] → {(market, symbol): 결과}"""
    kr = [i["symbol"] for i in items if i["market"] == "KR"]
    us = [i["symbol"] for i in items if i["market"] == "US"]
    kr_res, us_res = await asyncio.gather(
        analyze_kr_many(kr) if kr else _empty(),
        analyze_us_many(us, period) if us else _empty(),
    )
    out = {("KR", k): v for k, v in kr_res.items()}
    out.update({("US", k): v for k, v in us_res.items()})
    return out


async def _empty():
    return {}


async def _none():
    return None


def strip_candles(d: dict) -> dict:
    """응답 크기 줄이기 — 목록 화면에는 캔들 전체가 필요 없음"""
    return {k: v for k, v in d.items() if k != "candles"}


# ---------------- 실시간 갱신 (AI 추천) ----------------

async def live_prices(items: list) -> dict:
    """현재가만 빠르게: 국내 KIS 현재가, 미국 yfinance 1분봉 마지막 값 → {(market, symbol): {price, change_rate}}"""
    kr = [i["symbol"] for i in items if i["market"] == "KR"]
    us = [i["symbol"] for i in items if i["market"] == "US"]

    async def kr_one(s):
        try:
            p = await kis_client.get_kr_stock_price(s)
            return ("KR", s), {"price": p["price"], "change_rate": p["change_rate"], "volume": p["volume"]}
        except Exception as e:
            return ("KR", s), {"error": str(e)}

    async def kr_all():
        """30종목씩 멀티종목 시세 1번 호출 (종목마다 1번씩 부르던 것보다 KIS 호출 수가 1/30)
        → 멀티 호출이 실패했거나 응답에 빠진 종목만 같은 KIS 의 종목별 현재가로 다시"""
        got: dict = {}
        for i in range(0, len(kr), 30):
            chunk = kr[i:i + 30]
            try:
                for code, v in (await kis_client.get_kr_multi_price(chunk)).items():
                    got[("KR", code)] = v
            except Exception as e:
                print(f"[quote] 멀티종목 시세 실패 → 종목별 조회: {str(e)[:120]}")
        rest = [s for s in kr if ("KR", s) not in got]
        return list(got.items()) + list(await asyncio.gather(*[kr_one(s) for s in rest]))

    def us_sync():
        if not us:
            return {}
        data = yf.download(us, period="1d", interval="1m", progress=False, auto_adjust=True, threads=True)
        out = {}
        if data is None or data.empty:
            return out
        multi = isinstance(data.columns, pd.MultiIndex)
        for s in us:
            try:
                col = data["Close"][s] if multi else data["Close"]
                col = col.dropna()
                if len(col):
                    out[("US", s)] = {"price": round(float(col.iloc[-1]), 2)}
            except KeyError:
                pass
        return out

    kr_res, us_res = await asyncio.gather(
        kr_all(),
        asyncio.get_event_loop().run_in_executor(None, us_sync),
    )
    out = dict(kr_res)
    out.update(us_res)
    return out


def patch_candles(market: str, candles: list, live: dict) -> list:
    """일봉의 오늘 봉을 실시간 현재가로 갱신 (오늘 봉이 아직 없고 장중이면 새로 추가)"""
    price = live.get("price")
    if not price or not candles:
        return candles
    cs = copy.deepcopy(candles)
    last = cs[-1]
    today = market_today(market).isoformat()
    if last["date"][:10] == today:
        last["close"] = price
        last["high"] = max(last["high"], price)
        last["low"] = min(last["low"], price)
        if live.get("volume"):
            last["volume"] = live["volume"]
    elif is_market_open(market) and last["date"][:10] < today:
        cs.append({"date": today, "open": price, "high": price, "low": price, "close": price,
                   "volume": live.get("volume", 0)})
    return cs


# ---------------- 환율 ----------------

async def get_usdkrw() -> float:
    hit = _fx_cache.get("usdkrw")
    if hit and time.time() - hit["ts"] < 300:
        return hit["rate"]

    def _fetch():
        hist = yf.Ticker("KRW=X").history(period="5d")
        if hist.empty:
            raise RuntimeError("USD/KRW 환율 데이터 없음 (yfinance KRW=X)")
        return float(hist["Close"].dropna().iloc[-1])
    rate = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    _fx_cache["usdkrw"] = {"ts": time.time(), "rate": rate}
    return rate
