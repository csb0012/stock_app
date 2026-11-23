"""규칙 기반 챗봇 — 질문의 키워드로 할 일을 고르고, 앱 데이터를 조회해 정해진 형식으로 답변 (외부 AI API 없음)

질문 → 의도 판단 (위에서부터 먼저 맞는 것):
  1. 종목명·코드가 정확히 들어 있으면       → 종목 분석 (예: "삼성전자 사도 돼?", "NVDA 어때")
  2. 투자종목·보유·손익·수익                → 내 투자종목 점검
  3. 관심종목                               → 관심종목 현황
  4. 매도·팔·하락·위험                       → 하락 확률 높은 종목 (보유 중이면 표시)
  5. 매수·추천·살·오를·상승                  → 상승 확률 높은 종목
  6. 적중률·정확도·믿을                      → 예측 적중률
  7. 이벤트·일정·만기·FOMC·CPI·발표          → 변동성 이벤트 일정
  8. 시장·지수·코스피·나스닥·환율·VIX         → 시장 현황
  9. 그 밖                                  → 이름 일부로 종목 찾기 (3글자 이상) → 못 찾으면 사용법 안내
조건: "국내/한국/코스피" → 국내만, "미국/나스닥/해외" → 미국만, "3개" → 개수.

원칙: 숫자는 전부 조회한 값 그대로 (지어내지 않음). 조회 실패는 실패라고 답함. 읽기 전용 (주문·수정 없음).
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.database import AsyncSessionLocal

DISCLAIMER = "\n\n_예측은 참고용이며 투자 판단과 손실 책임은 본인에게 있습니다._"

# 종목코드처럼 보이지만 질문에서는 다른 뜻으로 쓰이는 영문 단어
_NOT_SYMBOL = {"AI", "ETF", "ETN", "VIX", "CPI", "PCE", "GDP", "PPI", "FOMC", "PER", "PBR", "RSI", "MACD", "USD",
               "KRW", "KR", "US", "ET", "OK", "PM", "AM", "IPO", "EPS", "ATR", "MA", "TOP", "BEST", "NOW", "BUY", "SELL"}
# 종목명 뒤에 붙는 조사·어미
_JOSA = ("에서는", "으로는", "이랑", "하고", "에서", "으로", "한테", "은", "는", "이", "가", "을", "를", "도", "의",
         "에", "랑", "로", "좀", "요")
_STOP = {"오늘", "내일", "지금", "종목", "주식", "추천", "매수", "매도", "어때", "사도", "팔까", "괜찮", "전망", "분석",
         "알려줘", "알려", "줘", "해줘", "어떻게", "얼마", "언제", "국내", "미국", "한국", "해외", "시장"}

_KW = [
    ("portfolio", r"투자\s*종목|보유|포트폴리오|내\s*(주식|종목)|손익|수익률?|평가\s*금액|물렸"),
    ("watchlist", r"관심\s*종목|관심\s*목록|찜"),
    ("theme", r"테마"),
    ("accum", r"매집|바닥\s*(다지|권|주)|다지기|급등\s*전|터질|세력"),
    ("sell", r"매도|팔(까|아|고|야|지|면)|파는|팔\s|하락|떨어|위험|손절|빠질|약세"),
    ("buy", r"매수|추천|살\s*만|사(도|면|야|고|볼|자|려)|오를|상승|유망|강세|좋은\s*종목|뭐\s*살"),
    ("track", r"적중|정확도|맞(췄|았|나|아)|믿을|신뢰|성적|성능"),
    ("events", r"이벤트|일정|만기|마녀|fomc|cpi|pce|고용|금리\s*결정|발표|지표"),
    ("market", r"시장|지수|코스피|코스닥|나스닥|다우|s&p|환율|달러|vix|공포|유가|국채|금리|빅테크|증시|장\s*어때"),
    ("help", r"도움|사용법|뭘?\s*할\s*수|기능|안녕|hello|\bhi\b"),
]


# ---------------- 질문 해석 ----------------

def _market_filter(q: str) -> str:
    kr = re.search(r"국내|한국|코스피|코스닥|\bkr\b", q, re.I)
    us = re.search(r"미국|나스닥|해외|뉴욕|\bus\b", q, re.I)
    return "KR" if kr and not us else "US" if us and not kr else "ALL"


def _count(q: str, default: int = 5) -> int:
    m = re.search(r"(\d{1,2})\s*(개|종목|가지|위)", q)
    return max(1, min(10, int(m.group(1)))) if m else default


def _strip_josa(w: str) -> str:
    for j in _JOSA:
        if w.endswith(j) and len(w) > len(j) + 1:
            return w[: -len(j)]
    return w


def _tokens(q: str) -> list:
    words = [w for w in re.split(r"[\s,?!.~·/()\"']+", q) if w]
    out = []
    for w in words + [a + b for a, b in zip(words, words[1:])]:   # "LG 에너지솔루션" 처럼 띄어 쓴 이름
        for t in (w, _strip_josa(w)):
            if t and t not in out:
                out.append(t)
    return out


def _find_stock(q: str, fuzzy: bool = False) -> dict | None:
    """질문 안의 종목: 이름·코드가 정확히 일치하는 것 우선. fuzzy=True 면 이름 앞부분·일부 일치도 (3글자 이상)"""
    from app.services import stock_master
    toks = _tokens(q)
    for t in toks:
        if t.upper() in _NOT_SYMBOL or t in _STOP:
            continue
        for h in stock_master.search(t, "ALL", 3):
            if h["symbol"].upper() == t.upper() or h["name"].replace(" ", "").lower() == t.lower():
                return h
    if fuzzy:
        for t in sorted(toks, key=len, reverse=True):
            if len(t) < 3 or t.upper() in _NOT_SYMBOL or t in _STOP or re.fullmatch(r"[a-z]+", t):
                continue
            hits = stock_master.search(t, "ALL", 1)
            if hits:
                return hits[0]
    return None


def route(q: str) -> tuple:
    """질문 → (의도, 종목 또는 None)"""
    stock = _find_stock(q)
    ql = q.lower()
    intents = [name for name, pat in _KW if re.search(pat, ql)]
    if "theme" in intents:          # "로봇 테마", "삼성전자 테마"
        return "theme", stock
    if "accum" in intents:          # "매집 종목", "삼성전자 매집 점수"
        return "accum", stock
    if stock and not ({"portfolio", "watchlist"} & set(intents)):
        return "stock", stock
    if "buy" in intents and "sell" in intents:
        # "매수 추천해줘, 언제 팔지도" 는 매수 / "하락할 종목 추천" 은 매도 — 강한 매도 단어가 있을 때만 매도 쪽
        intents.remove("buy" if re.search(r"매도|하락|떨어|위험|손절|약세|팔아야", ql) else "sell")
    for name in ("portfolio", "watchlist", "sell", "buy", "track", "events", "market"):
        if name in intents:
            return name, None
    stock = _find_stock(q, fuzzy=True)   # "하이닉스 어때" 처럼 이름 일부
    if stock:
        return "stock", stock
    return ("help" if "help" in intents else "unknown"), None


# ---------------- 형식 ----------------

def _px(v, market: str) -> str:
    if v is None:
        return "-"
    return f"₩{v:,.0f}" if market == "KR" else f"${v:,.2f}"


def _won(v) -> str:
    """부호 있는 원화 금액: +₩45,678 / -₩1,200"""
    return f"{'-' if v < 0 else '+'}₩{abs(v):,.0f}"


def _pct(v) -> str:
    return "-" if v is None else f"{v:+.2f}%"


def _opinion(prob) -> str:
    if prob is None:
        return "-"
    return "상승 우세" if prob >= 55 else "하락 우세" if prob < 45 else "방향 약함"


def _buy_zone(p: dict, market: str) -> str:
    if p.get("buy_low") and p.get("buy_high") and p["buy_low"] != p["buy_high"]:
        return f"{_px(p['buy_low'], market)}~{_px(p['buy_high'], market)}"
    return _px(p.get("buy_price"), market)


async def _accuracy_line() -> str:
    from app.services import prediction_log
    try:
        rv = await prediction_log.review(90, "ALL", "all", "all", 1)
    except Exception as e:
        return f"(적중률 조회 실패: {e})"
    o = rv["overall"]
    if not o["accuracy"]:
        return "아직 채점된 예측이 없어 적중률을 알 수 없습니다 — 확률은 참고만 하세요."
    note = " — 50% 근처라 참고 수준입니다" if o["accuracy"] < 55 else ""
    return f"최근 90일 예측 적중률 **{o['accuracy']}%** ({o['hit']}/{o['hit'] + o['miss']}건){note}."


# ---------------- 답변 ----------------

async def _picks(user, side: str, q: str) -> str:
    from app.api.routes import stocks
    market, limit = _market_filter(q), _count(q)
    rows, errors = {}, []
    for kind in ("longterm", "shortterm"):
        try:
            data = await stocks._live(kind)
        except Exception as e:
            errors.append(f"{'장기' if kind == 'longterm' else '단기'} 후보 조회 실패: {getattr(e, 'detail', e)}")
            continue
        for r in data["items"]:
            if market == "ALL" or r["market"] == market:
                rows.setdefault((r["market"], r["symbol"]), r)
    if not rows:
        return "추천 후보를 불러오지 못했습니다.\n" + "\n".join(f"- {e}" for e in errors)

    def prob(r):
        return r["prediction"].get("probability_exact", r["prediction"]["probability"])
    where = {"KR": "국내", "US": "미국"}.get(market, "국내·미국")
    title = "상승 확률이 높은" if side == "buy" else "하락 확률이 높은"
    # 매수 후보는 상승 쪽(50% 초과)만, 매도·주의 후보는 하락 쪽(50% 미만)만
    items = sorted([r for r in rows.values() if (prob(r) > 50 if side == "buy" else prob(r) < 50)],
                   key=prob, reverse=(side == "buy"))[:limit]
    if not items:
        return (f"지금 {where} AI 추천 후보 {len(rows)}개 중 {'상승' if side == 'buy' else '하락'} 쪽으로 예측된 종목이 없습니다."
                + "".join(f"\n⚠ {e}" for e in errors))
    held = await _held_symbols(user) if side == "sell" else set()
    target = items[0]["prediction"].get("target_label") or "다음 거래일"
    lines = [f"**{where} {title} 종목 {len(items)}개** ({target} 기준, AI 추천 후보 {len(rows)}개 중)", ""]
    if side == "buy":
        lines += ["| 종목 | 현재가 | 상승 확률 | 추천 매입가 | 목표가 | 손절가 |", "|---|---|---|---|---|---|"]
        for r in items:
            p, m = r["prediction"], r["market"]
            lines.append(f"| {r['name']} ({r['symbol']}) | {_px(r['price'], m)} ({_pct(r['change_rate'])}) | "
                         f"{p['probability']}% | {_buy_zone(p, m)} | {_px(p.get('target_price'), m)} | {_px(p.get('stop_loss'), m)} |")
    else:
        lines += ["| 종목 | 현재가 | 상승 확률 | 보유 | 의견 |", "|---|---|---|---|---|"]
        for r in items:
            p, m = r["prediction"], r["market"]
            mine = (m, r["symbol"]) in held
            lines.append(f"| {r['name']} ({r['symbol']}) | {_px(r['price'], m)} ({_pct(r['change_rate'])}) | "
                         f"{p['probability']}% | {'**보유 중**' if mine else '-'} | "
                         f"{'비중 축소 검토' if mine else '신규 매수 보류'} |")
    lines += ["", "**근거**"]
    for r in items:
        lines.append(f"- **{r['name']}**: {(r['prediction'].get('summary') or '-')[:160]}")
    if side == "buy":
        lines += ["", "추천 매입가 근처로 내려올 때 사고, 목표가에서 익절·손절가 아래로 내려가면 정리하는 계획입니다."]
    if errors:
        lines += [""] + [f"⚠ {e}" for e in errors]
    lines += ["", await _accuracy_line()]
    return "\n".join(lines)


async def _held_symbols(user) -> set:
    from app.models.portfolio import PortfolioItem
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(PortfolioItem).where(PortfolioItem.user_id == user.id))).scalars().all()
    return {(r.market, r.symbol) for r in rows}


async def _stock(stock: dict) -> str:
    from app.services.quote import analyze_kr, analyze_us_many
    try:
        r = await analyze_kr(stock["symbol"]) if stock["market"] == "KR" else (await analyze_us_many([stock["symbol"]]))[stock["symbol"]]
    except Exception as e:
        return f"{stock['name']}({stock['symbol']}) 조회 실패: {e}"
    if "error" in r:
        return f"{stock['name']}({stock['symbol']}) 조회 실패: {r['error']}"
    p, m, ind = r["prediction"], r["market"], r.get("indicators") or {}
    lines = [
        f"**{r['name']} ({r['symbol']})** — 현재가 {_px(r['price'], m)} ({_pct(r['change_rate'])})",
        "",
        f"- {p.get('target_label') or '다음 거래일'} 상승 확률 **{p['probability']}%** → **{p.get('signal', '-')}** (신뢰도 {p.get('confidence', '-')})",
        f"- 추천 매입가 {_buy_zone(p, m)}" + (f" — {p['buy_comment']}" if p.get("buy_comment") else ""),
        f"- 목표가 {_px(p.get('target_price'), m)} / 손절가 {_px(p.get('stop_loss'), m)}",
    ]
    extra = []
    if ind.get("rsi") is not None:
        extra.append(f"RSI {ind['rsi']:.0f}")
    if r.get("per"):
        extra.append(f"PER {r['per']:.1f}")
    if r.get("pbr"):
        extra.append(f"PBR {r['pbr']:.2f}")
    if extra:
        lines.append("- " + " · ".join(extra))
    fl = r.get("flows")
    if fl:
        lines.append(f"- 최근 {fl['days']}거래일 순매수: 외국인 {fl['frgn_qty']:+,}주 · 기관 {fl['orgn_qty']:+,}주 · 개인 {fl['prsn_qty']:+,}주")
    lines += ["", f"**요약**: {p.get('summary') or '-'}"]
    factors = (p.get("factors") or [])[:5]
    if factors:
        lines += ["", "**근거**"] + [f"- {'▲' if f.get('impact') == 'up' else '▼' if f.get('impact') == 'down' else '·'} "
                                    f"{f['name']}: {f['detail'][:140]}" for f in factors]
    news = (r.get("news") or {}).get("headlines") or []
    if news:
        lines += ["", "**최근 뉴스**"] + [
            f"- {'[' + h['press'] + '] ' if h.get('press') else ''}{h.get('title', '')[:90]}"
            f"{' (국내 기사 · 참고, 확률 미반영)' if h.get('weighted') is False else ''}" for h in news[:4]]
    for w in p.get("warnings") or []:
        lines.append(f"\n⚠ {w}")
    lines += ["", await _accuracy_line()]
    return "\n".join(lines)


async def _portfolio(user) -> str:
    from app.api.routes.portfolio import analyze_portfolio
    async with AsyncSessionLocal() as db:
        try:
            data = await analyze_portfolio(current_user=user, db=db)
        except Exception as e:
            return f"투자종목 조회 실패: {getattr(e, 'detail', e)}"
    items = data.get("items") or []
    if not items:
        return "등록된 투자종목이 없습니다. **투자종목** 메뉴에서 보유 종목을 추가하세요."
    lines = []
    c = data.get("combined_krw")
    if c:
        lines.append(f"**총 평가금액 ₩{c['value']:,}** · 손익 {_won(c['pnl'])} ({c['pnl_pct']:+.2f}%) · 오늘 {_won(c['day_pnl'])}")
    elif data.get("fx_error"):
        lines.append(f"(환율 조회 실패로 원화 합계 없음: {data['fx_error']})")
    lines += ["", "| 종목 | 수량 | 평단가 | 현재가 | 손익률 | 상승 확률 | 의견 |", "|---|---|---|---|---|---|---|"]
    warn = []
    for r in items:
        m = r["market"]
        if r.get("error"):
            lines.append(f"| {r['name']} ({r['symbol']}) | {r['quantity']:g} | {_px(r['avg_price'], m)} | 조회 실패 | - | - | - |")
            warn.append(f"{r['name']}: {r['error']}")
            continue
        p = r.get("prediction") or {}
        prob = p.get("probability")
        op = "보유·추가 검토" if prob is not None and prob >= 55 else "비중 축소 검토" if prob is not None and prob < 45 else "관망"
        if p.get("stop_loss") and r["current_price"] <= p["stop_loss"]:
            op = "**손절가 이하**"
        lines.append(f"| {r['name']} ({r['symbol']}) | {r['quantity']:g} | {_px(r['avg_price'], m)} | {_px(r['current_price'], m)} | "
                     f"{_pct(r.get('pnl_pct'))} | {prob if prob is not None else '-'}% | {op} |")
        if r.get("warning"):
            warn.append(r["warning"])
    downs = [r["name"] for r in items if (r.get("prediction") or {}).get("probability", 50) < 45]
    if downs:
        lines += ["", f"하락 확률이 높은 보유 종목: **{', '.join(downs)}** — 손절가·비중을 확인하세요."]
    lines += [""] + [f"⚠ {w}" for w in warn]
    lines += [await _accuracy_line()]
    return "\n".join(lines)


async def _watchlist(user) -> str:
    from app.api.routes.watchlist import analyze_watchlist
    async with AsyncSessionLocal() as db:
        try:
            rows = await analyze_watchlist(current_user=user, db=db)
        except Exception as e:
            return f"관심종목 조회 실패: {getattr(e, 'detail', e)}"
    if not rows:
        return "등록된 관심종목이 없습니다. **관심종목** 메뉴에서 추가하세요."
    lines = ["| 종목 | 현재가 | 오늘 | 20일 | 상승 확률 | 목표가 |", "|---|---|---|---|---|---|"]
    for r in rows:
        m = r["market"]
        if r.get("error"):
            lines.append(f"| {r['name']} ({r['symbol']}) | 조회 실패 | - | - | - | - |")
            continue
        p = r.get("prediction") or {}
        tp = _px(r["target_price"], m) + (" **도달**" if r.get("target_reached") else "") if r.get("target_price") else "-"
        lines.append(f"| {r['name']} ({r['symbol']}) | {_px(r['current_price'], m)} | {_pct(r.get('change_rate'))} | "
                     f"{_pct(r.get('change_20d'))} | {p.get('probability', '-')}% ({_opinion(p.get('probability'))}) | {tp} |")
    reached = [r["name"] for r in rows if r.get("target_reached")]
    if reached:
        lines += ["", f"목표가(이하)에 도달한 종목: **{', '.join(reached)}**"]
    return "\n".join(lines)


async def _market(user) -> str:
    from app.api.routes.market import get_market_overview
    try:
        data = await get_market_overview(current_user=user)
    except Exception as e:
        return f"시장 데이터 조회 실패: {getattr(e, 'detail', e)}"
    names = {"kospi": "코스피", "kosdaq": "코스닥", "dow": "다우", "sp500": "S&P 500", "nasdaq": "나스닥",
             "sox": "필라델피아 반도체", "vix": "VIX", "us10y": "미 10년 금리", "dxy": "달러인덱스", "wti": "WTI 원유",
             "usdkrw": "원/달러"}
    lines = ["| 지수 | 값 | 등락 | 기준 |", "|---|---|---|---|"]
    for k, label in names.items():
        v = (data.get("indices") or {}).get(k)
        if v is None:
            continue
        if v.get("error"):
            lines.append(f"| {label} | 조회 실패 | - | - |")
        else:
            lines.append(f"| {label} | {v.get('price', 0):,.2f} | {_pct(v.get('change_rate'))} | {v.get('source', '')} {v.get('as_of', '')} |")
    vix = (data.get("indices") or {}).get("vix") or {}
    if vix.get("price"):
        lines += ["", f"VIX {vix['price']:.1f} — " + ("⚠ 고위험 구간" if vix["price"] >= 30 else "경계 구간" if vix["price"] >= 20 else "안정 구간")]
    big = [b for b in data.get("bigtech") or [] if not b.get("error")]
    if big:
        lines += ["", "**빅테크**: " + " · ".join(
            f"{b['symbol']} ${b['price']:.2f} ({_pct(b['change_rate'])})"
            + (f" [{b['ext']['label']} {_pct(b['ext']['change_rate'])}]" if b.get("ext") else "") for b in big)]
    return "\n".join(lines)


async def _track() -> str:
    from app.services import prediction_log
    try:
        rv = await prediction_log.review(90, "ALL", "all", "all", 1)
    except Exception as e:
        return f"적중률 조회 실패: {e}"

    def fmt(a):
        n = a["hit"] + a["miss"]
        return f"{a['accuracy']}% ({a['hit']}/{n}건)" if n else "채점 없음"
    lines = [f"**최근 90일 예측 적중률: {fmt(rv['overall'])}** (실제 예측 + 과거 백테스트)", "",
             f"- 상승 예측: {fmt(rv['up_calls'])}", f"- 하락 예측: {fmt(rv['down_calls'])}",
             f"- 국내: {fmt(rv['by_market']['KR'])} / 미국: {fmt(rv['by_market']['US'])}",
             f"- 실제 예측: {fmt(rv['by_kind']['live'])} / 백테스트: {fmt(rv['by_kind']['backtest'])}"]
    ma = [m for m in rv.get("method_accuracy") or [] if m.get("n")]
    if ma:
        lines += ["", "**방식별 방향 적중률**"] + [f"- {m['label']}: {m.get('dir_accuracy')}% ({m['n']}건)" for m in ma]
    acc = rv["overall"]["accuracy"]
    if acc is not None:
        lines += ["", "50%에 가까우면 동전 던지기와 비슷하다는 뜻이라, 확률은 참고 수준으로만 보세요." if acc < 55
                  else "50%보다 확실히 높지만 하루 방향 예측이라 틀리는 날도 많습니다."]
    lines.append("자세한 내용은 **예측 검증** 메뉴에서 볼 수 있습니다.")
    return "\n".join(lines)


async def _events(q: str) -> str:
    from app.services import events
    m = re.search(r"(\d{1,2})\s*일", q)
    days = int(m.group(1)) if m else 30 if "달" in q else 7 if "주" in q else 14
    days = max(1, min(60, days))
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    out = []
    for i in range(days + 1):
        d = today + timedelta(days=i)
        for mk in ("KR", "US"):
            ox = events.option_expiry(mk, d)
            if ox:
                out.append((d.isoformat(), "국내" if mk == "KR" else "미국", ox))
    for e in events._cache["events"]:
        if today.isoformat() <= e["date"][:10] <= (today + timedelta(days=days)).isoformat():
            out.append((e["date"][:10], "미국", e["event"]))
    out.sort()
    note = events.status().get("error")
    if not out:
        return f"앞으로 {days}일 동안 등록된 변동성 이벤트가 없습니다." + (f"\n(미국 지표 일정 조회 문제: {note})" if note else "")
    lines = [f"**앞으로 {days}일 변동성 이벤트**", "", "| 날짜 | 시장 | 이벤트 |", "|---|---|---|"]
    lines += [f"| {d} | {mk} | {ev} |" for d, mk, ev in out]
    lines += ["", "이런 날은 가격이 크게 움직일 수 있어 예측이 더 자주 틀립니다."]
    if note:
        lines.append(f"(미국 지표 일정 조회 문제: {note})")
    return "\n".join(lines)


async def _theme(q: str, stock: dict | None) -> str:
    from app.services import themes
    from app.api.routes import themes as themes_route
    if stock:
        names = themes.themes_of(stock["symbol"])
        return (f"**{stock['name']}** 이 속한 테마: " + ", ".join(names)) if names else f"{stock['name']} 은 등록된 테마가 없습니다."
    data = themes.load()
    if not data:
        st = themes.status()
        return "테마 데이터가 아직 없습니다 — " + (st.get("error") or "서버 시작 후 몇 분 뒤 자동으로 받습니다.")
    # 질문 속 단어로 테마 찾기 ("로봇 테마" → 이름에 '로봇' 이 들어간 테마)
    words = [w for w in _tokens(q) if len(w) >= 2 and "테마" not in w and w not in _STOP]
    hits = [t for t in data["themes"] if any(w.lower() in t["name"].lower() for w in words)]
    if hits:
        t = hits[0]
        try:
            d = await themes_route._detail.get(t["no"], lambda: themes.detail(t["no"]))
        except Exception as e:
            return f"{t['name']} 테마 조회 실패: {e}"
        lines = [f"**{t['name']}** 테마 {len(d['items'])}종목 (오늘 등락률 순)"
                 + (f" · 비슷한 테마: {', '.join(h['name'] for h in hits[1:4])}" if len(hits) > 1 else ""), "",
                 "| 종목 | 현재가 | 등락률 | 매집 점수 |", "|---|---|---|---|"]
        for r in d["items"][:_count(q, 10)]:
            lines.append(f"| {r['name']} ({r['symbol']}) | {_px(r['price'], 'KR')} | {_pct(r['change_rate'])} | "
                         f"{r['accum_score'] if r['accum_score'] is not None else '-'} |")
        return "\n".join(lines)
    try:
        ov = await themes_route._overview.get("all", themes.overview)
    except Exception as e:
        return f"테마 조회 실패: {e}"
    lines = ["**오늘 많이 움직인 테마** (테마 종목 평균 등락률 순)", "", "| 테마 | 평균 | 상승/하락 | 주도주 |", "|---|---|---|---|"]
    for t in ov["themes"][:_count(q, 5)]:
        lead = ", ".join(f"{x['name']} {_pct(x['change_rate'])}" for x in t["leaders"][:2])
        lines.append(f"| {t['name']} | {_pct(t['avg_change'])} | {t['up']}/{t['down']} | {lead} |")
    lines += ["", "특정 테마는 \"로봇 테마\"처럼 물어보세요. 전체는 사이드바 **테마별 주식**에서 볼 수 있습니다."]
    return "\n".join(lines)


async def _accum(q: str, stock: dict | None) -> str:
    from app.services import accumulation
    r = accumulation.result()
    if not r:
        st = accumulation.status()
        return ("매집 탐지 결과가 아직 없습니다 — " +
                (f"전 종목 계산 중 ({st['done']}/{st['total']})" if st["running"] else "국내 장 마감 후 자동으로 계산합니다."))
    val = {v["min_score"]: v for v in r.get("validation", [])}
    base, v60 = val.get(0, {}), val.get(60, {})
    proof = (f"검증: 점수 60 이상일 때 20거래일 안 +20% 도달 **{v60.get('hit_rate')}%** "
             f"(전체 평균 {base.get('hit_rate')}%, {v60.get('n', 0):,}건)" if v60.get("n") else "검증 표본이 아직 부족합니다.")
    if stock:
        sc = r.get("scores", {}).get(stock["symbol"])
        c = next((x for x in r["candidates"] if x["symbol"] == stock["symbol"]), None)
        if sc is None:
            return f"{stock['name']} 은 매집 점수가 없습니다 (국내 일반 주식만, 상장 120거래일 이상)."
        lines = [f"**{stock['name']}** 매집 점수 **{sc}/100** ({r['base_date']} 종가 기준)"]
        if c:
            lines += [f"- {p['name']} {p['score']}/{p['max']}: {p['detail']}" for p in c["parts"]]
        return "\n".join(lines + ["", proof])
    cands = r["candidates"][:_count(q, 10)]
    if not cands:
        return f"{r['base_date']} 기준 매집 점수 50 이상 후보가 없습니다.\n\n{proof}"
    lines = [f"**매집·바닥 다지기 후보** ({r['base_date']} 종가 기준, {r['scanned']:,}종목 중)", "",
             "| 종목 | 점수 | 현재가 | 20일 | 주요 근거 |", "|---|---|---|---|---|"]
    for c in cands:
        top = sorted(c["parts"], key=lambda p: -p["score"] / p["max"])[:2]
        lines.append(f"| {c['name']} ({c['symbol']}) | {c['score']} | {_px(c['price'], 'KR')} | {_pct(c['ret20'])} | "
                     f"{' · '.join(p['detail'] for p in top)} |")
    lines += ["", proof, "급등을 보장하지 않습니다 — 몇 주~몇 달 횡보가 이어지거나 그대로 내려가는 경우도 많습니다."]
    return "\n".join(lines)


HELP = """이 챗봇은 앱 데이터를 조회해서 정해진 형식으로 답합니다. 이렇게 물어보세요:

- **종목 분석**: "삼성전자 어때?", "NVDA 사도 돼?", "005930"
- **매수 후보**: "오늘 국내 매수 추천 3개", "미국 오를 종목"
- **매도·주의 후보**: "하락할 종목", "팔아야 할 거 있어?" (보유 중이면 표시)
- **내 투자종목 점검**: "내 투자종목 어때?", "손익 알려줘"
- **관심종목**: "관심종목 보여줘"
- **시장 현황**: "오늘 시장 어때?", "환율", "VIX"
- **예측 적중률**: "적중률 알려줘"
- **이벤트 일정**: "이번 주 이벤트", "옵션 만기 언제야?"
- **테마**: "오늘 테마", "로봇 테마", "삼성전자 테마"
- **매집·바닥 다지기**: "매집 종목", "바닥 다지는 종목 5개", "휴림로봇 매집 점수"

조건: "국내/미국"으로 시장을, "3개"처럼 개수를 정할 수 있습니다."""

TOOL = {"stock": "analyze_stock", "buy": "today_picks", "sell": "today_picks", "portfolio": "my_portfolio",
        "watchlist": "my_watchlist", "market": "market_overview", "track": "track_record", "events": "upcoming_events",
        "theme": "themes", "accum": "accumulation"}


class ChatError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


async def chat(user, history: list) -> dict:
    """history: [{"role", "content"}] (마지막은 user) → {"reply", "tools", "model"}"""
    if not history or history[-1].get("role") != "user" or not (history[-1].get("content") or "").strip():
        raise ChatError(400, "마지막 메시지는 사용자 질문이어야 합니다")
    q = history[-1]["content"].strip()
    intent, stock = route(q)
    if intent == "stock":
        reply = await _stock(stock)
    elif intent in ("buy", "sell"):
        reply = await _picks(user, intent, q)
    elif intent == "portfolio":
        reply = await _portfolio(user)
    elif intent == "watchlist":
        reply = await _watchlist(user)
    elif intent == "market":
        reply = await _market(user)
    elif intent == "track":
        reply = await _track()
    elif intent == "events":
        reply = await _events(q)
    elif intent == "theme":
        reply = await _theme(q, stock)
    elif intent == "accum":
        reply = await _accum(q, stock)
    elif intent == "help":
        reply = HELP
    else:
        reply = "질문을 이해하지 못했습니다. 종목명은 정확히(예: 삼성전자, NVDA) 적어 주세요.\n\n" + HELP
    if intent in ("stock", "buy", "sell", "portfolio", "accum"):
        reply += DISCLAIMER
    return {"reply": reply, "tools": [TOOL[intent]] if intent in TOOL else [], "model": "규칙 기반"}
