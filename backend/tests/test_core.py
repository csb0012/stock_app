"""기존 핵심 계산의 기본 안전장치: 지표에 NaN 없음 · 확률 범위 · 가격대 순서 · SWR 캐시 · 미래 데이터 미사용"""
import asyncio
import json
import math

import pytest

from tests.conftest import run
from app.core.swr import SWRCache
from app.services.analysis import calc_technical_indicators, predict_next_day


def make(closes):
    return [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c, "high": c * 1.01, "low": c * 0.99,
             "close": c, "volume": 1000 + i} for i, c in enumerate(closes)]


@pytest.mark.parametrize("closes", [
    [100.0] * 80,                                         # 가격 변동 없음 (분모 0)
    [100.0 + i for i in range(80)],                       # 계속 상승
    [100.0 - i * 0.5 for i in range(80)],                 # 계속 하락
    [100.0, 101.0, 99.0],                                 # 데이터 부족
])
def test_indicators_json_safe(closes):
    ind = calc_technical_indicators(make(closes))
    json.dumps(ind, allow_nan=False)                      # NaN/inf 가 있으면 ValueError
    for v in ind.values():
        assert not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def test_prediction_ranges_and_levels():
    c = make([100 + (i % 7) - 3 + i * 0.2 for i in range(90)])
    p = predict_next_day(c, calc_technical_indicators(c))
    assert 15 <= p["probability"] <= 85
    assert p["stop_loss"] < p["buy_price"] <= c[-1]["close"] * 1.0001 < p["target_price"]
    json.dumps(p, allow_nan=False, default=str)


def test_prediction_no_future_data():
    """그날까지의 데이터만 쓰는지: 뒤에 붙는 데이터가 바뀌어도 그날 결과는 같아야 함"""
    base = [100 + (i % 5) + i * 0.1 for i in range(80)]
    a = make(base + [150, 160])[:80]
    b = make(base + [50, 40])[:80]
    pa = predict_next_day(a, calc_technical_indicators(a))
    pb = predict_next_day(b, calc_technical_indicators(b))
    assert pa["probability"] == pb["probability"] and pa["target_price"] == pb["target_price"]


def test_swr_fresh_stale_and_error():
    async def scenario():
        c = SWRCache("t", fresh=0.05, max_stale=10)
        n = {"v": 0, "fail": False}

        async def fn():
            n["v"] += 1
            if n["fail"]:
                raise RuntimeError("갱신 실패")
            return {"v": n["v"]}
        first = await c.get("k", fn)
        assert first["v"] == 1 and first["refreshing"] is False and "updated_at" in first
        assert (await c.get("k", fn))["v"] == 1             # 신선 기간 안 → 다시 안 부름
        await asyncio.sleep(0.06)
        n["fail"] = True
        stale = await c.get("k", fn)                        # 오래됨 → 기존 값 바로 + 뒤에서 갱신
        assert stale["v"] == 1 and stale["refreshing"] is True
        await asyncio.sleep(0.01)
        after = await c.get("k", fn)
        assert after["v"] == 1 and "갱신 실패" in (after.get("refresh_error") or "")
        c.invalidate()
        with pytest.raises(RuntimeError):                   # 값이 없으면 오류 그대로 (빈 값으로 숨기지 않음)
            await c.get("k", fn)
    run(scenario())
