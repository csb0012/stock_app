"""AI 챗봇 — Claude API(도구 사용)로 앱 데이터를 직접 조회해서 답변

Claude 가 질문에 필요한 도구를 스스로 골라 부름 (SDK tool runner 가 반복 처리):
  today_picks       오늘의 매수(상승 확률 높은)·매도/주의(하락 확률 높은) 후보 — AI 추천 데이터
  analyze_stock     종목 하나 상세 (현재가·상승 확률·추천 매입가·목표가·손절가·근거·수급·뉴스)
  my_portfolio      내 투자종목 손익 + 다음 거래일 전망
  my_watchlist      내 관심종목 + 전망
  market_overview   지수·환율·VIX 등
  track_record      예측 적중률 (실제 + 백테스트) — 확률을 얼마나 믿어도 되는지
  upcoming_events   옵션 만기일·미국 주요 지표 발표 일정

원칙: 모든 숫자는 도구 결과에서만 (지어내지 않음). 도구는 읽기 전용 (주문·수정 없음).
ANTHROPIC_API_KEY 가 없거나 API 오류면 그대로 오류로 알림 (다른 답으로 대체하지 않음).
"""
import json
from datetime import date, datetime, timedelta

import anthropic
from anthropic import beta_async_tool

from app.core.config import settings
from app.core.database import AsyncSessionLocal

SYSTEM = """당신은 개인용 주식 앱 'StockApp' 안의 투자 도우미입니다. 사용자는 한국어로 묻고, 국내(KOSPI·KOSDAQ)와 미국 주식을 합니다.

## 데이터 원칙
- 가격·확률·적중률·수급 등 모든 숫자는 반드시 도구로 조회한 값만 씁니다. 기억이나 추측으로 숫자를 만들지 않습니다.
- 도구가 오류를 돌려주면 그 사실을 그대로 말하고, 다른 값으로 메우지 않습니다.
- 질문에 필요한 도구는 먼저 호출하세요. 여러 도구가 필요하면 한 번에 같이 호출해도 됩니다.

## 매수·매도 추천 방식
- 앱의 '상승 확률'은 다음 거래일 하루의 방향 예측입니다. 50% 초과 = 상승 쪽, 50% 미만 = 하락 쪽.
- 추천할 때는 track_record 로 확인한 실제 적중률을 함께 알려 확률을 얼마나 믿을지 판단하게 하세요. 적중률이 50% 근처면 "참고 수준"이라고 분명히 말합니다.
- 주식에 '확실한' 종목은 없습니다. 사용자가 확실한 종목을 원하면, 근거가 가장 많이 겹치는 후보를 고르되 왜 확실하지 않은지(적중률·변동성 이벤트)를 짧게 덧붙이세요. 과장하지 않습니다.
- 종목을 추천할 때는 행동 계획을 구체적으로 줍니다:
  - 언제·얼마에 살지: 추천 매입가(범위)와 그 조건(buy_comment). 현재가가 매입가보다 높으면 "눌릴 때까지 기다림".
  - 언제 팔지: 목표가(익절), 손절가(이 가격 아래로 내려가면 정리). 예측 대상일(target_label) 기준임을 밝힙니다.
  - 근거: 학습 모델/지표 요인, 외국인·기관 수급, 뉴스, 공시 중 실제로 나온 것.
  - 주의: events(옵션 만기·FOMC·CPI 등), warnings.
- 하락 확률이 높은 종목은 "매도·비중 축소 검토" 또는 "신규 매수 보류"로 제시합니다. 사용자가 보유 중인지(my_portfolio) 확인해서 구분하세요.
- 사용자의 투자종목·관심종목 질문에는 평단가 대비 손익과 다음 거래일 전망을 같이 봅니다.

## 답변 형식
- 한국어, 간결하게. 핵심 결론을 먼저, 그다음 종목별 표나 목록.
- 가격은 국내 ₩, 미국 $ 로 표시합니다.
- 마지막 줄에 한 문장으로: 예측은 참고용이며 투자 판단과 손실 책임은 본인에게 있다는 점.
"""


def _brief_pred(p: dict | None) -> dict | None:
    if not p:
        return None
    keys = ("target_label", "probability", "signal", "confidence", "buy_price", "buy_low", "buy_high", "buy_gap_pct",
            "buy_comment", "target_price", "stop_loss", "method", "model_status", "events", "warnings")
    out = {k: p.get(k) for k in keys if p.get(k) not in (None, [], "")}
    if p.get("summary"):
        out["summary"] = p["summary"][:400]
    factors = [f"{f['name']}: {f['detail'][:120]}" for f in (p.get("factors") or [])[:6]]
    if factors:
        out["factors"] = factors
    return out


def _headlines(news: dict | list | None, n: int = 3) -> list:
    items = news.get("headlines", []) if isinstance(news, dict) else (news or [])
    return [{"title": h.get("title", "")[:90], "date": h.get("date"), "tone": h.get("tone")} for h in items[:n]]


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def make_tools(user):
    """요청한 사용자 기준의 도구들 (투자종목·관심종목은 그 사용자 것만)"""

    @beta_async_tool
    async def today_picks(side: str = "buy", market: str = "ALL", limit: int = 5) -> str:
        """오늘의 매수 후보 또는 매도/주의 후보를 AI 추천 데이터(장기 후보 + 단기 거래량 급증 종목)에서 고릅니다.

        Args:
            side: "buy" = 상승 확률 높은 순(매수 후보), "sell" = 하락 확률 높은 순(매도·주의 후보)
            market: "KR"(국내), "US"(미국), "ALL"(전체)
            limit: 돌려줄 종목 수 (1~10)
        """
        from app.api.routes import stocks
        limit = max(1, min(10, int(limit)))
        rows, errors = {}, []
        for kind in ("longterm", "shortterm"):
            try:
                data = await stocks._live(kind)
            except Exception as e:
                errors.append(f"{kind}: {getattr(e, 'detail', e)}")
                continue
            for r in data["items"]:
                if market != "ALL" and r["market"] != market:
                    continue
                rows.setdefault((r["market"], r["symbol"]), r)
        items = sorted(rows.values(), key=lambda r: r["prediction"].get("probability_exact", r["prediction"]["probability"]),
                       reverse=(side != "sell"))[:limit]
        out = [{
            "name": r["name"], "symbol": r["symbol"], "market": r["market"], "category": r.get("category"),
            "price": r["price"], "change_rate_today": r["change_rate"], "per": r.get("per"), "pbr": r.get("pbr"),
            "prediction": _brief_pred(r["prediction"]), "flows_5d": r.get("flows"),
            "news": _headlines(r.get("news"), 2), "long_term_score": r.get("long_term_score"),
        } for r in items]
        return _dump({"side": side, "market": market, "candidates_total": len(rows), "items": out, "errors": errors})

    @beta_async_tool
    async def analyze_stock(query: str) -> str:
        """종목 하나를 이름이나 코드로 찾아 상세 분석합니다 (현재가, 다음 거래일 상승 확률, 추천 매입가·목표가·손절가, 근거, 수급, 뉴스).

        Args:
            query: 종목명 또는 코드 (예: 삼성전자, 005930, 엔비디아, NVDA)
        """
        from app.services import stock_master
        from app.services.quote import analyze_kr, analyze_us_many, strip_candles
        hits = stock_master.search(query, "ALL", 5)
        if not hits:
            return _dump({"error": f"'{query}' 종목을 찾지 못함 (KIS 종목마스터 기준)"})
        m = hits[0]
        try:
            if m["market"] == "KR":
                r = await analyze_kr(m["symbol"])
            else:
                r = (await analyze_us_many([m["symbol"]]))[m["symbol"]]
        except Exception as e:
            return _dump({"error": f"{m['name']} 조회 실패: {e}"})
        if "error" in r:
            return _dump({"error": f"{m['name']}: {r['error']}"})
        r = strip_candles(r)
        ind = r.get("indicators") or {}
        return _dump({
            "name": r["name"], "symbol": r["symbol"], "market": r["market"], "category": r.get("category"),
            "price": r["price"], "change_rate_today": r["change_rate"], "per": r.get("per"), "pbr": r.get("pbr"),
            "indicators": {k: ind.get(k) for k in ("rsi", "macd_hist", "ma20", "ma60", "bb_upper", "bb_lower")},
            "prediction": _brief_pred(r["prediction"]), "flows_5d": r.get("flows"),
            "news": _headlines(r.get("news"), 4), "style": r.get("style"),
            "other_matches": [f"{h['name']}({h['symbol']})" for h in hits[1:4]],
        })

    @beta_async_tool
    async def my_portfolio() -> str:
        """사용자의 투자종목(보유 종목): 수량·평단가·현재가·손익률·오늘 손익과 다음 거래일 전망, 통화별 합계."""
        from app.api.routes.portfolio import analyze_portfolio
        async with AsyncSessionLocal() as db:
            try:
                data = await analyze_portfolio(current_user=user, db=db)
            except Exception as e:
                return _dump({"error": f"투자종목 조회 실패: {getattr(e, 'detail', e)}"})
        rows = []
        for r in data.get("items", []):
            rows.append({k: r.get(k) for k in ("name", "symbol", "market", "quantity", "avg_price", "current_price",
                                                "pnl_pct", "pnl_amount", "day_pnl", "weight", "error", "warning")}
                        | {"prediction": _brief_pred(r.get("prediction"))})
        return _dump({"items": rows, "totals_by_currency": data.get("totals"), "usdkrw": data.get("usdkrw"),
                      "combined_krw": data.get("combined_krw"), "fx_error": data.get("fx_error")})

    @beta_async_tool
    async def my_watchlist() -> str:
        """사용자의 관심종목: 현재가·등락·5/20일 변화·메모·사용자가 정한 목표가와 다음 거래일 전망."""
        from app.api.routes.watchlist import analyze_watchlist
        async with AsyncSessionLocal() as db:
            try:
                rows = await analyze_watchlist(current_user=user, db=db)
            except Exception as e:
                return _dump({"error": f"관심종목 조회 실패: {getattr(e, 'detail', e)}"})
        return _dump([{k: r.get(k) for k in ("name", "symbol", "market", "memo", "target_price", "current_price",
                                             "change_rate", "change_5d", "change_20d", "rsi", "target_reached", "error")}
                       | {"prediction": _brief_pred(r.get("prediction"))} for r in rows])

    @beta_async_tool
    async def market_overview() -> str:
        """시장 전체: 코스피·코스닥(KIS 실시간), 다우·S&P500·나스닥·SOX·VIX·미 10년 금리·달러인덱스·유가·환율, 빅테크 종가와 시간외."""
        from app.api.routes.market import get_market_overview
        try:
            data = await get_market_overview(current_user=user)
        except Exception as e:
            return _dump({"error": f"시장 데이터 조회 실패: {e}"})
        idx = {k: {f: v.get(f) for f in ("price", "change_rate", "as_of", "source", "stale", "error") if v.get(f) is not None}
               for k, v in (data.get("indices") or {}).items()}
        big = [{f: b.get(f) for f in ("symbol", "price", "change_rate", "as_of", "ext", "error") if b.get(f) is not None}
               for b in data.get("bigtech") or []]
        return _dump({"indices": idx, "bigtech": big})

    @beta_async_tool
    async def track_record(days: int = 90) -> str:
        """앱 예측의 실제 적중률 (실제 예측 + 과거 백테스트): 전체·상승/하락 예측별·시장별·방식별, 학습 모델 사용 상태.

        Args:
            days: 최근 며칠 기준 (7~180)
        """
        from app.services import prediction_log, ml_model
        days = max(7, min(180, int(days)))
        rv = await prediction_log.review(days, "ALL", "all", "all", 1)
        models = {v: (None if not m else {k: m.get(k) for k in ("adopted", "adopt_reason", "stack_usable", "stack_reason")})
                  for v, m in ml_model.status().items() if v in ml_model.VARIANT_FEATURES}
        return _dump({
            "days": days, "overall": rv["overall"], "up_calls": rv["up_calls"], "down_calls": rv["down_calls"],
            "by_market": rv["by_market"], "by_kind": rv["by_kind"],
            "method_accuracy": [{k: m.get(k) for k in ("label", "n", "dir_accuracy", "accuracy", "calls")}
                                for m in rv.get("method_accuracy", [])],
            "models": models,
        })

    @beta_async_tool
    async def upcoming_events(days: int = 14) -> str:
        """앞으로 며칠 동안의 변동성 이벤트: 국내·미국 옵션 만기일(마녀의 날)과 미국 주요 지표 발표(CPI·고용·FOMC·PCE·GDP).

        Args:
            days: 앞으로 며칠 (1~60)
        """
        from app.services import events
        days = max(1, min(60, int(days)))
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        out = []
        for i in range(days + 1):
            d = today + timedelta(days=i)
            for mk in ("KR", "US"):
                ox = events.option_expiry(mk, d)
                if ox:
                    out.append({"date": d.isoformat(), "market": mk, "event": ox})
        for e in events._cache["events"]:
            if today.isoformat() <= e["date"][:10] <= (today + timedelta(days=days)).isoformat():
                out.append({"date": e["date"][:10], "market": "US", "event": e["event"]})
        out.sort(key=lambda x: x["date"])
        return _dump({"events": out, "note": events.status().get("error")})

    return [today_picks, analyze_stock, my_portfolio, my_watchlist, market_overview, track_record, upcoming_events]


def _now_context() -> str:
    from app.services.market_calendar import market_status
    kr, us = market_status("KR"), market_status("US")
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d (%a) %H:%M")  # 서버 시계가 UTC 여도 한국시간
    return (f"[현재 {now} 한국시간 · 국내장 {kr['state']}"
            f"{' (다음 개장 ' + kr['next_open_label'] + ')' if kr.get('next_open_label') else ''}"
            f" · 미국장 {us['state']}{' (다음 개장 ' + us['next_open_kst'] + ' 한국시간)' if us.get('next_open_kst') else ''}]")


class ChatError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


async def chat(user, history: list) -> dict:
    """history: [{"role": "user"|"assistant", "content": "..."}] (마지막은 user) → {"reply", "tools", "model", "usage"}"""
    if not settings.anthropic_api_key:
        raise ChatError(503, "ANTHROPIC_API_KEY 가 backend/.env 에 없습니다 — console.anthropic.com 에서 API 키를 발급해 넣고 백엔드를 재시작하세요")
    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-20:] if m.get("content")]
    if not msgs or msgs[-1]["role"] != "user":
        raise ChatError(400, "마지막 메시지는 사용자 질문이어야 합니다")
    while msgs and msgs[0]["role"] != "user":   # 첫 메시지는 user 여야 함
        msgs.pop(0)
    # 현재 시각·장 상태는 매번 바뀌므로 system 이 아니라 마지막 질문 앞에 붙임 (system 은 캐시되도록 고정)
    msgs[-1] = {"role": "user", "content": f"{_now_context()}\n{msgs[-1]['content']}"}

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    runner = client.beta.messages.tool_runner(
        model=settings.chat_model,
        max_tokens=16000,
        system=SYSTEM,
        messages=msgs,
        tools=make_tools(user),
        output_config={"effort": settings.chat_effort},
        cache_control={"type": "ephemeral"},
        max_iterations=8,
        # 안전 분류기가 거절하면 서버가 다른 모델로 같은 요청을 이어서 처리
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    tools_used, last = [], None
    try:
        async for message in runner:
            last = message
            tools_used += [b.name for b in message.content if b.type == "tool_use"]
    except anthropic.AuthenticationError:
        raise ChatError(502, "Claude API 키가 올바르지 않습니다 (ANTHROPIC_API_KEY 확인)")
    except anthropic.PermissionDeniedError as e:
        raise ChatError(502, f"Claude API 권한 오류: {e.message}")
    except anthropic.RateLimitError:
        raise ChatError(429, "Claude API 호출 한도 초과 — 잠시 후 다시 시도하세요")
    except anthropic.BadRequestError as e:
        raise ChatError(502, f"Claude API 요청 오류: {e.message}")
    except anthropic.APIStatusError as e:
        raise ChatError(502, f"Claude API 오류 ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise ChatError(502, "Claude API 에 연결하지 못했습니다 (인터넷 연결 확인)")
    finally:
        await client.close()

    if last is None:
        raise ChatError(502, "Claude API 응답 없음")
    if last.stop_reason == "refusal":
        raise ChatError(502, "AI 가 이 질문에는 답하지 않았습니다 (안전 정책). 질문을 바꿔 보세요")
    text = "\n".join(b.text for b in last.content if b.type == "text").strip()
    if last.stop_reason == "max_tokens":
        text += "\n\n(답변이 길어 중간에 끊겼습니다 — 질문을 나눠 주세요)"
    u = last.usage
    return {"reply": text or "(빈 답변)", "tools": tools_used, "model": last.model,
            "usage": {"input": u.input_tokens, "output": u.output_tokens,
                      "cache_read": getattr(u, "cache_read_input_tokens", None)}}
