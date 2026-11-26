"""한국은행 금융통화위원회 (기준금리 결정) — 한국은행 홈페이지 공개 페이지 (키 필요 없음)

- 회의 일정: '통화정책방향 결정회의 일정 및 자료' (해마다 8번, pYear=연도). 다음 해 일정은 연말에 공개
- 기준금리 이력: '한국은행 기준금리 추이' 표 (바뀐 날만 있음 → 그 사이 회의는 동결)
- 오늘 결정: 메인 페이지의 '통화정책방향 (YYYY.MM.DD)' 결정문 첫 줄 (이력 표가 늦게 바뀔 때 대비)
페이지 형식이 바뀌어 날짜·금리를 못 찾으면 오류 (가짜 일정·값으로 채우지 않음). 일정·이력은 6시간 캐시 (결정일엔 30분)
"""
import re
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

BASE = "https://www.bok.or.kr"
SCHEDULE_URL = BASE + "/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear={year}"
RATES_URL = BASE + "/portal/singl/baseRate/list.do?dataSeCd=01&menuNo=200643"
MAIN_URL = BASE + "/portal/main/main.do"
KST = ZoneInfo("Asia/Seoul")
ANNOUNCE_HM = (10, 0)        # 결정 발표 (보통 오전 10시 전후) — 이 전이면 '발표 전'

_cache: dict = {"schedule": {}, "rates": None, "latest": None, "ts": {}}


def _text(html: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    t = re.sub(r"<[^>]+>", "|", t)
    t = t.replace("&nbsp;", " ").replace("&middot;", "·")
    return re.sub(r"\s+", " ", t)


def parse_schedule(html: str, year: int) -> list:
    """회의 일정 페이지 → 그해 결정회의 날짜 ['YYYY-MM-DD'] (표의 '회의일자' 칸 뒤에서 'MM월 DD일(요일)')"""
    i = html.find("회의일자")
    if i < 0:
        return []
    out = []
    for m, d, _w in re.findall(r"(\d{1,2})월\s*(\d{1,2})일\s*\(([월화수목금토일])\)", html[i:]):
        try:
            out.append(date(year, int(m), int(d)).isoformat())
        except ValueError:
            continue
    return sorted(set(out))


def parse_rates(html: str) -> list:
    """기준금리 추이 표 → [('YYYY-MM-DD', 금리 %)] 오래된 순 (변경일만)"""
    i = html.find("<tbody")
    if i < 0:
        return []
    cells = [c.strip() for c in _text(html[i:html.find("</tbody>", i)]).split("|") if c.strip()]
    out = []
    for k in range(len(cells) - 2):
        y, md, r = cells[k], cells[k + 1], cells[k + 2]
        m = re.fullmatch(r"(\d{1,2})월\s*(\d{1,2})일", md)
        if re.fullmatch(r"\d{4}", y) and m and re.fullmatch(r"\d+(\.\d+)?", r):
            try:
                out.append((date(int(y), int(m.group(1)), int(m.group(2))).isoformat(), float(r)))
            except ValueError:
                continue
    return sorted(set(out))


_DECISION = re.compile(r"통화정책방향\s*\((\d{4})\.(\d{2})\.(\d{2})\)\s*\|*\s*(.{0,220})")


def parse_latest(html: str) -> dict | None:
    """메인 페이지 → 가장 최근 결정 {date, rate, prev, change(up/down/flat), text}. 결정문 첫 줄의 '…%에서 …%로' / '…% 수준에서 유지'"""
    for y, m, d, body in _DECISION.findall(_text(html)):
        body = body.replace("|", " ")
        mv = re.search(r"(\d+\.\d+)%\)?\s*(?:수준)?에서\s*(\d+\.\d+)%로", body)
        keep = re.search(r"(\d+\.\d+)%\)?\s*(?:수준)?(?:으로|에서)?\s*(?:유지|동결)", body)
        if mv:
            prev, rate = float(mv.group(1)), float(mv.group(2))
        elif keep:
            prev = rate = float(keep.group(1))
        else:
            continue
        ch = "up" if rate > prev else "down" if rate < prev else "flat"
        return {"date": f"{y}-{m}-{d}", "rate": rate, "prev": prev, "change": ch, "text": body.split("다.")[0].strip() + "다."}
    return None


def decision_on(day: str, rates: list, latest: dict | None, now: datetime | None = None) -> dict:
    """결정일 day 의 결과 → {released, actual, previous, change, note}.
    이력 표에 그날 변경이 있으면 그것 / 메인 결정문이 그날이면 그것 / 그날이 지난 회의이고 더 뒤 기록이 있으면 동결.
    결정일 당일 발표 전이거나 아직 아무 데도 안 올라왔으면 released=False (동결로 짐작하지 않음)"""
    now = now or datetime.now(KST)
    before = [r for d, r in rates if d < day]
    on = [r for d, r in rates if d == day]
    prev = before[-1] if before else None
    if on:
        a = on[-1]
        return {"released": True, "actual": a, "previous": prev, "change": "up" if prev is not None and a > prev else "down" if prev is not None and a < prev else "flat"}
    if latest and latest["date"] == day:
        return {"released": True, "actual": latest["rate"], "previous": latest["prev"], "change": latest["change"], "statement": latest["text"]}
    today = now.date().isoformat()
    if day > today or (day == today and (now.hour, now.minute) < ANNOUNCE_HM):
        return {"released": False, "note": "발표 전 (한국은행은 보통 오전 10시 전후 발표)"}
    newer = (latest and latest["date"] > day) or any(d > day for d, _r in rates)
    if day < today or newer:
        if prev is None:
            return {"released": False, "note": "기준금리 이력을 못 읽음"}
        return {"released": True, "actual": prev, "previous": prev, "change": "flat"}
    return {"released": False, "note": "발표 시간이 지났지만 한국은행 홈페이지에 아직 결정이 안 올라옴"}


async def _get(client, url: str) -> str:
    r = await client.get(url)
    if r.status_code != 200:
        raise RuntimeError(f"한국은행 HTTP {r.status_code}")
    return r.text


def _fresh(key: str, ttl: float) -> bool:
    return time.time() - _cache["ts"].get(key, 0) < ttl


async def fetch(years: list) -> dict:
    """{schedule: [날짜], rates: [(날짜, 금리)], latest} — 일정은 하루, 이력·메인은 6시간(결정일엔 30분) 캐시"""
    today = date.today().isoformat()
    meeting_today = any(today in (_cache["schedule"].get(y) or []) for y in years)
    ttl = 1800 if meeting_today else 6 * 3600
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (StockApp)"}) as c:
        for y in years:
            k = f"s{y}"
            if not _fresh(k, 24 * 3600):
                _cache["schedule"][y] = parse_schedule(await _get(c, SCHEDULE_URL.format(year=y)), y)
                _cache["ts"][k] = time.time()
        if _cache["rates"] is None or not _fresh("rates", ttl):
            rates = parse_rates(await _get(c, RATES_URL))
            if not rates:
                raise RuntimeError("한국은행 기준금리 추이 표를 읽지 못함 (페이지 형식이 바뀌었을 수 있음)")
            _cache["rates"] = rates
            _cache["ts"]["rates"] = time.time()
            try:
                _cache["latest"] = parse_latest(await _get(c, MAIN_URL))
            except Exception:   # noqa: BLE001 — 메인 결정문은 보조 (이력 표로도 판단)
                _cache["latest"] = None
    sched = sorted(d for y in years for d in (_cache["schedule"].get(y) or []))
    if not sched and years:
        raise RuntimeError("한국은행 결정회의 일정을 찾지 못함 (페이지 형식이 바뀌었을 수 있음)")
    return {"schedule": sched, "rates": _cache["rates"], "latest": _cache["latest"]}
