"""경제 캘린더 — 미국 주요 지표 발표 일정 + 실제 발표값(FRED) + 지표별 해설

- 일정: FRED 공식 발표 일정(releases/dates) + FOMC 금리 결정일(연준 공식 일정 페이지).
  FRED 의 "FOMC Press Release" 는 매일 갱신되는 기준금리 데이터라 날마다 발표일로 나와서 쓰지 않음.
- 실제·이전 값: FRED 시리즈를 **발표 당일 기준(vintage)** 으로 조회 → 그날 시장이 본 숫자 (나중에 수정된 값이 아님).
  발표일 전날 기준과 비교해 새 값이 생겼을 때만 '발표됨'. FRED 에 아직 안 올라왔으면 값 없이 사유 표시.
- 예상치(시장 컨센서스)는 무료 공식 출처가 없어 다루지 않음 (Finnhub 경제 캘린더는 유료, Investing.com 등은 수집 금지).
- 해설: 지표 설명 + 이번 값이 이전보다 오름/내림/같음일 때 일반적인 시장 영향. 예측 확률에는 쓰지 않음.
"""
import asyncio
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings

FRED_BASE = "https://api.stlouisfed.org/fred"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

DISCLAIMER = ("해설은 지표가 오르거나 내렸을 때의 일반적인 경향입니다. 실제 시장은 '예상보다 좋았나 나빴나'와 "
              "다른 뉴스에 따라 다르게 반응할 수 있습니다 (예상치는 무료 공식 출처가 없어 표시하지 않음).")


def _pct(v):
    return f"{v:.1f}%"


def _z(v, digits=1):
    """반올림하면 0 인 값은 0 으로 (화면에 -0.0 이 안 보이게)"""
    return 0.0 if round(v, digits) == 0 else v


def _signed_pct(v):
    return f"{_z(v):+.1f}%"


def _man_people(v):          # PAYEMS: 천 명 단위 → 만 명
    return f"{_z(v / 10):+.1f}만 명"


def _man_count(v):           # ICSA: 건 → 만 건
    return f"{v / 10000:.1f}만 건"


def _man_from_thousand(v):   # JTSJOL: 천 건 → 만 건
    return f"{v / 10:,.0f}만 건"


def _plain(v):
    return f"{v:.1f}"


# 지표별 설정
#   calc: yoy(전년 대비 %) / mom(전월 대비 %) / chg(전기 대비 증감) / level(값 그대로)
#   words: 이전보다 (오름, 내림, 같음) 일 때 표시 문구
#   up / down / flat: 그 방향일 때 일반적인 시장 영향
INDICATORS = {
    "consumer price index": dict(
        name="미국 CPI (소비자물가)", impact="high", series="CPIAUCSL", calc="yoy", metric="전년 대비 상승률",
        fmt=_pct, unit="%p", words=("상승률 확대", "상승률 둔화", "같음"),
        about="미국 소비자가 사는 물건·서비스 가격이 1년 전보다 얼마나 올랐는지. 연준 금리 결정에 가장 큰 영향을 주는 물가 지표 (목표 2%).",
        up="물가 상승 압력이 커짐 → 연준 금리 인하가 늦어지거나 인상 우려 → 미 국채 금리·달러 강세 경향 → "
           "기술·성장주에 부담, 원화 약세로 외국인 매도가 나오면 코스피에도 부담.",
        down="물가 둔화 → 금리 인하 기대 ↑ → 국채 금리 하락·달러 약세 경향 → 기술·성장주에 우호적, "
             "원화 강세로 외국인 매수 유입 기대.",
        flat="물가 흐름 유지 → 금리 전망 변화는 작음. 시장은 근원 물가(에너지·식품 제외)와 예상치 대비 결과에 더 반응.",
    ),
    "personal income and outlays": dict(
        name="미국 근원 PCE 물가", impact="high", series="PCEPILFE", calc="yoy", metric="전년 대비 상승률 (에너지·식품 제외)",
        fmt=_pct, unit="%p", words=("상승률 확대", "상승률 둔화", "같음"),
        about="개인소비지출 물가 중 에너지·식품을 뺀 근원 지표. 연준이 2% 목표를 판단할 때 가장 중시하는 물가.",
        up="연준이 보는 물가가 다시 오름 → 금리 인하 지연·동결 장기화 우려 → 금리·달러 강세 경향 → 성장주와 신흥국 증시에 부담.",
        down="연준 목표(2%)에 가까워짐 → 금리 인하 기대 ↑ → 금리 하락·달러 약세 경향 → 주식에 우호적.",
        flat="물가 흐름 유지 → 금리 전망 변화는 작음. CPI 가 먼저 나오므로 시장 반응은 대체로 CPI 보다 작음.",
    ),
    "producer price index": dict(
        name="미국 PPI (생산자물가)", impact="medium", series="PPIFIS", calc="yoy", metric="전년 대비 상승률 (최종 수요)",
        fmt=_pct, unit="%p", words=("상승률 확대", "상승률 둔화", "같음"),
        about="기업이 파는 물건·서비스 가격 변화. 시차를 두고 소비자물가(CPI)로 옮겨가는 경우가 많아 물가의 선행 신호로 봄.",
        up="생산 비용 상승 → 앞으로 소비자물가 상승 압력 → 금리 인하 기대 ↓. 가격을 못 올리는 기업은 이익률 악화 우려.",
        down="생산 비용 안정 → 앞으로 소비자물가 둔화 기대 → 금리 인하 기대 ↑, 기업 이익률에 우호적.",
        flat="생산자 물가 흐름 유지 → 시장 영향 작음.",
    ),
    "employment situation": dict(
        name="미국 고용보고서 (비농업)", impact="high", series="PAYEMS", calc="chg", metric="비농업 일자리 증감 (전월 대비)",
        fmt=_man_people, unit="만 명", scale=0.1, words=("증가폭 확대", "증가폭 축소", "같음"),
        about="농업을 뺀 미국 일자리가 한 달 동안 얼마나 늘었는지 (같은 날 실업률도 발표). 경기와 금리 방향을 함께 보여주는 지표.",
        up="고용이 강함 → 경기 견조 신호지만 임금·물가 압력 → 금리 인하 지연 우려 → 금리·달러 상승 경향. "
           "경기민감주엔 호재, 기술·성장주엔 부담일 수 있음.",
        down="고용 둔화 → 금리 인하 기대 ↑ (금리·달러 하락 경향) → 성장주엔 우호적. "
             "다만 크게 줄거나 마이너스면 경기 침체 우려로 증시 전반 하락 가능.",
        flat="고용 흐름 유지 → 시장은 실업률·임금 상승률과 예상치 대비 결과에 반응.",
    ),
    "gross domestic product": dict(
        name="미국 GDP", impact="high", series="A191RL1Q225SBEA", calc="level", metric="실질 성장률 (전기 대비 연율)",
        fmt=_pct, unit="%p", words=("성장 가속", "성장 둔화", "같음"),
        about="미국 경제가 한 분기 동안 얼마나 성장했는지 (연율 환산). 같은 분기를 속보·잠정·확정치로 세 번 발표.",
        up="성장 가속 → 기업 실적 기대 ↑ (증시 호재). 너무 강하면 물가 우려로 금리 인하 지연.",
        down="성장 둔화 → 실적 우려, 금리 인하 기대 ↑. 2분기 연속 마이너스면 경기침체 신호로 증시 부담.",
        flat="성장 흐름 유지 → 시장 영향 작음.",
    ),
    "advance monthly sales for retail and food services": dict(
        name="미국 소매판매", impact="medium", series="RSAFS", calc="mom", metric="전월 대비 증감률",
        fmt=_signed_pct, unit="%p", words=("증가율 확대", "증가율 둔화", "같음"),
        about="미국 소매점·음식점 매출 변화. 미국 경제의 약 70%가 소비라서 경기 체력을 보여주는 지표.",
        up="소비가 강함 → 경기 견조, 유통·소비재주에 호재. 물가 압력으로 금리 인하 기대는 ↓.",
        down="소비 둔화 → 경기 둔화 우려, 소비 관련주 부담. 금리 인하 기대는 ↑.",
        flat="소비 흐름 유지 → 시장 영향 작음.",
    ),
    "job openings and labor turnover survey": dict(
        name="JOLTS 구인건수", impact="medium", series="JTSJOL", calc="level", metric="구인 건수",
        fmt=_man_from_thousand, unit="만 건", scale=0.1, words=("증가", "감소", "같음"),
        about="기업이 사람을 구하는 일자리 수. 노동 수요가 얼마나 강한지 보여줌 (고용보고서보다 한 달 늦은 기준).",
        up="구인 수요가 강함 → 노동시장 과열, 임금 상승 압력 → 금리 인하 기대 ↓.",
        down="노동 수요가 식음 → 임금 압력 완화 → 금리 인하 기대 ↑. 급감하면 경기 둔화 신호.",
        flat="노동 수요 유지 → 시장 영향 작음.",
    ),
    "unemployment insurance weekly claims report": dict(
        name="미국 신규 실업수당 청구", impact="medium", series="ICSA", calc="level", metric="주간 청구 건수",
        fmt=_man_count, unit="만 건", scale=1e-4, words=("증가", "감소", "같음"),
        about="한 주 동안 처음 실업수당을 신청한 사람 수. 매주 나와서 고용 변화를 가장 빨리 보여줌 (늘면 고용 약화).",
        up="실직자 증가 → 고용 약화 신호 → 금리 인하 기대 ↑. 계속 크게 늘면 경기 침체 우려.",
        down="실직자 감소 → 고용 탄탄 → 경기 견조, 금리 인하 기대는 ↓.",
        flat="고용 흐름 유지 → 시장 영향 작음.",
    ),
    "surveys of consumers": dict(
        name="미시간대 소비자심리", impact="low", series="UMCSENT", calc="level", metric="소비자심리지수",
        fmt=_plain, unit="", words=("개선", "악화", "같음"),
        about="미국 소비자가 경기·살림살이를 어떻게 느끼는지 조사한 지수. 앞으로의 소비 방향을 미리 보여줌.",
        up="소비심리 개선 → 앞으로 소비 증가 기대 → 경기 호재.",
        down="소비심리 위축 → 소비 둔화 우려 → 소비 관련주 부담.",
        flat="소비심리 유지 → 시장 영향 작음.",
    ),
}

FOMC = dict(
    name="FOMC 금리결정", impact="high", metric="기준금리 목표 범위", words=("인상", "인하", "동결"),
    about="미국 연준이 기준금리를 정하는 회의 (1년 8번). 전 세계 금리·환율·주식에 가장 큰 영향을 주는 이벤트. "
          "'(경제전망·점도표)' 회의는 위원들의 앞으로 금리 전망도 함께 발표.",
    up="금리 인상 → 대출·자금 비용 ↑ → 달러 강세 → 기술·성장주와 코스피 같은 신흥국 증시에 부담.",
    down="금리 인하 → 시중 유동성 ↑ → 주식에 우호적, 달러 약세·원화 강세 경향. "
         "다만 경기 악화 때문에 급히 내린 것이면 증시 반응이 엇갈릴 수 있음.",
    flat="동결 → 시장은 성명서 문구·기자회견·점도표에서 다음 금리 방향 힌트에 반응.",
)


def err_text(e: BaseException) -> str:
    """화면·로그용 오류 문구 — httpx 시간 초과·연결 오류는 str(e) 가 빈 문자열이라 종류를 적어 줌"""
    if isinstance(e, httpx.TimeoutException):
        return f"응답 시간 초과 ({type(e).__name__})"
    if isinstance(e, httpx.TransportError):
        return f"연결 실패 ({type(e).__name__}{': ' + str(e) if str(e) else ''})"
    return str(e) or type(e).__name__


async def _fred(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    """FRED 호출 — 느릴 때가 있어 시간 초과·연결 끊김이면 한 번 재시도.
    raise_for_status() 문구엔 api_key 가 든 URL 이 들어가 화면·로그에 키가 남으므로 상태 코드만 올림."""
    params = {**params, "api_key": settings.fred_api_key, "file_type": "json"}
    for attempt in range(2):
        try:
            resp = await client.get(f"{FRED_BASE}/{path}", params=params)
            break
        except httpx.TransportError:
            if attempt:
                raise
            await asyncio.sleep(2)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} ({resp.text[:80]})")
    return resp.json()


# ---------------- 일정 ----------------

async def _fred_calendar(start: str, end: str) -> list:
    """FRED 발표 일정 (공식 일정 — 날짜만, 값은 _values 에서)"""
    async with httpx.AsyncClient(timeout=30) as client:
        data = await _fred(client, "releases/dates", {
            "realtime_start": start, "realtime_end": end,
            "include_release_dates_with_no_data": "true", "limit": 1000, "sort_order": "asc"})
    seen, events = set(), []
    for r in data.get("release_dates") or []:
        key = (r.get("release_name") or "").strip().lower()
        if key not in INDICATORS or (key, r.get("date")) in seen:
            continue
        seen.add((key, r.get("date")))
        ind = INDICATORS[key]
        events.append({"date": r.get("date", ""), "key": key, "event": ind["name"], "country": "US",
                       "impact": ind["impact"]})
    return events


_MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december"]
_MONTHS = {**{m: i for i, m in enumerate(_MONTH_NAMES, 1)}, **{m[:3]: i for i, m in enumerate(_MONTH_NAMES, 1)}}
_fomc_cache = {"ts": 0.0, "events": []}
_FOMC_ROW = re.compile(
    r'fomc-meeting__month[^"]*"[^>]*>\s*<strong>\s*([^<]+?)\s*</strong>\s*</div>\s*'
    r'<div class="[^"]*fomc-meeting__date[^"]*"[^>]*>\s*([^<]+?)\s*</div>', re.S)


def parse_fomc_page(html: str) -> list:
    """연준 FOMC 일정 페이지 → 정례 회의의 금리 결정일(회의 마지막 날) 목록.
    표결만 한 회의('22 (notation vote)')·임시 회의('(unscheduled)')처럼 날짜 칸이 숫자가 아니면 뺀다.
    '*' = 경제전망(점도표) 함께 발표, 'Apr/May 30-1' 처럼 달이 걸치면 결정일은 뒤쪽 달."""
    events = []
    parts = re.split(r">\s*(\d{4}) FOMC Meetings\s*<", html)
    for k in range(1, len(parts), 2):
        year = int(parts[k])
        for month_txt, date_txt in _FOMC_ROW.findall(parts[k + 1]):
            m = re.fullmatch(r"(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*(\*)?", date_txt)
            months = [_MONTHS.get(x.strip().rstrip(".").lower()) for x in month_txt.split("/")]
            if not m or not months or None in months:
                continue
            month, y = months[-1], year
            if month < months[0]:   # Dec/Jan 처럼 해를 넘김
                y += 1
            try:
                d = date(y, month, int(m.group(2) or m.group(1)))
            except ValueError:
                continue
            events.append({"date": d.isoformat(), "key": "fomc",
                           "event": FOMC["name"] + (" (경제전망·점도표)" if m.group(3) else ""),
                           "country": "US", "impact": "high"})
    return sorted(events, key=lambda e: e["date"])


async def _fomc_calendar(start: str, end: str) -> list:
    """FOMC 금리 결정일 (연준 공식 일정 페이지, 하루 캐시). 페이지 형식이 바뀌어 날짜를 못 찾으면 오류."""
    if not _fomc_cache["events"] or time.time() - _fomc_cache["ts"] > 24 * 3600:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(FOMC_URL)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        events = parse_fomc_page(resp.text)
        if not events:
            raise RuntimeError("연준 FOMC 일정 페이지에서 회의 날짜를 찾지 못함 (페이지 형식이 바뀌었을 수 있음)")
        _fomc_cache.update(ts=time.time(), events=events)
    return [dict(e) for e in _fomc_cache["events"] if start <= e["date"] <= end]


# ---------------- 발표값 ----------------

_value_cache: dict = {}   # (key, 날짜) → 발표값. 발표된 값은 바뀌지 않으므로(그날 기준) 계속 씀
_FRED_TZ = ZoneInfo("America/Chicago")   # FRED(세인트루이스 연은) 서버 날짜 기준


def fred_today() -> date:
    """FRED 가 보는 '오늘' (미국 중부 시간). 한국은 하루 앞서 있어서(한국 오전 = 미국 전날 밤)
    한국 날짜로 realtime_start 를 보내면 FRED 가 '미래 날짜'라며 HTTP 400 을 돌려줌."""
    return datetime.now(_FRED_TZ).date()


def _future_vintage_error(e: BaseException) -> bool:
    """FRED 400: 'Variable realtime_start can not be after today's date' (시계 차이 등으로 미국 날짜가 아직 전날)"""
    return "realtime_start" in str(e) and "400" in str(e)


def _obs(data: dict) -> list:
    """FRED 관측값 → [(기준일, 값)] (최신순, 결측 '.' 제외)"""
    out = []
    for o in data.get("observations") or []:
        try:
            out.append((o["date"], float(o["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _calc(calc: str, vals: list, i: int):
    """vals(최신순 값 목록)의 i 번째 기준 계산값. 데이터가 모자라면 None"""
    need = {"yoy": 12, "mom": 1, "chg": 1, "level": 0}[calc]
    if len(vals) <= i + need:
        return None
    v, b = vals[i], vals[i + need]
    if calc == "yoy":
        return (v / b - 1) * 100 if b else None
    if calc == "mom":
        return (v / b - 1) * 100 if b else None
    if calc == "chg":
        return v - b
    return v


def _period(day: str, series: str) -> str:
    """관측 기준일 → '10월' / '3분기' / '11/14 주'"""
    d = date.fromisoformat(day)
    if series == "ICSA":
        return f"{d.month}/{d.day} 주"
    if series == "A191RL1Q225SBEA":
        return f"{d.year} {(d.month - 1) // 3 + 1}분기"
    return f"{d.year}년 {d.month}월"


def _direction(ind: dict, actual: float, prev: float):
    """화면에 보이는 숫자 기준으로 오름/내림/같음 (반올림해서 같으면 같음)"""
    if ind["fmt"](actual) == ind["fmt"](prev):
        return "flat", 0.0
    return ("up" if actual > prev else "down"), actual - prev


def _change_text(ind: dict, change: str, diff: float) -> str:
    word = dict(zip(("up", "down", "flat"), ind["words"]))[change]
    if change == "flat":
        return word
    scale = ind.get("scale", 1)
    num = f"{abs(diff) * scale:,.1f}{ind['unit']}" if ind["unit"] else f"{abs(diff):.1f}"
    return f"{'▲' if change == 'up' else '▼'} {num} {word}"


async def _indicator_value(client, key: str, day: str) -> dict:
    """발표일(day) 기준 FRED 값 vs 전날 기준 값 → 그날 새로 나온 숫자"""
    ind = INDICATORS[key]
    limit = {"yoy": 26, "mom": 4, "chg": 4, "level": 3}[ind["calc"]]
    prev_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    base = {"series_id": ind["series"], "sort_order": "desc", "limit": limit}
    now, before = await asyncio.gather(
        _fred(client, "series/observations", {**base, "realtime_start": day, "realtime_end": day}),
        _fred(client, "series/observations", {**base, "realtime_start": prev_day, "realtime_end": prev_day}))
    now, before = _obs(now), _obs(before)
    if not now:
        return {"released": False, "note": "FRED 에 값 없음"}
    revised = bool(before) and now[0][0] == before[0][0] and now[0][1] != before[0][1]
    if before and now[0][0] <= before[0][0] and not revised:
        return {"released": False, "note": "FRED 에 아직 반영 전 (보통 발표 후 1시간 안에 올라옴)"}
    vals = [v for _, v in now]
    actual = _calc(ind["calc"], vals, 0)
    if revised:   # GDP 잠정·확정치처럼 같은 기간을 다시 발표 → 이전 = 직전 발표치
        prev = _calc(ind["calc"], [v for _, v in before], 0)
    else:
        prev = _calc(ind["calc"], vals, 1)
    if actual is None or prev is None:
        return {"released": False, "note": "FRED 데이터가 모자라 계산 못 함"}
    change, diff = _direction(ind, actual, prev)
    return {"released": True, "actual": ind["fmt"](actual), "prev": ind["fmt"](prev),
            "period": _period(now[0][0], ind["series"]) + (" (수정 발표)" if revised else ""),
            "metric": ind["metric"], "change": change, "change_text": _change_text(ind, change, diff)}


async def _fomc_value(client, day: str) -> dict:
    """결정일 전날까지의 목표 범위 vs 결정일 다음 날 목표 범위 (DFEDTARL·DFEDTARU, 현재 기준 일별 값)"""
    d = date.fromisoformat(day)
    rng = {"observation_start": (d - timedelta(days=7)).isoformat(),
           "observation_end": (d + timedelta(days=5)).isoformat(), "sort_order": "asc"}
    lo, hi = await asyncio.gather(_fred(client, "series/observations", {**rng, "series_id": "DFEDTARL"}),
                                  _fred(client, "series/observations", {**rng, "series_id": "DFEDTARU"}))
    lo, hi = dict(_obs(lo)), dict(_obs(hi))
    before = [k for k in hi if k < day and k in lo]
    after = [k for k in hi if k > day and k in lo]
    if not before:
        return {"released": False, "note": "FRED 에 결정 전 금리 값 없음"}
    if not after:
        return {"released": False, "note": "FRED 에 아직 반영 전 (결정 다음 날 값이 올라오면 표시)"}
    b, a = max(before), min(after)
    prev_txt, act_txt = f"{lo[b]:.2f}~{hi[b]:.2f}%", f"{lo[a]:.2f}~{hi[a]:.2f}%"
    diff = hi[a] - hi[b]
    change = "flat" if abs(diff) < 1e-9 else ("up" if diff > 0 else "down")
    words = dict(zip(("up", "down", "flat"), FOMC["words"]))
    return {"released": True, "actual": act_txt, "prev": prev_txt, "period": "", "metric": FOMC["metric"],
            "change": change,
            "change_text": words[change] if change == "flat" else f"{'▲' if diff > 0 else '▼'} {abs(diff):.2f}%p {words[change]}"}


def _explain(e: dict) -> dict:
    ind = FOMC if e["key"] == "fomc" else INDICATORS[e["key"]]
    out = {"about": ind["about"], "metric": ind["metric"],
           "scenarios": {w: ind[c] for c, w in zip(("up", "down", "flat"), ind["words"])}}
    if e.get("change"):
        out["effect"] = ind[e["change"]]
    return out


async def _attach_values(events: list) -> list:
    """오늘까지의 일정에 발표값을 붙임. 실패한 건은 note 에 사유, 오류 문구 목록 반환.
    '오늘' 은 미국(FRED) 날짜 — 한국 날짜로는 오늘이어도 미국은 아직 전날 밤이면 발표 전"""
    today = fred_today().isoformat()
    sem = asyncio.Semaphore(4)
    errors = []

    async def one(client, e):
        if e["date"] > today:
            e.update(released=False)
            if e["date"] <= date.today().isoformat():
                e["note"] = "미국 현지 날짜로 아직 발표일 전 (한국 시간으로 보통 밤 10시 30분 이후 발표)"
            return
        ck = (e["key"], e["date"])
        if ck in _value_cache:
            e.update(_value_cache[ck])
            return
        if not settings.fred_api_key:
            e.update(released=False, note="FRED_API_KEY 없음 — 발표값 없이 일정만")
            return
        async with sem:
            try:
                v = await (_fomc_value(client, e["date"]) if e["key"] == "fomc"
                           else _indicator_value(client, e["key"], e["date"]))
            except Exception as ex:
                if _future_vintage_error(ex):   # 미국 날짜가 아직 발표일 전 — 오류가 아니라 '발표 전'
                    e.update(released=False, note="미국 현지 날짜로 아직 발표일 전 — FRED 에 그날 기준 값이 없음")
                    return
                errors.append(f"{e['event']} {e['date']}: {err_text(ex)}")
                e.update(released=False, note=f"발표값 조회 실패 — {err_text(ex)}")
                return
        if v["released"]:
            _value_cache[ck] = v
        e.update(v)

    async with httpx.AsyncClient(timeout=30) as client:
        await asyncio.gather(*(one(client, e) for e in events))
    for e in events:
        e["explain"] = _explain(e)
    return errors


async def get_economic_calendar() -> dict:
    """경제 캘린더 (최근 2주 + 앞으로 4주): FRED 발표 일정 + 연준 FOMC 일정 + 발표값·해설.
    일정을 하나도 못 받으면 오류 (가짜 일정 없음)."""
    today = datetime.now().date()
    start, end = (today - timedelta(days=14)).isoformat(), (today + timedelta(days=28)).isoformat()
    errors, retry, events, used = [], False, [], []   # retry: 일시적 실패 → 캐시를 짧게 (routes/market.py)
    if settings.fred_api_key:
        try:
            events += await _fred_calendar(start, end)
            used.append("FRED 공식 발표 일정·발표값")
        except Exception as e:
            errors.append(f"FRED: {err_text(e)}")
            retry = True
    else:
        errors.append("FRED: FRED_API_KEY 없음 — CPI·고용 등 지표 일정·발표값 없음")
    try:
        events += await _fomc_calendar(start, end)
        used.append("연준 FOMC 일정")
    except Exception as e:
        errors.append(f"FOMC 일정(연준): {err_text(e)}")
        retry = True
    if not used:
        raise RuntimeError(" / ".join(errors))
    events.sort(key=lambda e: (e["date"], e["event"]))
    value_errors = await _attach_values(events)
    if value_errors:
        errors.append(f"발표값 {len(value_errors)}건 조회 실패 ({value_errors[0]})")
        retry = True
    return {"source": " + ".join(used), "events": events, "errors": errors, "retry": retry,
            "disclaimer": DISCLAIMER}
