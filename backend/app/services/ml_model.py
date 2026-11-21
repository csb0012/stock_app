"""학습형 예측 모델 — 과거 일봉으로 "다음 거래일 상승 여부"를 학습한 로지스틱 회귀

규칙 점수(RSI 30점·MACD 25점…)는 사람이 정한 가중치라 실제 적중률이 50% 근처였다.
여기서는 같은 지표 + 최근 수익률·거래량·변동성·지수 흐름(국내는 간밤 미국장 등락 포함)을 숫자 그대로 넣고,
어떤 지표가 실제로 다음 날 등락과 관련 있었는지를 과거 데이터에서 직접 학습한다.

검증 원칙 (미래 정보 누설 금지):
- 학습 데이터 = 예측 대상일 '이전'에 결과가 확정된 날짜만 (walk-forward: 10거래일마다 다시 학습)
- 특징값은 모두 그날 종가까지의 데이터로만 계산 (rolling/ewm 은 과거만 봄)
- 국내 '간밤 미국장' 특징은 미국장이 끝난 뒤(한국 시간 새벽 6시경 이후)에만 사용. 그 전엔 이 특징이 없는 모델(KR_base) 사용

채택 원칙: walk-forward 백테스트에서 규칙 점수보다 적중률이 높을 때만 실제 화면에 사용 (아니면 기존 규칙 유지).
학습 결과(계수·검증 성적)는 backend/app/data/model_{KR,KR_base,US}.json 에 저장.
"""
import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

IDX_TICKERS = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "US": "^GSPC", "NDX": "^IXIC"}

BASE_FEATURES = ["ret1", "ret5", "ret20", "rsi", "macd", "bbz", "dist5", "dist20", "dist60",
                 "volr", "atr", "clv", "gap", "idx1", "idx5", "rel5"]
OVERNIGHT = ["ov_spx", "ov_ndx"]
VARIANT_FEATURES = {"US": BASE_FEATURES, "KR_base": BASE_FEATURES, "KR": BASE_FEATURES + OVERNIGHT}

LABELS = {
    "ret1": "전일 등락", "ret5": "5일 등락", "ret20": "20일 등락", "rsi": "RSI", "macd": "MACD 히스토그램",
    "bbz": "볼린저 위치", "dist5": "5일선 이격", "dist20": "20일선 이격", "dist60": "60일선 이격",
    "volr": "거래량(20일 평균 대비)", "atr": "변동성(ATR)", "clv": "당일 종가 위치(고가~저가)", "gap": "시가 갭",
    "idx1": "지수 전일 등락", "idx5": "지수 5일 등락", "rel5": "지수 대비 5일 초과수익",
    "ov_spx": "간밤 S&P500", "ov_ndx": "간밤 나스닥",
}
_PCT = {"ret1", "ret5", "ret20", "dist5", "dist20", "dist60", "atr", "gap", "idx1", "idx5", "rel5", "ov_spx", "ov_ndx"}

MIN_TRAIN = 800       # 학습 샘플이 이보다 적으면 모델 안 씀
TRAIN_DAYS = 730      # 최근 2년으로 학습
RETRAIN_EVERY = 10    # walk-forward 재학습 주기 (거래일)
MIN_CALLS = 30        # 채택 판단에 필요한 최소 예측(상승/하락 판정) 건수
UP_TH, DOWN_TH = 0.55, 0.45

_models: dict = {}
_ctx: dict = {"ts": 0.0, "idx": {}, "error": None}


# ---------------- 특징값 ----------------

def _series_by_date(candles: list) -> pd.Series:
    return pd.Series({c["date"][:10]: float(c["close"]) for c in candles}, dtype=float).sort_index()


def index_returns(idx_candles: list) -> pd.DataFrame:
    s = _series_by_date(idx_candles)
    return pd.DataFrame({"r1": s.pct_change(), "r5": s / s.shift(5) - 1})


def feature_frame(candles: list, own_idx: pd.DataFrame | None, spx: pd.DataFrame | None = None,
                  ndx: pd.DataFrame | None = None) -> pd.DataFrame:
    """일봉 → 날짜별 특징값 (각 행은 그날 종가까지의 데이터만 사용)"""
    df = pd.DataFrame(candles)
    df["date"] = df["date"].str[:10]
    c, h, l = df["close"].astype(float), df["high"].astype(float), df["low"].astype(float)
    o = df["open"].astype(float).where(df["open"] > 0, c)
    v = df["volume"].astype(float)
    prev = c.shift(1)

    f = pd.DataFrame(index=df.index)
    f["date"] = df["date"]
    f["ret1"] = c / prev - 1
    f["ret5"] = c / c.shift(5) - 1
    f["ret20"] = c / c.shift(20) - 1
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    f["rsi"] = (rsi.fillna(50) - 50) / 50
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    f["macd"] = (macd - macd.ewm(span=9, adjust=False).mean()) / c
    ma20, sd20 = c.rolling(20).mean(), c.rolling(20).std()
    f["bbz"] = (c - ma20) / (2 * sd20.replace(0, np.nan))
    f["dist5"] = c / c.rolling(5).mean() - 1
    f["dist20"] = c / ma20 - 1
    f["dist60"] = c / c.rolling(60).mean() - 1
    f["volr"] = np.log((v + 1) / (v.rolling(20).mean().shift(1) + 1))
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    f["atr"] = tr.rolling(14).mean() / c
    rng = (h - l).replace(0, np.nan)
    f["clv"] = ((c - l) / rng - 0.5).fillna(0)
    f["gap"] = o / prev - 1

    dates = f["date"]
    if own_idx is not None:
        f["idx1"] = dates.map(own_idx["r1"]).astype(float)
        f["idx5"] = dates.map(own_idx["r5"]).astype(float)
    else:
        f["idx1"] = np.nan
        f["idx5"] = np.nan
    f["rel5"] = f["ret5"] - f["idx5"]
    # 국내: 그날(한국 장 마감 후) 열린 미국장 등락 — 같은 날짜의 미국 일봉
    f["ov_spx"] = dates.map(spx["r1"]).astype(float) if spx is not None else np.nan
    f["ov_ndx"] = dates.map(ndx["r1"]).astype(float) if ndx is not None else np.nan
    # 극단값 완화 (분할·오류 데이터가 학습을 망치지 않게)
    for col in ("ret1", "ret5", "ret20", "dist5", "dist20", "dist60", "gap", "rel5"):
        f[col] = f[col].clip(-0.4, 0.4)
    f["volr"] = f["volr"].clip(-3, 3)
    f["bbz"] = f["bbz"].clip(-3, 3)
    f["macd"] = f["macd"].clip(-0.1, 0.1)
    return f


def samples(candles: list, feats: pd.DataFrame) -> pd.DataFrame:
    """학습용: 각 날짜(base) 특징값 + 다음 거래일(target) 상승 여부"""
    c = pd.Series([float(x["close"]) for x in candles])
    s = feats.copy()
    s["target_date"] = s["date"].shift(-1)
    s["y"] = (c.shift(-1) > c).astype(float)
    s["change"] = c.shift(-1) / c - 1
    s["ti"] = np.arange(len(s)) + 1
    return s.iloc[:-1]


# ---------------- 로지스틱 회귀 (numpy, L2) ----------------

def fit(X: np.ndarray, y: np.ndarray, l2: float = 5.0) -> dict:
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1
    Z = np.hstack([np.ones((len(X), 1)), (X - mean) / std])
    w = np.zeros(Z.shape[1])
    reg = np.full(Z.shape[1], l2)
    reg[0] = 0
    for _ in range(25):  # Newton(IRLS)
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) + reg * w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(reg)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return {"mean": mean.tolist(), "std": std.tolist(), "intercept": float(w[0]), "coef": w[1:].tolist()}


def predict(m: dict, X: np.ndarray) -> np.ndarray:
    z = (X - np.array(m["mean"])) / np.array(m["std"])
    return 1 / (1 + np.exp(-np.clip(m["intercept"] + z @ np.array(m["coef"]), -30, 30)))


def _acc(probs, changes) -> dict:
    """상승/하락 판정(55%/45%) 적중률 + 50% 기준 방향 적중률"""
    probs, changes = np.asarray(probs, float), np.asarray(changes, float)
    up, dn = probs >= UP_TH, probs <= DOWN_TH
    hit = int(((changes > 0) & up).sum() + ((changes < 0) & dn).sum())
    calls = int(up.sum() + dn.sum())
    dir_hit = int(((probs > 0.5) & (changes > 0)).sum() + ((probs < 0.5) & (changes < 0)).sum())
    dir_n = int((probs != 0.5).sum())
    return {"calls": calls, "hit": hit, "accuracy": round(hit / calls * 100, 1) if calls else None,
            "coverage": round(calls / len(probs) * 100, 1) if len(probs) else None,
            "dir_accuracy": round(dir_hit / dir_n * 100, 1) if dir_n else None, "n": int(len(probs))}


def walk_forward(data: pd.DataFrame, features: list, test_from: str) -> pd.Series:
    """test_from 이후 대상일을 10거래일 단위로 나눠, 각 구간은 그 이전에 결과가 나온 샘플로만 학습해 예측"""
    data = data.dropna(subset=features + ["y"])
    out = pd.Series(np.nan, index=data.index)
    test_dates = sorted(d for d in data["target_date"].unique() if d >= test_from)
    for i in range(0, len(test_dates), RETRAIN_EVERY):
        block = test_dates[i:i + RETRAIN_EVERY]
        start = block[0]
        lo = (date.fromisoformat(start) - timedelta(days=TRAIN_DAYS)).isoformat()
        tr = data[(data["target_date"] < start) & (data["target_date"] >= lo)]
        if len(tr) < MIN_TRAIN:
            continue
        m = fit(tr[features].to_numpy(), tr["y"].to_numpy())
        te = data[data["target_date"].isin(block)]
        out.loc[te.index] = predict(m, te[features].to_numpy())
    return out


# ---------------- 결합(앙상블) + 보정 ----------------
# 학습 모델 확률과 규칙 점수 확률을, 백테스트에서 '실제로 맞은 정도'만큼만 반영하도록 로지스틱 회귀로 결합.
# 실력이 없는 쪽은 가중치가 0 근처가 되고, 둘 다 없으면 확률이 50% 근처로 모여 '중립' → 해를 끼치지 않음.
STACK_BLOCKS = 5     # 백테스트 기간을 시간순 5구간으로 나눠, 앞 구간들로 결합 → 다음 구간 예측 (미래 누설 없음)
STACK_MIN = 200


def stack_features(model_p, rule_p) -> np.ndarray:
    mp = np.clip(np.asarray(model_p, float), 1e-4, 1 - 1e-4)
    return np.column_stack([np.log(mp / (1 - mp)), (np.asarray(rule_p, float) - 0.5) * 4])


def stack_predict(stack: dict, model_p: float, rule_p: float) -> float:
    return float(predict(stack, stack_features([model_p], [rule_p]))[0])


def stack_fit(test: pd.DataFrame, model_p: pd.Series) -> tuple:
    """test: target_date·y·change·rule_p, model_p: 같은 행의 walk-forward 모델 확률
    → (구간별 결합 예측 Series, 최종 결합 계수, 성적)"""
    dates = sorted(test["target_date"].unique())
    if len(dates) < STACK_BLOCKS * 2:
        return pd.Series(np.nan, index=test.index), None, {}
    bounds = [dates[int(len(dates) * k / STACK_BLOCKS)] for k in range(STACK_BLOCKS)] + ["9999"]
    X = stack_features(model_p.loc[test.index], test["rule_p"])
    y = test["y"].to_numpy()
    out = pd.Series(np.nan, index=test.index)
    td = test["target_date"].to_numpy()
    for k in range(1, STACK_BLOCKS):
        tr = td < bounds[k]
        te = (td >= bounds[k]) & (td < bounds[k + 1])
        if tr.sum() < STACK_MIN or not te.any():
            continue
        out[te] = predict(fit(X[tr], y[tr], l2=10.0), X[te])
    ev = out.dropna()
    acc = _acc(ev, test.loc[ev.index, "change"]) if len(ev) else {}
    return out, fit(X, y, l2=10.0), acc


def stack_usable(acc: dict, stack: dict | None, rule: dict) -> tuple:
    """결합 사용 조건 (엄격한 채택보다 느슨하지만, 판정이 오히려 나빠지는 경우는 막음):
    1) 모델 쪽 가중치가 양수 (모델이 높다고 하면 실제로도 더 오름)
    2) 방향 적중률 50% 초과
    3) 상승/하락 판정 MIN_CALLS 건 이상이고, 판정 적중률이 50% 와 규칙 점수보다 높음
    """
    d, n, calls, a = acc.get("dir_accuracy"), acc.get("n") or 0, acc.get("calls") or 0, acc.get("accuracy")
    if d is None or n < STACK_MIN or not stack:
        return False, f"결합 검증 데이터 부족 ({n}건)"
    if stack["coef"][0] <= 0:
        return False, "결합 결과 모델 가중치가 0 이하 (모델 신호가 실제 등락과 반대)"
    if d <= 50:
        return False, f"결합 방향 적중률 {d}% — 50% 이하"
    if calls < MIN_CALLS:
        return False, f"결합 판정이 {calls}건뿐 (최소 {MIN_CALLS}건)"
    ra = rule.get("accuracy")
    if a is None or a <= 50 or (ra is not None and a <= ra):
        return False, f"결합 판정 적중률 {a}%가 50%·규칙 {ra}%보다 높지 않음"
    return True, f"결합 방향 {d}%·판정 {a}% (규칙 {ra}%, {n}건)"


def adoption(wf: dict, rule: dict) -> tuple:
    """채택 조건 (운으로 잘 맞은 것을 걸러냄):
    1) 전체 예측의 방향(50% 기준) 적중률이 동전 던지기보다 통계적으로 높음 (단측 95%)
    2) 상승/하락 판정(55%/45%)이 MIN_CALLS 건 이상
    3) 판정 적중률이 같은 기간 규칙 점수보다 높음
    """
    n, d = wf.get("n") or 0, wf.get("dir_accuracy")
    need = 50 + 164.5 * math.sqrt(0.25 / n) if n else 100
    if d is None or n < 200 or d <= need:
        return False, f"방향 적중률 {d}%가 우연 수준(기준 {need:.1f}%, {n}건)을 못 넘음"
    if wf.get("calls", 0) < MIN_CALLS:
        return False, f"상승/하락 판정이 {wf.get('calls', 0)}건뿐 (최소 {MIN_CALLS}건)"
    if rule.get("accuracy") is not None and (wf.get("accuracy") or 0) <= rule["accuracy"]:
        return False, f"판정 적중률 {wf.get('accuracy')}%가 규칙 점수 {rule['accuracy']}%보다 높지 않음"
    return True, f"판정 적중률 {wf.get('accuracy')}% > 규칙 {rule.get('accuracy')}%, 방향 {d}% (기준 {need:.1f}%)"


def train_final(data: pd.DataFrame, variant: str, wf: dict, rule: dict, stack: dict | None = None,
                stack_acc: dict | None = None) -> dict | None:
    feats = VARIANT_FEATURES[variant]
    data = data.dropna(subset=feats + ["y"])
    if data.empty:
        return None
    lo = (date.fromisoformat(data["target_date"].max()) - timedelta(days=TRAIN_DAYS)).isoformat()
    tr = data[data["target_date"] >= lo]
    if len(tr) < MIN_TRAIN:
        return None
    m = fit(tr[feats].to_numpy(), tr["y"].to_numpy())
    adopted, reason = adoption(wf, rule)
    m.update({"variant": variant, "features": feats, "n": int(len(tr)), "adopt_reason": reason,
              "trained_until": data["target_date"].max(), "trained_at": datetime.now().isoformat(timespec="seconds"),
              "walk_forward": wf, "rules": rule, "adopted": adopted})
    usable, sreason = stack_usable(stack_acc or {}, stack, rule) if stack else (False, "결합 계산 안 됨")
    m.update({"stack": stack, "stack_eval": stack_acc or {}, "stack_usable": usable, "stack_reason": sreason})
    return m


def save(m: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"model_{m['variant']}.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    _models[m["variant"]] = m


def load(variant: str) -> dict | None:
    if variant not in _models:
        p = DATA_DIR / f"model_{variant}.json"
        try:
            _models[variant] = json.loads(p.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            _models[variant] = None
    return _models[variant]


def status() -> dict:
    out = {}
    for v in VARIANT_FEATURES:
        m = load(v)
        out[v] = None if not m else {k: m.get(k) for k in ("n", "trained_until", "trained_at", "walk_forward",
                                                           "rules", "adopted", "adopt_reason", "stack_eval",
                                                           "stack_usable", "stack_reason")}
    out["index_data"] = {"updated": _ctx["ts"] and datetime.fromtimestamp(_ctx["ts"]).isoformat(timespec="seconds"),
                         "error": _ctx["error"]}
    return out


# ---------------- 실시간 예측 ----------------

async def refresh_ctx():
    """지수 일봉(코스피·코스닥·S&P500·나스닥) — 실시간 예측의 지수 특징값용 (10분마다)"""
    from app.services.quote import batch_yf_history  # 순환 import 방지
    try:
        hist = await batch_yf_history(list(IDX_TICKERS.values()), "3mo")
        missing = [t for t, cs in hist.items() if len(cs) < 10]
        if missing:
            raise RuntimeError(f"지수 일봉 부족: {', '.join(missing)}")
        hist = {t: list(cs) for t, cs in hist.items()}
        await _patch_kr_index(hist)
        _ctx.update(ts=time.time(), idx={t: index_returns(cs) for t, cs in hist.items()},
                    raw={t: cs for t, cs in hist.items()}, error=None)
    except Exception as e:
        _ctx["error"] = str(e)
        print(f"[model] 지수 데이터 조회 실패: {e}")


async def _patch_kr_index(hist: dict):
    """Yahoo 의 코스피·코스닥 일봉은 하루 늦게 갱신되는 경우가 있어, 최신 거래일 값은 KIS 실시간 지수로 채움
    (KIS 실패 시 Yahoo 값 그대로 — 그 날짜가 없으면 live_predict 가 '특징값 부족'으로 규칙 점수를 씀)"""
    from app.services.kis_api import kis_client
    from app.services.market_calendar import last_session_date
    day = last_session_date("KR").isoformat()
    for code, ticker in (("0001", IDX_TICKERS["KOSPI"]), ("1001", IDX_TICKERS["KOSDAQ"])):
        try:
            v = await kis_client.get_kr_index(code)
        except Exception as e:
            print(f"[model] KIS 지수({code}) 조회 실패 — Yahoo 값 사용: {e}")
            continue
        cs = [c for c in hist.get(ticker, []) if c["date"][:10] != day]
        cs.append({"date": day, "open": v["price"], "high": v["price"], "low": v["price"],
                   "close": v["price"], "volume": 0})
        hist[ticker] = cs


def _us_session_closed(d: str) -> bool:
    now = datetime.now(ZoneInfo("America/New_York"))
    day = date.fromisoformat(d)
    return now.date() > day or (now.date() == day and now.hour * 60 + now.minute >= 16 * 60 + 20)


def live_predict(market: str, symbol: str, candles: list) -> dict:
    """현재 일봉으로 학습 모델 확률 계산 → {"prob", "variant", "drivers", ...} 또는 {"status": 사유}"""
    from app.services.prediction_log import index_key  # 순환 import 방지
    if len(candles) < 61:
        return {"status": "일봉 61개 미만 — 학습 모델 사용 불가"}
    if not _ctx["idx"]:
        return {"status": f"지수 데이터 준비 중{' (' + _ctx['error'] + ')' if _ctx['error'] else ''}"}
    key = index_key(market, symbol)
    own = _ctx["idx"].get(IDX_TICKERS[key])
    base_date = candles[-1]["date"][:10]
    variant = "US"
    spx = ndx = None
    if market == "KR":
        spx, ndx = _ctx["idx"].get(IDX_TICKERS["US"]), _ctx["idx"].get(IDX_TICKERS["NDX"])
        known = (_us_session_closed(base_date) and spx is not None and base_date in spx.index
                 and not math.isnan(spx.loc[base_date, "r1"]))
        full = load("KR")
        variant = "KR" if known and full and (full.get("stack_usable") or full.get("adopted")) else "KR_base"
    m = load(variant)
    if not m:
        return {"status": "학습 모델 없음 — 백테스트가 끝나면 학습됨"}
    feats = feature_frame(candles[-130:], own, spx, ndx)
    row = feats.iloc[-1]
    if row[m["features"]].isna().any():
        miss = [LABELS[f] for f in m["features"] if pd.isna(row[f])]
        return {"status": f"특징값 부족 ({', '.join(miss[:3])})", "variant": variant}
    x = row[m["features"]].to_numpy(dtype=float)
    p = float(predict(m, x[None, :])[0])
    z = (x - np.array(m["mean"])) / np.array(m["std"])
    contrib = np.array(m["coef"]) * z
    order = np.argsort(-np.abs(contrib))[:3]
    drivers = []
    for i in order:
        f = m["features"][i]
        val = f"{x[i] * 100:+.1f}%" if f in _PCT else f"{x[i]:+.2f}"
        drivers.append({"feature": f, "label": LABELS[f], "value": val, "effect": float(contrib[i])})
    use = "stack" if m.get("stack_usable") and m.get("stack") else "model" if m.get("adopted") else None
    return {"prob": p, "variant": variant, "adopted": bool(m.get("adopted")), "reason": m.get("adopt_reason"),
            "use": use, "stack": m.get("stack"), "stack_eval": m.get("stack_eval"),
            "stack_reason": m.get("stack_reason"),
            "drivers": drivers,
            "n": m.get("n"), "walk_forward": m.get("walk_forward"), "rules": m.get("rules")}
