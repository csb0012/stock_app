"""한국은행 금통위 — 일정·기준금리 이력·결정문 파싱, 결정일 결과(발표 전·동결·인상), 캘린더·이벤트 경고·모의투자 이벤트 반영"""
from datetime import datetime

import pytest

from tests.conftest import run
from app.services import bok, econ_calendar, events, paper_engine as pe

SCHEDULE = """<html><select name="pYear"><option>2027년</option><option>2026년</option></select>
<table><thead><tr><th>회의일자</th><th>결정문</th></tr></thead><tbody>
<tr><td>01월 15일(목)</td><td>국문보도자료(2601).pdf</td></tr>
<tr><td>10월 22일(목)</td></tr><tr><td>11월 26일(목)</td></tr><tr><td>02월 30일(월)</td></tr>
</tbody></table></html>"""
RATES = """<table><thead><tr><th>변경일자</th><th>기준금리</th></tr></thead><tbody>
<tr><td>2026</td><td>11월 26일</td><td>3.25</td></tr>
<tr><td>2026</td><td>08월 27일</td><td>3.00</td></tr>
<tr><td>2025</td><td>05월 29일</td><td>2.50</td></tr></tbody></table>"""
MAIN_UP = """<div><a>통화정책방향 (2026.11.26)</a><p>금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 3.00%에서 3.25%로
0.25%p 상향 조정하여 통화정책을 운용하기로 하였습니다.</p></div>"""
MAIN_KEEP = """<a>통화정책방향 (2026.10.22)</a><p>금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 현 수준(3.00%)에서
유지하여 통화정책을 운용하기로 하였습니다.</p>"""
KST = bok.KST


def test_parse_schedule_rates_latest():
    assert bok.parse_schedule(SCHEDULE, 2026) == ["2026-01-15", "2026-10-22", "2026-11-26"]   # 없는 날짜(2/30)는 뺌
    assert bok.parse_schedule("<html>일정 없음</html>", 2027) == []
    assert bok.parse_rates(RATES) == [("2025-05-29", 2.5), ("2026-08-27", 3.0), ("2026-11-26", 3.25)]
    assert bok.parse_rates("<p>no table</p>") == []
    up = bok.parse_latest(MAIN_UP)
    assert up["date"] == "2026-11-26" and up["rate"] == 3.25 and up["prev"] == 3.0 and up["change"] == "up"
    keep = bok.parse_latest(MAIN_KEEP)
    assert keep["rate"] == keep["prev"] == 3.0 and keep["change"] == "flat"
    assert bok.parse_latest("<p>다른 소식</p>") is None


def test_decision_on_cases():
    rates = bok.parse_rates(RATES)
    later = datetime(2026, 11, 26, 15, 0, tzinfo=KST)
    # 이력 표에 그날 변경 → 인상
    assert bok.decision_on("2026-11-26", rates, None, later) == {"released": True, "actual": 3.25, "previous": 3.0, "change": "up"}
    # 표엔 없지만 지난 회의 → 동결
    assert bok.decision_on("2026-10-22", rates, None, later)["change"] == "flat"
    # 당일 발표 전(오전 9시) → 발표 전 (동결로 짐작하지 않음)
    early = datetime(2026, 11, 26, 9, 0, tzinfo=KST)
    r = bok.decision_on("2026-11-26", rates[:-1], None, early)
    assert r["released"] is False and "발표 전" in r["note"]
    # 당일 오후인데 표·메인 둘 다 아직 → 안 올라옴 (동결로 짐작 안 함)
    r = bok.decision_on("2026-11-26", rates[:-1], None, later)
    assert r["released"] is False and "아직" in r["note"]
    # 표는 늦어도 메인 결정문이 그날이면 그것
    r = bok.decision_on("2026-11-26", rates[:-1], bok.parse_latest(MAIN_UP), later)
    assert r["actual"] == 3.25 and r["change"] == "up" and "상향" in r["statement"]
    # 앞으로의 회의 → 발표 전
    assert bok.decision_on("2026-12-30", rates, None, later)["released"] is False


def test_calendar_bok_events_and_news(monkeypatch):
    async def fake_fetch(years):
        return {"schedule": ["2026-10-22", "2026-11-26", "2027-01-15"], "rates": bok.parse_rates(RATES), "latest": None}
    monkeypatch.setattr(bok, "fetch", fake_fetch)
    evs = run(econ_calendar._bok_events("2026-11-01", "2026-12-31", datetime(2026, 11, 26, 15, 0, tzinfo=KST)))
    assert [e["date"] for e in evs] == ["2026-11-26"]
    e = evs[0]
    assert e["country"] == "KR" and e["actual"] == "3.25%" and e["prev"] == "3.00%" and e["change_text"] == "▲ 0.25%p 인상"
    assert econ_calendar._explain(e)["effect"].startswith("금리 인상")

    from app.services import news
    calls = []

    async def fake_google(q, lang):
        calls.append(q)
        return [{"title": "한은 금리 인상", "date": "2026-11-26", "url": "https://x/a", "press": "연합뉴스"},
                {"title": "광고성 기사", "date": "2026-11-26", "url": "https://x/b", "press": "어느블로그"},
                {"title": "옛날 기사", "date": "2025-01-01", "url": "https://x/c", "press": "연합뉴스"}]
    monkeypatch.setattr(news, "_fetch_google", fake_google)
    monkeypatch.setattr(econ_calendar, "_news_cache", {})

    class D(econ_calendar.date):
        @classmethod
        def today(cls):
            return econ_calendar.date(2026, 11, 26)
    monkeypatch.setattr(econ_calendar, "date", D)
    far = {"date": "2026-12-20", "key": "fomc", "event": "FOMC"}
    errs = run(econ_calendar._attach_news([e, far]))
    assert errs == [] and [a["title"] for a in e["news"]] == ["한은 금리 인상"]   # 믿을 만한 언론사·최근 7일만
    assert "news" not in far and len(calls) == 1                                  # 먼 일정엔 뉴스 안 붙임

    async def boom(q, lang):
        raise RuntimeError("막힘")
    monkeypatch.setattr(news, "_fetch_google", boom)
    monkeypatch.setattr(econ_calendar, "_news_cache", {})
    e2 = dict(e)
    e2.pop("news")
    errs = run(econ_calendar._attach_news([e2]))
    assert errs and e2["news_error"]


def test_bok_events_warn_kr_only_and_paper_labels(monkeypatch):
    monkeypatch.setitem(events._cache, "events", [{"date": "2026-11-26", "event": "한국은행 금리 결정", "country": "KR"},
                                                  {"date": "2026-11-25", "event": "FOMC 금리결정"}])
    kr = events.warnings_for("KR", "2026-11-26")
    assert "한국은행 금리 결정일 — 변동성 주의" in kr and any("간밤 미국 FOMC" in w for w in kr)
    assert not any("한국은행" in w for w in events.warnings_for("US", "2026-11-26"))
    macro = events._cache["events"]
    assert "한국은행 금리 결정일" in pe.event_labels("KR", "2026-11-26", macro)
    assert not any("한국은행" in x for x in pe.event_labels("US", "2026-11-26", macro))
    assert not any("한국은행" in x for x in pe.event_labels("KR", "2026-11-27", macro))


def test_fetch_raises_when_page_changes(monkeypatch):
    async def changed(client, url):
        return "<html>바뀐 페이지</html>"
    monkeypatch.setattr(bok, "_get", changed)
    with pytest.raises(RuntimeError, match="기준금리 추이"):
        run(bok.fetch([2026]))

    async def ok(client, url):
        return SCHEDULE if "listYear" in url else RATES if "baseRate" in url else MAIN_UP
    monkeypatch.setattr(bok, "_get", ok)
    monkeypatch.setattr(bok, "_cache", {"schedule": {}, "rates": None, "latest": None, "ts": {}})
    d = run(bok.fetch([2026]))
    assert d["schedule"][-1] == "2026-11-26" and d["rates"][-1] == ("2026-11-26", 3.25) and d["latest"]["rate"] == 3.25
