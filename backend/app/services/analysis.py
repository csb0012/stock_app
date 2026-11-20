"""기술적 분석 + AI 예측 서비스"""
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Optional


def _clean(v):
    """NaN/inf → None (가격이 전혀 안 움직인 종목은 RSI 가 NaN 이 되고, NaN 은 JSON 응답을 깨뜨림)"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def calc_technical_indicators(candles: list) -> dict:
    """캔들 데이터로 주요 기술지표 계산"""
    if len(candles) < 20:
        return {}

    df = pd.DataFrame(candles)
    df["close"] = pd.to_numeric(df["close"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["volume"] = pd.to_numeric(df["volume"])

    # RSI (14일)
    rsi = ta.rsi(df["close"], length=14)
    rsi_val = _clean(rsi.iloc[-1]) if rsi is not None and not rsi.empty else None

    # MACD
    macd_df = ta.macd(df["close"])
    macd_val = _clean(macd_df["MACD_12_26_9"].iloc[-1]) if macd_df is not None else None
    macd_signal = _clean(macd_df["MACDs_12_26_9"].iloc[-1]) if macd_df is not None else None
    macd_hist = _clean(macd_df["MACDh_12_26_9"].iloc[-1]) if macd_df is not None else None

    # 볼린저밴드 (pandas-ta 버전에 따라 컬럼명이 다를 수 있어 동적으로 찾음)
    bb = ta.bbands(df["close"], length=20)
    bb_upper = bb_mid = bb_lower = None
    if bb is not None:
        cols = bb.columns.tolist()
        upper_col = next((c for c in cols if c.startswith("BBU_")), None)
        mid_col   = next((c for c in cols if c.startswith("BBM_")), None)
        lower_col = next((c for c in cols if c.startswith("BBL_")), None)
        if upper_col: bb_upper = _clean(bb[upper_col].iloc[-1])
        if mid_col:   bb_mid   = _clean(bb[mid_col].iloc[-1])
        if lower_col: bb_lower = _clean(bb[lower_col].iloc[-1])

    # 이동평균
    ma5 = _clean(ta.sma(df["close"], 5).iloc[-1])
    ma20 = _clean(ta.sma(df["close"], 20).iloc[-1])
    ma60 = _clean(ta.sma(df["close"], 60).iloc[-1]) if len(df) >= 60 else None

    # 현재가
    curr_price = float(df["close"].iloc[-1])

    return {
        # 0 도 유효한 값이므로 None 일 때만 비움 (예전엔 0 이 None 으로 사라졌음)
        "rsi": round(rsi_val, 2) if rsi_val is not None else None,
        "macd": round(macd_val, 4) if macd_val is not None else None,
        "macd_signal": round(macd_signal, 4) if macd_signal is not None else None,
        "macd_hist": round(macd_hist, 4) if macd_hist is not None else None,
        "bb_upper": round(bb_upper, 2) if bb_upper is not None else None,
        "bb_mid": round(bb_mid, 2) if bb_mid is not None else None,
        "bb_lower": round(bb_lower, 2) if bb_lower is not None else None,
        "ma5": round(ma5, 2) if ma5 is not None else None,
        "ma20": round(ma20, 2) if ma20 is not None else None,
        "ma60": round(ma60, 2) if ma60 is not None else None,
        "current_price": curr_price,
    }


def predict_next_day(candles: list, indicators: dict, news: dict | None = None) -> dict:
    """
    내일 상승 확률 예측 (규칙 기반 + 기술적 분석 종합)
    - 완벽한 예측은 없으며, 참고용 확률입니다
    """
    if not indicators or not candles:
        return {"probability": 50, "signal": "중립", "confidence": "낮음", "reasons": [], "factors": [],
                "summary": "분석에 필요한 가격 데이터가 부족함"}

    score = 0
    max_score = 0
    factors = []  # {name, short, detail, impact(up/down/neutral), score, max}

    def add(name: str, short: str, detail: str, got: int, full: int):
        ratio = got / full if full else 0.5
        impact = "up" if ratio >= 0.6 else "down" if ratio <= 0.3 else "neutral"
        factors.append({"name": name, "short": short, "detail": detail,
                        "impact": impact, "score": got, "max": full})

    curr = indicators.get("current_price", 0)

    # 1. RSI 분석 (30점)
    rsi = indicators.get("rsi")
    if rsi is not None:
        max_score += 30
        if rsi < 30:
            got, short, detail = 30, "RSI 과매도", f"RSI {rsi:.1f} → 과매도 구간 (반등 가능성)"
        elif rsi < 45:
            got, short, detail = 20, "RSI 약세권 하단", f"RSI {rsi:.1f} → 약세권 하단 (추가 하락 여력 적음)"
        elif rsi < 55:
            got, short, detail = 15, "RSI 중립", f"RSI {rsi:.1f} → 중립"
        elif rsi < 70:
            got, short, detail = 10, "RSI 강세권", f"RSI {rsi:.1f} → 강세권 (상승 여력 줄어드는 중)"
        else:
            got, short, detail = 0, "RSI 과매수", f"RSI {rsi:.1f} → 과매수 구간 (조정 주의)"
        score += got
        add("RSI", short, detail, got, 30)

    # 2. MACD 분석 (25점)
    macd = indicators.get("macd")
    macd_signal = indicators.get("macd_signal")
    macd_hist = indicators.get("macd_hist")
    if macd is not None and macd_signal is not None:
        max_score += 25
        if macd > macd_signal and macd_hist and macd_hist > 0:
            got, short, detail = 25, "MACD 상승 모멘텀", "MACD가 시그널선 위 + 히스토그램 플러스 → 상승 모멘텀"
        elif macd > macd_signal:
            got, short, detail = 15, "MACD 매수신호", "MACD가 시그널선 위 (매수신호)"
        elif macd_hist and macd_hist > 0:
            got, short, detail = 10, "MACD 혼조", "MACD 히스토그램만 플러스 (방향 불분명)"
        else:
            got, short, detail = 0, "MACD 데드크로스", "MACD가 시그널선 아래 (매도압력)"
        score += got
        add("MACD", short, detail, got, 25)

    # 3. 볼린저밴드 (20점)
    bb_lower = indicators.get("bb_lower")
    bb_upper = indicators.get("bb_upper")
    if bb_lower and bb_upper and curr:
        max_score += 20
        bb_pos = (curr - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
        pos_txt = f"밴드 내 위치 {bb_pos * 100:.0f}%"
        if bb_pos < 0.2:
            got, short, detail = 20, "볼린저 하단 근처", f"볼린저밴드 하단 근처 ({pos_txt}) → 반등 기대"
        elif bb_pos < 0.4:
            got, short, detail = 15, "볼린저 중하단", f"볼린저밴드 중하단 ({pos_txt})"
        elif bb_pos < 0.6:
            got, short, detail = 10, "볼린저 중간", f"볼린저밴드 중간 ({pos_txt})"
        elif bb_pos < 0.8:
            got, short, detail = 5, "볼린저 중상단", f"볼린저밴드 중상단 ({pos_txt}) → 상승 여력 제한"
        else:
            got, short, detail = 0, "볼린저 상단 과열", f"볼린저밴드 상단 ({pos_txt}) → 과열 주의"
        score += got
        add("볼린저밴드", short, detail, got, 20)

    # 4. 이동평균 배열 (25점)
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    ma60 = indicators.get("ma60")
    if ma5 and ma20 and curr:
        max_score += 25
        if curr > ma5 > ma20:
            got = 25
            if ma60 and curr > ma60:
                short, detail = "이평선 정배열", "현재가 > 5일선 > 20일선, 60일선 위 → 상승 추세"
            else:
                short, detail = "단기 정배열", "현재가 > 5일선 > 20일선 (단기 상승 추세)"
        elif curr > ma20:
            got, short, detail = 15, "20일선 지지", "현재가가 20일 이평 위 (중기 지지)"
        elif curr > ma5:
            got, short, detail = 10, "5일선 위", "5일 이평 위지만 20일선 아래 (단기 반등 시도)"
        else:
            got, short, detail = 0, "이평선 하회", "현재가가 5일·20일 이평 아래 (하락 추세)"
        score += got
        add("이동평균", short, detail, got, 25)

    # 5. 뉴스 분위기 (15점) — news: {"pos": n, "neg": n, "total": n, "headlines": [...]} (news.py)
    if news is not None:
        max_score += 15
        pos, neg, total = news.get("pos", 0), news.get("neg", 0), news.get("total", 0)
        if news.get("error"):
            got, short, detail = 7, "뉴스 조회 실패", f"뉴스 조회 실패 — 중립 처리 ({news['error'][:60]})"
        elif pos + neg == 0:
            got, short, detail = 7, "뉴스 중립", f"최근 뉴스 {total}건, 뚜렷한 호재·악재 키워드 없음"
        else:
            got = round(15 * pos / (pos + neg))
            tone = "호재 우세" if pos > neg else "악재 우세" if neg > pos else "호재·악재 혼재"
            short = f"뉴스 {tone}"
            sample = next((h["title"] for h in news.get("headlines", []) if h.get("tone") == ("pos" if pos >= neg else "neg")), "")
            detail = f"최근 뉴스 {total}건 중 호재 {pos} · 악재 {neg}" + (f" — 예: {sample[:50]}" if sample else "")
        score += got
        add("뉴스", short, detail, got, 15)

    reasons = [f["detail"] for f in factors]

    # 확률 계산
    probability = int((score / max_score * 60) + 20) if max_score > 0 else 50
    probability = max(15, min(85, probability))  # 15~85% 범위

    if probability >= 65:
        signal = "매수 고려"
        signal_color = "green"
    elif probability >= 55:
        signal = "약한 매수"
        signal_color = "lightgreen"
    elif probability >= 45:
        signal = "중립"
        signal_color = "gray"
    elif probability >= 35:
        signal = "약한 매도"
        signal_color = "orange"
    else:
        signal = "매도 고려"
        signal_color = "red"

    # 목표가·손절가 (ATR 기반 단순 계산)
    if candles and curr:
        highs = [c["high"] for c in candles[-14:]]
        lows = [c["low"] for c in candles[-14:]]
        atr = np.mean([h - l for h, l in zip(highs, lows)])
        target_price = round(curr + atr * 2, 2)
        stop_loss = round(curr - atr * 1.5, 2)
    else:
        target_price = None
        stop_loss = None

    # 진입 추천가
    entry_price = None
    entry_comment = None
    if curr:
        ma20 = indicators.get("ma20")
        bb_lower_v = indicators.get("bb_lower")
        if probability >= 65:
            if bb_lower_v and curr > bb_lower_v * 1.03:
                entry_price = round(bb_lower_v * 1.01, 2)
                entry_comment = "볼린저 하단 근처 분할 매수"
            else:
                entry_price = round(curr * 0.985, 2)
                entry_comment = "1~2% 하락 시 분할 매수"
        elif probability >= 55:
            entry_price = round(curr, 2)
            entry_comment = "현재가 소규모 진입"

    confidence = "높음" if max_score >= 80 and len(reasons) >= 3 else "중간" if max_score >= 50 else "낮음"

    ups = [f["short"] for f in factors if f["impact"] == "up"]
    downs = [f["short"] for f in factors if f["impact"] == "down"]
    up_txt, down_txt = ", ".join(ups), ", ".join(downs)
    if probability >= 55:
        summary = f"상승 우세 — 근거: {up_txt or '지표 종합'}"
        if downs:
            summary += f" / 주의: {down_txt}"
    elif probability < 45:
        summary = f"하락 우세 — 근거: {down_txt or '지표 종합'}"
        if ups:
            summary += f" / 긍정 요인: {up_txt}"
    else:
        summary = "방향성 약함 — 상승·하락 신호가 섞여 있음"
        if ups or downs:
            summary += f" (긍정: {up_txt or '없음'} / 부정: {down_txt or '없음'})"

    return {
        "probability": probability,
        "signal": signal,
        "signal_color": signal_color,
        "confidence": confidence,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "entry_price": entry_price,
        "entry_comment": entry_comment,
        "reasons": reasons,
        "factors": factors,
        "summary": summary,
        "disclaimer": "이 분석은 참고용이며 투자 손실에 대한 책임을 지지 않습니다.",
    }


def classify_investment_style(candles: list, indicators: dict, per: float = 0, pbr: float = 0) -> dict:
    """장기투자 vs 단기/스윙 스타일 분류"""
    if not candles or len(candles) < 60:
        return {"long_term_score": 0, "short_term_score": 0}

    df = pd.DataFrame(candles)
    df["close"] = pd.to_numeric(df["close"])

    # 장기 안정성 점수 (변동성 낮음 + 꾸준한 우상향)
    returns = df["close"].pct_change().dropna()
    volatility = float(returns.std() * np.sqrt(252))  # 연간 변동성
    trend = float((df["close"].iloc[-1] - df["close"].iloc[0]) / df["close"].iloc[0])

    long_term_score = 0
    if volatility < 0.2:
        long_term_score += 40
    elif volatility < 0.35:
        long_term_score += 25
    if trend > 0.1:
        long_term_score += 30
    elif trend > 0:
        long_term_score += 15
    if pbr and 0 < pbr < 3:
        long_term_score += 15
    if per and 0 < per < 25:
        long_term_score += 15

    # 단기/스윙 점수 (모멘텀 강함)
    rsi = indicators.get("rsi", 50)
    macd_hist = indicators.get("macd_hist", 0) or 0
    short_term_score = 0
    if 40 < (rsi or 50) < 60:
        short_term_score += 30
    if macd_hist > 0:
        short_term_score += 30
    if volatility > 0.25:
        short_term_score += 20
    if abs(trend) > 0.05:
        short_term_score += 20

    return {
        "long_term_score": min(100, long_term_score),
        "short_term_score": min(100, short_term_score),
        "volatility": round(volatility, 3),
        "trend_6m": round(trend * 100, 1),
    }
