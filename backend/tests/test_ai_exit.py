"""AI 매도 판단 (사용자 요청 2026-11-27): 익절 보류·이익 지키기·손절 보류·강제 손절·보유일 연장·물타기.
꺼져 있으면 예전 규칙과 똑같아야 하고, 켜도 미래 데이터를 쓰지 않아야 함"""
import numpy as np
import pytest

from app.services import paper_engine as pe
from tests.test_papertrade import series, universe, _rows

ON = {"ai_exit": True}


def _pos(params, px=100.0, **kw):
    st = pe.new_state(1e6)
    pe.fill_buy(st, "A", "가", 10_000, px, "d0", "r", params, "US")
    st["positions"]["A"].update(kw)
    return st, st["positions"]["A"]


def test_defaults_off_and_hard_stop():
    p = pe.clean_params({})
    assert p["ai_exit"] is False and p["avg_down"] is False
    assert pe.hard_pct(pe.clean_params({"stop_pct": 7})) == 14
    assert pe.hard_pct(pe.clean_params({"stop_pct": 20})) == 30      # 손절 +10% 까지만
    params = pe.clean_params(ON)
    _, p = _pos(params)
    assert pe.hard_stop(p, params) == pytest.approx(p["entry_px"] * 0.86)


def test_live_exit_off_is_old_rule():
    params = pe.clean_params({})
    _, p = _pos(params, ai_hold=True)
    assert pe.live_exit(p, p["stop"] - 0.01, params)[0] == "stop"
    assert pe.live_exit(p, p["target"] + 0.01, params)[0] == "target"
    assert pe.live_exit(p, p["avg"], params) is None


def test_live_exit_holds_stop_once_then_hard_stop():
    params = pe.clean_params(ON)
    _, p = _pos(params, ai_hold=True)
    k, memo = pe.live_exit(p, p["stop"] - 0.5, params)
    assert k == "hold" and "보류" in memo and p["stop_held"]
    assert pe.live_exit(p, p["stop"] - 1, params) is None              # 같은 보류를 계속 알리지 않음
    assert pe.live_exit(p, pe.hard_stop(p, params) - 0.01, params)[0] == "hard"
    p["ai_hold"] = False                                               # AI 가 약해지면 그냥 손절
    p["stop_held"] = False
    assert pe.live_exit(p, p["stop"] - 0.5, params)[0] == "stop"


def test_live_exit_ride_raises_stop_and_target():
    params = pe.clean_params(ON)
    _, p = _pos(params, ai_hold=True)
    t0, avg = p["target"], p["avg"]
    k, memo = pe.live_exit(p, t0 + 0.1, params)
    assert k == "ride" and "안 팖" in memo
    assert p["stop"] == pytest.approx(t0 * 0.93) and p["stop"] > avg   # 이익 지키는 손절가
    assert p["target"] == pytest.approx(t0 * 1.075)
    # 올라간 손절가(이익 쪽)는 AI 가 보류하지 않음 — 그대로 팜
    assert pe.live_exit(p, p["stop"] - 0.01, params)[0] == "stop"


def test_intraday_exit_with_ai_exit():
    params = pe.clean_params(ON)
    _, p = _pos(params, ai_hold=True)
    hs = pe.hard_stop(p, params)
    assert pe.intraday_exit(p, hs - 1, hs, hs - 2, params) == (hs - 1, "강제 손절 — 시가가 강제 손절선 아래로 출발")
    assert pe.intraday_exit(p, 99, 100, hs - 1, params)[0] == pytest.approx(hs)
    hit = pe.intraday_exit(p, 99, 100, p["stop"] - 0.5, params)
    assert hit[0] is None and "보류" in hit[1]
    _, q = _pos(params, ai_hold=True)
    hit = pe.intraday_exit(q, 110, q["target"] + 1, 109, params)
    assert hit[0] is None and q["stop"] > q["avg"]
    _, r = _pos(params, ai_hold=True)       # 같은 날 손절·목표 둘 다 → 예전처럼 손절 먼저 (보수적)
    assert pe.intraday_exit(r, 100, r["target"] + 1, r["stop"] - 0.1, pe.clean_params({}))[0] == pytest.approx(r["stop"])


def test_decide_profit_lock_and_stop_review():
    params = pe.clean_params(ON)
    st = pe.new_state(1e6)
    for s in ("A", "B", "C"):
        pe.fill_buy(st, s, s, 10_000, 100, "d", "r", params, "US")
    rows = {**_rows({"A": 55}, close=106, prob=45),     # 이익 6% + 하락 쪽 확신 → 이익 지키기
            **_rows({"B": 50}, close=92, prob=50),      # 손절선 아래 + AI 약함 → 매도
            **_rows({"C": 70}, close=92, prob=60)}      # 손절선 아래 + AI 강세 → 보류 (물타기 꺼짐)
    orders, notes = pe.decide(st, rows, "상승 추세", [], params, "US")
    sells = {o["symbol"]: o["reason"] for o in orders if o["side"] == "sell"}
    assert set(sells) == {"A", "B"} and "이익 지키기" in sells["A"] and "회복 기대 낮음" in sells["B"]
    assert any("C 손절선 아래" in n and "보류" in n for n in notes)
    assert st["positions"]["C"]["ai_hold"] is True and st["positions"]["B"]["ai_hold"] is False
    # 끄면 예전 규칙: 확률 45%·손절선 아래 종가는 종가 판단으로 안 팖 (장중 손절이 처리)
    off, _ = pe.decide(st, rows, "상승 추세", [], pe.clean_params({}), "US")
    assert [o for o in off if o["side"] == "sell"] == []


def test_decide_max_hold_extension():
    params = pe.clean_params({**ON, "max_hold": 5})
    st = pe.new_state(1e6)
    for s in ("A", "B", "C"):
        pe.fill_buy(st, s, s, 10_000, 100, "d", "r", params, "US")
    st["positions"]["A"]["hold_days"] = 5
    st["positions"]["B"]["hold_days"] = 5
    st["positions"]["C"]["hold_days"] = 10
    rows = {**_rows({"A": 70}, close=101, prob=60), **_rows({"B": 52}, close=101, prob=50), **_rows({"C": 70}, close=101, prob=60)}
    orders, notes = pe.decide(st, rows, "상승 추세", [], params, "US")
    sells = {o["symbol"]: o["reason"] for o in orders if o["side"] == "sell"}
    assert set(sells) == {"B", "C"} and "연장 한도" in sells["C"] and "최대 보유일" in sells["B"]
    assert any("A 보유 5거래일" in n and "더 들고" in n for n in notes)


def test_avg_down_once_half_budget_and_regime():
    params = pe.clean_params({**ON, "avg_down": True})
    st = pe.new_state(1e6)
    pe.fill_buy(st, "A", "가", 10_000, 100, "d", "r", params, "US")
    p = st["positions"]["A"]
    rows = _rows({"A": 70}, close=92, prob=60)
    orders, _ = pe.decide(st, rows, "상승 추세", [], params, "US")
    add = [o for o in orders if o.get("add")]
    assert len(add) == 1 and add[0]["budget"] == pytest.approx(p["entry_cost"] * 0.5, abs=0.01) and "물타기" in add[0]["reason"]
    none, _ = pe.decide(st, rows, "하락 추세", [], params, "US")      # 시장 하락 추세면 안 물탐
    assert not [o for o in none if o.get("add")]
    entry, hard = p["entry_px"], pe.hard_stop(p, params)
    t = pe.fill_buy(st, "A", "가", add[0]["budget"], 92, "d1", add[0]["reason"], params, "US")
    assert t["side"] == "buy" and p["added"] == 1 and p["entry_px"] == entry and pe.hard_stop(p, params) == pytest.approx(hard)
    assert entry > p["avg"] > 92 and p["stop"] == pytest.approx(p["avg"] * 0.93) and p["peak"] == pytest.approx(t["price"])
    again, _ = pe.decide(st, _rows({"A": 70}, close=p["stop"] - 1, prob=60), "상승 추세", [], params, "US")
    assert [o["side"] for o in again if o["symbol"] == "A"] == ["sell"]   # 물탄 뒤엔 손절선 지킴
    assert not pe.can_hold_stop(p, params)


def _sim(stocks, idx, start, end, **kw):
    return pe.simulate(stocks, idx, [], "US", 100_000, start, end,
                       pe.clean_params({"max_positions": 3, "entry_guard": False, **kw}))


def test_simulate_ai_exit_shape_and_accounting():
    stocks, idx = universe(), series(360, 99, 0.0003)
    dates = [c["date"] for c in stocks["S0"]["candles"]]
    r = _sim(stocks, idx, dates[280], dates[-1], ai_exit=True, avg_down=True)
    assert set(r["ai_exit"]) == {"stop_held", "rides", "adds"}
    held = sum(p["value"] for p in r["positions"])
    assert r["equity"][-1]["cash"] + held == pytest.approx(r["summary"]["final_equity"], rel=1e-6)
    off = _sim(stocks, idx, dates[280], dates[-1])
    assert off["ai_exit"] is None


def test_simulate_ai_exit_no_future_data():
    stocks, idx = universe(), series(360, 99, 0.0003)
    dates = [c["date"] for c in stocks["S0"]["candles"]]
    start, cut = dates[280], dates[320]
    kw = {"ai_exit": True, "avg_down": True}
    a = _sim(stocks, idx, start, dates[-1], **kw)
    stocks2 = {k: {"name": v["name"], "candles": [dict(c) for c in v["candles"]]} for k, v in stocks.items()}
    rng = np.random.default_rng(7)
    for v in stocks2.values():
        for c in v["candles"]:
            if c["date"] > cut:
                f = float(rng.uniform(0.5, 1.8))
                for k in ("open", "high", "low", "close"):
                    c[k] *= f
    b = _sim(stocks2, idx, start, dates[-1], **kw)
    assert [x for x in a["log"] if x["date"] <= cut] == [x for x in b["log"] if x["date"] <= cut]
    assert [t for t in a["trades"] if t["date"] <= cut] == [t for t in b["trades"] if t["date"] <= cut]
    assert a["log"] != b["log"]
