"""시장 상태: 추세·분산일 판단 · 미래 데이터 미사용 · 검증 표 · 데이터 부족"""
import json

import numpy as np
import pandas as pd

from tests.conftest import run
from app.services import market_regime as mr


def idx(closes, vols=None, start="2021-01-04"):
    dates = pd.bdate_range(start, periods=len(closes)).strftime("%Y-%m-%d")
    vols = vols if vols is not None else [1e6] * len(closes)
    return [{"date": d, "open": c, "high": c, "low": c, "close": c, "volume": v} for d, c, v in zip(dates, closes, vols)]


def test_uptrend_downtrend_pressure():
    up = list(np.linspace(2000, 3000, 300))
    assert mr.summarize("KOSPI", idx(up))["state"] == "상승 추세"
    down = list(np.linspace(3000, 2000, 300))
    s = mr.summarize("KOSPI", idx(down))
    assert s["state"] == "하락 추세" and s["vs_ma200"] < 0
    # 오르다가 최근 50일선 아래로 밀림 (200일선 위) → 상승 압박
    pres = list(np.linspace(2000, 3000, 280)) + list(np.linspace(3000, 2850, 20))
    assert mr.summarize("KOSPI", idx(pres))["state"] == "상승 압박"


def test_distribution_days_turn_uptrend_into_pressure():
    closes = list(np.linspace(2000, 3000, 300))
    vols = [1e6] * 300
    # 최근 25일 중 6일: 0.3% 하락 + 거래량 증가 (그 전후로는 다시 회복해 추세 유지)
    for k in range(6):
        i = 280 + k * 3
        closes[i] = closes[i - 1] * 0.997
        vols[i] = 2e6
    s = mr.summarize("KOSPI", idx(closes, vols))
    assert s["dist_days"] >= 5 and s["state"] == "상승 압박"
    assert mr.summarize("KOSPI", idx(closes, [0] * 300))["dist_days"] is None   # 지수 거래량 없음


def test_no_future_data_and_validation():
    rng = np.random.default_rng(2)
    base = list(3000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 900))))
    a = mr.regime_frame(idx(base[:800] + [x * 3 for x in base[800:]]))
    b = mr.regime_frame(idx(base[:800] + [x * 0.3 for x in base[800:]]))
    assert a["state"].iloc[:800].tolist() == b["state"].iloc[:800].tolist()
    s = mr.summarize("SPX", idx(base))
    json.dumps(s, allow_nan=False)
    v = {r["state"]: r for r in s["validation"]}
    assert sum(r["n"] for r in v.values()) == 900 - 199 - 20
    assert all(r["up_rate"] is None or 0 <= r["up_rate"] <= 100 for r in v.values())


def test_short_data_and_get_all(monkeypatch):
    assert "error" in mr.summarize("KOSPI", idx([2000.0] * 100))
    from app.services import quote

    async def fake_hist(tickers, period):
        return {t: (idx(list(np.linspace(2000, 3000, 300))) if t != "^KQ11" else []) for t in tickers}
    monkeypatch.setattr(quote, "batch_yf_history", fake_hist)
    out = run(mr.get_all())
    assert out["items"]["KOSPI"]["state"] == "상승 추세" and "error" in out["items"]["KOSDAQ"]
    assert out["items"]["KOSPI"]["stale"]                         # 2021년 데이터 → 최신 아님 표시

    async def empty(tickers, period):
        return {t: [] for t in tickers}
    monkeypatch.setattr(quote, "batch_yf_history", empty)
    try:
        run(mr.get_all())
        assert False, "전부 실패면 오류여야 함"
    except RuntimeError as e:
        assert "지수 데이터를 받지 못함" in str(e)
