"""예측 기록·채점·복기

1) record(): 분석 결과의 상승 확률을 (종목, 예측 대상일) 단위로 저장. 대상일 전까지는 최신 값으로 덮어씀
2) evaluate_pending(): 대상일 장이 끝난 기록을 실제 등락과 비교해 채점하고, 맞은/틀린 이유를 찾음
3) review(): 적중률 통계 + 기록 목록
"""
import asyncio
import json
from datetime import date, datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.prediction import PredictionLog, BacktestLog
from app.services import stock_master
from app.services.market_calendar import market_today, is_market_open, _after_close

UP_TH, DOWN_TH = 55, 45

# AI 추천(15초 갱신)·투자종목·관심종목이 동시에 같은 종목을 기록하면 UNIQUE 충돌/SQLite 잠금이 나므로 직렬화
_record_lock = asyncio.Lock()  # 이 이상이면 '상승 예측', 이 이하면 '하락 예측', 사이는 중립(채점 제외)

_INDEX = {"KOSPI": ("^KS11", "코스피"), "KOSDAQ": ("^KQ11", "코스닥"), "US": ("^GSPC", "S&P500")}


def direction(prob: int) -> str:
    return "up" if prob >= UP_TH else "down" if prob <= DOWN_TH else "neutral"


async def record(results: list, source: str):
    """results: quote 분석 결과 목록 (error 항목은 건너뜀)

    예측 기록은 부가 기능이라, 저장이 실패해도 시세 화면 응답은 그대로 내보내고 로그만 남긴다.
    """
    rows = [r for r in results if r and "error" not in r and r.get("prediction", {}).get("target_date")]
    if not rows:
        return
    try:
        async with _record_lock:
            await _record(rows, source)
    except Exception as e:
        print(f"[prediction] 예측 기록 실패 ({source}): {e}")


async def _record(rows: list, source: str):
    async with AsyncSessionLocal() as db:
        for r in rows:
            p = r["prediction"]
            existing = (await db.execute(select(PredictionLog).where(
                PredictionLog.market == r["market"], PredictionLog.symbol == r["symbol"],
                PredictionLog.target_date == p["target_date"],
            ))).scalar_one_or_none()
            if existing and existing.evaluated:
                continue
            if existing is None:
                existing = PredictionLog(market=r["market"], symbol=r["symbol"], target_date=p["target_date"], sources="")
                db.add(existing)
            srcs = set(filter(None, (existing.sources or "").split(",")))
            srcs.add(source)
            existing.sources = ",".join(sorted(srcs))
            existing.name = r.get("name")
            existing.base_date = p["base_date"]
            existing.base_price = float(r["price"])
            existing.probability = int(p["probability"])
            existing.signal = p.get("signal")
            existing.summary = p.get("summary")
            existing.factors = json.dumps(p.get("factors", []), ensure_ascii=False)
        await db.commit()


def _ready(market: str, target_date: str) -> bool:
    """대상일 장이 끝났는지"""
    today = market_today(market).isoformat()
    if target_date < today:
        return True
    return target_date == today and not is_market_open(market) and _after_close(market)


def _reasons(log: PredictionLog, change: float, gap: float | None, vol_ratio: float | None,
             idx_name: str | None, idx_change: float | None, hit: bool, pred_dir: str,
             news: dict | None = None) -> list:
    out = []
    moved_up = change > 0
    factors = json.loads(log.factors or "[]")
    ups = [f["short"] for f in factors if f["impact"] == "up"]
    downs = [f["short"] for f in factors if f["impact"] == "down"]

    if idx_change is not None and abs(idx_change) >= 0.7 and (idx_change > 0) == moved_up:
        out.append(f"시장 전체가 {'올라' if idx_change > 0 else '빠져'} 같이 움직임 ({idx_name} {idx_change:+.2f}%)")
    elif idx_change is not None and abs(idx_change) >= 0.7:
        out.append(f"시장({idx_name} {idx_change:+.2f}%)과 반대로 움직임 — 종목 자체 이슈 가능성")
    if gap is not None and abs(gap) >= 1.5:
        txt = f"시가부터 {gap:+.1f}% 갭{'상승' if gap > 0 else '하락'} 출발 — 장 시작 전 뉴스·해외시장 영향"
        if (gap > 0) != moved_up:
            txt += ", 장중 반전"
        out.append(txt)
    if vol_ratio is not None and vol_ratio >= 2:
        out.append(f"거래량이 평소의 {vol_ratio:.1f}배 — 재료·수급 이벤트 발생")
    if abs(change) >= 5:
        out.append(f"변동폭 {change:+.1f}% — 기술적 지표로 잡기 어려운 이벤트성 움직임")
    # 대상일(또는 전날) 뉴스 중 실제 움직임과 같은 방향의 기사
    if news and news.get("headlines"):
        want = "pos" if moved_up else "neg"
        days = {log.target_date, log.base_date}
        hits = [h for h in news["headlines"]
                if h.get("tone") == want and h.get("date", "")[:10].replace(".", "-") in days]
        for h in hits[:2]:
            out.append(f"{'호재' if want == 'pos' else '악재'} 뉴스: {h['title'][:60]}")

    if not hit and pred_dir == "up" and ups:
        out.append(f"상승 근거였던 {', '.join(ups)} 신호가 이번엔 통하지 않음")
    if not hit and pred_dir == "down" and downs:
        out.append(f"하락 근거였던 {', '.join(downs)} 신호가 이번엔 통하지 않음")
    if hit:
        key = ups if pred_dir == "up" else downs
        if key:
            out.insert(0, f"예측 근거({', '.join(key)})대로 움직임")
    if not out:
        out.append("뚜렷한 외부 요인 없이 소폭 움직임 (일반적인 등락 범위)" if abs(change) < 1
                   else "뚜렷한 외부 요인을 찾지 못함")
    return out


def index_key(market: str, symbol: str) -> str:
    if market == "US":
        return "US"
    m = stock_master.get("KR", symbol) or {}
    return "KOSDAQ" if m.get("exchange") == "KOSDAQ" else "KOSPI"


def index_change_fn(idx_hist: dict):
    """{지수티커: 일봉} → (지수키, 날짜) 의 지수 등락률(%) 조회 함수"""
    def f(key: str, date: str):
        cs = idx_hist.get(_INDEX[key][0], [])
        for i, c in enumerate(cs):
            if c["date"][:10] == date and i > 0:
                return round((c["close"] / cs[i - 1]["close"] - 1) * 100, 2)
        return None
    return f


def measure(candles: list, ti: int) -> tuple:
    """대상일(candles[ti]) 등락률·시가 갭·20일 평균 대비 거래량 배수"""
    t, prev = candles[ti], candles[ti - 1]
    change = round((t["close"] / prev["close"] - 1) * 100, 2)
    gap = round((t["open"] / prev["close"] - 1) * 100, 2) if t.get("open") else None
    vols = [c["volume"] for c in candles[max(0, ti - 20):ti] if c["volume"]]
    vol_ratio = round(t["volume"] / (sum(vols) / len(vols)), 2) if vols and t["volume"] else None
    return change, gap, vol_ratio


def grade(log, candles: list, ti: int, idx_change, news: dict | None = None):
    """log(PredictionLog/BacktestLog)에 대상일 실제 결과·적중 여부·이유를 채움"""
    change, gap, vol_ratio = measure(candles, ti)
    key = index_key(log.market, log.symbol)
    ic = idx_change(key, log.target_date)
    pred_dir = direction(log.probability)
    if pred_dir == "neutral":
        hit, outcome = False, "neutral"
    else:
        hit = (change > 0) if pred_dir == "up" else (change < 0)
        outcome = "hit" if hit else "miss"
    log.actual_close = candles[ti]["close"]
    log.actual_change = change
    log.gap_pct = gap
    log.volume_ratio = vol_ratio
    log.index_name = _INDEX[key][1]
    log.index_change = ic
    log.outcome = outcome
    log.review = json.dumps(_reasons(log, change, gap, vol_ratio, _INDEX[key][1], ic, hit, pred_dir, news),
                            ensure_ascii=False)
    log.evaluated = True
    log.evaluated_at = datetime.now()


async def evaluate_pending() -> int:
    # 순환 import 방지
    from app.services.quote import kr_chart, batch_yf_history
    from app.services.news import get_news_tone

    async with AsyncSessionLocal() as db:
        pending = (await db.execute(select(PredictionLog).where(PredictionLog.evaluated == False))).scalars().all()  # noqa: E712
        pending = [p for p in pending if _ready(p.market, p.target_date)]
        if not pending:
            return 0

        idx_hist = await batch_yf_history([v[0] for v in _INDEX.values()], "3mo")
        us_syms = sorted({p.symbol for p in pending if p.market == "US"})
        us_hist = await batch_yf_history(us_syms, "3mo") if us_syms else {}

        idx_change = index_change_fn(idx_hist)

        done = 0
        for log in pending:
            try:
                candles = (await kr_chart(log.symbol, 100))["candles"] if log.market == "KR" else us_hist.get(log.symbol, [])
            except Exception:
                continue  # 조회 실패 시 다음에 다시 채점
            ti = next((i for i, c in enumerate(candles) if c["date"][:10] == log.target_date), None)
            if ti is None or ti == 0:
                if log.target_date < market_today(log.market).isoformat():
                    log.evaluated, log.outcome = True, "no_data"
                    log.review = json.dumps(["대상일 시세 없음 (거래정지 등)"], ensure_ascii=False)
                    log.evaluated_at = datetime.now()
                    done += 1
                continue
            news = await get_news_tone(log.market, log.symbol) if direction(log.probability) != "neutral" else None
            grade(log, candles, ti, idx_change, news)
            done += 1
        await db.commit()
        return done


def _acc(rows: list) -> dict:
    hit = sum(1 for r in rows if r["outcome"] == "hit")
    miss = sum(1 for r in rows if r["outcome"] == "miss")
    return {"hit": hit, "miss": miss, "accuracy": round(hit / (hit + miss) * 100, 1) if hit + miss else None}


def _row(l, kind: str) -> dict:
    return {
        "id": f"{kind[0]}{l.id}", "kind": kind, "market": l.market, "symbol": l.symbol, "name": l.name,
        "sources": l.sources, "base_date": l.base_date, "target_date": l.target_date, "base_price": l.base_price,
        "probability": l.probability, "direction": direction(l.probability), "signal": l.signal,
        "summary": l.summary, "factors": json.loads(l.factors or "[]"),
        "evaluated": l.evaluated, "outcome": l.outcome, "actual_close": l.actual_close,
        "actual_change": l.actual_change, "gap_pct": l.gap_pct, "volume_ratio": l.volume_ratio,
        "index_name": l.index_name, "index_change": l.index_change,
        "review": json.loads(l.review or "[]"),
    }


async def review(days: int = 30, market: str = "ALL", kind: str = "all", outcome: str = "all",
                 limit: int = 200) -> dict:
    """적중률 통계 + 기록 목록

    kind: live = 실제로 화면에서 낸 예측만 / backtest = 과거 백테스트만 /
          all = 둘 다 (같은 종목·대상일이면 실제 예측 우선)
    outcome: all / hit / miss / pending — 목록만 거름 (통계는 전체 기준)
    """
    cutoff = date.fromordinal(datetime.now().date().toordinal() - days).isoformat()
    rows: dict = {}
    async with AsyncSessionLocal() as db:
        for model, k in ((BacktestLog, "backtest"), (PredictionLog, "live")):
            if kind not in ("all", k):
                continue
            q = select(model).where(model.target_date >= cutoff)
            if market != "ALL":
                q = q.where(model.market == market)
            for l in (await db.execute(q)).scalars().all():
                rows[(l.market, l.symbol, l.target_date)] = _row(l, k)  # live 가 나중에 덮어씀
    rows = sorted(rows.values(), key=lambda r: (r["target_date"], r["probability"]), reverse=True)

    scored = [r for r in rows if r["outcome"] in ("hit", "miss")]
    buckets = []
    for lo, hi, label in [(15, 35, "15~34%"), (35, 45, "35~44%"), (45, 55, "45~54%"), (55, 65, "55~64%"), (65, 86, "65~85%")]:
        b = [r for r in rows if r["evaluated"] and r["actual_change"] is not None and lo <= r["probability"] < hi]
        ups = sum(1 for r in b if r["actual_change"] > 0)
        buckets.append({
            "label": label, "count": len(b),
            "avg_prob": round(sum(r["probability"] for r in b) / len(b), 1) if b else None,
            "actual_up_rate": round(ups / len(b) * 100, 1) if b else None,
        })

    # 요인별 적중률 — 어떤 지표가 실제로 잘 맞는지 (상승 신호였을 때 실제 상승 비율, 하락 신호였을 때 실제 하락 비율)
    fstats: dict = {}
    for r in rows:
        if not r["evaluated"] or r["actual_change"] is None:
            continue
        for f in r["factors"]:
            name = f.get("name") or f.get("short")
            if not name or f.get("impact") not in ("up", "down"):
                continue
            st = fstats.setdefault(name, {"name": name, "up_n": 0, "up_hit": 0, "down_n": 0, "down_hit": 0})
            if f["impact"] == "up":
                st["up_n"] += 1
                st["up_hit"] += r["actual_change"] > 0
            else:
                st["down_n"] += 1
                st["down_hit"] += r["actual_change"] < 0
    factor_accuracy = []
    for st in fstats.values():
        st["up_rate"] = round(st["up_hit"] / st["up_n"] * 100, 1) if st["up_n"] else None
        st["down_rate"] = round(st["down_hit"] / st["down_n"] * 100, 1) if st["down_n"] else None
        factor_accuracy.append(st)
    factor_accuracy.sort(key=lambda x: -(x["up_n"] + x["down_n"]))

    # 날짜별 적중률
    by_date = {}
    for r in scored:
        by_date.setdefault(r["target_date"], []).append(r)
    daily = [{"date": d, **_acc(v)} for d, v in sorted(by_date.items())]

    # 종목별 적중률 (채점 5건 이상)
    by_sym: dict = {}
    for r in scored:
        by_sym.setdefault((r["market"], r["symbol"]), []).append(r)
    by_symbol = [{"market": m, "symbol": s, "name": v[0]["name"], **_acc(v)}
                 for (m, s), v in by_sym.items() if len(v) >= 5]
    by_symbol.sort(key=lambda x: (-(x["accuracy"] or 0), -(x["hit"] + x["miss"])))

    def match(r):
        return (outcome == "all" or (outcome == "pending" and not r["evaluated"])
                or r["outcome"] == outcome)

    counts = {
        "all": len(rows),
        "hit": sum(1 for r in rows if r["outcome"] == "hit"),
        "miss": sum(1 for r in rows if r["outcome"] == "miss"),
        "pending": sum(1 for r in rows if not r["evaluated"]),
    }
    listed = [r for r in rows if match(r)]
    items = []
    for r in listed[:limit]:
        r = dict(r)
        r.pop("factors")  # 목록에선 안 씀 (응답 크기 줄임)
        items.append(r)

    return {
        "overall": _acc(scored),
        "up_calls": _acc([r for r in scored if r["direction"] == "up"]),
        "down_calls": _acc([r for r in scored if r["direction"] == "down"]),
        "by_market": {m: _acc([r for r in scored if r["market"] == m]) for m in ("KR", "US")},
        "by_kind": {k: _acc([r for r in scored if r["kind"] == k]) for k in ("live", "backtest")},
        "neutral_count": sum(1 for r in rows if r["outcome"] == "neutral"),
        "pending_count": counts["pending"],
        "calibration": buckets,
        "factor_accuracy": factor_accuracy,
        "by_symbol": by_symbol,
        "daily": daily,
        "counts": counts,
        "items": items,
        "items_total": len(listed),
        "thresholds": {"up": UP_TH, "down": DOWN_TH},
    }
