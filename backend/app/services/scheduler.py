"""정해진 시각에 자동으로 예측을 기록 — 화면을 열지 않아도 채점 대상이 매일 쌓이도록

| 작업 | 시각 (현지) | 하는 일 |
|---|---|---|
| 국내 장 마감 후 | 15:40~16:20 KST | 국내 대상 종목의 다음 거래일 예측 기록 (출처 "장마감 자동") |
| 미국 장 마감 후 | 16:10~16:50 ET  | 미국 대상 종목의 다음 거래일 예측 기록 |
| 국내 장 시작 전 | 08:20~08:58 KST | 간밤 미국장을 반영해 국내 예측 다시 기록 (출처 "장전 자동") — 이 값이 채점됨 |

대상 종목 = AI 추천 후보 + 관심종목 + 투자종목 (backtest._universe).
거래일에만 하루 한 번씩 실행. 5분마다 시각을 확인하므로 서버가 그 시간대에 켜져 있어야 한다.

그리고 AI 추천 기본 데이터(일봉·뉴스)를 14분마다 미리 만들어 둔다 → 화면을 처음 열 때 10~20초 기다리지 않음.
"""
import asyncio
from datetime import datetime

import time

from app.services import backtest, ml_model, prediction_log, flows, events
from app.services.market_calendar import _TZ, is_trading_day

JOBS = [
    # (이름, 시장, 시작 분, 끝 분, 출처)
    ("preopen_kr", "KR", 8 * 60 + 20, 8 * 60 + 58, "장전 자동"),
    ("close_kr", "KR", 15 * 60 + 40, 16 * 60 + 20, "장마감 자동"),
    ("close_us", "US", 16 * 60 + 10, 16 * 60 + 50, "장마감 자동"),
    # 외국인·기관 수급은 장 마감 후 확정치가 늦게 나와 저녁에 수집 (KIS 는 최근 30일만 줘서 매일 쌓음)
    ("flow_kr", "KR", 18 * 60 + 10, 18 * 60 + 50, None),
    # 매집·바닥 다지기 전 종목 스캔 (종가 확정 후, 7~10분 걸림)
    ("accum_kr", "KR", 16 * 60 + 30, 23 * 60 + 30, None),
]
_done: dict = {}   # 작업 이름 -> 마지막 실행 날짜
_last: dict = {}   # 작업 이름 -> 결과 문자열 (점검용)


def status() -> dict:
    return {"jobs": {name: {"last_day": str(_done.get(name)), "result": _last.get(name)} for name, *_ in JOBS},
            "flows": flows.status(), "events": events.status()}


async def _run_job(name: str, market: str, source: str):
    from app.services.quote import analyze_kr_many, analyze_us_many  # 순환 import 방지
    if name == "accum_kr":
        from app.services import accumulation
        if not accumulation.stale():
            _last[name] = "오늘 결과 이미 있음 (건너뜀)"
            return
        st = await accumulation.scan()
        _last[name] = st.get("message") or "실행"
        if (st.get("message") or "").startswith("실패"):
            raise RuntimeError(st["message"])
        return
    if name == "flow_kr":
        stocks = [s["symbol"] for s in await backtest._universe() if s["market"] == "KR"]
        r = await flows.collect(stocks)
        _last[name] = f"수급 {len(stocks)}종목 수집, 새 날짜 {r['added']}건" + (f" · 실패 {len(r['errors'])}건" if r["errors"] else "")
        print(f"[scheduler] {name}: {_last[name]}")
        return
    if name == "preopen_kr":
        await ml_model.refresh_ctx()  # 간밤 미국장 마감 지수 반영
    stocks = [s["symbol"] for s in await backtest._universe() if s["market"] == market]
    if market == "KR":
        res = await analyze_kr_many(stocks, count=130, with_news=True)
    else:
        res = await analyze_us_many(stocks, period="6mo", with_news=True)
    ok = [r for r in res.values() if "error" not in r]
    await prediction_log.record(list(res.values()), source)
    errs = [f"{r['symbol']}: {r['error']}" for r in res.values() if "error" in r]
    _last[name] = f"{len(ok)}/{len(stocks)}종목 기록" + (f" · 실패 {len(errs)}건 ({errs[0][:80]})" if errs else "")
    print(f"[scheduler] {name}: {_last[name]}")


async def loop():
    from app.services.kis_api import mark_background
    mark_background()  # 화면 요청보다 KIS 호출 순서를 뒤로
    await asyncio.sleep(30)
    while True:
        if events.due():   # 미국 지표 발표 일정 (경고용) 6시간마다, 일시적 실패면 10분 뒤
            await events.refresh()
        for name, market, start, end, source in JOBS:
            now = datetime.now(_TZ[market])
            hm = now.hour * 60 + now.minute
            if _done.get(name) == now.date() or not is_trading_day(market, now.date()) or not (start <= hm < end):
                continue
            try:
                await _run_job(name, market, source)
                _done[name] = now.date()
            except Exception as e:  # 다음 5분 주기에 다시 시도 (시간대 안이면)
                _last[name] = f"실패: {e}"
                print(f"[scheduler] {name} 실패: {e}")
        await asyncio.sleep(300)


async def warm_recommendations():
    """AI 추천 기본 데이터를 미리 만들어 둠 (캐시 15분 → 14분마다 갱신)"""
    from app.api.routes import stocks  # 순환 import 방지
    from app.services.kis_api import mark_background
    mark_background()
    await asyncio.sleep(45)
    while True:
        for kind in ("shortterm", "longterm"):
            try:
                await stocks.refresh_base(kind)
            except Exception as e:  # 화면에서 열면 그때 오류가 그대로 표시됨
                print(f"[scheduler] AI 추천({kind}) 미리 계산 실패: {getattr(e, 'detail', e)}")
        await asyncio.sleep(14 * 60)
