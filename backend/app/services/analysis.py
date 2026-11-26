"""기술적 분석 + AI 예측 서비스"""
import pandas as pd
import pandas_ta as ta
import numpy as np


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


# 학습 모델을 쓸 때 뉴스·외부 데이터는 과거 기록이 없어 학습에 못 넣음 → 확률을 소폭만 움직임 (최대 ±%p)
# 공시(DART)는 회사가 직접 낸 공식 자료라 가장 크게 (±6%p)
_SHIFT = {"뉴스": 3, "거시환경": 2, "애널리스트": 3, "실적": 2, "공시": 6}


def _apply_model(model: dict, factors: list, rule_prob: int) -> tuple:
    """학습 모델(또는 모델+규칙 결합) 확률 + 뉴스·외부데이터 소폭 보정 → (최종 확률, 요약 문장)"""
    raw = model["prob"] * 100
    if model.get("use") == "stack":
        from app.services.ml_model import stack_predict
        p = stack_predict(model["stack"], model["prob"], rule_prob / 100) * 100
    else:
        p = raw
    shift = 0.0
    for f in factors:
        if f["name"] in _SHIFT and f.get("max"):
            shift += (f["score"] / f["max"] - 0.5) * 2 * _SHIFT[f["name"]]
    prob = int(round(max(15, min(85, p + shift))))
    drivers = ", ".join(f"{d['label']} {d['value']}({'↑' if d['effect'] > 0 else '↓'})" for d in model.get("drivers", []))
    wf = model.get("walk_forward") or {}
    when = {"KR": " · 간밤 미국장 반영", "KR_base": " · 미국장 결과 반영 전",
            "KRF": " · 간밤 미국장·외국인/기관 수급 반영", "KRF_base": " · 외국인/기관 수급 반영"}.get(model.get("variant"), "")
    combo = (f" · 모델 {raw:.0f}% + 지표 점수 {rule_prob}% 를 백테스트 성적만큼 결합·보정 ({model.get('stack_reason')})"
             if model.get("use") == "stack" else "")
    detail = (f"과거 {model.get('n') or 0:,}건으로 학습한 모델 → 상승 {p:.0f}%{when}{combo}"
              f"{f' · 뉴스·외부데이터 보정 {shift:+.1f}%p' if abs(shift) >= 0.5 else ''}"
              f" · 주요 근거: {drivers or '-'}"
              f" · 백테스트 적중률 {wf.get('accuracy')}% (규칙 {(model.get('rules') or {}).get('accuracy')}%)")
    impact = "up" if p >= 55 else "down" if p <= 45 else "neutral"
    name = "학습 모델(결합)" if model.get("use") == "stack" else "학습 모델"
    factors.insert(0, {"name": name, "short": f"{name} {p:.0f}%", "detail": detail,
                       "impact": impact, "score": round(p), "max": 100})
    head = "상승 우세" if prob >= 55 else "하락 우세" if prob <= 45 else "방향성 약함"
    summary = f"{name} {head} ({prob}%) — 주요 근거: {drivers or '-'} · 지표 점수 기준 {rule_prob}%"
    return prob, summary, (round(p) if model.get("use") == "stack" else None), p + shift


def predict_next_day(candles: list, indicators: dict, news: dict | None = None, extra: dict | None = None,
                     model: dict | None = None, weights: dict | None = None) -> dict:
    """
    내일 상승 확률 예측 (규칙 기반 + 기술적 분석 종합)
    - 완벽한 예측은 없으며, 참고용 확률입니다
    - weights: 지표별 배율 (factor_weights.live — 예측 검증에서 덜 맞은 지표 비중 축소). 실시간 예측에서만 넘김.
      학습 모델을 쓸 땐 모델이 원래 비중 확률로 학습됐으므로 모델 입력은 원래 비중 그대로
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
    #    국내 종목(weight_source="foreign")은 해외 주요 매체 영문 기사만 반영. 국내(네이버) 기사는 보여주기만 하고 점수 0
    if news is not None and news.get("weight_source") == "foreign":
        pos, neg, total, kr = news.get("pos", 0), news.get("neg", 0), news.get("total", 0), news.get("kr_total", 0)
        kr_note = f" · 국내 기사 {kr}건은 참고만 (확률 미반영)" if kr else ""
        if news.get("foreign_error"):
            add("뉴스", "해외 기사 조회 실패", f"해외 기사 조회 실패 — 뉴스 요인 미반영 ({news['foreign_error'][:80]}){kr_note}", 0, 0)
        elif total == 0:
            add("뉴스", "해외 기사 없음", f"최근 2주 해외 주요 매체(Reuters·Bloomberg 등) 기사 없음 — 뉴스 요인 미반영{kr_note}", 0, 0)
        else:
            max_score += 15
            if pos + neg == 0:
                got, short = 7, "해외 뉴스 중립"
                detail = f"해외 기사 {total}건, 뚜렷한 호재·악재 표현 없음"
            else:
                got = round(15 * pos / (pos + neg))
                short = "해외 뉴스 " + ("호재 우세" if pos > neg else "악재 우세" if neg > pos else "호재·악재 혼재")
                sample = next((h for h in news.get("headlines", []) if h.get("weighted") and h.get("tone") == ("pos" if pos >= neg else "neg")), None)
                detail = f"해외 기사 {total}건 중 호재 {pos} · 악재 {neg}" + (f" — 예: [{sample['press']}] {sample['title'][:60]}" if sample else "")
            score += got
            add("뉴스", short, detail + kr_note, got, 15)
    elif news is not None:
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

    # 6~9. 추가 데이터 요인 (FRED·Finnhub·DART — extras.py, 키가 있는 것만)
    warnings: list = []
    for name, full, fn in _EXTRA_FACTORS:
        if not extra or name not in extra:
            continue
        d = extra[name]
        max_score += full
        half = full // 2
        if d.get("pending"):
            got, short, detail = half, f"{_EXTRA_LABEL[name]} 수집 중", "데이터 수집 중 — 잠시 후 반영 (중립 처리)"
        elif d.get("error"):
            got, short, detail = half, f"{_EXTRA_LABEL[name]} 조회 실패", f"조회 실패 — 중립 처리 ({d['error'][:120]})"
        else:
            got, short, detail = fn(d, full, warnings)
        score += got
        add(_EXTRA_LABEL[name], short, detail, got, full)

    reasons = [f["detail"] for f in factors]

    # 확률 계산
    exact = (score / max_score * 60) + 20 if max_score > 0 else 50.0   # 정렬용 (15~85 로 자르기 전 값)
    probability = max(15, min(85, int(exact)))  # 15~85% 범위
    rule_probability = probability
    weighted_probability, exact_w = None, None
    if weights:
        wscore = wfull = 0.0
        for f in factors:
            w = weights.get(f["name"], 1.0)
            if w != 1.0:
                f["weight"] = w
                f["detail"] += f" · 비중 ×{w:g} (예측 검증에서 덜 맞은 지표)"
            wscore += f["score"] * w
            wfull += f["max"] * w
        if wfull > 0:
            exact_w = wscore / wfull * 60 + 20
            weighted_probability = max(15, min(85, int(exact_w)))

    # 학습 모델 (백테스트에서 규칙보다 잘 맞았을 때만 채택됨 — ml_model.py)
    model_summary = None
    model_status = None
    combo_probability = None
    method = "rules"
    if model and "prob" in model and model.get("use"):
        probability, model_summary, combo_probability, exact = _apply_model(model, factors, rule_probability)
        method = f"{'combo' if model.get('use') == 'stack' else 'model'}:{model.get('variant')}"
    elif weighted_probability is not None:   # 규칙 점수를 쓸 때만 조정한 비중 (모델 입력은 원래 비중)
        probability, exact, method = weighted_probability, exact_w, "rules:weighted"
    if model and "prob" in model and model.get("use"):
        model_status = None
    elif model and "prob" in model:
        model_status = (f"학습 모델 미사용 ({model.get('reason')} / {model.get('stack_reason')}) → 규칙 점수 사용 "
                        f"(참고: 모델 확률 {model['prob'] * 100:.0f}%)")
    elif model:
        model_status = f"학습 모델 사용 안 함 — {model.get('status')}"

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

    # 목표가·손절가·추천 매입가 (ATR + 지지선)
    target_price = stop_loss = None
    buy = {"price": None, "low": None, "high": None, "gap_pct": None, "comment": None, "basis": None}
    if candles and curr:
        highs = [c["high"] for c in candles[-14:]]
        lows = [c["low"] for c in candles[-14:]]
        atr = float(np.mean([h - l for h, l in zip(highs, lows)])) or curr * 0.01
        buy = _buy_zone(candles, indicators, probability, curr, atr)
        target_price = round(curr + atr * 2, 2)
        # 손절가는 추천 매입가보다 아래 (매입가 지지선이 깨지면 손절)
        stop_loss = round(min(curr - atr * 1.5, buy["price"] - atr * 1.0), 2)

    # 예전 필드명 유지 (entry_*)
    entry_price, entry_comment = buy["price"], buy["comment"]

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
    if model_summary:
        summary = model_summary
    for w in warnings:
        summary += f" · ⚠ {w}"

    return {
        "probability": probability,
        "probability_exact": round(float(exact), 3),
        "rule_probability": rule_probability,
        "weighted_probability": weighted_probability,
        "model_probability": round(model["prob"] * 100) if model and "prob" in model else None,
        "combo_probability": combo_probability,
        "method": method,
        "model_status": model_status,
        "signal": signal,
        "signal_color": signal_color,
        "confidence": confidence,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "entry_price": entry_price,
        "entry_comment": entry_comment,
        "buy_price": buy["price"],
        "buy_low": buy["low"],
        "buy_high": buy["high"],
        "buy_gap_pct": buy["gap_pct"],
        "buy_comment": buy["comment"],
        "buy_basis": buy["basis"],
        "warnings": warnings,
        "reasons": reasons,
        "factors": factors,
        "summary": summary,
        "disclaimer": "이 분석은 참고용이며 투자 손실에 대한 책임을 지지 않습니다.",
    }


def _buy_zone(candles: list, ind: dict, prob: int, curr: float, atr: float) -> dict:
    """추천 매입가: 현재가 아래 지지선(20일선·60일선·볼린저·최근 저점)과 ATR(하루 평균 변동폭)로 계산

    - 상승 우세(65%↑): 지금 가격대 분할 매수
    - 약상승(55~64%): 가까운 지지선(1.5 ATR 이내)까지 눌리면 매수
    - 중립(45~54%): 1 ATR 이상 아래 지지선까지 기다림
    - 하락 우세(45% 미만): 더 깊은 지지선(볼린저 하단·최근 저점)에서 하락이 멈추는지 확인 후
    """
    low20 = min(c["low"] for c in candles[-20:])
    cands = [("20일선", ind.get("ma20")), ("60일선", ind.get("ma60")), ("볼린저 중심선", ind.get("bb_mid")),
             ("볼린저 하단", ind.get("bb_lower")), ("최근 20일 저점", low20)]
    supports = sorted([(n, float(v)) for n, v in cands if v and v < curr], key=lambda x: -x[1])

    def pick(min_gap: float, max_gap: float | None):
        for n, v in supports:
            gap = curr - v
            if gap >= min_gap and (max_gap is None or gap <= max_gap):
                return n, v
        return None

    if prob >= 65:
        price, basis = curr - atr * 0.3, "현재가 부근"
        comment = "상승 우세 — 지금 가격대에서 2~3번 나눠 분할 매수"
    elif prob >= 55:
        s = pick(atr * 0.2, atr * 1.5)
        if s:
            basis, price = s
            comment = f"약상승 — {basis} 부근까지 눌리면 매수"
        else:
            price, basis = curr - atr * 0.5, "소폭 조정"
            comment = "약상승 — 하루 변동폭 절반 정도 조정 시 매수"
    elif prob >= 45:
        s = pick(atr * 1.0, atr * 3.0)
        if s:
            basis, price = s
            comment = f"방향성 약함 — {basis}까지 내려오면 매수, 그 전엔 관망"
        else:
            price, basis = curr - atr * 1.2, "조정 대기"
            comment = "방향성 약함 — 하루 변동폭 이상 조정 시 매수, 그 전엔 관망"
    else:
        # 볼린저 하단·최근 저점 중, 현재가보다 0.5 ATR 이상 아래인 가장 가까운 것 (없으면 가장 깊은 것)
        deep = [(n, v) for n, v in supports if n in ("볼린저 하단", "최근 20일 저점")]
        far_enough = [x for x in deep if curr - x[1] >= atr * 0.5]
        if far_enough:
            basis, price = max(far_enough, key=lambda x: x[1])
        elif deep:
            basis, price = min(deep, key=lambda x: x[1])
        else:
            price, basis = curr - atr * 2.0, "추가 하락 대기"
        comment = f"하락 우세 — {basis}에서 하락이 멈추는지(양봉·거래량 감소) 확인 후 매수"

    price = min(price, curr)
    return {
        "price": round(price, 2),
        "low": round(price - atr * 0.3, 2),
        "high": round(min(curr, price + atr * 0.3), 2),
        "gap_pct": round((price / curr - 1) * 100, 2),
        "comment": comment,
        "basis": basis,
    }


# ---------------- 추가 데이터 요인 (extras.py) ----------------

def _f_macro(d: dict, full: int, warnings: list):
    got = round(full * d["score"] / 10)
    note = ", ".join(d.get("notes", [])[:3])
    if d["score"] >= 6:
        return got, "시장 위험선호", f"거시 환경 양호 — {note}"
    if d["score"] <= 3:
        return got, "시장 위험회피", f"거시 환경 불안 — {note}"
    return got, "시장 환경 보통", f"거시 환경 보통 — {note}"


def _f_analyst(d: dict, full: int, warnings: list):
    if not d.get("total"):
        return full // 2, "애널리스트 의견 없음", "애널리스트 의견 데이터 없음 (중립)"
    bull, bear = d["bull_ratio"], d["bear_ratio"]
    got = round(full * max(0.0, min(1.0, 0.5 + (bull - bear) / 2)))
    txt = (f"{d['period']} 기준 {d['total']}명 중 매수 {d['strong_buy'] + d['buy']} · 보유 {d['hold']} · "
           f"매도 {d['sell'] + d['strong_sell']}")
    short = "애널리스트 매수 우위" if bull >= 0.6 else "애널리스트 매도 우위" if bear >= 0.3 else "애널리스트 중립"
    return got, short, txt


def _f_earnings(d: dict, full: int, warnings: list):
    if d.get("upcoming"):
        warnings.append(f"실적발표 {d['upcoming'][5:].replace('-', '/')} 예정 — 변동성 확대")
    if not d.get("quarters"):
        return full // 2, "실적 데이터 없음", "최근 실적 데이터 없음 (중립)"
    ratio = d["beats"] / d["quarters"]
    got = round(full * ratio)
    txt = f"최근 {d['quarters']}분기 중 예상치 상회 {d['beats']}회 · 하회 {d['misses']}회"
    if d.get("last_surprise_pct") is not None:
        txt += f" (직전 {d['last_period']} 서프라이즈 {d['last_surprise_pct']:+.1f}%)"
    if d.get("upcoming"):
        txt += f" · 실적발표 {d['upcoming']} 예정"
    short = "실적 꾸준히 상회" if ratio >= 0.75 else "실적 하회 잦음" if ratio <= 0.25 else "실적 혼조"
    return got, short, txt


def _f_disclosure(d: dict, full: int, warnings: list):
    if d.get("na"):
        return full // 2, "공시 대상 아님", "DART 공시 대상 아님 (중립)"
    pos, neg = d.get("pos", 0), d.get("neg", 0)
    if pos + neg == 0:
        return full // 2, "특이 공시 없음", f"최근 14일 공시 {d.get('total', 0)}건, 호재·악재성 공시 없음"
    got = round(full * pos / (pos + neg))
    sample = next((i["title"] for i in d.get("items", []) if i["tone"] == ("neg" if neg >= pos else "pos")), "")
    if neg > pos:
        warnings.append(f"악재성 공시: {sample[:30]}")
    short = "호재성 공시" if pos > neg else "악재성 공시" if neg > pos else "공시 혼재"
    return got, short, f"최근 14일 호재성 {pos} · 악재성 {neg}" + (f" — 예: {sample[:50]}" if sample else "")


_EXTRA_FACTORS = [("macro", 10, _f_macro), ("analyst", 15, _f_analyst),
                  ("earnings", 10, _f_earnings), ("disclosure", 20, _f_disclosure)]   # 공시 = 공식 자료라 2배
_EXTRA_LABEL = {"macro": "거시환경", "analyst": "애널리스트", "earnings": "실적", "disclosure": "공시"}


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
