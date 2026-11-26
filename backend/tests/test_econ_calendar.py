"""경제 캘린더: FRED 발표일 기준 값 계산 · FOMC 일정 파싱 · 응답에 발표값/해설이 붙는지"""
from datetime import date, timedelta

import pytest

from tests.conftest import run
from app.services import econ_calendar as ec



@pytest.fixture(autouse=True)
def _no_kr_and_news(monkeypatch):
    """이 파일은 미국(FRED·FOMC) 흐름만 — 한국은행 일정·관련 뉴스는 test_bok.py 에서"""
    from app.services import econ_calendar

    async def no_bok(start, end, now=None):
        return []

    async def no_news(events):
        return []
    monkeypatch.setattr(econ_calendar, "_bok_events", no_bok)
    monkeypatch.setattr(econ_calendar, "_attach_news", no_news)

def obs(pairs):
    return {"observations": [{"date": d, "value": v} for d, v in pairs]}


class FakeFred:
    """series_id·realtime_start 별 응답을 돌려주는 가짜 FRED"""
    def __init__(self, table):
        self.table, self.calls = table, []

    async def __call__(self, client, path, params):
        self.calls.append((path, dict(params)))
        if path == "releases/dates":
            return self.table["releases"]
        key = (params["series_id"], params.get("realtime_start"))
        if key not in self.table:
            key = (params["series_id"], None)
        v = self.table.get(key)
        if isinstance(v, Exception):
            raise v
        return v or {"observations": []}


def test_claims_released_vs_previous(monkeypatch):
    fake = FakeFred({("ICSA", "2026-11-19"): obs([("2026-11-14", "235000"), ("2026-11-07", "221000")]),
                     ("ICSA", "2026-11-18"): obs([("2026-11-07", "221000"), ("2026-10-31", "228000")])})
    monkeypatch.setattr(ec, "_fred", fake)
    v = run(ec._indicator_value(None, "unemployment insurance weekly claims report", "2026-11-19"))
    assert v["released"] and v["actual"] == "23.5만 건" and v["prev"] == "22.1만 건"
    assert v["change"] == "up" and v["change_text"].startswith("▲ 1.4만 건")
    assert v["period"] == "11/14 주"


def test_not_yet_on_fred(monkeypatch):
    same = obs([("2026-11-07", "221000"), ("2026-10-31", "228000")])
    monkeypatch.setattr(ec, "_fred", FakeFred({("ICSA", None): same}))
    v = run(ec._indicator_value(None, "unemployment insurance weekly claims report", "2026-11-19"))
    assert v["released"] is False and "반영 전" in v["note"]


def test_gdp_revision(monkeypatch):
    monkeypatch.setattr(ec, "_fred", FakeFred({
        ("A191RL1Q225SBEA", "2026-11-25"): obs([("2026-07-01", "3.1"), ("2026-04-01", "2.0")]),
        ("A191RL1Q225SBEA", "2026-11-24"): obs([("2026-07-01", "2.8"), ("2026-04-01", "2.0")])}))
    v = run(ec._indicator_value(None, "gross domestic product", "2026-11-25"))
    assert v["released"] and v["actual"] == "3.1%" and v["prev"] == "2.8%" and "수정 발표" in v["period"]


def test_cpi_yoy_flat_and_empty(monkeypatch):
    vals = [(f"2026-{m:02d}-01", str(300 + m)) for m in range(10, 0, -1)] + [(f"2025-{m:02d}-01", str(290 + m)) for m in range(12, 0, -1)]
    before = vals[1:]
    monkeypatch.setattr(ec, "_fred", FakeFred({("CPIAUCSL", "2026-11-10"): obs(vals), ("CPIAUCSL", "2026-11-09"): obs(before)}))
    v = run(ec._indicator_value(None, "consumer price index", "2026-11-10"))
    assert v["released"] and v["actual"].endswith("%") and v["change"] in ("up", "down", "flat")
    monkeypatch.setattr(ec, "_fred", FakeFred({}))
    v = run(ec._indicator_value(None, "consumer price index", "2026-11-10"))
    assert v == {"released": False, "note": "FRED 에 값 없음"}


def test_calc_edges():
    assert ec._calc("yoy", [1.0] * 5, 0) is None          # 데이터 부족
    assert ec._calc("mom", [110.0, 100.0], 0) == pytest.approx(10.0)
    assert ec._calc("mom", [110.0, 0.0], 0) is None         # 0 으로 나누기 없음
    assert ec._calc("chg", [5.0, 3.0], 0) == 2.0
    assert ec._signed_pct(-0.001) == "+0.0%"               # -0.0 표시 안 함


FOMC_HTML = """
<h4><a>2026 FOMC Meetings</a></h4>
<div class="fomc-meeting__month col-xs-5"><strong>October/November</strong></div>
<div class="fomc-meeting__date col-xs-4">31-1</div>
<div class="fomc-meeting__month col-xs-5"><strong>December</strong></div>
<div class="fomc-meeting__date col-xs-4">8-9*</div>
<div class="fomc-meeting__month col-xs-5"><strong>March</strong></div>
<div class="fomc-meeting__date col-xs-4">22 (notation vote)</div>
"""


def test_parse_fomc_page():
    ev = ec.parse_fomc_page(FOMC_HTML.replace(">2026 FOMC", "> 2026 FOMC"))
    assert [e["date"] for e in ev] == ["2026-11-01", "2026-12-09"]
    assert "점도표" in ev[1]["event"] and "점도표" not in ev[0]["event"]


def test_calendar_response_has_values_and_explain(monkeypatch):
    """화면이 '실제·이전·해설'을 그릴 수 있는 형식인지 (예전 형식이면 화면에 '-' 만 보였음)"""
    today = date.today()
    past = (today - timedelta(days=3)).isoformat()
    prev_day = (today - timedelta(days=4)).isoformat()
    future = (today + timedelta(days=5)).isoformat()
    fake = FakeFred({
        "releases": {"release_dates": [
            {"release_name": "Unemployment Insurance Weekly Claims Report", "date": past},
            {"release_name": "Gross Domestic Product", "date": future},
            {"release_name": "Something Else", "date": past}]},
        ("ICSA", past): obs([("2026-11-14", "235000"), ("2026-11-07", "221000")]),
        ("ICSA", prev_day): obs([("2026-11-07", "221000"), ("2026-10-31", "228000")]),
    })
    monkeypatch.setattr(ec, "_fred", fake)
    monkeypatch.setattr(ec.settings, "fred_api_key", "dummy")
    ec._value_cache.clear()

    async def no_fomc(start, end):
        return []
    monkeypatch.setattr(ec, "_fomc_calendar", no_fomc)
    data = run(ec.get_economic_calendar())
    assert [e["event"] for e in data["events"]] == ["미국 신규 실업수당 청구", "미국 GDP"]
    claims, gdp = data["events"]
    assert claims["released"] and claims["actual"] == "23.5만 건" and claims["explain"]["effect"]
    assert gdp["released"] is False and set(gdp["explain"]["scenarios"]) == {"성장 가속", "성장 둔화", "같음"}
    assert data["errors"] == [] and data["retry"] is False


def test_calendar_value_error_marks_retry(monkeypatch):
    today = date.today()
    past = (today - timedelta(days=2)).isoformat()
    fake = FakeFred({"releases": {"release_dates": [{"release_name": "Advance Monthly Sales for Retail and Food Services", "date": past}]},
                     ("RSAFS", None): RuntimeError("HTTP 500 (boom)")})
    monkeypatch.setattr(ec, "_fred", fake)
    monkeypatch.setattr(ec.settings, "fred_api_key", "dummy")
    ec._value_cache.clear()

    async def no_fomc(start, end):
        return []
    monkeypatch.setattr(ec, "_fomc_calendar", no_fomc)
    data = run(ec.get_economic_calendar())
    e = data["events"][0]
    assert e["released"] is False and "HTTP 500" in e["note"] and data["retry"] is True
    assert "explain" in e                                      # 실패해도 해설(시나리오)은 표시


def test_calendar_no_sources_raises(monkeypatch):
    monkeypatch.setattr(ec.settings, "fred_api_key", "")

    async def boom(start, end):
        raise RuntimeError("연결 실패")
    monkeypatch.setattr(ec, "_fomc_calendar", boom)

    async def bok_boom(start, end, now=None):
        raise RuntimeError("한국은행 막힘")
    monkeypatch.setattr(ec, "_bok_events", bok_boom)
    with pytest.raises(RuntimeError, match="FRED_API_KEY 없음.*한국은행 막힘"):
        run(ec.get_economic_calendar())


def _one_release(name, day):
    return {"releases": {"release_dates": [{"release_name": name, "date": day}]}}


def test_kst_today_is_us_yesterday_no_fred_query(monkeypatch):
    """한국 11/25 오전 = 미국 11/24 밤 → 11/25 발표(GDP·PCE)는 '발표 전'. FRED 에 realtime_start=11/25 를 보내면
    HTTP 400 ('realtime_start can not be after today') 이 나서 화면에 오류가 떴음 (2026-11-25 버그)"""
    today = date.today()
    fake = FakeFred(_one_release("Gross Domestic Product", today.isoformat()))
    monkeypatch.setattr(ec, "_fred", fake)
    monkeypatch.setattr(ec.settings, "fred_api_key", "dummy")
    monkeypatch.setattr(ec, "fred_today", lambda: today - timedelta(days=1))
    ec._value_cache.clear()

    async def no_fomc(start, end):
        return []
    monkeypatch.setattr(ec, "_fomc_calendar", no_fomc)
    data = run(ec.get_economic_calendar())
    e = data["events"][0]
    assert e["released"] is False and "아직 발표일 전" in e["note"]
    assert not [c for c in fake.calls if c[0] == "series/observations"]   # 미래 날짜로 조회 안 함
    assert data["errors"] == [] and data["retry"] is False


def test_fred_future_vintage_400_is_not_error(monkeypatch):
    """시계 차이로 그래도 400 이 오면 오류가 아니라 '발표 전' 으로 (재시도 표시도 안 함)"""
    today = date.today()
    err = RuntimeError('HTTP 400 ({"error_code":400,"error_message":"Bad Request. Variable realtime_start can not be after today\'s date'
                       '"})')
    fake = FakeFred({**_one_release("Personal Income and Outlays", today.isoformat()), ("PCEPILFE", None): err})
    monkeypatch.setattr(ec, "_fred", fake)
    monkeypatch.setattr(ec.settings, "fred_api_key", "dummy")
    monkeypatch.setattr(ec, "fred_today", lambda: today)
    ec._value_cache.clear()

    async def no_fomc(start, end):
        return []
    monkeypatch.setattr(ec, "_fomc_calendar", no_fomc)
    data = run(ec.get_economic_calendar())
    e = data["events"][0]
    assert e["released"] is False and "발표일 전" in e["note"]
    assert data["errors"] == [] and data["retry"] is False


def test_fred_today_is_us_central():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    assert ec.fred_today() == datetime.now(ZoneInfo("America/Chicago")).date()
