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


def market_today(market: str) -> date:
    return datetime.now(_TZ[market]).date()


def is_market_open(market: str) -> bool:
    now = datetime.now(_TZ[market])
    if not is_trading_day(market, now.date()):
        return False
    hm = now.hour * 60 + now.minute
    if market == "KR":
        return 9 * 60 <= hm <= 15 * 60 + 30
    return 9 * 60 + 30 <= hm <= 16 * 60


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
    return hm > (15 * 60 + 30 if market == "KR" else 16 * 60)
