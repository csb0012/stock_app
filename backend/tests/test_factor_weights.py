"""예측 검증 결과로 지표 비중 조정 — 덜 맞은 지표만 줄임 · 날짜별 검증(그 전 결과만 씀)에서 나을 때만 채택 · 실시간에만 적용"""
import datetime as dt
import json

import numpy as np
import pytest

from tests.conftest import run
from app.services import factor_weights as fw
from app.services.analysis import calc_technical_indicators, predict_next_day


def F(rsi, macd, bb=10, ma=12):
    return [{"name": "RSI", "score": rsi, "max": 30}, {"name": "MACD", "score": macd, "max": 25},
            {"name": "볼린저밴드", "score": bb, "max": 20}, {"name": "이동평균", "score": ma, "max": 25}]


def synth(days=160, per_day=12, seed=1, rsi_good=False):
    """RSI 는 거꾸로 맞고(상승 신호 → 실제 하락) MACD 는 잘 맞는 가짜 기록 (rsi_good 이면 RSI 도 잘 맞음)"""
    rng = np.random.default_rng(seed)
    rows, d = [], dt.date(2025, 6, 2)
    for _ in range(days):
        for _ in range(per_day):
            up = rng.random() < 0.5
            macd = 25 if (up if rng.random() < 0.62 else not up) else 0
            rsi = 30 if ((up if rsi_good else not up) if rng.random() < 0.62 else (not up if rsi_good else up)) else 0
            rows.append((d.isoformat(), F(rsi, macd), float(rng.uniform(0.2, 3)) * (1 if up else -1)))
        d += dt.timedelta(days=1)
    return rows


def test_weight_rule():
    assert fw.weight_for(None, 1000) == 1.0 and fw.weight_for(40, 100) == 1.0          # 신호 부족 → 그대로
    assert fw.weight_for(53, 1000) == 1.0 and fw.weight_for(51, 1000) == 1.0           # 늘리지는 않음
    assert fw.weight_for(46, 1000) == fw.MIN_WEIGHT and fw.weight_for(30, 1000) == fw.MIN_WEIGHT
    assert fw.weight_for(48.5, 1000) == pytest.approx(0.65, abs=0.01)


def test_probability_matches_analysis():
    rng = np.random.default_rng(3)
    p, cs, d = 100.0, [], dt.date(2025, 1, 2)
    for _ in range(130):
        p *= 1 + rng.normal(0, 0.02)
        cs.append({"date": d.isoformat(), "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1e6})
        d += dt.timedelta(days=1)
    pred = predict_next_day(cs, calc_technical_indicators(cs))
    assert fw.probability(pred["factors"]) == pred["rule_probability"]


def test_bad_factor_is_reduced_and_adopted():
    r = fw.evaluate(synth())
    by = {f["name"]: f for f in r["factors"]}
    assert by["RSI"]["accuracy"] < 45 and by["RSI"]["weight"] == fw.MIN_WEIGHT
    assert by["MACD"]["accuracy"] > 55 and by["MACD"]["weight"] == 1.0
    wf = r["walk_forward"]
    assert wf["n"] >= fw.MIN_TEST and wf["weighted_accuracy"] > wf["base_accuracy"]
    assert r["adopted"] and "더 잘 맞음" in r["reason"]


def test_not_adopted_when_no_gain_or_too_few():
    rng = np.random.default_rng(5)
    noise = [(f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", F(30 if rng.random() < 0.5 else 0, 25 if rng.random() < 0.5 else 0),
              float(rng.choice([-1, 1]))) for i in range(300) for _ in range(1)]
    r = fw.evaluate(noise)
    assert not r["adopted"]
    assert fw.evaluate([])["adopted"] is False


def test_walk_forward_uses_only_past_results():
    """날짜 D 에 쓰는 비중은 D 전에 결과가 나온 기록만으로 — 이후 결과를 바꿔도 그 전 날짜의 비중은 같아야 함"""
    rows = synth(days=120, rsi_good=True)     # 앞쪽은 모든 지표가 잘 맞음 → 비중 그대로
    a, b = [], []
    ra = fw.evaluate(rows, a)
    cut = a[5][0]    # 검증 초반 6일 — 그 뒤 결과를 뒤집음 (전체로 보면 지표가 덜 맞게 됨)
    flipped = [(t, f, -ch if t >= cut else ch) for t, f, ch in rows]
    rb = fw.evaluate(flipped, b)
    before = [x for x in a if x[0] <= cut]
    assert before and before == [x for x in b if x[0] <= cut]
    assert all(v == 1.0 for _, w in before for v in w.values())   # 뒤쪽 결과(뒤집힘)를 미리 알면 앞쪽 비중이 줄었을 것
    assert ra["walk_forward"] != rb["walk_forward"] and ra["factors"] != rb["factors"]   # 바뀐 결과는 이후 계산에만 반영


def test_predict_uses_weights_only_for_rules():
    rng = np.random.default_rng(7)
    p, cs, d = 100.0, [], dt.date(2025, 1, 2)
    for _ in range(130):
        p *= 1 + rng.normal(0.003, 0.02)
        cs.append({"date": d.isoformat(), "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1e6})
        d += dt.timedelta(days=1)
    ind = calc_technical_indicators(cs)
    base = predict_next_day(cs, ind)
    w = {"RSI": 0.3, "MACD": 0.3}
    adj = predict_next_day(cs, ind, weights=w)
    assert adj["rule_probability"] == base["rule_probability"]          # 원래 비중 확률은 그대로 기록
    assert adj["weighted_probability"] == fw.probability(base["factors"], w)
    assert adj["probability"] == adj["weighted_probability"] and adj["method"] == "rules:weighted"
    rsi = next(f for f in adj["factors"] if f["name"] == "RSI")
    assert rsi["weight"] == 0.3 and "비중 ×0.3" in rsi["detail"]
    model = {"prob": 0.61, "use": "model", "variant": "US", "n": 1000, "drivers": [], "walk_forward": {}}
    m = predict_next_day(cs, ind, model=dict(model), weights=w)
    assert m["method"] == "model:US" and m["probability"] == predict_next_day(cs, ind, model=dict(model))["probability"]


def test_live_and_recompute(monkeypatch, tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import StaticPool
    from app.core import database
    from app.core.database import Base
    from app.models.prediction import BacktestLog
    monkeypatch.setattr(fw, "_FILE", tmp_path / "factor_weights.json")
    monkeypatch.setitem(fw._cache, "loaded", False)
    assert fw.live("KR") is None and fw.report() is None
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", Session)

    async def fill():
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with Session() as s:
            for i, (t, f, ch) in enumerate(synth()):
                s.add(BacktestLog(market="KR", symbol=f"S{i % 12}", target_date=t, base_date=t, base_price=1, probability=50,
                                  factors=json.dumps(f + [{"name": "뉴스", "score": 15, "max": 15}]), evaluated=True, actual_change=ch))
            s.add(BacktestLog(market="US", symbol="X", target_date="2025-06-02", base_date="2025-06-01", base_price=1, probability=50,
                              factors=json.dumps(F(30, 25)), evaluated=False))
            await s.commit()
    run(fill())
    v0 = fw.version()
    m = run(fw.recompute())
    assert set(m) == {"KR"} and m["KR"]["adopted"] and fw.version() == v0 + 1
    assert fw.live("KR") == {"RSI": fw.MIN_WEIGHT} and fw.live("US") is None
    assert json.loads((tmp_path / "factor_weights.json").read_text(encoding="utf-8"))["markets"]["KR"]["adopted"]
    monkeypatch.setitem(fw._cache, "loaded", False)       # 다시 켜도 파일에서 읽음
    assert fw.live("KR") == {"RSI": fw.MIN_WEIGHT}
    run(engine.dispose())
