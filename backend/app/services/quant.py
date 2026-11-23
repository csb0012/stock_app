"""퀀트 점수 (국내 전 종목) — Seeking Alpha Quant Rating · TipRanks Smart Score · IBD RS Rating 방식을 참고한 '요인 등급'

다른 사이트들이 하는 것 → 여기서 하는 것
- 요인별 등급(A~F)을 **같은 날 전 종목 안의 순위(백분위)** 로 매김 (절대값이 아니라 상대 비교 — Quant Rating 방식)
- 모멘텀 = IBD RS Rating 식 가중 수익률(최근 분기 가중)을 전 종목 백분위 1~99 로
- 종합 점수 1~10 (Smart Score 식). 요인 가중치는 손으로 정하지 않고 **과거에 실제로 맞았던 정도(순위 상관, IC)** 로 정함
- 맞는지 확인: 앞쪽 기간으로 가중치를 정하고 **뒤쪽(처음 보는) 기간**에서 점수 구간별 20거래일 뒤 성과를 잼
  (Danelfin 처럼 '시장 대비' 확률: 20거래일 뒤 수익률이 그날 전 종목 중간값보다 높았던 비율)

모든 요인은 그날까지의 일봉만 사용 (미래 데이터 미사용). 20거래일 뒤 수익률(fwd20)은 검증에만 쓰고 점수 계산에는 안 씀.
데이터: 매집 탐지 스캔이 받는 국내 전 종목 일봉 200개를 같이 씀 (KIS 추가 호출 없음).
한계: 일봉 200개라 RS 는 12개월이 아니라 1·3·6개월 가중, 52주 고점은 200일 고점. 검증 기간이 약 2~3개월로 짧음.
"""
import math

import numpy as np
import pandas as pd

HORIZON = 20
MIN_TV = 1e8                  # 20일 평균 거래대금 1억 원 미만은 순위에서 제외 (매집 탐지와 같은 기준)
MIN_ROWS = 127                # 6개월 수익률(126일) 계산 가능부터
FACTORS = [
    # key, 이름, 설명
    ("rs", "모멘텀(RS)", "최근 1·3·6개월 수익률 가중(0.2·0.4·0.4) — IBD 상대강도 방식"),
    ("trend", "추세", "주가 > 50일선 > 120일선, 120일선 상승, 200일 고점에서 25% 안, 200일 저점보다 30% 위 (충족 개수)"),
    ("updown", "거래량 매집", "최근 50일 상승일 거래량 ÷ 하락일 거래량 (IBD 매집/분산 방식)"),
    ("lowvol", "안정성", "최근 60일 하루 등락률의 표준편차가 작을수록 높음 (저변동성)"),
    ("high52", "고점 근접", "200일 최고가 대비 현재가 (52주 신고가 근접 효과)"),
]
KEYS = [k for k, _, _ in FACTORS]
BUCKETS = [(80, 100), (60, 80), (40, 60), (20, 40), (0, 20)]
GRADES = [(90, "A+"), (80, "A"), (65, "B+"), (50, "B"), (35, "C"), (20, "D"), (0, "F")]


def grade(pct: float) -> str:
    for th, g in GRADES:
        if pct >= th:
            return g
    return "F"


def factor_frame(candles: list) -> pd.DataFrame:
    """일봉 → 날짜별 요인 원값 (각 행은 그날까지의 데이터만). MIN_ROWS 전 행은 버림"""
    df = pd.DataFrame(candles)
    c, h, l, v = (df[k].astype(float) for k in ("close", "high", "low", "volume"))
    out = pd.DataFrame({"date": df["date"].astype(str).str[:10], "close": c})
    r = lambda n: c / c.shift(n) - 1   # noqa: E731
    out["rs"] = 0.2 * r(21) + 0.4 * r(63) + 0.4 * r(126)
    ma50, ma120 = c.rolling(50).mean(), c.rolling(120).mean()
    hi200, lo200 = h.rolling(200, min_periods=120).max(), l.rolling(200, min_periods=120).min()
    conds = [c > ma50, ma50 > ma120, ma120 > ma120.shift(20), c >= 0.75 * hi200, c >= 1.3 * lo200]
    out["trend"] = sum(x.astype(float) for x in conds) + 0.1 * (c / ma50 - 1).clip(-1, 1)
    d = c.diff()
    upv = v.where(d > 0, 0).rolling(50).sum()
    dnv = v.where(d < 0, 0).rolling(50).sum()
    out["updown"] = np.log((upv + 1) / (dnv + 1))
    out["lowvol"] = -(c.pct_change().rolling(60).std())
    out["high52"] = c / hi200
    out["tv20"] = (c * v).rolling(20).mean()
    out["fwd20"] = c.shift(-HORIZON) / c - 1       # 검증 전용 (미래)
    out = out.iloc[MIN_ROWS - 1:] if len(out) >= MIN_ROWS else out.iloc[0:0]
    return out.replace([np.inf, -np.inf], np.nan)


def _pct_rank(g: pd.DataFrame, cols: list) -> pd.DataFrame:
    """같은 날짜 안에서 백분위 1~99"""
    return g.groupby("date")[cols].rank(pct=True).mul(98).add(1)


def _ic(df: pd.DataFrame, col: str) -> float:
    """날짜별 순위 상관(점수 백분위 vs 시장 대비 초과수익)의 평균"""
    vals = []
    for _, g in df.groupby("date"):
        g = g[[col, "excess"]].dropna()
        if len(g) >= 20:
            x = g[col].rank()
            y = g["excess"].rank()
            if x.std() == 0 or y.std() == 0:
                continue                      # 그날 값이 전부 같으면 상관을 못 구함
            cc = np.corrcoef(x, y)[0, 1]
            if not math.isnan(cc):
                vals.append(cc)
    return float(np.mean(vals)) if vals else 0.0


def _weights(df: pd.DataFrame) -> tuple:
    """요인별 IC → 가중치 (IC 가 0 이하면 0). 전부 0 이면 같은 가중치"""
    ic = {k: _ic(df, f"p_{k}") for k in KEYS}
    pos = {k: max(v, 0.0) for k, v in ic.items()}
    s = sum(pos.values())
    w = {k: (pos[k] / s if s > 0 else 1 / len(KEYS)) for k in KEYS}
    return w, ic, s > 0


def _composite(df: pd.DataFrame, w: dict) -> pd.Series:
    raw = sum(df[f"p_{k}"].fillna(50) * w[k] for k in KEYS)
    tmp = pd.DataFrame({"date": df["date"], "raw": raw})
    return tmp.groupby("date")["raw"].rank(pct=True).mul(98).add(1)


def _bucket_table(df: pd.DataFrame, col: str) -> list:
    rows = []
    for lo, hi in BUCKETS:
        g = df[(df[col] >= lo) & (df[col] < hi + (1 if hi == 100 else 0))]
        n = int(len(g))
        rows.append({"range": f"{lo}~{hi}", "lo": lo, "hi": hi, "n": n,
                     "beat_rate": round(float((g["excess"] > 0).mean()) * 100, 1) if n else None,
                     "avg_excess": round(float(g["excess"].mean()) * 100, 2) if n else None})
    return rows


def build(frames: dict, names: dict | None = None) -> dict | None:
    """{종목: factor_frame} → 오늘 점수 + 가중치 + 검증. 계산할 종목이 없으면 None"""
    parts = []
    for sym, f in frames.items():
        if f is None or f.empty:
            continue
        g = f[f["tv20"] >= MIN_TV]
        if not g.empty:
            parts.append(g.assign(symbol=sym))
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    df = df.dropna(subset=["rs"])
    if df.empty:
        return None
    for k in KEYS:
        df[f"p_{k}"] = _pct_rank(df, [k])[k]

    # 검증용: 20거래일 뒤 결과가 있는 날짜, 시장 대비 = 그날 전 종목 중간값과의 차이
    lab = df.dropna(subset=["fwd20"]).copy()
    lab["excess"] = lab["fwd20"] - lab.groupby("date")["fwd20"].transform("median")
    dates = sorted(lab["date"].unique())
    validation = None
    if len(dates) >= 10:
        half = len(dates) // 2
        test_dates = dates[half:]
        # 학습 구간 결과(20거래일)가 검증 시작 전에 끝나도록 앞쪽을 비움 (겹치면 미래를 본 셈)
        train_dates = dates[:max(0, half - HORIZON)] or dates[:half]
        train, test = lab[lab["date"].isin(train_dates)], lab[lab["date"].isin(test_dates)].copy()
        w_tr, ic_tr, _ = _weights(train)
        test["comp"] = _composite(test, w_tr)
        top, bottom = test[test["comp"] >= 80], test[test["comp"] < 20]
        validation = {
            "train": [train_dates[0], train_dates[-1]], "test": [test_dates[0], test_dates[-1]],
            "train_weights": {k: round(v, 3) for k, v in w_tr.items()},
            "buckets": _bucket_table(test, "comp"),
            "ic": round(_ic(test.rename(columns={"comp": "p_comp"}), "p_comp"), 3),
            "spread": round(float(top["excess"].mean() - bottom["excess"].mean()) * 100, 2)
            if len(top) and len(bottom) else None,
            "n": int(len(test)),
        }

    # 오늘 점수: 가중치는 결과가 나온 모든 날짜로
    w, ic, useful = _weights(lab) if len(lab) else ({k: 1 / len(KEYS) for k in KEYS}, {k: 0.0 for k in KEYS}, False)
    last_date = df["date"].max()
    today = df[df["date"] == last_date].copy()
    today["comp"] = _composite(today, w)
    buckets = (validation or {}).get("buckets") or []

    def bucket_of(p):
        for b in buckets:
            if b["lo"] <= p < b["hi"] + (1 if b["hi"] == 100 else 0):
                return b
        return None

    scores = {}
    for _, r in today.iterrows():
        p = float(r["comp"])
        b = bucket_of(p)
        scores[r["symbol"]] = {
            "score": max(1, min(10, math.ceil(p / 10))), "pct": round(p), "grade": grade(p),
            "factors": {k: round(float(r[f"p_{k}"])) if not pd.isna(r[f"p_{k}"]) else None for k in KEYS},
            "beat_rate": b["beat_rate"] if b else None, "bucket": b["range"] if b else None,
            "price": float(r["close"]),
        }
    top = sorted(scores.items(), key=lambda kv: -kv[1]["pct"])[:150]
    return {
        "date": last_date, "universe": int(len(today)), "horizon_days": HORIZON,
        "weights": {k: round(v, 3) for k, v in w.items()}, "ic": {k: round(v, 3) for k, v in ic.items()},
        "useful": useful, "validation": validation, "scores": scores,
        "top": [{"symbol": s, "name": (names or {}).get(s, s), **v} for s, v in top],
        "factors": [{"key": k, "name": n, "about": a} for k, n, a in FACTORS],
    }
