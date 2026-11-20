"""예측 기록·채점·복기

1) record(): 분석 결과의 상승 확률을 (종목, 예측 대상일) 단위로 저장. 대상일 전까지는 최신 값으로 덮어씀
2) evaluate_pending(): 대상일 장이 끝난 기록을 실제 등락과 비교해 채점하고, 맞은/틀린 이유를 찾음
3) review(): 적중률 통계 + 기록 목록
"""
import json
from datetime import datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.prediction import PredictionLog
from app.services import stock_master
from app.services.market_calendar import market_today, is_market_open, _after_close

UP_TH, DOWN_TH = 55, 45  # 이 이상이면 '상승 예측', 이 이하면 '하락 예측', 사이는 중립(채점 제외)

_INDEX = {"KOSPI": ("^KS11", "코스피"), "KOSDAQ": ("^KQ11", "코스닥"), "US": ("^GSPC", "S&P500")}


def direction(prob: int) -> str:
    return "up" if prob >= UP_TH else "down" if prob <= DOWN_TH else "neutral"


async def record(results: list, source: str):
    """results: quote 분석 결과 목록 (error 항목은 건너뜀)"""
    rows = [r for r in results if r and "error" not in r and r.get("prediction", {}).get("target_date")]
    if not rows:
        return
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


def _index_key(log: PredictionLog) -> str:
    if log.market == "US":
        return "US"
    m = stock_master.get("KR", log.symbol) or {}
    return "KOSDAQ" if m.get("exchange") == "KOSDAQ" else "KOSPI"


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

        def idx_change(key: str, date: str):
            cs = idx_hist.get(_INDEX[key][0], [])
            for i, c in enumerate(cs):
                if c["date"][:10] == date and i > 0:
                    return round((c["close"] / cs[i - 1]["close"] - 1) * 100, 2)
            return None

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
            t, prev = candles[ti], candles[ti - 1]
            change = round((t["close"] / prev["close"] - 1) * 100, 2)
            gap = round((t["open"] / prev["close"] - 1) * 100, 2) if t.get("open") else None
            vols = [c["volume"] for c in candles[max(0, ti - 20):ti] if c["volume"]]
            vol_ratio = round(t["volume"] / (sum(vols) / len(vols)), 2) if vols and t["volume"] else None
            key = _index_key(log)
            ic = idx_change(key, log.target_date)

            pred_dir = direction(log.probability)
            if pred_dir == "neutral":
                hit, outcome = False, "neutral"
            else:
                hit = (change > 0) if pred_dir == "up" else (change < 0)
                outcome = "hit" if hit else "miss"

            log.actual_close = t["close"]
            log.actual_change = change
            log.gap_pct = gap
            log.volume_ratio = vol_ratio
            log.index_name = _INDEX[key][1]
            log.index_change = ic
            log.outcome = outcome
            news = await get_news_tone(log.market, log.symbol) if outcome != "neutral" else None
            log.review = json.dumps(_reasons(log, change, gap, vol_ratio, _INDEX[key][1], ic, hit, pred_dir, news),
                                    ensure_ascii=False)
            log.evaluated = True
            log.evaluated_at = datetime.now()
            done += 1
        await db.commit()
        return done


def _acc(rows: list) -> dict:
    hit = sum(1 for r in rows if r["outcome"] == "hit")
    miss = sum(1 for r in rows if r["outcome"] == "miss")
    return {"hit": hit, "miss": miss, "accuracy": round(hit / (hit + miss) * 100, 1) if hit + miss else None}


async def review(days: int = 30, market: str = "ALL") -> dict:
    async with AsyncSessionLocal() as db:
        q = select(PredictionLog).order_by(PredictionLog.target_date.desc(), PredictionLog.probability.desc())
        logs = (await db.execute(q)).scalars().all()

    cutoff = (datetime.now().date().toordinal() - days)
    rows = []
    for l in logs:
        if market != "ALL" and l.market != market:
            continue
        if datetime.fromisoformat(l.target_date).date().toordinal() < cutoff:
            continue
        rows.append({
            "id": l.id, "market": l.market, "symbol": l.symbol, "name": l.name, "sources": l.sources,
            "base_date": l.base_date, "target_date": l.target_date, "base_price": l.base_price,
            "probability": l.probability, "direction": direction(l.probability), "signal": l.signal,
            "summary": l.summary, "factors": json.loads(l.factors or "[]"),
            "evaluated": l.evaluated, "outcome": l.outcome, "actual_close": l.actual_close,
            "actual_change": l.actual_change, "gap_pct": l.gap_pct, "volume_ratio": l.volume_ratio,
            "index_name": l.index_name, "index_change": l.index_change,
            "review": json.loads(l.review or "[]"),
        })

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

    # 날짜별 적중률
    by_date = {}
    for r in scored:
        by_date.setdefault(r["target_date"], []).append(r)
    daily = [{"date": d, **_acc(v)} for d, v in sorted(by_date.items())]

    return {
        "overall": _acc(scored),
        "up_calls": _acc([r for r in scored if r["direction"] == "up"]),
        "down_calls": _acc([r for r in scored if r["direction"] == "down"]),
        "by_market": {m: _acc([r for r in scored if r["market"] == m]) for m in ("KR", "US")},
        "neutral_count": sum(1 for r in rows if r["outcome"] == "neutral"),
        "pending_count": sum(1 for r in rows if not r["evaluated"]),
        "calibration": buckets,
        "daily": daily,
        "items": rows,
        "thresholds": {"up": UP_TH, "down": DOWN_TH},
    }
