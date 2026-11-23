"""변동성 이벤트 경고 — 예측 대상일에 FOMC·CPI 등 주요 발표나 옵션 만기일이 걸리면 경고만 붙임 (확률은 안 바꿈)

- 옵션 만기일 (날짜 규칙으로 계산)
  - 국내: 매월 둘째 목요일 (휴장이면 앞 거래일). 3·6·9·12월은 "네 마녀의 날"
  - 미국: 매월 셋째 금요일 (휴장이면 앞 거래일). 3·6·9·12월은 "쿼드러플 위칭"
- 미국 주요 지표 발표일 (6시간마다 갱신): CPI·고용·GDP·PCE = FRED 공식 발표 일정 (market_data._fred_calendar),
  FOMC 금리 결정일 = 연준 공식 일정 페이지 (market_data._fomc_calendar)
  - 미국 종목: 대상일 당일 발표
  - 국내 종목: 직전 국내 거래일 ~ 대상일 전날 밤 발표 → "간밤 미국 ○○ 결과가 반영되는 날",
               대상일 당일 발표 → "오늘 밤 미국 ○○ 발표 예정"
FRED 키가 없거나 조회 실패하면 그 경고만 빠지고 status() 에 사유가 남음 (가짜 일정으로 채우지 않음)
"""
import time
from datetime import date, datetime, timedelta

from app.core.config import settings
from app.services.market_calendar import is_trading_day

_cache = {"ts": 0.0, "events": [], "error": None, "tried": 0.0, "retry": False}


def status() -> dict:
    return {"updated": _cache["ts"] and datetime.fromtimestamp(_cache["ts"]).isoformat(timespec="seconds"),
            "macro_events": len(_cache["events"]), "error": _cache["error"]}


def version() -> float:
    return _cache["ts"]


def due() -> bool:
    """다시 받을 때인지: 6시간마다, 일시적 실패(시간 초과 등)가 있었으면 10분 뒤"""
    if time.time() - _cache["ts"] > 6 * 3600:
        return time.time() - _cache["tried"] > 600 or not _cache["tried"]
    return _cache["retry"] and time.time() - _cache["tried"] > 600


async def refresh():
    from app.services.market_data import _fred_calendar, _fomc_calendar, err_text  # 순환 import 방지
    _cache["tried"] = time.time()
    today = date.today()
    start, end = (today - timedelta(days=7)).isoformat(), (today + timedelta(days=60)).isoformat()
    events, errors, ok, retry = [], [], False, False
    if settings.fred_api_key:
        try:
            events += [e for e in await _fred_calendar(start, end) if e["impact"] == "high"]
            ok = True
        except Exception as e:
            errors.append(f"FRED 발표 일정 조회 실패: {err_text(e)}")
            retry = True
    else:
        errors.append("FRED_API_KEY 없음 — CPI·고용 등 지표 발표 경고 없음")
    try:
        events += await _fomc_calendar(start, end)
        ok = True
    except Exception as e:
        errors.append(f"FOMC 일정(연준) 조회 실패: {err_text(e)}")
        retry = True
    if ok:   # 하나라도 받았으면 교체, 다 실패하면 이전 일정 유지
        _cache.update(ts=time.time(), events=sorted(events, key=lambda e: e["date"]))
    _cache.update(error=" / ".join(errors) or None, retry=retry)
    if errors:
        print(f"[events] {_cache['error']}")


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def option_expiry(market: str, d: date) -> str | None:
    base = _nth_weekday(d.year, d.month, 3, 2) if market == "KR" else _nth_weekday(d.year, d.month, 4, 3)
    while not is_trading_day(market, base):   # 휴장이면 앞 거래일로 당겨짐
        base -= timedelta(days=1)
    if d != base:
        return None
    if d.month in (3, 6, 9, 12):
        return "네 마녀의 날 (주가지수 선물·옵션 동시 만기)" if market == "KR" else "쿼드러플 위칭 (선물·옵션 동시 만기)"
    return "옵션 만기일"


def _prev_trading_day(market: str, d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(market, d):
        d -= timedelta(days=1)
    return d


def warnings_for(market: str, target: str) -> list:
    """예측 대상일(YYYY-MM-DD)에 걸리는 이벤트 경고 문구"""
    t = date.fromisoformat(target[:10])
    out = []
    ox = option_expiry(market, t)
    if ox:
        out.append(f"{ox} — 장 막판 변동성 주의")
    for e in _cache["events"]:
        d = date.fromisoformat(e["date"][:10])
        if market == "US" and d == t:
            out.append(f"미국 {e['event'].replace('미국 ', '')} 발표일 — 변동성 주의")
        elif market == "KR":
            if _prev_trading_day("KR", t) <= d < t:
                out.append(f"간밤 미국 {e['event'].replace('미국 ', '')} 발표 결과가 반영되는 날")
            elif d == t:
                out.append(f"오늘 밤 미국 {e['event'].replace('미국 ', '')} 발표 예정")
    return out
