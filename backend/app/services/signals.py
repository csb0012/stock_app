"""투자 신호 모음 — 투자 대가(13F)·가치·재무·수급(쌍끌이)을 한곳에서 AI 추천·종목 상세에 붙이고, 뒤에서 데이터를 채움

AI 장기 점수 반영 원칙 (검증된 것만 점수에, 나머지는 근거로만 표시):
- 투자 대가: 따라 사기 검증(공시 다음 날 사서 3개월, S&P500 대비)이 시장보다 나았을 때만 0~10점 (gurus.boost_points)
- 국내 가치·수익성·수급: 퀀트 점수에서 그 요인의 비중이 0보다 클 때만 (= 과거 20거래일 뒤 성과와 순위 상관이 양수로 검증됨)
  요인 백분위가 50에서 멀수록 ±최대 5점 × (그 요인 비중 ÷ 가장 큰 비중)
- 미국 가치(PER·PBR)는 이미 기존 장기 점수에 들어 있어 따로 더하지 않음
"""
import asyncio
import time
from datetime import datetime

from app.services import flows, fundamentals, gurus

_frames_cache = {"mtime": None, "closes": None}


def _quant() -> dict:
    from app.services import accumulation
    return (accumulation.result() or {}).get("quant") or {}


def liquid_universe() -> list:
    """퀀트 점수 대상(거래대금 1억↑) 국내 종목 — 수급·재무 수집 대상"""
    return list((_quant().get("scores") or {}).keys())


def kr_prices() -> tuple:
    """마지막 스캔 종가·20일 평균 거래대금 {종목: 값}"""
    sc = _quant().get("scores") or {}
    return {s: v.get("price") for s, v in sc.items()}, {s: v.get("tv20") for s, v in sc.items()}


def kr_closes() -> dict:
    """{종목: {날짜: 종가}} — 마지막 스캔의 요인 원값 파일에서 (바뀌었을 때만 다시 읽음)"""
    from app.services import accumulation
    try:
        mt = accumulation._FRAMES.stat().st_mtime
    except OSError:
        return {}
    if _frames_cache["mtime"] != mt:
        fr = accumulation.load_frames() or {}
        _frames_cache.update(mtime=mt, closes={s: dict(zip(f["date"], f["close"])) for s, f in fr.items()})
    return _frames_cache["closes"] or {}


def _kr_names(symbols) -> dict:
    from app.services import stock_master
    return {s: (stock_master.get("KR", s) or {}).get("name", s) for s in symbols}


# ---------------- 종목 1개 신호 (AI 추천·종목 상세) ----------------

def for_row(market: str, symbol: str, price: float | None = None) -> dict:
    """{guru, value, flow, score_parts, bonus} — 없는 신호는 None"""
    out = {"guru": None, "value": None, "flow": None}
    parts = []
    if market == "US":
        g = gurus.signal(symbol)
        out["guru"] = g
        if g:
            parts.append({"key": "guru", "label": "투자 대가", "points": g["points"],
                          "note": "따라 사기 검증 통과" if g["validated"] else "검증 미달 — 점수엔 안 넣고 참고만"})
    elif market == "KR":
        try:
            out["value"] = fundamentals.kr_now(symbol, price)
        except Exception:
            out["value"] = None
        s = flows.series(symbol)
        if s:
            _, tv = kr_prices()
            out["flow"] = flows.stock_signal(s, price, tv.get(symbol))
        q = _quant()
        mine = (q.get("scores") or {}).get(symbol) or {}
        w = q.get("weights") or {}
        wmax = max(w.values()) if w else 0
        for key, label in (("value", "가치(저PER·저PBR)"), ("quality", "수익성(ROE)"), ("flow", "수급(외국인+기관)")):
            p = (mine.get("factors") or {}).get(key)
            wk = w.get(key, 0) or 0
            if p is None:
                continue
            pts = round((p - 50) / 50 * 5 * (wk / wmax), 1) if wk > 0 and wmax > 0 else 0
            parts.append({"key": key, "label": label, "points": pts, "pct": p,
                          "note": f"퀀트 비중 {round(wk * 100)}%" if wk > 0 else "아직 검증 안 됨 — 점수엔 안 넣고 참고만"})
    bonus = round(sum(x["points"] for x in parts), 1)
    return {**out, "score_parts": parts, "bonus": bonus}


def apply_longterm(row: dict) -> dict:
    """AI 추천 행에 신호 붙이고 장기 점수 보정 (기존 점수는 long_term_base 로 남김)"""
    sig = for_row(row.get("market"), row.get("symbol"), row.get("price"))
    base = row.get("long_term_score") or 0
    return {**row, "signals": sig, "long_term_base": base,
            "long_term_score": int(max(0, min(100, round(base + sig["bonus"]))))}


# ---------------- 화면용 묶음 ----------------

def flow_overview(limit: int = 50) -> dict:
    prices, tv = kr_prices()
    rk = flows.rankings(prices, tv, None, limit)
    names = _kr_names({r["symbol"] for lst in rk["lists"].values() for r in lst})
    for lst in rk["lists"].values():
        for r in lst:
            r["name"] = names.get(r["symbol"], r["symbol"])
    daily = flows.market_daily(kr_closes())
    return {**rk, "daily": daily, "status": flows.status(), "universe": len(prices)}


def kr_value_rows() -> list:
    prices, _ = kr_prices()
    sc = _quant().get("scores") or {}
    extra = {s: {"quant_grade": v.get("grade"), "quant_score": v.get("score"),
                 "trend_pct": (v.get("factors") or {}).get("trend")} for s, v in sc.items()}
    rows = fundamentals.kr_table(prices, extra)
    for r in rows:
        s = flows.series(r["symbol"])
        if s:
            sig = flows.stock_signal(s, r.get("price"))
            r["flow_label"], r["flow_streak"] = sig.get("label"), sig.get("streak")
    return rows


# ---------------- 뒤에서 채우기 ----------------

_loop_status = {"last_fund": None, "last_flow_boot": None, "last_error": None}


def status() -> dict:
    return {**_loop_status, "fundamentals": fundamentals.status(), "flows": flows.status(), "gurus": gurus.status()}


async def _wait_scan():
    from app.services import accumulation
    while accumulation.status().get("running"):
        await asyncio.sleep(30)


async def tick():
    """재무(7일 지난 종목)·수급(처음 업데이트 직후 비어 있으면) 채우고 퀀트 다시 계산"""
    from app.services import accumulation
    from app.services.kis_api import mark_background
    await _wait_scan()
    uni = liquid_universe()
    if not uni:
        return
    changed = False
    st = await fundamentals.refresh_kr(uni)
    if st.get("total"):
        _loop_status["last_fund"] = datetime.now().isoformat(timespec="seconds") + " " + (st.get("message") or "")
        changed = True
    # 수급: 업데이트 직후 한 번 — 대상의 절반 넘게 비어 있으면 전 종목 수집 (평소엔 scheduler flow_kr 18:10)
    if flows.coverage(uni) < 0.5 and not flows.status().get("running"):
        mark_background()
        r = await flows.collect(uni)
        _loop_status["last_flow_boot"] = f"{datetime.now().isoformat(timespec='seconds')} {len(uni)}종목 · 새 날짜 {r['added']}건"
        changed = True
    if changed:
        await accumulation.rebuild_quant()


async def loop():
    """서버 시작 5분 뒤부터 30분마다 확인 (스캔 중이면 끝날 때까지 기다림)"""
    await asyncio.sleep(300)
    while True:
        try:
            await tick()
        except Exception as e:
            _loop_status["last_error"] = f"{time.strftime('%m-%d %H:%M')} {str(e)[:150]}"
            print(f"[signals] {e}")
        await asyncio.sleep(1800)
