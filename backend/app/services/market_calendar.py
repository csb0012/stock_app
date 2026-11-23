"""거래일 계산 — 예측 대상일(다음 거래일)과 화면 표시용 라벨

국내: holidays.XKRX (한국거래소 휴장일: 공휴일 + 연말 휴장 등)
미국: holidays.NYSE (뉴욕증권거래소 휴장일)
"""
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import holidays

_TZ = {"KR": ZoneInfo("Asia/Seoul"), "US": ZoneInfo("America/New_York")}
_WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"]


@lru_cache(maxsize=8)
def _holidays(market: str, year: int):
    if market == "KR":
        return holidays.XKRX(years=[year, year + 1])
    return holidays.NYSE(years=[year, year + 1])


def is_trading_day(market: str, d: date) -> bool:
    return d.weekday() < 5 and d not in _holidays(market, d.year)


def next_trading_day(market: str, after: date) -> date:
    d = after + timedelta(days=1)
    while not is_trading_day(market, d):
        d += timedelta(days=1)
    return d


def session_hours(market: str, d: date) -> tuple:
    """(개장, 마감) 분 단위. 국내는 새해 첫 거래일 10:00 개장 (한국거래소 개장식)"""
    if market == "KR":
        first = date(d.year, 1, 1)
        while not is_trading_day("KR", first):
            first += timedelta(days=1)
        return (10 * 60 if d == first else 9 * 60), 15 * 60 + 30
    return 9 * 60 + 30, 16 * 60


def last_session_date(market: str) -> date:
    """지금 화면에 보이는 시세가 어느 거래일 것인지 (장 시작 전·휴장이면 직전 거래일)"""
    now = datetime.now(_TZ[market])
    d = now.date()
    if is_trading_day(market, d) and now.hour * 60 + now.minute >= session_hours(market, d)[0]:
        return d
    d -= timedelta(days=1)
    while not is_trading_day(market, d):
        d -= timedelta(days=1)
    return d


def market_today(market: str) -> date:
    return datetime.now(_TZ[market]).date()


def is_market_open(market: str) -> bool:
    now = datetime.now(_TZ[market])
    if not is_trading_day(market, now.date()):
        return False
    hm = now.hour * 60 + now.minute
    open_hm, close_hm = session_hours(market, now.date())
    return open_hm <= hm <= close_hm


def market_status(market: str) -> dict:
    """장 운영 상태: 장중 / 개장 전 / 장 마감 / 휴장 + 다음 개장일"""
    now = datetime.now(_TZ[market])
    today = now.date()
    hm = now.hour * 60 + now.minute
    open_hm, close_hm = session_hours(market, today)
    if not is_trading_day(market, today):
        state, nxt = "휴장", next_trading_day(market, today)
    elif hm < open_hm:
        state, nxt = "개장 전", today
    elif hm <= close_hm:
        state, nxt = "장중", None
    else:
        state, nxt = "장 마감", next_trading_day(market, today)
    return {
        "market": market,
        "state": state,
        "open": state == "장중",
        "local_time": now.strftime("%H:%M"),
        "next_open": nxt.isoformat() if nxt else None,
        "next_open_label": session_label(market, nxt) if nxt else None,
        # 다음 개장 시각을 한국시간으로 (미국장은 날짜가 하루 어긋나 보이므로)
        "next_open_kst": _kst_open(market, nxt) if nxt else None,
        # 미국: 한국 낮 시간 주간거래 (정규장과 별개)
        **({"daytime": us_daytime_session()} if market == "US" else {}),
    }


def us_daytime_session(now: datetime | None = None) -> dict:
    """미국 주간거래(한국투자증권·토스 등, 블루오션 ATS) 시간인지.
    한국 10:00 ~ 미국 동부 04:00(프리마켓 시작) = 겨울 18:00 / 서머타임 17:00 (한국시간),
    그날(한국 날짜)이 미국 거래일일 때만 (월요일 낮 = 미국 월요일 장을 앞둔 거래)."""
    kr, us = _TZ["KR"], _TZ["US"]
    k = (now or datetime.now(kr)).astimezone(kr)
    d = k.date()
    start = datetime(d.year, d.month, d.day, 10, 0, tzinfo=kr)
    end = datetime(d.year, d.month, d.day, 4, 0, tzinfo=us).astimezone(kr)
    return {
        "open": is_trading_day("US", d) and start <= k < end,
        "session_date": d.isoformat(),
        "hours_kst": f"10:00~{end:%H:%M}",
        "end_kst": f"{end:%H:%M}",
    }


def _kst_open(market: str, d: date) -> str:
    oh, om = divmod(session_hours(market, d)[0], 60)
    local = datetime(d.year, d.month, d.day, oh, om, tzinfo=_TZ[market])
    k = local.astimezone(_TZ["KR"])
    return f"{_WEEKDAY[k.weekday()]} {k.month}/{k.day} {k.hour:02d}:{k.minute:02d}"


def session_label(market: str, target: date) -> str:
    """'오늘' / '내일' / '월요일(11/23)' — 사용자가 보는 기준(한국 날짜)"""
    today_kr = market_today("KR")
    if market == "KR":
        if target == today_kr:
            return "오늘"
        if target == today_kr + timedelta(days=1):
            return "내일"
    return f"{_WEEKDAY[target.weekday()]}요일({target.month}/{target.day})"


def prediction_target(market: str, last_candle_date: str) -> dict:
    """마지막 일봉 다음 거래일 = 예측 대상일

    장중이면 마지막 일봉은 오늘(진행 중) → 대상은 다음 거래일.
    장 시작 전이면 마지막 일봉은 직전 거래일 → 대상은 오늘.
    """
    last = date.fromisoformat(last_candle_date[:10])
    target = next_trading_day(market, last)
    # 장 마감 후 아직 오늘 일봉이 안 잡힌 경우(데이터 지연) 대상이 오늘로 잡히는 것을 방지
    today = market_today(market)
    if target <= today and is_trading_day(market, today) and not is_market_open(market) and _after_close(market):
        target = next_trading_day(market, today)
    return {"target_date": target.isoformat(), "target_label": session_label(market, target)}


def _after_close(market: str) -> bool:
    now = datetime.now(_TZ[market])
    hm = now.hour * 60 + now.minute
    return hm > session_hours(market, now.date())[1]
