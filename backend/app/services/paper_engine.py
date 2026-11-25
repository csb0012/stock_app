"""AI 모의투자 엔진 — 계산만 (DB·외부 호출 없음). 과거 시뮬레이션과 실시간 모의투자가 같은 판단 함수를 쓴다.

판단 시점 = 어느 날 장 마감(종가) 직후. 그날까지의 일봉만으로 점수를 매기고 주문을 낸 뒤,
주문은 **다음 거래일 시가**에 체결된다 (그날 종가를 보고 그날 종가에 사는 일은 없음 → 다음 날 데이터를 모르는 상태).

종목별 'AI 점수' (0~100, 50 = 중립) — 앱의 기존 분석 네 가지를 합침
  상승확률 45%  AI 추천과 같은 규칙 점수(RSI·MACD·볼린저·이평) 확률 (실시간은 학습 모델 포함 AI 추천 확률)
  퀀트 35%      퀀트 점수 화면과 같은 요인(모멘텀·추세·거래량 매집·안정성·고점 근접)의 종합 백분위.
               요인 비중은 그날 이미 결과(20거래일 뒤 수익률)가 나온 과거 날짜들로만 정함
  매집 20%      매집 탐지 점수 (40점 넘는 만큼 가산, 이미 급등·거래대금 부족 종목은 0)
시장·일정 (경제 캘린더·시장 상태)
  시장 상태     지수 50·200일선 (CAN SLIM 'M') — 상승 추세 100% / 상승 압박 60% / 하락 추세 30% 까지만 주식 보유
  이벤트        다음 거래일에 FOMC·CPI·고용·GDP·PCE 발표(국내는 간밤 결과 반영일)나 옵션 만기일이면 새 매수 금액 절반
매매 규칙 (사용자가 바꿀 수 있음)
  매수: AI 점수 ≥ 매수 기준 + 상승확률 ≥ 55% 인 종목을 점수 높은 순으로, 최대 보유 종목 수까지 같은 금액(총자산 ÷ 종목 수)
  매도: 손절가(매입가 −손절%, 추격 손절이면 보유 중 최고 종가 기준으로 올라감) / 목표가(매입가 +익절%) 는 장중 도달 즉시,
        AI 점수 < 매도 기준 · 상승확률 ≤ 40% · 최대 보유일 도달은 다음 날 시가
  비용: 수수료(사고팔 때) + 증권거래세(국내, 팔 때) + 슬리피지(불리한 쪽으로 체결)
"""
import math

import numpy as np
import pandas as pd
from datetime import date, timedelta

from app.services import quant, accumulation
from app.services.analysis import calc_technical_indicators, predict_next_day
from app.services.market_regime import regime_frame
from app.services.market_calendar import is_trading_day

WINDOW = 130                 # 상승확률 계산에 쓰는 일봉 (AI 추천·백테스트와 같음)
WARMUP = 260                 # 시뮬레이션 시작 전에 필요한 일봉 (200일 고저·퀀트 비중 학습)
WEIGHTS = {"prob": 0.45, "quant": 0.35, "accum": 0.20}
REGIME_EXPOSURE = {"상승 추세": 1.0, "상승 압박": 0.6, "하락 추세": 0.3}
EVENT_SIZE = 0.5             # 이벤트 전날 새 매수 금액 배율
MIN_PROB = 55
SELL_PROB = 40
QUANT_MIN_N = 5              # 퀀트 비중(IC) 계산에 필요한 그날 최소 종목 수 (후보 종목이 수십 개라 전 종목용 20 보다 작게)
QUANT_REWEIGHT = 20          # 퀀트 비중 다시 정하는 주기 (거래일)
MIN_TV = {"KR": 1e8, "US": 1e6}   # 20일 평균 거래대금 하한 (원 / 달러)

COSTS = {
    "KR": {"fee": 0.00015, "tax": 0.0020, "slip": 0.0005, "currency": "KRW"},
    "US": {"fee": 0.0025, "tax": 0.0, "slip": 0.0005, "currency": "USD"},
}
CAPITAL = {"KR": (10_000_000, 1_000_000, 10_000_000_000), "US": (10_000, 1_000, 10_000_000)}   # 기본, 최소, 최대
# 이름: (기본값, 최소, 최대)
PARAMS = {
    "max_positions": (5, 1, 15),
    "buy_score": (60, 50, 90),
    "sell_score": (45, 20, 60),
    "stop_pct": (7.0, 2.0, 30.0),
    "take_pct": (15.0, 3.0, 100.0),
    "max_hold": (20, 2, 120),
}
PARAM_LABELS = {
    "max_positions": "최대 보유 종목 수", "buy_score": "매수 기준 AI 점수", "sell_score": "매도 기준 AI 점수",
    "stop_pct": "손절 %", "take_pct": "익절(목표) %", "max_hold": "최대 보유 거래일", "trailing": "추격 손절",
}


def clean_params(raw: dict | None) -> dict:
    """사용자 입력 → 범위 안의 값 (범위 밖이면 ValueError — 조용히 바꾸지 않음)"""
    raw = raw or {}
    out = {}
    for k, (dflt, lo, hi) in PARAMS.items():
        v = raw.get(k, dflt)
        if v is None:
            v = dflt
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{PARAM_LABELS[k]} 값이 숫자가 아님: {v}")
        if not (lo <= v <= hi) or math.isnan(v):
            raise ValueError(f"{PARAM_LABELS[k]} 는 {lo}~{hi} 사이여야 함 (입력 {v:g})")
        out[k] = int(v) if isinstance(dflt, int) else round(v, 2)
    if out["sell_score"] >= out["buy_score"]:
        raise ValueError("매도 기준 AI 점수는 매수 기준보다 낮아야 함")
    out["trailing"] = bool(raw.get("trailing", True))
    return out


def check_capital(market: str, capital) -> float:
    dflt, lo, hi = CAPITAL[market]
    try:
        c = float(capital if capital is not None else dflt)
    except (TypeError, ValueError):
        raise ValueError("시작 자금이 숫자가 아님")
    if not (lo <= c <= hi):
        unit = "원" if market == "KR" else "달러"
        raise ValueError(f"시작 자금은 {lo:,.0f}~{hi:,.0f}{unit} 사이여야 함")
    return c


# ---------------- 점수 ----------------

def ai_score(prob, qpct, accum, accum_ok) -> int:
    P = max(-1.0, min(1.0, (prob - 50) / 15)) if prob is not None else 0.0
    Q = (qpct - 50) / 50 if qpct is not None else 0.0
    A = max(0.0, min(1.0, (accum - 40) / 40)) if accum is not None and accum_ok else 0.0
    return int(round(50 + 50 * (WEIGHTS["prob"] * P + WEIGHTS["quant"] * Q + WEIGHTS["accum"] * A)))


def _prob_series(candles: list, from_date: str, to_date: str = "9999") -> dict:
    """날짜 d → d 종가까지의 일봉 130개로 낸 '다음 거래일 상승확률' (d 이후 데이터 안 씀)"""
    out = {}
    for i in range(len(candles)):
        d = candles[i]["date"][:10]
        if d < from_date or d > to_date:
            continue
        hist = candles[max(0, i + 1 - WINDOW): i + 1]
        if len(hist) < 30:
            continue
        out[d] = int(predict_next_day(hist, calc_technical_indicators(hist))["probability"])
    return out


def _quant_panel(frames: dict, market: str, from_date: str) -> dict:
    """{종목: (factor_frame, 일봉 날짜 목록)} → {(날짜, 종목): (종합 백분위, 등급)} (from_date 이후만).
    요인 비중은 QUANT_REWEIGHT 거래일마다, 그날까지 결과가 확정된(20거래일 뒤 날짜 ≤ 그날) 행으로만 다시 정함."""
    parts = []
    for sym, (f, dates) in frames.items():
        if f is None or f.empty:
            continue
        g = f.copy()
        g["fwd_date"] = pd.Series(dates).shift(-quant.HORIZON).reindex(g.index).values
        parts.append(g.assign(symbol=sym))
    if not parts:
        return {}
    df = pd.concat(parts, ignore_index=True)
    df = df[df["tv20"] >= MIN_TV[market]].dropna(subset=["rs"])
    if df.empty:
        return {}
    for k in quant.KEYS:
        df[f"p_{k}"] = df.groupby("date")[k].rank(pct=True).mul(98).add(1)
    df["excess"] = df["fwd20"] - df.groupby("date")["fwd20"].transform("median")
    w = {k: 1 / len(quant.KEYS) for k in quant.KEYS}
    out, since = {}, QUANT_REWEIGHT
    for d, g in df.groupby("date", sort=True):
        if d < from_date:
            continue
        if since >= QUANT_REWEIGHT:
            lab = df[df["fwd_date"].notna() & (df["fwd_date"] <= d)].dropna(subset=["fwd20"])
            if len(lab):
                w, _, _ = quant._weights(lab, QUANT_MIN_N)
            since = 0
        since += 1
        raw = sum(g[f"p_{k}"].fillna(50) * w[k] for k in quant.KEYS)
        comp = raw.rank(pct=True).mul(98).add(1) if len(g) > 1 else pd.Series(50.0, index=g.index)
        for sym, p in zip(g["symbol"], comp):
            out[(d, sym)] = (round(float(p)), quant.grade(float(p)))
    return out


def build_features(stocks: dict, market: str, from_date: str, prob_override: dict | None = None,
                   overrides: dict | None = None, to_date: str = "9999") -> dict:
    """stocks: {종목: {"name", "candles"(오름차순)}} → {날짜: {종목: 행}} (from_date 이후 날짜만).
    각 날짜의 행은 그날 종가까지의 데이터로만 계산.
    prob_override / overrides: 실시간용 — 마지막 날 상승확률(학습 모델 포함 AI 추천) / 전 종목 퀀트·매집 결과로 덮어씀"""
    probs, accs, qframes = {}, {}, {}
    for sym, s in stocks.items():
        cs = s["candles"]
        if len(cs) < 30:
            continue
        probs[sym] = _prob_series(cs, from_date, to_date)
        if len(cs) >= 120:
            af = accumulation.score_frame(cs)
            accs[sym] = {str(d)[:10]: (None if pd.isna(sc) else int(sc), bool(el))
                         for d, sc, el in zip(af["date"], af["score"], af["eligible"])}
        qf = quant.factor_frame(cs)
        qframes[sym] = (qf, [c["date"][:10] for c in cs])
    qp = _quant_panel(qframes, market, from_date)
    out: dict = {}
    for sym, s in stocks.items():
        for c in s["candles"]:
            d = c["date"][:10]
            if d < from_date or d not in probs.get(sym, {}):
                continue
            acc, ok = accs.get(sym, {}).get(d, (None, False))
            q = qp.get((d, sym))
            out.setdefault(d, {})[sym] = {
                "name": s.get("name") or sym, "close": float(c["close"]),
                "prob": probs[sym][d], "quant": q[0] if q else None, "grade": q[1] if q else None,
                "accum": acc, "accum_ok": ok,
            }
    last = max(out) if out else None
    if last:
        for sym, row in out[last].items():
            if prob_override and prob_override.get(sym) is not None:
                row["prob"] = int(prob_override[sym])
            o = (overrides or {}).get(sym) or {}
            if o.get("quant") is not None:
                row["quant"], row["grade"] = o["quant"], o.get("grade") or quant.grade(o["quant"])
            if o.get("accum") is not None:
                row["accum"], row["accum_ok"] = o["accum"], bool(o.get("accum_ok"))
    for rows in out.values():
        for row in rows.values():
            row["score"] = ai_score(row["prob"], row["quant"], row["accum"], row["accum_ok"])
    return out


def regime_map(index_candles: list) -> dict:
    """{날짜: 상태} (그날까지의 지수 데이터로만)"""
    if not index_candles or len(index_candles) < 200:
        return {}
    f = regime_frame(index_candles)
    return {d: s for d, s in zip(f["date"], f["state"]) if s}


def regime_on(rmap: dict, d: str, _keys: list | None = None):
    """d 이하 가장 최근 지수 날짜의 상태 (지수 데이터가 하루 늦어도 미래 값은 안 씀)"""
    keys = _keys if _keys is not None else sorted(rmap)
    i = np.searchsorted(keys, d, side="right") - 1
    return rmap[keys[i]] if i >= 0 else None


def _prev_trading_day(market: str, d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(market, d):
        d -= timedelta(days=1)
    return d


def event_labels(market: str, trade_day: str, macro: list) -> list:
    """거래일 trade_day 에 걸리는 변동성 이벤트 (events.warnings_for 와 같은 규칙, 일정 목록을 직접 받음).
    macro: [{"date", "event"}] 미국 주요 발표 일정 — 발표 일정은 미리 공개되므로 미래 데이터가 아님"""
    from app.services.events import option_expiry
    t = date.fromisoformat(trade_day[:10])
    out = []
    ox = option_expiry(market, t)
    if ox:
        out.append(ox.split(" (")[0])
    for e in macro:
        d = date.fromisoformat(e["date"][:10])
        name = e["event"].replace("미국 ", "")
        if market == "US" and d == t:
            out.append(f"{name} 발표일")
        elif market == "KR" and _prev_trading_day("KR", t) <= d < t:
            out.append(f"간밤 미국 {name} 결과 반영")
    return out


# ---------------- 계좌 상태 · 판단 · 체결 ----------------

def new_state(capital: float) -> dict:
    return {"cash": float(capital), "positions": {}}


def equity_of(state: dict, prices: dict) -> float:
    return state["cash"] + sum(p["qty"] * prices.get(s, p["last"]) for s, p in state["positions"].items())


def _fmt_reason(row: dict, regime, ev: list) -> str:
    parts = [f"상승확률 {row['prob']}%"]
    if row.get("quant") is not None:
        parts.append(f"퀀트 {row['grade']}({row['quant']})")
    if row.get("accum") is not None:
        parts.append(f"매집 {row['accum']}점" + ("" if row.get("accum_ok") else "(제외 조건)"))
    txt = f"AI 점수 {row['score']} — " + " · ".join(parts)
    if regime:
        txt += f" · 시장 {regime}"
    if ev:
        txt += f" · ⚠ {', '.join(ev)} → 금액 절반"
    return txt


def decide(state: dict, rows: dict, regime, events_next: list, params: dict, market: str) -> tuple:
    """장 마감 후 판단 → (주문 목록, 메모). 주문은 다음 거래일 시가(실시간은 다음 개장 직후 현재가)에 체결.
    rows: {종목: 그날 행}. state 의 positions 에 hold_days 가 있어야 함."""
    orders, notes = [], []
    prices = {s: r["close"] for s, r in rows.items()}
    equity = equity_of(state, prices)
    selling = set()
    for sym, p in state["positions"].items():
        r = rows.get(sym)
        if r is None:
            continue
        why = None
        if r["score"] < params["sell_score"]:
            why = f"AI 점수 {r['score']} (매도 기준 {params['sell_score']} 미만)"
        elif r["prob"] <= SELL_PROB:
            why = f"상승확률 {r['prob']}% (40% 이하 — 하락 예상)"
        elif p.get("hold_days", 0) >= params["max_hold"]:
            why = f"보유 {p['hold_days']}거래일 — 최대 보유일 도달"
        if why:
            orders.append({"side": "sell", "symbol": sym, "name": p["name"], "qty": p["qty"], "reason": why})
            selling.add(sym)

    exposure = REGIME_EXPOSURE.get(regime, 0.6)
    kept_value = sum(p["qty"] * prices.get(s, p["last"]) for s, p in state["positions"].items() if s not in selling)
    sell_value = sum(p["qty"] * prices.get(s, p["last"]) for s, p in state["positions"].items() if s in selling)
    c = COSTS[market]
    cash_est = state["cash"] + sell_value * (1 - c["fee"] - c["tax"] - c["slip"])
    room = min(cash_est, equity * exposure - kept_value)
    slots = params["max_positions"] - (len(state["positions"]) - len(selling))
    per = equity / params["max_positions"] * (EVENT_SIZE if events_next else 1.0)
    if exposure < 1:
        notes.append(f"시장 {regime} → 주식 비중 최대 {int(exposure * 100)}%")
    if events_next:
        notes.append(f"다음 거래일 {', '.join(events_next)} → 새 매수 금액 절반")
    cands = sorted(((s, r) for s, r in rows.items()
                    if s not in state["positions"] and r["score"] >= params["buy_score"] and r["prob"] >= MIN_PROB),
                   key=lambda kv: (-kv[1]["score"], -kv[1]["prob"], kv[0]))
    for sym, r in cands:
        if slots <= 0:
            break
        budget = min(per, room)
        if budget < r["close"] * (1 + c["fee"] + c["slip"]) * 1.02:   # 1주도 못 사면 (시가 변동 여유 2%)
            if room < per:
                notes.append("현금·비중 한도 때문에 더 못 삼")
                break
            continue
        orders.append({"side": "buy", "symbol": sym, "name": r["name"], "budget": round(budget, 2),
                       "reason": _fmt_reason(r, regime, events_next), "score": r["score"]})
        room -= budget
        slots -= 1
    if not cands:
        notes.append(f"매수 조건(AI 점수 {params['buy_score']}↑·상승확률 {MIN_PROB}%↑)에 맞는 종목 없음")
    return orders, notes


def _trade(day, sym, name, side, qty, price, fee, tax, reason, pnl=None, pnl_pct=None) -> dict:
    return {"date": day, "symbol": sym, "name": name, "side": side, "qty": int(qty), "price": round(price, 4),
            "amount": round(qty * price, 2), "fee": round(fee + tax, 2), "reason": reason,
            "pnl": None if pnl is None else round(pnl, 2), "pnl_pct": None if pnl_pct is None else round(pnl_pct, 2)}


def fill_buy(state: dict, sym: str, name: str, budget: float, price: float, day: str, reason: str,
             params: dict, market: str) -> dict | None:
    c = COSTS[market]
    px = price * (1 + c["slip"])
    qty = math.floor(min(budget, state["cash"]) / (px * (1 + c["fee"])))
    if qty < 1:
        return None
    cost = qty * px
    fee = cost * c["fee"]
    state["cash"] -= cost + fee
    state["positions"][sym] = {
        "name": name, "qty": qty, "avg": px, "buy_fee": fee, "entry_date": day, "hold_days": 0,
        "peak": px, "last": px, "stop": px * (1 - params["stop_pct"] / 100),
        "target": px * (1 + params["take_pct"] / 100), "reason": reason,
    }
    return _trade(day, sym, name, "buy", qty, px, fee, 0.0, reason)


def fill_sell(state: dict, sym: str, price: float, day: str, reason: str, market: str) -> dict | None:
    p = state["positions"].pop(sym, None)
    if p is None:
        return None
    c = COSTS[market]
    px = price * (1 - c["slip"])
    gross = p["qty"] * px
    fee, tax = gross * c["fee"], gross * c["tax"]
    state["cash"] += gross - fee - tax
    cost = p["qty"] * p["avg"] + p["buy_fee"]
    pnl = gross - fee - tax - cost
    return _trade(day, sym, p["name"], "sell", p["qty"], px, fee, tax, reason, pnl, pnl / cost * 100 if cost else 0)


def intraday_exit(p: dict, o: float, h: float, l: float) -> tuple | None:
    """그날 시가·고가·저가로 손절/목표 도달 확인 → (체결가, 사유). 둘 다 닿았으면 손절 먼저 (보수적으로)"""
    if o <= p["stop"]:
        return o, "손절 — 시가가 손절가 아래로 출발"
    if l <= p["stop"]:
        return p["stop"], f"손절가 도달 ({'추격 손절' if p['stop'] > p['avg'] * 0.999 else '매입가 대비'})"
    if o >= p["target"]:
        return o, "목표가 도달 — 시가부터 목표가 위"
    if h >= p["target"]:
        return p["target"], "목표가 도달"
    return None


def after_close(state: dict, closes: dict, params: dict):
    """종가 확정 후: 보유일 +1, 최고 종가·추격 손절가 갱신"""
    for sym, p in state["positions"].items():
        cl = closes.get(sym)
        if cl is None:
            continue
        p["last"] = cl
        if p["entry_date"] != closes.get("__day__"):
            p["hold_days"] = p.get("hold_days", 0) + 1
        p["peak"] = max(p["peak"], cl)
        if params.get("trailing"):
            p["stop"] = max(p["stop"], p["peak"] * (1 - params["stop_pct"] / 100))


# ---------------- 과거 시뮬레이션 ----------------

def simulate(stocks: dict, index_candles: list, macro: list, market: str, capital: float, start: str, end: str,
             params: dict, progress=None) -> dict:
    """과거 시뮬레이션. stocks 일봉은 start 전 WARMUP 개 이상 있어야 점수가 나옴.
    progress(단계, 완료, 전체) — 진행 표시용 (선택)."""
    if progress:
        progress("점수 계산 중 (그날까지의 데이터로만)", 0, 1)
    feats = build_features(stocks, market, start, to_date=end)
    days = sorted(d for d in feats if d <= end)
    if len(days) < 2:
        raise ValueError("시뮬레이션 기간에 거래일 데이터가 부족함")
    bars = {sym: {c["date"][:10]: c for c in s["candles"]} for sym, s in stocks.items()}
    rmap = regime_map(index_candles)
    rkeys = sorted(rmap)
    idx_close = {c["date"][:10]: float(c["close"]) for c in index_candles}
    idx_keys = sorted(idx_close)

    def idx_on(d):
        i = np.searchsorted(idx_keys, d, side="right") - 1
        return idx_close[idx_keys[i]] if i >= 0 else None

    state = new_state(capital)
    pending: list = []
    trades, curve, log = [], [], []
    bench0 = idx_on(days[0])
    exposure_sum = 0.0
    for k, d in enumerate(days):
        acts = []
        if k > 0:
            # 1) 시가 체결: 매도 먼저 (현금 확보) → 매수
            for o in sorted(pending, key=lambda x: x["side"] != "sell"):
                bar = bars.get(o["symbol"], {}).get(d)
                if bar is None:
                    acts.append(f"{o['name']} 거래 없음 — 주문 취소")
                    continue
                if o["side"] == "sell":
                    t = fill_sell(state, o["symbol"], float(bar["open"]), d, o["reason"], market)
                else:
                    t = fill_buy(state, o["symbol"], o["name"], o["budget"], float(bar["open"]), d, o["reason"], params, market)
                    if t is None:
                        acts.append(f"{o['name']} 매수 취소 — 시가 상승으로 1주도 못 삼")
                if t:
                    trades.append(t)
                    acts.append(_act_text(t, market))
            pending = []
            # 2) 장중 손절·목표가
            for sym in list(state["positions"]):
                bar = bars.get(sym, {}).get(d)
                if bar is None:
                    continue
                hit = intraday_exit(state["positions"][sym], float(bar["open"]), float(bar["high"]), float(bar["low"]))
                if hit:
                    t = fill_sell(state, sym, hit[0], d, hit[1], market)
                    trades.append(t)
                    acts.append(_act_text(t, market))
        # 3) 종가: 평가 · 다음 날 주문 판단
        closes = {sym: float(bars[sym][d]["close"]) for sym in state["positions"] if d in bars.get(sym, {})}
        closes["__day__"] = d
        after_close(state, closes, params)
        prices = {s: p["last"] for s, p in state["positions"].items()}
        eq = equity_of(state, prices)
        invested = eq - state["cash"]
        exposure_sum += invested / eq if eq else 0
        regime = regime_on(rmap, d, rkeys)
        b = idx_on(d)
        curve.append({"date": d, "equity": round(eq, 2), "cash": round(state["cash"], 2),
                      "bench": round(capital * b / bench0, 2) if b and bench0 else None})
        notes, top = [], []
        if k < len(days) - 1:
            ev = event_labels(market, days[k + 1], macro)
            pending, notes = decide(state, feats[d], regime, ev, params, market)
            top = [{"symbol": s, "name": r["name"], "score": r["score"], "prob": r["prob"]}
                   for s, r in sorted(feats[d].items(), key=lambda kv: -kv[1]["score"])[:3]]
            acts += [f"주문(다음 날 시가): {'매수' if o['side'] == 'buy' else '매도'} {o['name']} — {o['reason']}" for o in pending]
        log.append({"date": d, "regime": regime, "equity": round(eq, 2), "actions": acts, "notes": notes, "top": top})
        if progress and k % 10 == 0:
            progress("매매 시뮬레이션 중", k + 1, len(days))
    return {"summary": summarize(curve, trades, capital, exposure_sum / len(days)), "equity": curve, "trades": trades,
            "log": log, "positions": positions_view(state, market), "days": len(days)}


def _act_text(t: dict, market: str) -> str:
    money = (lambda v: f"₩{v:,.0f}") if market == "KR" else (lambda v: f"${v:,.2f}")
    if t["side"] == "buy":
        return f"매수 {t['name']} {t['qty']}주 @ {money(t['price'])}"
    return f"매도 {t['name']} {t['qty']}주 @ {money(t['price'])} ({t['pnl_pct']:+.1f}%) — {t['reason']}"


def positions_view(state: dict, market: str) -> list:
    out = []
    for sym, p in state["positions"].items():
        out.append({"symbol": sym, "name": p["name"], "qty": p["qty"], "avg_price": round(p["avg"], 4),
                    "last": round(p["last"], 4), "ret_pct": round((p["last"] / p["avg"] - 1) * 100, 2),
                    "value": round(p["qty"] * p["last"], 2), "entry_date": p["entry_date"], "hold_days": p.get("hold_days", 0),
                    "stop": round(p["stop"], 4), "target": round(p["target"], 4), "reason": p.get("reason")})
    return sorted(out, key=lambda x: -x["value"])


def summarize(curve: list, trades: list, capital: float, avg_exposure: float = 0.0) -> dict:
    eq = [c["equity"] for c in curve]
    final = eq[-1] if eq else capital
    peak, mdd = -1e18, 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1 if peak > 0 else 0)
    sells = [t for t in trades if t["side"] == "sell" and t["pnl"] is not None]
    wins = [t for t in sells if t["pnl"] > 0]
    losses = [t for t in sells if t["pnl"] <= 0]
    gain, loss = sum(t["pnl"] for t in wins), -sum(t["pnl"] for t in losses)
    bench = [c.get("bench") for c in curve if c.get("bench")]
    bench_ret = (bench[-1] / bench[0] - 1) * 100 if len(bench) >= 2 else None
    ret = (final / capital - 1) * 100
    return {
        "start": curve[0]["date"] if curve else None, "end": curve[-1]["date"] if curve else None,
        "capital": capital, "final_equity": round(final, 2), "return_pct": round(ret, 2),
        "bench_return_pct": None if bench_ret is None else round(bench_ret, 2),
        "excess_pct": None if bench_ret is None else round(ret - bench_ret, 2),
        "mdd_pct": round(mdd * 100, 2), "trades": len(sells), "buys": len([t for t in trades if t["side"] == "buy"]),
        "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else None,
        "avg_win_pct": round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else None,
        "avg_loss_pct": round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else None,
        "profit_factor": round(gain / loss, 2) if loss > 0 else None,
        "fees": round(sum(t["fee"] for t in trades), 2), "avg_exposure_pct": round(avg_exposure * 100, 1),
    }
