"""퀀트 점수: 요인 계산 · 미래 데이터 미사용 · 가중치(IC) 학습 · 뒤쪽 기간 검증 · 경계값"""
import json
import time

import numpy as np
import pandas as pd
import pytest

from app.services import quant


def candles(closes, vol=None, start="2026-01-01"):
    dates = pd.bdate_range(start, periods=len(closes)).strftime("%Y-%m-%d")
    vol = vol if vol is not None else [100000] * len(closes)
    return [{"date": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": v}
            for d, c, v in zip(dates, closes, vol)]


def walk(n, drift, seed, vol=0.02):
    rng = np.random.default_rng(seed)
    return list(10000 * np.exp(np.cumsum(rng.normal(drift, vol, n))))


def test_factor_frame_shape_and_short_data():
    f = quant.factor_frame(candles(walk(200, 0, 1)))
    assert len(f) == 200 - quant.MIN_ROWS + 1
    assert set(quant.KEYS) <= set(f.columns)
    assert f["fwd20"].iloc[-20:].isna().all() and f["fwd20"].iloc[:-20].notna().all()
    assert quant.factor_frame(candles(walk(100, 0, 1))).empty          # 6개월 미만 → 빈 표
    flat = quant.factor_frame(candles([10000.0] * 200))                 # 가격 변동 없음
    assert not np.isinf(flat[quant.KEYS].to_numpy(dtype=float)).any()


def test_factor_frame_no_future_data():
    base = walk(200, 0.001, 7)
    a = quant.factor_frame(candles(base[:180] + [x * 2 for x in base[180:]]))
    b = quant.factor_frame(candles(base[:180] + [x * 0.5 for x in base[180:]]))
    cols = quant.KEYS
    # 180번째 날까지의 요인 값은 그 뒤 가격과 무관해야 함
    pd.testing.assert_frame_equal(a.iloc[:180 - quant.MIN_ROWS + 1][cols], b.iloc[:180 - quant.MIN_ROWS + 1][cols])


def make_universe(n=240, persistent=True, seed=0):
    """모멘텀이 이어지는 종목(추세 지속)을 섞은 가짜 전 종목 — persistent=False 면 순수 무작위"""
    rng = np.random.default_rng(seed)
    frames, names = {}, {}
    for i in range(n):
        drift = rng.normal(0, 0.003) if persistent else 0.0
        closes = walk(200, drift, seed * 1000 + i)
        frames[f"{i:06d}"] = quant.factor_frame(candles(closes))
        names[f"{i:06d}"] = f"종목{i}"
    return frames, names


def test_build_detects_persistent_momentum():
    frames, names = make_universe(persistent=True)
    q = quant.build(frames, names)
    json.dumps(q, allow_nan=False)
    assert q["universe"] == 240 and len(q["scores"]) == 240
    assert abs(sum(q["weights"].values()) - 1) < 1e-6
    v = q["validation"]
    assert v and v["train"][1] < v["test"][0]                           # 학습 구간이 검증 구간보다 앞
    # 추세가 이어지는 가짜 시장 → 모멘텀(RS)이 맞는 요인으로 잡히고, 상위 구간이 하위 구간보다 나아야 함
    assert q["ic"]["rs"] > 0.1 and q["weights"]["rs"] > 0
    top, bottom = v["buckets"][0], v["buckets"][-1]
    assert top["beat_rate"] > 55 > bottom["beat_rate"] and v["spread"] > 0
    s = next(iter(q["scores"].values()))
    assert 1 <= s["score"] <= 10 and s["grade"] in {"A+", "A", "B+", "B", "C", "D", "F"}
    assert q["top"][0]["pct"] >= q["top"][-1]["pct"] and q["top"][0]["name"].startswith("종목")


def test_build_random_market_is_honest():
    """무작위 시장에선 '검증'이 우연 수준으로 나와야 함 (좋아 보이게 꾸미지 않음)"""
    frames, names = make_universe(persistent=False, seed=3)
    v = quant.build(frames, names)["validation"]
    for b in v["buckets"]:
        assert 35 < b["beat_rate"] < 65


def test_build_excludes_illiquid_and_empty():
    assert quant.build({}) is None
    assert quant.build({"A": quant.factor_frame(candles(walk(100, 0, 1)))}) is None
    frames, _ = make_universe(n=30)
    frames["ILLQ"] = quant.factor_frame(candles(walk(200, 0, 9), vol=[1] * 200))   # 거래대금 1억 미만
    q = quant.build(frames)
    assert "ILLQ" not in q["scores"]


def test_grade_edges():
    assert quant.grade(99) == "A+" and quant.grade(90) == "A+" and quant.grade(89.9) == "A"
    assert quant.grade(0) == "F" and quant.grade(19.9) == "F" and quant.grade(20) == "D"


def test_build_speed_full_universe():
    """실제 전 종목(약 2,500개) 크기에서도 스캔 끝에 몇 초 안에 끝나야 함"""
    one = quant.factor_frame(candles(walk(200, 0.0005, 5)))
    rng = np.random.default_rng(1)
    frames = {f"{i:06d}": one.assign(**{k: one[k] * rng.uniform(0.5, 1.5) for k in quant.KEYS},
                                     fwd20=one["fwd20"] * rng.uniform(0.5, 1.5)) for i in range(2500)}
    t = time.time()
    q = quant.build(frames)
    assert q["universe"] == 2500
    assert time.time() - t < 30


def test_scan_stores_quant_and_api(monkeypatch, tmp_path):
    """매집 스캔(가짜 KIS 일봉) → 결과 파일에 퀀트 점수 → /api/quant · quant_of · 퀀트 실패해도 매집 결과는 저장"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests.conftest import run
    from app.services import accumulation, stock_master, kis_api, themes
    from app.api.routes import accumulation as route
    from app.api.routes.auth import get_current_user

    syms = [f"{i:06d}" for i in range(60)]
    monkeypatch.setattr(stock_master, "_items", [{"market": "KR", "symbol": s, "name": f"종목{s}", "type": "stock"} for s in syms])
    monkeypatch.setattr(stock_master, "_by_key", {("KR", s): {"name": f"종목{s}", "type": "stock"} for s in syms})
    monkeypatch.setattr(stock_master, "category", lambda i: "stock")
    monkeypatch.setattr(accumulation, "_FILE", tmp_path / "accumulation.json")
    monkeypatch.setattr(accumulation, "_FRAMES", tmp_path / "quant_frames.pkl")   # 실제 app/data 를 건드리지 않게
    monkeypatch.setattr(accumulation, "_result", None)
    monkeypatch.setattr(themes, "themes_of", lambda s: [])

    async def fake_chart(sym, count):
        return {"candles": candles(walk(200, 0.0005 * (int(sym) % 5 - 2), int(sym)))}
    monkeypatch.setattr(kis_api.kis_client, "get_kr_chart", fake_chart)
    run(accumulation.scan())
    r = accumulation.result()
    assert r["quant"]["universe"] == 60 and "quant_error" not in r
    q = accumulation.quant_of("000001")
    assert q and 1 <= q["score"] <= 10 and q["date"] == r["quant"]["date"]
    assert accumulation.quant_of("999999") is None

    app = FastAPI()
    app.include_router(route.quant_router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: object()
    body = TestClient(app).get("/api/quant?limit=5").json()
    assert len(body["quant"]["top"]) == 5 and body["quant"]["validation"]["buckets"]
    assert "scores" not in body["quant"]                               # 전 종목 점수는 응답에 안 실음 (크기)

    # 퀀트 계산이 터져도 매집 결과는 저장
    def boom(*a, **k):
        raise RuntimeError("테스트 오류")
    monkeypatch.setattr(quant, "build", boom)
    run(accumulation.scan())
    r = accumulation.result()
    assert r["quant"] is None and "테스트 오류" in r["quant_error"] and r["scanned"] == 60
    assert TestClient(app).get("/api/quant").json()["error"].startswith("퀀트 점수 계산 실패")


def test_rebuild_quant_from_saved_frames(monkeypatch, tmp_path):
    """재무·수급이 새로 들어오면 저장해 둔 요인 원값으로 퀀트만 다시 (KIS 호출 없음) — 추가 요인이 점수표에 들어감"""
    from tests.conftest import run
    from app.services import accumulation, stock_master, kis_api, fundamentals, flows

    syms = [f"{i:06d}" for i in range(40)]
    monkeypatch.setattr(stock_master, "_items", [{"market": "KR", "symbol": s, "name": s, "type": "stock"} for s in syms])
    monkeypatch.setattr(stock_master, "_by_key", {("KR", s): {"name": s, "type": "stock"} for s in syms})
    monkeypatch.setattr(stock_master, "category", lambda i: "stock")
    monkeypatch.setattr(accumulation, "_FILE", tmp_path / "accumulation.json")
    monkeypatch.setattr(accumulation, "_FRAMES", tmp_path / "quant_frames.pkl")
    monkeypatch.setattr(accumulation, "_result", None)
    monkeypatch.setattr(flows, "_mem", {})
    monkeypatch.setattr(fundamentals, "kr_factor_frame", lambda frames: None)

    async def fake_chart(sym, count):
        return {"candles": candles(walk(200, 0.0003 * (int(sym) % 3 - 1), int(sym) + 7))}
    monkeypatch.setattr(kis_api.kis_client, "get_kr_chart", fake_chart)
    run(accumulation.scan())
    assert (tmp_path / "quant_frames.pkl").exists()
    assert "value" not in accumulation.result()["quant"]["weights"]

    async def no_kis(*a, **k):
        raise AssertionError("다시 계산할 때 KIS 를 부르면 안 됨")
    monkeypatch.setattr(kis_api.kis_client, "get_kr_chart", no_kis)

    def fake_value(frames):
        rows = [{"date": d, "symbol": s, "value": float(i), "quality": None}
                for i, (s, f) in enumerate(frames.items()) for d in f["date"]]
        return pd.DataFrame(rows)
    monkeypatch.setattr(fundamentals, "kr_factor_frame", fake_value)
    assert run(accumulation.rebuild_quant()) is True
    q = accumulation.result()["quant"]
    assert "value" in q["weights"] and any(f["key"] == "value" for f in q["factors"])
    assert q["scores"]["000001"]["factors"]["value"] is not None
    monkeypatch.setattr(accumulation, "_FRAMES", tmp_path / "없음.pkl")       # 원값 파일이 없으면 안 함
    assert run(accumulation.rebuild_quant()) is False
