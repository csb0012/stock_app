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
개선 옵션 (기본 켬 — 과거 시뮬레이션이 같은 데이터로 '기본 방식'과 나란히 비교해 보여줌)
  학습형 가중치  상승확률·퀀트·매집의 비중을 고정값 대신, 그날까지 결과(10거래일 뒤 수익률)가 확정된 최근 120거래일에서
               '점수가 높을수록 실제로 더 올랐는지'(날짜별 순위 상관 IC)만큼 20거래일마다 다시 정함. 셋 다 안 맞으면 고정 비중.
               학습한 비중은 고정 비중과 반반 섞음(축소 추정) — 짧은 기간 결과에 과하게 맞추지 않게
  추세 필터     종가가 50일 이동평균 아래인 종목은 새로 사지 않음 (떨어지는 칼날 피하기 — 추세 추종)
AI 매도 판단 (ai_exit, 사용자 요청 2026-11-27 — 익절·손절·보유일을 고정 숫자 대신 AI 가 상황 보고 정함)
  'AI 강세' = 그날 종가 판단에서 매수 조건(AI 점수 ≥ 매수 기준 + 상승확률 ≥ 55%) 그대로 통과 — 새로 살 만한 종목이면 계속 들고 감
  익절 보류     목표가에 닿아도 AI 강세면 안 팔고, 손절가를 '닿은 목표가 −손절%' 로 올려 이익을 지키며 목표를 더 위로
  이익 지키기   이익 중(+3%↑)인데 상승확률 ≤ 45%(하락 쪽 확신)면 목표 전이라도 다음 날 판다
  손절 보류     매입가 아래 손절가에 닿아도 AI 강세면 바로 안 팔고 종가에 다시 판단 — 회복 기대 낮으면 판다
  강제 손절     첫 매입가 −min(손절%×2, 손절%+10)% (기본 −14%) 아래면 AI 판단과 상관없이 판다 (끝없이 버티지 않게)
  보유일 연장   최대 보유일이 돼도 AI 강세면 최대 2배까지 더 들고 감
  물타기 (avg_down, 따로 켬) 종가가 손절선 아래인데 AI 강세 + 시장이 하락 추세가 아니면 처음 산 금액의 절반만큼 한 번만 더 삼.
               물탄 뒤엔 손절 보류 없음 (새 평균가 기준 손절가를 그대로 지킴)
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
ADAPT_HORIZON = 10           # 학습형 가중치: 10거래일 뒤 수익률로 신호가 맞았는지 봄
ADAPT_LOOKBACK = 120         # 최근 120거래일 (결과가 확정된 날만)
ADAPT_MIN_DATES = 20         # 이보다 적으면 고정 비중
ADAPT_EVERY = 20             # 20거래일마다 다시 정함
ADAPT_SHRINK = 0.5           # 학습한 비중을 고정 비중과 반반 섞음 — 120일 결과는 들쭉날쭉해서 한 신호에 몰빵(100%)하지 않게
ADAPT_WARMUP_DAYS = 180      # 시뮬레이션 시작 전에도 점수를 계산해 두는 기간(달력) — 첫날부터 학습형 비중을 쓰기 위해
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
    "adaptive": "학습형 가중치", "trend_filter": "추세 필터 (50일선 아래는 안 삼)",
    "entry_guard": "급변 보호 (비싸게 출발하면 기다림 · 급락 출발이면 안 삼)",
    "ai_exit": "AI 매도 판단 (익절 보류·이익 지키기·손절 보류·보유일 연장, 강제 손절선은 지킴)",
    "avg_down": "물타기 (손절선 아래 + AI 강세면 처음 금액의 절반 1번)",
}
# 급변 보호 (KIS 모의투자 주문의 장중 규칙을 일봉으로 근사 — 장중 순서를 모르니 시가·저가로만):
#   시가가 판단 종가보다 +GUARD_GAP% 넘게 높으면 → 그날 저가가 종가×(1+GUARD_GAP%) 까지 내려오면 그 값에 삼, 아니면 안 삼
#   시가가 −2×GUARD_GAP% 넘게 낮으면(급락 출발) → 안 삼.  (10분 급락·VI·지수 보류는 일봉으로 알 수 없어 시뮬레이션에 없음)
GUARD_GAP = 3.0
# AI 매도 판단 (ai_exit / avg_down)
LOCK_PROFIT = 3.0            # 이익 지키기: 이만큼(%) 이익 중일 때
LOCK_PROB = 45               #   상승확률 이 값 이하(하락 쪽 확신 — 예측 검증의 '확신 예측' 기준)면 판다
HOLD_EXT = 2.0               # 보유일 연장: 최대 보유일의 몇 배까지
AVG_DOWN_RATIO = 0.5         # 물타기 금액 = 처음 산 금액 × 이 값 (한 번만)


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
    out["adaptive"] = bool(raw.get("adaptive", True))
    out["trend_filter"] = bool(raw.get("trend_filter", True))
    out["entry_guard"] = bool(raw.get("entry_guard", True))
    out["ai_exit"] = bool(raw.get("ai_exit", False))
    out["avg_down"] = bool(raw.get("avg_down", False))
    return out


# ---------------- AI 매도 판단 ----------------

def hard_pct(params: dict) -> float:
    """강제 손절 % (첫 매입가 대비) — AI 가 버티자고 해도 여기 아래면 판다"""
    return min(params["stop_pct"] * 2, params["stop_pct"] + 10)


def hard_stop(p: dict, params: dict) -> float:
    return float(p.get("entry_px") or p["avg"]) * (1 - hard_pct(params) / 100)


def ai_strong(r: dict | None, params: dict) -> bool:
    """AI 강세 = 지금 새로 사도 될 만큼 (매수 조건 그대로)"""
    return bool(r) and r["score"] >= params["buy_score"] and r["prob"] >= MIN_PROB


def loss_stop(p: dict) -> bool:
    """손절가가 매입가 아래(손실 쪽) — 추격 손절·익절 보류로 올라간 손절가(이익 지키기)는 AI 가 보류하지 않음"""
    return p["stop"] < p["avg"] * 0.9995


def can_hold_stop(p: dict, params: dict) -> bool:
    return bool(params.get("ai_exit")) and bool(p.get("ai_hold")) and loss_stop(p) and not p.get("added")


def ride(p: dict, params: dict) -> str:
    """익절 보류: 목표가에 닿았는데 AI 강세 → 손절가를 목표가 −손절% 로 올리고 목표를 더 위로 (p 를 바꿈) → 메모"""
    old = p["target"]
    p["stop"] = max(p["stop"], old * (1 - params["stop_pct"] / 100))
    p["target"] = old * (1 + params["take_pct"] / 200)
    p["rides"] = int(p.get("rides") or 0) + 1
    return (f"목표가 도달했지만 AI 가 더 오른다고 봐서 안 팖 — 손절가를 {(p['stop'] / p['avg'] - 1) * 100:+.1f}% 로 올려 이익 지킴 · "
            f"다음 검토 {(p['target'] / p['avg'] - 1) * 100:+.1f}%")


def live_exit(p: dict, px: float, params: dict) -> tuple | None:
    """장중 현재가 px 로 보유 종목 확인 → None 또는 (종류, 메모).
    종류: 'hard' 강제 손절 · 'stop' 손절 · 'target' 목표가 매도 · 'ride' 익절 보류(p 의 손절·목표를 바꿈) · 'hold' 손절 보류"""
    if params.get("ai_exit") and px <= hard_stop(p, params):
        return "hard", f"강제 손절선(첫 매입가 −{hard_pct(params):g}%) 도달 — AI 판단과 상관없이 매도"
    if px <= p["stop"]:
        if can_hold_stop(p, params):
            if p.get("stop_held"):
                return None
            p["stop_held"] = True
            return "hold", (f"손절가 도달했지만 AI 가 회복을 기대해 보류 — 종가에 다시 판단 · "
                            f"강제 손절선 {(hard_stop(p, params) / p['avg'] - 1) * 100:+.1f}%")
        return "stop", ("손절가 도달 (" + ("추격 손절" if not loss_stop(p) else "매입가 대비") + ")")
    if px >= p["target"]:
        if params.get("ai_exit") and p.get("ai_hold"):
            return "ride", ride(p, params)
        return "target", "목표가 도달"
    return None


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

def components(prob, qpct, accum, accum_ok) -> tuple:
    """상승확률·퀀트·매집을 -1~1 (매집은 0~1) 로"""
    P = max(-1.0, min(1.0, (prob - 50) / 15)) if prob is not None else 0.0
    Q = (qpct - 50) / 50 if qpct is not None else 0.0
    A = max(0.0, min(1.0, (accum - 40) / 40)) if accum is not None and accum_ok else 0.0
    return P, Q, A


def ai_score(prob, qpct, accum, accum_ok, weights: dict | None = None) -> int:
    w = weights or WEIGHTS
    P, Q, A = components(prob, qpct, accum, accum_ok)
    return int(round(50 + 50 * (w["prob"] * P + w["quant"] * Q + w["accum"] * A)))


def forward_labels(stocks: dict, horizon: int = ADAPT_HORIZON) -> dict:
    """{(날짜, 종목): (결과 확정일, horizon 거래일 뒤 수익률)} — 학습형 가중치 전용.
    미래 값이라 '결과 확정일 ≤ 판단일' 인 것만 쓴다 (adaptive_weights)"""
    out = {}
    for sym, s in stocks.items():
        cs = s["candles"]
        for i in range(len(cs) - horizon):
            c0 = float(cs[i]["close"])
            if c0 > 0:
                out[(cs[i]["date"][:10], sym)] = (cs[i + horizon]["date"][:10], float(cs[i + horizon]["close"]) / c0 - 1)
    return out


def _rank_ic(x: list, y: list) -> float | None:
    if len(x) < 5:
        return None
    xr, yr = pd.Series(x).rank(), pd.Series(y).rank()
    if xr.std() == 0 or yr.std() == 0:
        return None
    c = float(np.corrcoef(xr, yr)[0, 1])
    return None if math.isnan(c) else c


def adaptive_weights(feats: dict, labels: dict, day: str) -> dict | None:
    """day 판단에 쓸 비중: 결과 확정일 ≤ day 인 최근 ADAPT_LOOKBACK 개 날짜에서 요소별 날짜별 순위 상관(IC) 평균 → 양수만큼 비중.
    → {"weights", "ic", "dates"} 또는 표본 부족 None. 셋 다 0 이하면 고정 비중 + ic 표시"""
    keys = ("prob", "quant", "accum")
    days = [d for d in sorted(feats) if d < day]
    usable = []
    for d in reversed(days):
        rows = [(sym, r) for sym, r in feats[d].items() if (d, sym) in labels and labels[(d, sym)][0] <= day]
        if len(rows) >= 5:
            usable.append((d, rows))
        if len(usable) >= ADAPT_LOOKBACK:
            break
    if len(usable) < ADAPT_MIN_DATES:
        return None
    ics = {k: [] for k in keys}
    for d, rows in usable:
        comps = [components(r["prob"], r["quant"], r["accum"], r["accum_ok"]) for _, r in rows]
        rets = [labels[(d, sym)][1] for sym, _ in rows]
        for j, k in enumerate(keys):
            v = _rank_ic([c[j] for c in comps], rets)
            if v is not None:
                ics[k].append(v)
    ic = {k: (float(np.mean(v)) if v else 0.0) for k, v in ics.items()}
    pos = {k: max(v, 0.0) for k, v in ic.items()}
    tot = sum(pos.values())
    w = ({k: ADAPT_SHRINK * pos[k] / tot + (1 - ADAPT_SHRINK) * WEIGHTS[k] for k in keys} if tot > 0
         else dict(WEIGHTS))
    return {"weights": w, "ic": {k: round(v, 3) for k, v in ic.items()}, "dates": len(usable), "fallback": tot <= 0}


def rescore(rows: dict, weights: dict):
    for r in rows.values():
        r["score"] = ai_score(r["prob"], r["quant"], r["accum"], r["accum_ok"], weights)


def weights_text(aw: dict | None) -> str:
    if not aw:
        return "고정 비중 (학습할 과거 결과 부족)"
    w = aw["weights"]
    base = f"확률 {w['prob'] * 100:.0f}% · 퀀트 {w['quant'] * 100:.0f}% · 매집 {w['accum'] * 100:.0f}%"
    return ("고정 비중 (최근 세 신호 모두 결과와 반대·무관)" if aw["fallback"] else f"학습형 비중 {base}") + f" (최근 {aw['dates']}일 기준)"


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
                   overrides: dict | None = None, to_date: str = "9999", progress=None) -> dict:
    """stocks: {종목: {"name", "candles"(오름차순)}} → {날짜: {종목: 행}} (from_date 이후 날짜만).
    각 날짜의 행은 그날 종가까지의 데이터로만 계산.
    prob_override / overrides: 실시간용 — 마지막 날 상승확률(학습 모델 포함 AI 추천) / 전 종목 퀀트·매집 결과로 덮어씀"""
    probs, accs, qframes, ma50 = {}, {}, {}, {}
    for n, (sym, s) in enumerate(stocks.items()):
        if progress:
            progress(f"점수 계산 중 ({s.get('name') or sym})", n, len(stocks))
        cs = s["candles"]
        if len(cs) < 30:
            continue
        probs[sym] = _prob_series(cs, from_date, to_date)
        closes = pd.Series([float(c["close"]) for c in cs])
        ma50[sym] = dict(zip((c["date"][:10] for c in cs), closes.rolling(50).mean()))
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
                "ma50": None if pd.isna(ma50[sym].get(d, np.nan)) else float(ma50[sym][d]),
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
        if e.get("country") == "KR":   # 한국은행 금리 결정 — 국내 장중 발표라 그날만
            if market == "KR" and d == t:
                out.append(f"{name}일")
            continue
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
    if row.get("tags"):   # 후보가 된 이유·참고 신호 (가치주·쌍끌이·투자 대가·개미 감점) — signals.live_candidates
        txt += " · " + " · ".join(row["tags"][:3])
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
    ai_exit = bool(params.get("ai_exit"))
    adds = []
    for sym, p in state["positions"].items():
        r = rows.get(sym)
        if r is None:
            continue
        strong = ai_strong(r, params)
        if ai_exit:
            p["ai_hold"] = strong   # 다음 장중 손절·목표 판단에 씀 (live_exit · intraday_exit)
            if r["close"] > p["stop"]:
                p["stop_held"] = False   # 손절선 위로 돌아옴 → 다음에 닿으면 다시 알림
        ret = (r["close"] / p["avg"] - 1) * 100 if p.get("avg") else 0.0
        hd = p.get("hold_days", 0)
        why = None
        if r["score"] < params["sell_score"]:
            why = f"AI 점수 {r['score']} (매도 기준 {params['sell_score']} 미만)"
        elif r["prob"] <= SELL_PROB:
            why = f"상승확률 {r['prob']}% (40% 이하 — 하락 예상)"
        elif ai_exit and ret >= LOCK_PROFIT and r["prob"] <= LOCK_PROB:
            why = f"이익 {ret:+.1f}% 중인데 상승확률 {r['prob']}% — 떨어질 것 같아 이익 지키기 (AI 매도 판단)"
        elif ai_exit and r["close"] <= p["stop"] and loss_stop(p):
            if not strong or p.get("added"):
                why = (f"손절선 아래({ret:+.1f}%)" + (" — 물타기 뒤라 손절" if p.get("added")
                                                    else f" + AI 회복 기대 낮음 (점수 {r['score']}·확률 {r['prob']}%)"))
            elif (params.get("avg_down") and regime != "하락 추세"):
                adds.append((sym, p, r, ret))
            else:
                notes.append(f"{p['name']} 손절선 아래({ret:+.1f}%)지만 AI 가 회복 기대 (점수 {r['score']}·확률 {r['prob']}%) — 보류")
        if why is None and hd >= params["max_hold"]:
            if ai_exit and strong and hd < params["max_hold"] * HOLD_EXT:
                notes.append(f"{p['name']} 보유 {hd}거래일 — 최대 보유일이지만 AI 강세라 더 들고 감 "
                             f"(최대 {int(params['max_hold'] * HOLD_EXT)}일)")
            else:
                why = f"보유 {hd}거래일 — " + ("최대 보유일 도달" if not ai_exit or not strong else "연장 한도 도달")
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
    for sym, p, r, ret in adds:   # 물타기 — 처음 산 금액의 절반, 한 번만 (현금·비중 한도 안에서)
        budget = min(float(p.get("entry_cost") or p["qty"] * p["avg"]) * AVG_DOWN_RATIO, room)
        if budget < r["close"] * (1 + c["fee"] + c["slip"]) * 1.02:
            notes.append(f"{p['name']} 물타기 조건이지만 현금·비중 한도로 못 삼")
            continue
        orders.append({"side": "buy", "symbol": sym, "name": p["name"], "budget": round(budget, 2), "add": True,
                       "reason": f"물타기 — 손절선 아래({ret:+.1f}%)지만 AI 강세 · {_fmt_reason(r, regime, [])}",
                       "score": r["score"], "ref": r["close"]})
        room -= budget
    cands = sorted(((s, r) for s, r in rows.items()
                    if s not in state["positions"] and r["score"] >= params["buy_score"] and r["prob"] >= MIN_PROB),
                   key=lambda kv: (-kv[1]["score"], -kv[1]["prob"], kv[0]))
    if params.get("trend_filter"):
        below = [r["name"] for s, r in cands if r.get("ma50") is not None and r["close"] < r["ma50"]]
        cands = [(s, r) for s, r in cands if r.get("ma50") is None or r["close"] >= r["ma50"]]
        if below:
            notes.append(f"추세 필터: 50일선 아래라 안 삼 — {', '.join(below[:3])}{' 외' if len(below) > 3 else ''}")
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
                       "reason": _fmt_reason(r, regime, events_next), "score": r["score"], "ref": r["close"]})
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
    old = state["positions"].get(sym)
    if old:   # 물타기 — 평균가·손절·목표를 새 평균가로 (강제 손절선은 첫 매입가 기준 그대로)
        n = old["qty"] + qty
        old["avg"] = (old["qty"] * old["avg"] + cost) / n
        old["qty"], old["buy_fee"] = n, old.get("buy_fee", 0.0) + fee
        old.setdefault("entry_px", px)
        old["added"] = int(old.get("added") or 0) + 1
        old["stop"] = old["avg"] * (1 - params["stop_pct"] / 100)
        old["target"] = old["avg"] * (1 + params["take_pct"] / 100)
        old["peak"] = px   # 추격 손절을 물탄 가격부터 다시 (예전 최고가 기준이면 바로 손절선 위라 팔림)
        old["stop_held"] = False
        return _trade(day, sym, name, "buy", qty, px, fee, 0.0, reason)
    state["positions"][sym] = {
        "name": name, "qty": qty, "avg": px, "buy_fee": fee, "entry_date": day, "hold_days": 0,
        "peak": px, "last": px, "stop": px * (1 - params["stop_pct"] / 100),
        "target": px * (1 + params["take_pct"] / 100), "reason": reason,
        "entry_px": px, "entry_cost": cost,
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


def guarded_entry(ref: float | None, o: float, l: float) -> tuple:
    """급변 보호 매수가 → (체결가 또는 None, 메모). ref = 판단한 날 종가"""
    if not ref:
        return o, None
    if o < ref * (1 - 2 * GUARD_GAP / 100):
        return None, f"급락 출발 ({(o / ref - 1) * 100:.1f}%) — 매수 취소 (급변 보호)"
    cap = ref * (1 + GUARD_GAP / 100)
    if o > cap:
        if l <= cap:
            return cap, f"비싸게 출발 (+{(o / ref - 1) * 100:.1f}%) → +{GUARD_GAP:g}% 까지 내려와서 삼"
        return None, f"비싸게 출발 (+{(o / ref - 1) * 100:.1f}%) 하고 안 내려옴 — 안 삼 (급변 보호)"
    return o, None


def intraday_exit(p: dict, o: float, h: float, l: float, params: dict | None = None) -> tuple | None:
    """그날 시가·고가·저가로 손절/목표 도달 확인 → (체결가, 사유). 둘 다 닿았으면 손절 먼저 (보수적으로).
    AI 매도 판단(params.ai_exit)이면 강제 손절 먼저 · 손절 보류/익절 보류는 (None, 메모) — 바뀐 손절·목표는 다음 날부터 (장중 순서를 모름)"""
    params = params or {}
    if params.get("ai_exit"):
        hs = hard_stop(p, params)
        if o <= hs:
            return o, "강제 손절 — 시가가 강제 손절선 아래로 출발"
        if l <= hs:
            return hs, f"강제 손절선(첫 매입가 −{hard_pct(params):g}%) 도달"
        if l <= p["stop"] and can_hold_stop(p, params):
            if p.get("stop_held"):
                return None
            p["stop_held"] = True
            return None, "손절가 도달했지만 AI 회복 기대로 보류 (종가에 다시 판단)"
        if h >= p["target"] and p.get("ai_hold") and not (l <= p["stop"]):
            return None, ride(p, params)
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

def prepare(stocks: dict, market: str, start: str, end: str, progress=None) -> dict:
    """시뮬레이션용 점수 (그날까지 데이터로만) — 학습형 가중치용으로 시작 ADAPT_WARMUP_DAYS 전부터 계산.
    같은 데이터로 '기본 방식' 비교를 돌릴 때 다시 계산하지 않게 따로 둠"""
    feat_from = (date.fromisoformat(start) - timedelta(days=ADAPT_WARMUP_DAYS)).isoformat()
    return build_features(stocks, market, feat_from, to_date=end, progress=progress)


def simulate(stocks: dict, index_candles: list, macro: list, market: str, capital: float, start: str, end: str,
             params: dict, progress=None, feats: dict | None = None) -> dict:
    """과거 시뮬레이션. stocks 일봉은 start 전 WARMUP 개 이상 있어야 점수가 나옴.
    progress(단계, 완료, 전체) — 진행 표시용 (선택, 예외를 올리면 중단). feats: prepare() 결과 (없으면 계산)"""
    if feats is None:
        feats = prepare(stocks, market, start, end, progress)
    feats = {d: {s: dict(r) for s, r in rows.items()} for d, rows in feats.items()}   # 점수를 바꿔 쓰므로 복사
    days = sorted(d for d in feats if start <= d <= end)
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
    trades, curve, log, weight_log = [], [], [], []
    bench0 = idx_on(days[0])
    exposure_sum = 0.0
    labels = forward_labels(stocks) if params.get("adaptive") else {}
    aw, since = None, ADAPT_EVERY
    guard_n = [0, 0]   # 급변 보호: 안 산 수, 기다렸다 산 수
    ai_n = [0, 0]      # AI 매도 판단: 손절 보류 수, 익절 보류 수
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
                    px, memo = (guarded_entry(o.get("ref"), float(bar["open"]), float(bar["low"])) if params.get("entry_guard")
                                else (float(bar["open"]), None))
                    if memo:
                        acts.append(f"{o['name']} {memo}")
                        guard_n[0 if px is None else 1] += 1
                    t = None if px is None else fill_buy(state, o["symbol"], o["name"], o["budget"], px, d, o["reason"], params, market)
                    if t is None and px is not None:
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
                hit = intraday_exit(state["positions"][sym], float(bar["open"]), float(bar["high"]), float(bar["low"]), params)
                if hit and hit[0] is None:
                    acts.append(f"{state['positions'][sym]['name']} {hit[1]}")
                    ai_n[0 if hit[1].startswith("손절") else 1] += 1
                elif hit:
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
            if params.get("adaptive"):
                if since >= ADAPT_EVERY:
                    aw, since = adaptive_weights(feats, labels, d), 0
                    weight_log.append({"date": d, **(aw or {"weights": dict(WEIGHTS), "ic": None, "dates": 0, "fallback": True})})
                    notes.append(weights_text(aw))
                since += 1
            rescore(feats[d], aw["weights"] if aw else WEIGHTS)
            ev = event_labels(market, days[k + 1], macro)
            pending, dnotes = decide(state, feats[d], regime, ev, params, market)
            notes += dnotes
            top = [{"symbol": s, "name": r["name"], "score": r["score"], "prob": r["prob"]}
                   for s, r in sorted(feats[d].items(), key=lambda kv: -kv[1]["score"])[:3]]
            acts += [f"주문(다음 날 시가): {'매수' if o['side'] == 'buy' else '매도'} {o['name']} — {o['reason']}" for o in pending]
        log.append({"date": d, "regime": regime, "equity": round(eq, 2), "actions": acts, "notes": notes, "top": top})
        if progress and k % 10 == 0:
            progress("매매 시뮬레이션 중", k + 1, len(days))
    return {"summary": summarize(curve, trades, capital, exposure_sum / len(days)), "equity": curve, "trades": trades,
            "log": log, "positions": positions_view(state, market), "days": len(days), "weights": weight_log,
            "guard": {"skipped": guard_n[0], "waited": guard_n[1]} if params.get("entry_guard") else None,
            "ai_exit": ({"stop_held": ai_n[0], "rides": ai_n[1],
                         "adds": len([t for t in trades if t["side"] == "buy" and t["reason"].startswith("물타기")])}
                        if params.get("ai_exit") else None)}


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
                    "stop": round(p["stop"], 4), "target": round(p["target"], 4), "reason": p.get("reason"),
                    "ai_hold": p.get("ai_hold"), "added": int(p.get("added") or 0)})
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
