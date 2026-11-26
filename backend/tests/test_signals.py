"""투자 대가(13F)·가치·재무·수급(쌍끌이) — 파싱·변화·검증·미래 데이터 미사용·퀀트 추가 요인·AI 장기 점수 보정·API"""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services import gurus, fundamentals, flows, quant, signals

XML = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
    <value>600</value><shrsOrPrnAmt><sshPrnamt>60</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
    <value>400</value><shrsOrPrnAmt><sshPrnamt>40</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>CALL</titleOfClass><cusip>037833100</cusip>
    <value>999</value><shrsOrPrnAmt><sshPrnamt>5</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Call</putCall></infoTable>
  <infoTable><nameOfIssuer>SOME BOND</nameOfIssuer><titleOfClass>NOTE</titleOfClass><cusip>123456AB1</cusip>
    <value>500</value><shrsOrPrnAmt><sshPrnamt>500</sshPrnamt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>COCA COLA</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>191216100</cusip>
    <value>300</value><shrsOrPrnAmt><sshPrnamt>30</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>"""


def test_parse_info_table_aggregates_and_skips_options_bonds():
    rows = gurus.parse_info_table(XML)
    assert [r["cusip"] for r in rows] == ["037833100", "191216100"]       # 값 큰 순, 옵션·채권 제외
    assert rows[0]["value"] == 1000 and rows[0]["shares"] == 100           # 같은 CUSIP 두 줄 합침
    c = gurus.compact(rows)
    assert c["total_value"] == 1300 and c["n_total"] == 2


def filing(period, filed, rows):
    total = sum(r[1] for r in rows)
    return {"period": period, "filed": filed, "total_value": total, "n_total": len(rows),
            "rows": [{"cusip": c, "name": c, "cls": "COM", "value": v, "shares": s} for c, v, s in rows]}


CMAP = {"AAA000001": {"t": "AAA"}, "BBB000001": {"t": "BBB"}, "CCC000001": {"t": "CCC"}, "DDD000001": {"t": None}}


def test_portfolio_changes_new_add_reduce_sold():
    prev = filing("2026-06-30", "2026-08-14", [("AAA000001", 500, 100), ("BBB000001", 300, 100), ("CCC000001", 200, 100)])
    cur = filing("2026-09-30", "2026-11-14", [("AAA000001", 600, 150), ("BBB000001", 200, 50), ("DDD000001", 200, 10)])
    pf = gurus.portfolio(cur, prev, CMAP)
    ch = {h["cusip"]: h["change"] for h in pf["holdings"]}
    assert ch == {"AAA000001": "add", "BBB000001": "reduce", "DDD000001": "new"}
    assert pf["holdings"][0]["weight"] == 60.0 and pf["holdings"][0]["share_change_pct"] == 50.0
    assert [s["ticker"] for s in pf["sold"]] == ["CCC"]
    first = gurus.portfolio(cur, None, CMAP)          # 직전 분기 없음 → 변화 표시 없음
    assert all(h["change"] is None for h in first["holdings"]) and first["sold"] == []


def _filings():
    prev = filing("2026-06-30", "2026-08-14", [("AAA000001", 500, 100), ("CCC000001", 500, 100)])
    cur = filing("2026-09-30", "2026-11-14", [("AAA000001", 500, 100), ("BBB000001", 500, 100)])
    old = filing("2025-03-31", "2025-05-15", [("AAA000001", 1000, 100)])
    return {"buffett": [cur, prev], "lilu": [filing("2026-09-30", "2026-11-13", [("BBB000001", 100, 10), ("AAA000001", 100, 10)])],
            "pabrai": [old]}


def test_build_holders_buyers_estimate_and_stale():
    quotes = {"AAA": {"change_52w": 10.0, "price": 1}, "BBB": {"change_52w": 30.0, "price": 2}}
    r = gurus.build(_filings(), CMAP, quotes)
    json.dumps(r, allow_nan=False)
    g = {x["key"]: x for x in r["gurus"]}
    assert g["buffett"]["est_return_1y"] == 20.0 and g["buffett"]["est_coverage"] == 100.0
    assert g["pabrai"]["stale"] is True
    s = r["stocks"]
    assert s["BBB"]["n_holders"] == 2 and s["BBB"]["n_buyers"] == 1            # 버핏 신규 (리 루는 직전 분기 없음)
    assert s["CCC"]["n_sellers"] == 1 and s["CCC"]["sellers"][0]["change"] == "sold"
    assert "AAA" in s and s["AAA"]["n_holders"] == 2                            # 오래된 공시(파브라이)는 합계에 안 넣음


def closes_from(dates, start, step):
    return [(d, start * (1 + step) ** i) for i, d in enumerate(dates)]


def test_validate_entry_after_filing_and_no_future():
    dates = pd.bdate_range("2026-01-01", periods=200).strftime("%Y-%m-%d").tolist()
    sig = [{"key": "buffett", "ticker": "AAA", "filed": dates[10], "period": "2025-12-31", "weight": 5.0}]
    spy = closes_from(dates, 100, 0.0)
    aaa = closes_from(dates, 50, 0.01)
    v = gurus.validate(sig, {"SPY": spy, "AAA": aaa})
    assert v["n"] == 1 and v["recent"][0]["entry"] == dates[11]      # 공시 당일이 아니라 다음 거래일
    assert v["recent"][0]["exit"] == dates[11 + gurus.HORIZON]
    assert v["avg_excess"] > 0 and v["validated"] is False             # 표본 30 미만 → 점수 반영 안 함
    # 보유 기간이 끝난 뒤의 가격을 바꿔도 결과는 같아야 함
    aaa2 = aaa[:11 + gurus.HORIZON + 1] + [(d, 1.0) for d, _ in aaa[11 + gurus.HORIZON + 1:]]
    assert gurus.validate(sig, {"SPY": spy, "AAA": aaa2})["avg_excess"] == v["avg_excess"]
    # 아직 보유 기간이 안 끝난 공시 → pending
    late = [{**sig[0], "filed": dates[-10]}]
    assert gurus.validate(late, {"SPY": spy, "AAA": aaa})["pending"] == 1


def test_validate_threshold_and_boost_points():
    dates = pd.bdate_range("2025-01-01", periods=300).strftime("%Y-%m-%d").tolist()
    spy = closes_from(dates, 100, 0.0)
    closes = {"SPY": spy}
    sigs = []
    for i in range(30):
        t = f"T{i}"
        closes[t] = closes_from(dates, 10, 0.002)
        sigs.append({"key": "buffett", "ticker": t, "filed": dates[i], "period": "x", "weight": 2})
    v = gurus.validate(sigs, closes)
    assert v["n"] == 30 and v["validated"] is True and v["beat_rate"] == 100.0
    s = {"n_buyers": 1, "n_holders": 3, "n_sellers": 0}
    assert gurus.boost_points(s, v) == 7
    assert gurus.boost_points(s, {**v, "validated": False}) == 0
    assert gurus.boost_points({"n_buyers": 3, "n_holders": 9, "n_sellers": 0}, v) == 10


def test_buy_signals_only_meaningful_buys():
    f = _filings()
    sigs = gurus.buy_signals({"buffett": f["buffett"]}, CMAP)
    assert [(s["ticker"], s["filed"]) for s in sigs] == [("BBB", "2026-11-14")]   # AAA 는 그대로라 아님


# ---------------- 국내 재무 ----------------

NAVER = {"financeInfo": {
    "trTitleList": [{"isConsensus": "N", "key": k} for k in ("202509", "202512", "202603", "202606", "202609")]
    + [{"isConsensus": "Y", "key": "202612"}],
    "rowList": [
        {"title": "매출액", "columns": {"202509": {"value": "1,000"}, "202512": {"value": "1,000"}, "202603": {"value": "1,000"},
                                      "202606": {"value": "1,000"}, "202609": {"value": "1,500"}, "202612": {"value": "9,999"}}},
        {"title": "영업이익", "columns": {"202509": {"value": "-10"}, "202512": {"value": "100"}, "202603": {"value": "100"},
                                       "202606": {"value": "100"}, "202609": {"value": "300"}, "202612": {"value": "999"}}},
        {"title": "EPS", "columns": {"202509": {"value": "100"}, "202512": {"value": "100"}, "202603": {"value": "100"},
                                   "202606": {"value": "100"}, "202609": {"value": "200"}, "202612": {"value": "9,999"}}},
        {"title": "BPS", "columns": {k: {"value": "5,000"} for k in ("202509", "202512", "202603", "202606", "202609")}},
        {"title": "주당배당금", "columns": {"202512": {"value": "50"}, "202609": {"value": "-"}}},
        {"title": "부채비율", "columns": {"202609": {"value": "80.5"}, "202606": {"value": "90"}}},
    ]}}


def test_parse_quarter_skips_consensus():
    q = fundamentals.parse_quarter(NAVER)
    assert [x["q"] for x in q] == ["202509", "202512", "202603", "202606", "202609"]
    assert q[-1]["eps"] == 200 and q[0]["op"] == -10 and q[0]["dps"] is None
    with pytest.raises(ValueError):
        fundamentals.parse_quarter({"financeInfo": {}})


def test_known_from_report_deadlines():
    assert fundamentals.known_from("202609") == date(2026, 11, 14)      # 9/30 + 45일
    assert fundamentals.known_from("202512") == date(2026, 3, 31)       # 12/31 + 90일 (사업보고서)


def test_metrics_point_in_time():
    q = fundamentals.parse_quarter(NAVER)
    before = fundamentals.metrics(q, date(2026, 11, 13))                 # 202609 아직 모름
    after = fundamentals.metrics(q, date(2026, 11, 14))
    assert before["q"] == "202606" and before["eps_ttm"] == 400
    assert after["q"] == "202609" and after["eps_ttm"] == 500 and after["roe"] == 10.0
    assert after["sales_yoy"] == 50.0 and after["op_yoy"] is None and after["turnaround"] is True   # 전년 적자 → 흑자
    assert fundamentals.metrics(q, date(2026, 5, 1)) is None              # 알려진 분기 4개 미만
    p = fundamentals.with_price(after, 5000)
    assert p["per"] == 10.0 and p["pbr"] == 1.0 and p["div_yield"] == 1.0
    loss = fundamentals.with_price({**after, "eps_ttm": -5}, 5000)
    assert loss["per"] is None                                            # 적자면 PER 없음


def test_factor_rows_no_future_data():
    q = fundamentals.parse_quarter(NAVER)
    dates = pd.bdate_range("2026-08-01", "2026-12-31").strftime("%Y-%m-%d")
    fr = pd.DataFrame({"date": dates, "close": 5000.0})
    a = fundamentals.factor_rows(q, fr)
    # 202609 실적을 바꿔도 공시 기한(11/14) 전 날짜의 값은 같아야 함
    q2 = [dict(x) for x in q]
    q2[-1]["eps"] = 99999
    b = fundamentals.factor_rows(q2, fr)
    cut = a["date"] < "2026-11-14"
    pd.testing.assert_frame_equal(a[cut], b[cut])
    assert not a.loc[~cut, "ep"].equals(b.loc[~cut, "ep"])


def test_run_screen_conditions():
    rows = [{"symbol": "A", "per": 8, "roe": 20, "pbr": 0.6, "eps_ttm": 10, "op_margin": 25, "div_yield": 5},
            {"symbol": "B", "per": 30, "roe": 5, "pbr": 3, "eps_ttm": 1, "op_margin": 3, "div_yield": 0},
            {"symbol": "C", "per": None, "roe": -5, "pbr": 0.5, "eps_ttm": -3, "op_margin": None, "div_yield": 6}]
    assert [r["symbol"] for r in fundamentals.run_screen(rows, "high_roe_cheap")] == ["A"]
    assert [r["symbol"] for r in fundamentals.run_screen(rows, "cheap_value")] == ["A"]          # 적자(C) 제외
    assert [r["symbol"] for r in fundamentals.run_screen(rows, "dividend")] == ["A"]
    with pytest.raises(KeyError):
        fundamentals.run_screen(rows, "nope")


def test_quote_row_handles_missing_and_nan():
    r = fundamentals.quote_row({"trailingPE": float("nan"), "priceToBook": 1.234, "regularMarketPrice": 10})
    assert r["per"] is None and r["pbr"] == 1.23 and r["price"] == 10 and r["div_yield"] is None
    assert fundamentals.quote_row({"trailingPE": -5})["per"] is None


# ---------------- 수급 ----------------

def flow_series(vals):
    dates = pd.bdate_range("2026-11-01", periods=len(vals)).strftime("%Y-%m-%d")
    return {d: {"frgn_qty": f, "orgn_qty": o, "prsn_qty": p} for d, (f, o, p) in zip(dates, vals)}


def test_stock_signal_streak_and_labels():
    s = flow_series([(-1, -1, 2), (5, 5, -10), (3, 2, -5), (1, 4, -5)])
    sig = flows.stock_signal(s, 1000, tv20=10_000_000)
    assert sig["streak"] == 3 and sig["label"] == "쌍끌이 3일 연속"
    assert sig["frgn5"] == 8 and sig["prsn_amt5"] == -18000
    assert sig["intensity"] == round(18 * 1000 / (10_000_000 * 5) * 100, 2)
    retail = flows.stock_signal(flow_series([(-5, 1, 4), (-5, 1, 4)]), 1000)
    assert retail["label"] == "개인만 순매수 (외국인·기관 순매도)"
    sell = flows.stock_signal(flow_series([(-5, -1, 6), (-5, -1, 6)]), 1000)
    assert sell["sell_streak"] == 2 and "동반 순매도" in sell["label"]
    assert flows.stock_signal({}, 1000) is None


def test_rankings_and_market_daily(monkeypatch):
    mem = {"A": flow_series([(1, 1, -2), (2, 2, -4)]), "B": flow_series([(-3, -1, 4), (-3, -1, 4)]),
           "C": flow_series([(1, 1, 1)])}   # C 는 마지막 날짜가 다름 → 순위에서 뺌
    monkeypatch.setattr(flows, "_mem", mem)
    rk = flows.rankings({"A": 100, "B": 200, "C": 300})
    assert rk["n"] == 2
    assert [r["symbol"] for r in rk["lists"]["double"]] == ["A"]
    assert [r["symbol"] for r in rk["lists"]["retail_buy"]] == ["B"]
    assert [r["symbol"] for r in rk["lists"]["double_sell"]] == ["B"]
    d0, d1 = sorted(mem["A"])
    daily = flows.market_daily({"A": {d0: 100, d1: 100}, "B": {d0: 200, d1: 200}})
    assert [x["date"] for x in daily] == [d0, d1]
    assert daily[1]["frgn"] == 2 * 100 - 3 * 200 and daily[1]["prsn"] == -4 * 100 + 4 * 200 and daily[1]["double"] == 1


def test_flow_factor_uses_previous_days_only(monkeypatch):
    dates = pd.bdate_range("2026-10-01", periods=12).strftime("%Y-%m-%d")
    f = pd.DataFrame({"date": dates, "close": 1000.0, "tv20": 1e6})
    base = {d: {"frgn_qty": 10, "orgn_qty": 10, "prsn_qty": -20} for d in dates}
    monkeypatch.setattr(flows, "_mem", {"A": base})
    a = flows.factor_frame({"A": f}).set_index("date")["flow"]
    changed = dict(base)
    changed[dates[-1]] = {"frgn_qty": -999, "orgn_qty": -999, "prsn_qty": 0}
    monkeypatch.setattr(flows, "_mem", {"A": changed})
    b = flows.factor_frame({"A": f}).set_index("date")["flow"]
    assert a[dates[-1]] == b[dates[-1]]                    # 그날 수급은 그날 요인에 안 들어감
    assert np.isnan(a[dates[4]]) and a[dates[5]] == pytest.approx(100 * 1000 / 5e6)


# ---------------- 퀀트 추가 요인 ----------------

def _universe_with_extra(n_dates_extra: int, informative: bool):
    from tests.test_quant import make_universe
    frames, names = make_universe(n=120, persistent=True, seed=3)
    rows = []
    for s, f in frames.items():
        for _, r in f.iterrows():
            rows.append({"date": r["date"], "symbol": s,
                         "value": (r["fwd20"] if informative and not pd.isna(r["fwd20"]) else np.random.default_rng(hash(s + r["date"]) % 2**32).normal()),
                         "quality": np.nan, "flow": np.nan})
    extra = pd.DataFrame(rows)
    keep = sorted(extra["date"].unique())[-n_dates_extra:]
    extra.loc[~extra["date"].isin(keep), "value"] = np.nan
    return frames, names, extra


def test_quant_extra_factor_needs_enough_dates():
    frames, names, extra = _universe_with_extra(25, informative=True)   # 20거래일 뒤 결과가 난 날짜는 5개뿐
    q = quant.build(frames, names, extra)
    json.dumps(q, allow_nan=False)
    assert q["weights"]["value"] == 0
    fv = next(f for f in q["factors"] if f["key"] == "value")
    assert fv["extra"] and fv["dates"] < quant.MIN_EXTRA_DATES and fv["coverage"] == 120
    assert "value" in next(iter(q["scores"].values()))["factors"]


def test_quant_extra_factor_gets_weight_when_validated():
    # 미래 수익률을 그대로 넣은 '정답' 요인 — 날짜가 충분하면 IC 가 커서 비중을 받아야 함 (계산 경로 확인용)
    frames, names, extra = _universe_with_extra(60, informative=True)
    q = quant.build(frames, names, extra)
    assert q["weights"]["value"] > 0.3
    assert q["weights"]["quality"] == 0 and q["weights"]["flow"] == 0       # 값이 없는 요인


def test_signals_for_row_bonus_only_when_weighted(monkeypatch):
    q = {"weights": {"rs": 0.5, "value": 0.5, "quality": 0.0, "flow": 0.0},
         "scores": {"005930": {"factors": {"value": 100, "quality": 100, "flow": 0}, "price": 1000, "tv20": 1e9}}}
    monkeypatch.setattr(signals, "_quant", lambda: q)
    monkeypatch.setattr(fundamentals, "kr_now", lambda s, p: {"per": 5})
    monkeypatch.setattr(flows, "_mem", {})
    r = signals.for_row("KR", "005930", 1000)
    parts = {p["key"]: p for p in r["score_parts"]}
    assert parts["value"]["points"] == 5.0 and parts["quality"]["points"] == 0 and parts["flow"]["points"] == 0
    assert r["bonus"] == 5.0 and r["value"] == {"per": 5}
    row = signals.apply_longterm({"market": "KR", "symbol": "005930", "price": 1000, "long_term_score": 98})
    assert row["long_term_score"] == 100 and row["long_term_base"] == 98      # 0~100 으로 자름
    monkeypatch.setattr(gurus, "signal", lambda s: None)
    us = signals.for_row("US", "AAPL")
    assert us["bonus"] == 0 and us["guru"] is None


# ---------------- API ----------------

def test_signal_routes(api_client, monkeypatch):
    client, _, _ = api_client
    res = gurus.build(_filings(), CMAP, {"AAA": {"change_52w": 10.0}, "BBB": {"change_52w": 30.0}})
    res.update(updated_at="2026-11-26T10:00:00", validation={"n": 3, "validated": False}, accs={})
    monkeypatch.setattr(gurus, "_result", res)
    monkeypatch.setattr(gurus, "_read", lambda p, d: d if p != gurus._RESULT_FILE else res)
    r = client.get("/api/gurus").json()
    assert r["gurus"][0]["key"] == "buffett" and r["validation"]["n"] == 3 and "status" in r
    st = client.get("/api/gurus/stocks", params={"sort": "buyers"}).json()
    assert [s["ticker"] for s in st["items"]] == ["BBB"]
    assert client.get("/api/gurus/nobody").status_code == 404
    d = client.get("/api/gurus/buffett").json()
    assert d["guru"]["key"] == "buffett" and d["holdings"] == []

    sc = client.get("/api/value/screens").json()
    assert {s["key"] for s in sc["KR"]} >= {"cheap_value", "high_roe_cheap"} and len(sc["US"]) == 8
    assert client.get("/api/value/KR/nope").status_code == 404
    assert client.get("/api/value/JP/x").status_code == 400
    monkeypatch.setattr(signals, "kr_value_rows", lambda: [{"symbol": "A", "name": "가", "per": 8, "roe": 20, "eps_ttm": 1}])
    v = client.get("/api/value/KR/high_roe_cheap").json()
    assert v["items"][0]["symbol"] == "A" and v["total"] == 1
    monkeypatch.setattr(signals, "kr_value_rows", lambda: [])
    empty = client.get("/api/value/KR/high_roe_cheap").json()
    assert empty["items"] == [] and "재무" in empty["message"]

    def boom(key, limit):
        raise RuntimeError("Yahoo 막힘")
    monkeypatch.setattr(fundamentals, "us_screen_sync", boom)
    e = client.get("/api/value/US/cash_cow")
    assert e.status_code == 502 and "Yahoo 막힘" in e.json()["detail"]

    monkeypatch.setattr(flows, "_mem", {"A": flow_series([(1, 1, -2), (2, 2, -4)])})
    monkeypatch.setattr(signals, "kr_prices", lambda: ({"A": 100}, {"A": 1e6}))
    monkeypatch.setattr(signals, "kr_closes", lambda: {})
    fo = client.get("/api/flows/overview").json()
    assert fo["lists"]["double"][0]["symbol"] == "A" and fo["daily"] == [] and fo["universe"] == 1


def test_name_match_fallback():
    sec = {"0": {"cik_str": 1, "ticker": "CB", "title": "Chubb Ltd"},
           "1": {"cik_str": 2, "ticker": "LBTYA", "title": "Liberty Global Ltd."},
           "2": {"cik_str": 2, "ticker": "LBTYK", "title": "Liberty Global Ltd."},
           "3": {"cik_str": 3, "ticker": "ABC", "title": "Same Name Inc"},
           "4": {"cik_str": 4, "ticker": "XYZ", "title": "Same Name Corp"},
           "5": {"cik_str": 5, "ticker": "STX", "title": "Seagate Technology Holdings plc"}}
    idx = gurus.name_index(sec)
    assert gurus.match_name(idx, "CHUBB LIMITED", "COM") == "CB"
    assert gurus.match_name(idx, "Seagate Technology Hldngs Pl", "ORD SHS") == "STX"     # 약어·잘린 이름
    assert gurus.match_name(idx, "LIBERTY GLOBAL LTD", "COM CL C") is None               # 여러 클래스 중 C → 모호
    assert gurus.match_name(idx, "LIBERTY GLOBAL LTD", "COM CL A") == "LBTYA"
    assert gurus.match_name(idx, "SAME NAME INC", "COM") is None                          # 다른 회사가 같은 이름 → 안 씀
    assert gurus.match_name(idx, "UNKNOWN CO", "COM") is None


def test_flows_collect_bulk_store(monkeypatch):
    """전 종목 수집: 묶어서 저장(CHUNK) · 같은 날짜는 덮어씀 · 실패 종목은 건너뛰고 계속"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import StaticPool
    from tests.conftest import run
    from app.core.database import Base
    from app.models.flow import InvestorFlow
    from app.services import kis_api

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    run(setup())
    monkeypatch.setattr(flows, "AsyncSessionLocal", Session)
    monkeypatch.setattr(flows, "_mem", {})
    monkeypatch.setattr(flows, "CHUNK", 2)
    calls = {"n": 0}

    async def fake_investor(sym):
        calls["n"] += 1
        if sym == "BAD":
            raise RuntimeError("KIS 오류")
        q = 10 * calls["n"]
        return [{"date": "2026-11-24", "frgn_qty": q, "orgn_qty": 1, "prsn_qty": -q},
                {"date": "2026-11-25", "frgn_qty": q, "orgn_qty": 2, "prsn_qty": -q}]
    monkeypatch.setattr(kis_api.kis_client, "get_kr_investor", fake_investor)
    r = run(flows.collect(["A", "B", "BAD", "C", "A"]))      # 중복 A 는 한 번만
    assert r["added"] == 6 and len(r["errors"]) == 1 and calls["n"] == 4
    r2 = run(flows.collect(["A"]))                              # 같은 날짜 → 새 행 없이 덮어씀
    assert r2["added"] == 0 and flows.series("A")["2026-11-25"]["frgn_qty"] == 50

    async def rows():
        async with Session() as s:
            return (await s.execute(select(InvestorFlow))).scalars().all()
    got = run(rows())
    assert len(got) == 6 and {x.frgn_qty for x in got if x.symbol == "A"} == {50}
    assert flows.status()["running"] is False
    run(engine.dispose())
