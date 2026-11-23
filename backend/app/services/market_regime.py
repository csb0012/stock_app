"""시장 상태 (CAN SLIM 의 'M' — 시장 방향) — 지수가 상승 추세인지, 매도 압력(분산일)이 쌓이는지

- 추세: 지수 vs 50일선·200일선, 200일선 기울기(20거래일 전 대비)
- 분산일(distribution day): 최근 25거래일 중 지수가 0.2% 이상 내렸는데 거래량은 전날보다 많은 날 (큰손 매도 흔적, IBD 방식).
  지수 거래량이 없는 데이터면 분산일은 계산하지 않음 (None)
- 상태: 상승 추세(지수 > 50일선 > 200일선, 200일선 상승, 분산일 4일 이하) / 하락 추세(지수 < 200일선) / 그 외 상승 압박
- 검증: 지난 몇 년 동안 날마다 상태를 매기고 20거래일 뒤 지수 수익률을 상태별로 비교 (그날까지 데이터만으로 상태 판단)

예측 확률에는 넣지 않고 경고·참고로만 씀 (학습 모델 특징값으로 넣으려면 백테스트 검증부터).
"""
from datetime import date

import numpy as np
import pandas as pd

INDICES = {"KOSPI": ("^KS11", "코스피", "KR"), "KOSDAQ": ("^KQ11", "코스닥", "KR"),
           "SPX": ("^GSPC", "S&P 500", "US"), "NASDAQ": ("^IXIC", "나스닥 종합", "US")}
HORIZON = 20
DIST_WINDOW, DIST_DROP, DIST_WARN = 25, -0.002, 5
STATES = ["상승 추세", "상승 압박", "하락 추세"]
ADVICE = {
    "상승 추세": "지수가 50일·200일선 위에서 오르는 중 — 매수 신호를 따르기 좋은 환경",
    "상승 압박": "추세는 살아 있지만 50일선 아래로 밀렸거나 매도 흔적(분산일)이 쌓임 — 신규 매수는 줄이고 손절가 엄수",
    "하락 추세": "지수가 200일선 아래 — 개별 종목 상승 신호도 잘 안 맞는 시기, 현금 비중·분할 매수",
}


def regime_frame(candles: list) -> pd.DataFrame:
    """지수 일봉 → 날짜별 상태 (각 날짜는 그날까지의 데이터만)"""
    df = pd.DataFrame(candles)
    c, v = df["close"].astype(float), df["volume"].astype(float).fillna(0)
    out = pd.DataFrame({"date": df["date"].astype(str).str[:10], "close": c})
    out["ma50"], out["ma200"] = c.rolling(50).mean(), c.rolling(200).mean()
    out["ma200_up"] = out["ma200"] > out["ma200"].shift(20)
    ret = c.pct_change()
    has_vol = (v > 0).rolling(DIST_WINDOW).sum() >= DIST_WINDOW - 2
    dist = ((ret <= DIST_DROP) & (v > v.shift(1))).astype(float).rolling(DIST_WINDOW).sum()
    out["dist"] = dist.where(has_vol)
    up = (c > out["ma50"]) & (out["ma50"] > out["ma200"]) & out["ma200_up"] & ~(out["dist"] >= DIST_WARN)
    down = c < out["ma200"]
    out["state"] = np.where(out["ma200"].isna(), None, np.where(down, "하락 추세", np.where(up, "상승 추세", "상승 압박")))
    out["fwd20"] = c.shift(-HORIZON) / c - 1          # 검증 전용
    return out


def validate(f: pd.DataFrame) -> list:
    g = f.dropna(subset=["fwd20"])
    g = g[g["state"].notna()]
    base = float((g["fwd20"] > 0).mean()) * 100 if len(g) else None
    rows = []
    for s in STATES:
        x = g[g["state"] == s]
        rows.append({"state": s, "n": int(len(x)),
                     "up_rate": round(float((x["fwd20"] > 0).mean()) * 100, 1) if len(x) else None,
                     "avg_ret": round(float(x["fwd20"].mean()) * 100, 2) if len(x) else None,
                     "base_up_rate": round(base, 1) if base is not None else None})
    return rows


def summarize(key: str, candles: list, expect_date: date | None = None) -> dict:
    ticker, name, market = INDICES[key]
    if len(candles) < 220:
        return {"key": key, "name": name, "market": market, "error": f"지수 일봉 부족 ({len(candles)}개, 220개 이상 필요)"}
    f = regime_frame(candles)
    last = f.iloc[-1]
    pct = lambda a, b: round((a / b - 1) * 100, 2) if b and not pd.isna(b) else None   # noqa: E731
    # 최근 상태가 바뀐 날 (며칠째 이 상태인지)
    states = f["state"].tolist()
    since = len(states) - 1
    while since > 0 and states[since - 1] == states[-1]:
        since -= 1
    out = {
        "key": key, "name": name, "market": market, "ticker": ticker,
        "state": last["state"], "advice": ADVICE.get(last["state"]), "as_of": last["date"],
        "close": round(float(last["close"]), 2),
        "vs_ma50": pct(last["close"], last["ma50"]), "vs_ma200": pct(last["close"], last["ma200"]),
        "ma200_up": bool(last["ma200_up"]), "dist_days": None if pd.isna(last["dist"]) else int(last["dist"]),
        "since": f.iloc[since]["date"], "days_in_state": len(states) - since,
        "validation": validate(f), "horizon_days": HORIZON,
        "period": [f.iloc[200]["date"], f["date"].iloc[-1]],
    }
    if expect_date and last["date"] < expect_date.isoformat():
        out["stale"] = f"Yahoo 지수 데이터가 {last['date']} 기준 — 최신 거래일({expect_date.isoformat()}) 아님"
    return out


async def get_all() -> dict:
    """4개 지수 상태 (yfinance 5년 일봉). 지수별 실패는 그 지수에만 error"""
    from app.services.quote import batch_yf_history
    from app.services.market_calendar import last_session_date
    hist = await batch_yf_history([t for t, _, _ in INDICES.values()], "5y")
    items = {}
    for key, (ticker, name, market) in INDICES.items():
        try:
            items[key] = summarize(key, hist.get(ticker) or [], last_session_date(market))
        except Exception as e:
            items[key] = {"key": key, "name": name, "market": market, "error": f"시장 상태 계산 실패: {e}"}
    if all("error" in v for v in items.values()):
        raise RuntimeError("지수 데이터를 받지 못함 — " + " / ".join(v["error"] for v in items.values())[:300])
    return {"items": items, "rules": {"dist_window": DIST_WINDOW, "dist_drop_pct": DIST_DROP * 100, "dist_warn": DIST_WARN}}

