"""기술적 분석 + AI 예측 서비스"""
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Optional


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
    rsi_val = float(rsi.iloc[-1]) if rsi is not None and not rsi.empty else None

    # MACD
    macd_df = ta.macd(df["close"])
    macd_val = float(macd_df["MACD_12_26_9"].iloc[-1]) if macd_df is not None else None
    macd_signal = float(macd_df["MACDs_12_26_9"].iloc[-1]) if macd_df is not None else None
    macd_hist = float(macd_df["MACDh_12_26_9"].iloc[-1]) if macd_df is not None else None

    # 볼린저밴드
    bb = ta.bbands(df["close"], length=20)
    bb_upper = float(bb["BBU_20_2.0"].iloc[-1]) if bb is not None else None
    bb_mid = float(bb["BBM_20_2.0"].iloc[-1]) if bb is not None else None
    bb_lower = float(bb["BBL_20_2.0"].iloc[-1]) if bb is not None else None

    # 이동평균
    ma5 = float(ta.sma(df["close"], 5).iloc[-1])
    ma20 = float(ta.sma(df["close"], 20).iloc[-1])
    ma60 = float(ta.sma(df["close"], 60).iloc[-1]) if len(df) >= 60 else None

    # 현재가
    curr_price = float(df["close"].iloc[-1])

    return {
        "rsi": round(rsi_val, 2) if rsi_val else None,
        "macd": round(macd_val, 4) if macd_val else None,
        "macd_signal": round(macd_signal, 4) if macd_signal else None,
        "macd_hist": round(macd_hist, 4) if macd_hist else None,
        "bb_upper": round(bb_upper, 2) if bb_upper else None,
        "bb_mid": round(bb_mid, 2) if bb_mid else None,
        "bb_lower": round(bb_lower, 2) if bb_lower else None,
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2) if ma60 else None,
        "current_price": curr_price,
    }


def predict_next_day(candles: list, indicators: dict) -> dict:
    """
    내일 상승 확률 예측 (규칙 기반 + 기술적 분석 종합)
    - 완벽한 예측은 없으며, 참고용 확률입니다
    """
    if not indicators or not candles:
        return {"probability": 50, "signal": "중립", "confidence": "낮음", "reasons": []}

    score = 0
    max_score = 0
    reasons = []

    curr = indicators.get("current_price", 0)

    # 1. RSI 분석 (30점)
    rsi = indicators.get("rsi")
    if rsi is not None:
        max_score += 30
        if rsi < 30:
            score += 30
            reasons.append(f"RSI {rsi:.1f} → 과매도 구간 (반등 가능성)")
        elif rsi < 45:
            score += 20
            reasons.append(f"RSI {rsi:.1f} → 약세권 하단")
        elif rsi < 55:
            score += 15
            reasons.append(f"RSI {rsi:.1f} → 중립")
        elif rsi < 70:
            score += 10
            reasons.append(f"RSI {rsi:.1f} → 강세권")
        else:
            score += 0
            reasons.append(f"RSI {rsi:.1f} → 과매수 구간 (조정 주의)")

    # 2. MACD 분석 (25점)
    macd = indicators.get("macd")
    macd_signal = indicators.get("macd_signal")
    macd_hist = indicators.get("macd_hist")
    if macd is not None and macd_signal is not None:
        max_score += 25
        if macd > macd_signal and macd_hist and macd_hist > 0:
            score += 25
            reasons.append("MACD 골든크로스 / 상승 모멘텀")
        elif macd > macd_signal:
            score += 15
            reasons.append("MACD 양전 (매수신호)")
        elif macd_hist and macd_hist > 0:
            score += 10
            reasons.append("MACD 히스토그램 플러스")
        else:
            score += 0
            reasons.append("MACD 데드크로스 (매도압력)")

    # 3. 볼린저밴드 (20점)
    bb_lower = indicators.get("bb_lower")
    bb_upper = indicators.get("bb_upper")
    bb_mid = indicators.get("bb_mid")
    if bb_lower and bb_upper and curr:
        max_score += 20
        bb_pos = (curr - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
        if bb_pos < 0.2:
            score += 20
            reasons.append(f"볼린저밴드 하단 근처 → 반등 기대")
        elif bb_pos < 0.4:
            score += 15
            reasons.append("볼린저밴드 중하단")
        elif bb_pos < 0.6:
            score += 10
            reasons.append("볼린저밴드 중간")
        elif bb_pos < 0.8:
            score += 5
            reasons.append("볼린저밴드 중상단")
        else:
            score += 0
            reasons.append("볼린저밴드 상단 → 과열 주의")

    # 4. 이동평균 배열 (25점)
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    ma60 = indicators.get("ma60")
    if ma5 and ma20 and curr:
        max_score += 25
        if curr > ma5 > ma20:
            score += 25
            if ma60 and curr > ma60:
                reasons.append("정배열 (5MA > 20MA, 현재가 위) → 상승 추세")
            else:
                reasons.append("단기 정배열 (5MA > 20MA)")
        elif curr > ma20:
            score += 15
            reasons.append("20일 이평 위 (중기 지지)")
        elif curr > ma5:
            score += 10
            reasons.append("5일 이평 위 (단기 지지)")
        else:
            score += 0
            reasons.append("이동평균 하회 (하락 추세)")

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
        prices = [c["close"] for c in candles[-14:]]
        highs = [c["high"] for c in candles[-14:]]
        lows = [c["low"] for c in candles[-14:]]
        atr = np.mean([h - l for h, l in zip(highs, lows)])
        target_price = round(curr + atr * 2, 2)
        stop_loss = round(curr - atr * 1.5, 2)
    else:
        target_price = None
        stop_loss = None

    confidence = "높음" if max_score >= 80 and len(reasons) >= 3 else "중간" if max_score >= 50 else "낮음"

    return {
        "probability": probability,
        "signal": signal,
        "signal_color": signal_color,
        "confidence": confidence,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "reasons": reasons,
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
