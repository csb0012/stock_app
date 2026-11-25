"""백테스트: 1년 기간 설정 · 저장된 날짜는 규칙 점수를 다시 계산하지 않음 (미래 데이터 미사용 유지)"""
import numpy as np

from app.services import backtest


def _candles(n=300, seed=1):
    rng = np.random.default_rng(seed)
    p = 100 * np.cumprod(1 + rng.normal(0, 0.02, n))
    out = []
    import datetime as dt
    d = dt.date(2025, 1, 1)
    for x in p:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        out.append({"date": d.isoformat(), "open": x, "high": x * 1.01, "low": x * 0.99, "close": x, "volume": 1e6})
        d += dt.timedelta(days=1)
    return out


def test_backtest_period_is_one_year():
    assert backtest.DAYS == 365 and backtest.status()["days"] == 365
    assert backtest.KR_COUNT >= 750      # 1년 + 학습 2년


def test_rule_preds_reuses_saved(monkeypatch):
    cs = _candles()
    cutoff = cs[200]["date"]
    st = {"market": "US", "symbol": "X"}
    full = backtest._rule_preds(st, cs, cutoff)
    saved = {t: p["probability"] for t, (_, p) in list(full.items())[:50]}
    calls = []
    orig = backtest.predict_next_day
    monkeypatch.setattr(backtest, "predict_next_day", lambda *a, **k: calls.append(1) or orig(*a, **k))
    again = backtest._rule_preds(st, cs, cutoff, saved)
    assert set(again) == set(full)
    assert len(calls) == len(full) - 50                         # 저장된 50일은 계산 안 함
    for t, (ti, p) in again.items():
        assert p["probability"] == full[t][1]["probability"]    # 저장값 = 다시 계산한 값
        assert ti == full[t][0]


def test_rule_preds_no_future_data():
    """대상일 t 의 예측은 t 이후 일봉을 바꿔도 같아야 함"""
    cs = _candles()
    cutoff = cs[200]["date"]
    st = {"market": "US", "symbol": "X"}
    a = backtest._rule_preds(st, cs, cutoff)
    t = cs[220]["date"]
    cs2 = [dict(c) for c in cs]
    for c in cs2[220:]:
        c["close"] *= 3
        c["high"] *= 3
    b = backtest._rule_preds(st, cs2, cutoff)
    assert a[t][1]["probability"] == b[t][1]["probability"]
