"""장기 보유 분석 — 과거 월봉으로 '그때 사서 N년 들고 있었다면' 을 전부 계산

- 데이터: 국내 = KIS 월봉(수정주가, 배당 제외) / 미국·지수 = yfinance 월봉(배당·분할 반영 수정주가).
  비교 지수: 국내 = 코스피(^KS11), 미국 나스닥 상장 = 나스닥 종합(^IXIC), 그 외 = S&P 500(^GSPC)
- 보유 기간 H(개월)마다, 데이터의 모든 달을 '산 달'로 놓고 H개월 뒤 수익률을 구함(겹치는 구간):
  이익 확률(수익률 > 0 비율), 하위 10%·중간값·상위 10% 수익률, 최악·최고, 연평균(중간값 기준), 지수보다 나았던 비율
- 보유 기간 제안: 그 기간 이상 들고 있으면 과거 모든 구간에서 이익 확률 90% 이상 / 손실 구간 0 이 된 가장 짧은 기간
- 최대 낙폭(고점 대비 최대 하락)·회복 기간·지금 고점 대비 위치·연평균 수익률·연 변동성
- 장기 점수(0~100) = 5년 이익 확률 40 + 5년 지수 대비 우위 30 + 최대 낙폭 20 + 데이터 길이 10
과거 통계일 뿐 미래 보장이 아님. 특히 후보가 '지금 살아남은 유명 종목'이라 과거 성적이 좋게 나오는 쪽으로 치우침(생존 편향).
"""
import asyncio
import math
from datetime import datetime

import pandas as pd
import yfinance as yf

from app.core.swr import SWRCache

SCAN = [12, 24, 36, 48, 60, 72, 84, 96, 108, 120, 144, 180, 240]   # 보유 기간 후보 (개월)
SHOW = [12, 36, 60, 120]                                              # 화면에 보여줄 보유 기간
MIN_WINDOWS = 24   # 구간이 이보다 적으면 통계를 내지 않음 (2년치 이상의 '산 달')
BENCH = {"KR": ("^KS11", "코스피"), "NAS": ("^IXIC", "나스닥 종합"), "US": ("^GSPC", "S&P 500")}

DISCLAIMER = ("과거 월봉으로 '그때 사서 N년 보유했다면'을 모든 달에 대해 계산한 통계입니다. 미래를 보장하지 않으며, "
              "후보가 지금까지 살아남은 유명 종목이라 과거 성적이 실제보다 좋게 보일 수 있습니다(생존 편향). "
              "국내 종목은 배당 제외 주가 기준, 미국은 배당 포함 수정주가 기준입니다.")


# ---------------- 계산 (순수 함수) ----------------

def _mk(d: str) -> int:
    """'YYYY-MM-..' → 월 번호 (연*12 + 월-1)"""
    return int(d[:4]) * 12 + int(d[5:7]) - 1


def _label(mk: int) -> str:
    return f"{mk // 12}-{mk % 12 + 1:02d}"


def to_monthly(rows: list) -> dict:
    """[{date, close}] → {월 번호: 그달 마지막 종가} (0 이하·NaN·inf 제외)"""
    out = {}
    for r in sorted(rows or [], key=lambda x: x["date"]):
        try:
            c = float(r["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if c > 0 and math.isfinite(c):
            out[_mk(r["date"])] = c
    return out


def window_returns(m: dict, months: int) -> dict:
    """산 달 → months 개월 뒤 수익률 (둘 다 있는 달만)"""
    return {k: m[k + months] / m[k] - 1 for k in m if k + months in m}


def _q(xs: list, p: float) -> float:
    """정렬된 목록의 p 분위수 (선형 보간)"""
    if len(xs) == 1:
        return xs[0]
    i = (len(xs) - 1) * p
    lo = int(i)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def _r(x, digits=1):
    return None if x is None else round(x * 100, digits)


def _drawdown(keys: list, closes: list) -> dict:
    peak, peak_k = closes[0], keys[0]
    mdd, mdd_peak, mdd_trough, mdd_peak_val = 0.0, keys[0], keys[0], closes[0]
    for k, c in zip(keys, closes):
        if c > peak:
            peak, peak_k = c, k
        dd = c / peak - 1
        if dd < mdd:
            mdd, mdd_peak, mdd_trough, mdd_peak_val = dd, peak_k, k, peak
    recovered = next((k for k, c in zip(keys, closes) if k > mdd_trough and c >= mdd_peak_val), None)
    return {"max_drawdown": _r(mdd), "peak": _label(mdd_peak), "trough": _label(mdd_trough),
            "recovered": _label(recovered) if recovered is not None else None,
            "recovery_months": (recovered - mdd_trough) if recovered is not None else None,
            "from_high": _r(closes[-1] / max(closes) - 1)}


def horizon_stats(rows: list, bench_rows: list | None = None) -> dict:
    """월봉 → 보유 기간별 통계·제안·낙폭·점수. 데이터가 모자라면 enough=False 와 사유"""
    m = to_monthly(rows)
    if len(m) < 13:
        return {"enough": False, "months": len(m), "reason": f"월봉 {len(m)}개 — 1년치 이상 필요"}
    keys = sorted(m)
    closes = [m[k] for k in keys]
    span = keys[-1] - keys[0]
    bm = to_monthly(bench_rows) if bench_rows else {}

    rets = [math.log(m[k + 1] / m[k]) for k in keys if k + 1 in m]
    vol = (pd.Series(rets).std() * math.sqrt(12)) if len(rets) >= 12 else None

    horizons = {}
    for h in SCAN:
        w = window_returns(m, h)
        if len(w) < MIN_WINDOWS:
            continue
        rs = sorted(w.values())
        st = {"months": h, "windows": len(rs), "win": round(sum(r > 0 for r in rs) / len(rs) * 100, 1),
              "p10": _r(_q(rs, 0.1)), "p50": _r(_q(rs, 0.5)), "p90": _r(_q(rs, 0.9)),
              "worst": _r(rs[0]), "best": _r(rs[-1]),
              "ann_p50": _r((1 + _q(rs, 0.5)) ** (12 / h) - 1),
              "worst_start": _label(min(w, key=w.get))}
        bw = window_returns(bm, h) if bm else {}
        common = [k for k in w if k in bw]
        if len(common) >= MIN_WINDOWS:
            st["beat"] = round(sum(w[k] > bw[k] for k in common) / len(common) * 100, 1)
            st["bench_win"] = round(sum(bw[k] > 0 for k in common) / len(common) * 100, 1)
            st["bench_p50"] = _r(_q(sorted(bw[k] for k in common), 0.5))
        horizons[h] = st

    def shortest(ok) -> int | None:
        """그 기간 '이상' 모든 보유 기간에서 조건을 만족한 가장 짧은 기간 (긴 기간에 다시 손실이 있으면 인정 안 함)"""
        hs = sorted(horizons)
        for i, h in enumerate(hs):
            if all(ok(horizons[x]) for x in hs[i:]):
                return h
        return None

    hold90 = shortest(lambda s: s["win"] >= 90)
    no_loss = shortest(lambda s: s["win"] >= 100)
    dd = _drawdown(keys, closes)

    # 장기 점수 — 5년 보유 통계가 없으면 3년으로 (3년은 0.75배)
    base = horizons.get(60) or horizons.get(36)
    factor = 1.0 if 60 in horizons else 0.75
    parts = {
        "이익 확률": round((base["win"] / 100 * 40 * factor) if base else 0, 1),
        "지수 대비": round((base["beat"] / 100 * 30 * factor) if base and "beat" in base else (15 * factor if base else 0), 1),
        "낙폭": round(max(0.0, 1 + dd["max_drawdown"] / 80) * 20, 1),
        "기간": round(min(span / 12, 20) / 20 * 10, 1),
    }
    return {
        "enough": True, "start": _label(keys[0]), "end": _label(keys[-1]), "years": round(span / 12, 1),
        "cagr": _r((closes[-1] / closes[0]) ** (12 / span) - 1) if span else None,
        "volatility": _r(vol) if vol is not None and math.isfinite(vol) else None,
        **dd,
        "horizons": {str(h): horizons[h] for h in SHOW if h in horizons},
        "hold90_months": hold90, "no_loss_months": no_loss,
        "longest_months": max(horizons) if horizons else None,
        # 보유 기간 통계가 없으면(3년 미만) 점수를 매기지 않음
        "score": round(sum(parts.values())) if base else None, "score_parts": parts if base else None,
        "advice": advice(horizons, hold90, no_loss, dd),
    }


def _yrs(months: int) -> str:
    return f"{months // 12}년" if months % 12 == 0 else f"{months / 12:.1f}년"


def advice(horizons: dict, hold90, no_loss, dd: dict) -> str:
    if not horizons:
        return "데이터가 짧아(3년 미만) 보유 기간 통계를 낼 수 없음"
    longest = max(horizons)
    lines = []
    if no_loss:
        lines.append(f"과거 기록상 {_yrs(no_loss)} 이상 보유하면 손실 구간이 없었음")
    elif hold90:
        lines.append(f"과거 기록상 {_yrs(hold90)} 이상 보유하면 90% 이상 이익 (그래도 손실 구간 있음)")
    else:
        lines.append(f"과거 {_yrs(longest)} 보유해도 이익 확률 90% 미만 — 오래 들고 있는 것만으로는 안전하지 않았음")
    if hold90 and no_loss and hold90 < no_loss:
        lines.append(f"{_yrs(hold90)} 이상이면 90% 이상 이익")
    if dd["max_drawdown"] is not None and dd["max_drawdown"] > -1:
        lines.append("월말 종가 기준으로 1% 넘게 하락한 구간 없음")
    elif dd["max_drawdown"] is not None:
        rec = (f"{_yrs(dd['recovery_months'])} 만에 회복" if dd["recovery_months"] is not None else "아직 그 고점 회복 못 함")
        lines.append(f"최대 {dd['max_drawdown']}% 하락한 적 있음 ({dd['peak']}→{dd['trough']}, {rec})")
    return " · ".join(lines)


# ---------------- 데이터 받기 ----------------

def _yf_monthly_sync(tickers: list) -> dict:
    """yfinance 월봉 전체 기간 → {ticker: [{date, close}]}"""
    data = yf.download(tickers, period="max", interval="1mo", auto_adjust=True, progress=False, threads=True)
    out = {t: [] for t in tickers}
    if data is None or data.empty:
        return out
    close = data["Close"]
    for t in tickers:
        s = close[t] if isinstance(close, pd.DataFrame) and t in close.columns else (close if len(tickers) == 1 else None)
        if s is None:
            continue
        out[t] = [{"date": str(ts.date()), "close": float(v)} for ts, v in s.dropna().items()]
    return out


async def _kr_monthly(symbols: list) -> tuple:
    from app.services.kis_api import kis_client
    out, errors = {}, {}

    async def one(s):
        try:
            out[s] = await kis_client.get_kr_monthly(s)
        except Exception as e:
            errors[s] = str(e)[:150] or type(e).__name__
    await asyncio.gather(*(one(s) for s in symbols))
    return out, errors


def _bench_key(market: str, exchange: str | None) -> str:
    return "KR" if market == "KR" else ("NAS" if exchange == "NAS" else "US")


async def analyze(candidates: list) -> dict:
    """후보 [{symbol, market, exchange?}] → {items: {"KR-005930": 통계}, benchmarks, errors}"""
    kr = [c["symbol"] for c in candidates if c["market"] == "KR"]
    us = [c["symbol"] for c in candidates if c["market"] == "US"]
    bench_tickers = [t for t, _ in BENCH.values()]
    loop = asyncio.get_event_loop()
    (kr_rows, kr_err), yf_rows = await asyncio.gather(
        _kr_monthly(kr), loop.run_in_executor(None, lambda: _yf_monthly_sync(us + bench_tickers)))

    benchmarks, bench_rows = {}, {}
    for key, (t, name) in BENCH.items():
        rows = yf_rows.get(t) or []
        bench_rows[key] = rows
        st = horizon_stats(rows) if rows else {"enough": False, "reason": "지수 월봉 조회 실패 (Yahoo)"}
        benchmarks[key] = {"ticker": t, "name": name, **st}

    items, errors = {}, []
    for c in candidates:
        key = f"{c['market']}-{c['symbol']}"
        rows = kr_rows.get(c["symbol"]) if c["market"] == "KR" else yf_rows.get(c["symbol"])
        if not rows:
            err = kr_err.get(c["symbol"]) if c["market"] == "KR" else "Yahoo 월봉 없음"
            errors.append({"market": c["market"], "symbol": c["symbol"], "error": err or "월봉 없음"})
            continue
        bk = _bench_key(c["market"], c.get("exchange"))
        items[key] = {**horizon_stats(rows, bench_rows.get(bk)), "bench": bk, "bench_name": BENCH[bk][1]}
    if not items:
        raise RuntimeError("장기 분석 실패: " + "; ".join(f"{e['symbol']}: {e['error']}" for e in errors[:3]))
    return {"items": items, "benchmarks": benchmarks, "errors": errors, "disclaimer": DISCLAIMER,
            "computed_at": datetime.now().isoformat(timespec="seconds")}


# 월봉은 하루에 한 번 바뀌는 정도라 6시간 캐시, 일주일까지는 이전 값을 먼저 보여주고 뒤에서 갱신
_cache = SWRCache("longterm_horizon", fresh=6 * 3600, max_stale=7 * 24 * 3600)


async def get(candidates: list) -> dict:
    return await _cache.get("all", lambda: analyze(candidates))
