"""국내 종목 투자자별 수급(외국인·기관·개인 순매수) — KIS 에서 받아 DB(investor_flow)에 쌓고 메모리에 보관

- KIS 주식현재가 투자자 API 는 최근 약 30거래일만 줌 → 처음엔 30일치, 이후 매일 장 마감 후(18:10~) 추가
- 대상: AI 추천 후보·관심·투자종목 + 거래대금 1억↑ 국내 전 종목(퀀트 점수 대상) — 쌍끌이·개미 동향·퀀트 '수급' 요인용
- 학습 모델의 수급 특징값(ml_model: frgn1·frgn5·orgn1·orgn5)과 AI 추천 카드의 "수급(5일)" 표시에도 사용
- 수집 실패는 부가 기능이라 로그 + status() 로 남기고, 수급 없는 모델로 예측 (가짜 값으로 채우지 않음)

쌍끌이 = 외국인과 기관이 같은 날 함께 순매수. 개미 = 개인 순매수.
금액(원)은 수량 × 그날 종가로 어림 (KIS 투자자 API 가 수량만 주는 종목이 있어 통일).
"""
import time

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.flow import InvestorFlow

_mem: dict = {}          # symbol -> {date: {"frgn_qty", "orgn_qty", "prsn_qty"}}
_status = {"loaded": 0, "last_collect": None, "collected": 0, "errors": [], "running": False, "done": 0, "total": 0}
KEYS = ("frgn_qty", "orgn_qty", "prsn_qty")
CHUNK = 100              # DB 저장 단위 (한 번에 오래 잠그지 않게)


def status() -> dict:
    return {**_status, "symbols": len(_mem), "rows": sum(len(v) for v in _mem.values())}


async def load_all():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(InvestorFlow))).scalars().all()
    for r in rows:
        _mem.setdefault(r.symbol, {})[r.date] = {"frgn_qty": r.frgn_qty, "orgn_qty": r.orgn_qty, "prsn_qty": r.prsn_qty}
    _status["loaded"] = len(rows)


async def _store(batch: dict) -> int:
    """{종목: [{date, frgn_qty, ...}]} → DB 에 한 번에 (이미 있는 날짜는 최신 값으로 덮어씀). 반환: 새 날짜 수"""
    if not batch:
        return 0
    added = 0
    async with AsyncSessionLocal() as db:
        have = {(r.symbol, r.date): r for r in (await db.execute(
            select(InvestorFlow).where(InvestorFlow.symbol.in_(list(batch))))).scalars().all()}
        for s, rows in batch.items():
            for r in rows:
                row = have.get((s, r["date"]))
                if row is None:
                    row = InvestorFlow(symbol=s, date=r["date"])
                    db.add(row)
                    have[(s, r["date"])] = row
                    added += 1
                row.frgn_qty, row.orgn_qty, row.prsn_qty = r["frgn_qty"], r["orgn_qty"], r["prsn_qty"]
                _mem.setdefault(s, {})[r["date"]] = {k: r[k] for k in KEYS}
        await db.commit()
    return added


async def collect(symbols: list) -> dict:
    """KIS 에서 최근 30일 수급을 받아 저장. 이미 수집 중이면 건너뜀"""
    from app.services.kis_api import kis_client  # 순환 import 방지
    if _status["running"]:
        return {"added": 0, "errors": ["이미 수집 중"], "skipped": True}
    symbols = list(dict.fromkeys(symbols))
    _status.update(running=True, done=0, total=len(symbols))
    added, errors, batch = 0, [], {}
    try:
        for s in symbols:
            try:
                batch[s] = await kis_client.get_kr_investor(s)
            except Exception as e:
                errors.append(f"{s}: {str(e)[:100]}")
            _status["done"] += 1
            if len(batch) >= CHUNK:
                added += await _store(batch)
                batch = {}
        added += await _store(batch)
    finally:
        _status.update(running=False, last_collect=time.strftime("%Y-%m-%d %H:%M"), collected=added, errors=errors[:10])
    if errors:
        print(f"[flows] 수급 수집 실패 {len(errors)}/{len(symbols)}건: {errors[0]}")
    return {"added": added, "errors": errors}


def series(symbol: str) -> dict:
    return _mem.get(symbol, {})


def summary(symbol: str, days: int = 5) -> dict | None:
    """화면용: 최근 N거래일 외국인·기관·개인 순매수 합계(주)"""
    s = _mem.get(symbol)
    if not s:
        return None
    dates = sorted(s)[-days:]
    tot = {k: sum((s[d].get(k) or 0) for d in dates) for k in KEYS}
    return {"days": len(dates), "from": dates[0], "to": dates[-1], **tot}


def coverage(symbols: list) -> float:
    """대상 종목 중 수급이 쌓여 있는 비율 (처음 업데이트 직후 전 종목 수집이 필요한지 판단)"""
    return sum(1 for s in symbols if _mem.get(s)) / len(symbols) if symbols else 1.0


# ---------------- 쌍끌이·개미 (순수 계산) ----------------

def stock_signal(s: dict, price: float | None, tv20: float | None = None) -> dict | None:
    """종목 1개 수급 신호: 쌍끌이 연속 일수·5일 순매수 금액·설명. s = {date: {frgn_qty, orgn_qty, prsn_qty}}"""
    if not s:
        return None
    dates = sorted(s)
    last = s[dates[-1]]
    streak = 0
    for d in reversed(dates):
        v = s[d]
        if (v.get("frgn_qty") or 0) > 0 and (v.get("orgn_qty") or 0) > 0:
            streak += 1
        else:
            break
    sell_streak = 0
    for d in reversed(dates):
        v = s[d]
        if (v.get("frgn_qty") or 0) < 0 and (v.get("orgn_qty") or 0) < 0:
            sell_streak += 1
        else:
            break
    d5 = dates[-5:]
    q5 = {k: sum((s[d].get(k) or 0) for d in d5) for k in KEYS}
    px = price or 0
    amt5 = {k.replace("_qty", "_amt5"): round(q5[k] * px) for k in KEYS}
    amt1 = {k.replace("_qty", "_amt1"): round((last.get(k) or 0) * px) for k in KEYS}
    smart = q5["frgn_qty"] + q5["orgn_qty"]
    intensity = round(smart * px / (tv20 * 5) * 100, 2) if tv20 and px else None   # 5일 외국인+기관 순매수 ÷ 5일 거래대금 (%)
    if streak >= 2:
        label = f"쌍끌이 {streak}일 연속"
    elif streak == 1:
        label = "외국인·기관 동반 순매수"
    elif sell_streak >= 2:
        label = f"외국인·기관 동반 순매도 {sell_streak}일"
    elif q5["prsn_qty"] > 0 and smart < 0:
        label = "개인만 순매수 (외국인·기관 순매도)"
    elif q5["prsn_qty"] < 0 and smart > 0:
        label = "외국인·기관 순매수 · 개인 순매도"
    else:
        label = None
    return {"date": dates[-1], "days": len(d5), "streak": streak, "sell_streak": sell_streak, "label": label,
            **{k.replace("_qty", "5"): q5[k] for k in KEYS}, **amt5, **amt1, "intensity": intensity, "price": price}


def rankings(prices: dict, tv20: dict | None = None, names: dict | None = None, limit: int = 50) -> dict:
    """전 종목 수급 순위. prices: {종목: 종가} (가격 없는 종목은 금액을 못 구해 뺌). 마지막 날짜가 가장 흔한 날짜인 종목만"""
    names, tv20 = names or {}, tv20 or {}
    sig = {}
    for sym, s in _mem.items():
        p = prices.get(sym)
        if not s or not p:
            continue
        sig[sym] = stock_signal(s, p, tv20.get(sym))
    if not sig:
        return {"date": None, "lists": {}, "n": 0}
    latest = pd.Series([v["date"] for v in sig.values()]).mode().iloc[0]
    rows = [{"symbol": k, "name": names.get(k, k), **v} for k, v in sig.items() if v["date"] == latest]

    def top(key, cond=lambda r: True, rev=True):
        return sorted([r for r in rows if cond(r)], key=lambda r: r[key], reverse=rev)[:limit]

    lists = {
        "double": sorted([r for r in rows if r["streak"] >= 1],
                         key=lambda r: (-r["streak"], -(r["frgn_amt1"] + r["orgn_amt1"])))[:limit],
        "foreign": top("frgn_amt5", lambda r: r["frgn_amt5"] > 0),
        "institution": top("orgn_amt5", lambda r: r["orgn_amt5"] > 0),
        "retail_buy": top("prsn_amt5", lambda r: r["prsn_amt5"] > 0),
        "retail_sell": top("prsn_amt5", lambda r: r["prsn_amt5"] < 0, rev=False),
        "double_sell": sorted([r for r in rows if r["sell_streak"] >= 2],
                              key=lambda r: (-r["sell_streak"], r["frgn_amt1"] + r["orgn_amt1"]))[:limit],
    }
    return {"date": latest, "n": len(rows), "lists": lists}


def market_daily(closes: dict, days: int = 20) -> list:
    """수집한 종목 합계: 날짜별 외국인·기관·개인 순매수 금액(원 어림) — 개미 투자 동향.
    closes: {종목: {날짜: 종가}} (그날 종가가 없는 종목은 그날 합계에서 뺌)"""
    agg: dict = {}
    for sym, s in _mem.items():
        c = closes.get(sym) or {}
        for d, v in s.items():
            px = c.get(d)
            if not px:
                continue
            a = agg.setdefault(d, {"date": d, "frgn": 0.0, "orgn": 0.0, "prsn": 0.0, "n": 0, "double": 0})
            a["frgn"] += (v.get("frgn_qty") or 0) * px
            a["orgn"] += (v.get("orgn_qty") or 0) * px
            a["prsn"] += (v.get("prsn_qty") or 0) * px
            a["n"] += 1
            a["double"] += int((v.get("frgn_qty") or 0) > 0 and (v.get("orgn_qty") or 0) > 0)
    out = sorted(agg.values(), key=lambda a: a["date"])
    if out:   # 종목 수가 적은 날(수집 시작 전 날짜 등)은 빼서 합계가 들쭉날쭉하지 않게
        mx = max(a["n"] for a in out)
        out = [a for a in out if a["n"] >= mx * 0.5]
    return [{**a, **{k: round(a[k]) for k in ("frgn", "orgn", "prsn")}} for a in out[-days:]]


def factor_frame(frames: dict) -> pd.DataFrame | None:
    """퀀트 '수급' 요인: 그 전날까지 5거래일 외국인+기관 순매수 금액 ÷ 20일 평균 거래대금×5.
    전날까지만 쓰는 이유: 수급 확정치는 저녁에 나와서 장 마감 직후 점수엔 그날 값이 없음 (과거·오늘을 같은 기준으로)"""
    parts = []
    for sym, f in frames.items():
        s = _mem.get(sym)
        if not s or f is None or f.empty:
            continue
        fl = pd.DataFrame([{"date": d, "q": (v.get("frgn_qty") or 0) + (v.get("orgn_qty") or 0)} for d, v in s.items()])
        fl = fl.sort_values("date")
        g = f[["date", "close", "tv20"]].merge(fl, on="date", how="left")
        have = g["q"].notna()
        q5 = g["q"].rolling(5, min_periods=5).sum().shift(1)          # 전날까지 5거래일
        ok5 = have.astype(float).rolling(5, min_periods=5).sum().shift(1) == 5
        val = (q5 * g["close"]) / (g["tv20"] * 5)
        parts.append(pd.DataFrame({"date": g["date"], "symbol": sym, "flow": val.where(ok5)}))
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    return df.replace([np.inf, -np.inf], np.nan)


# ---------------- '개인만 순매수' 종목이 실제로 약했나 (감점 여부 — 사용자 결정 2026-11-26: 과거 사례로 판단) ----------------
RETAIL_HORIZON = 20
RETAIL_MIN_N, RETAIL_MIN_DATES = 300, 10
RETAIL_MAX_EXCESS, RETAIL_MAX_BEAT = -0.5, 47.0     # 이보다 나빠야 '약했다' (평균 초과수익 %p, 이긴 비율 %)
RETAIL_PENALTY = 5                                  # AI 점수 감점


def _is_retail_only(q5: dict) -> bool:
    return q5["prsn_qty"] > 0 and q5["frgn_qty"] + q5["orgn_qty"] < 0


def retail_check(closes: dict, horizon: int = RETAIL_HORIZON) -> dict:
    """그날(d)까지 5거래일 '개인만 순매수(외국인+기관은 순매도)' 종목 vs 나머지 — d 다음 거래일 종가에 사서 horizon 거래일 뒤,
    같은 날 수급이 있는 전 종목 중간값 대비 초과수익. 수급 확정치는 저녁에 나오므로 그날 종가가 아니라 다음 날 종가부터 셈 (미래 데이터 미사용).
    closes: {종목: {날짜: 종가}} → {retail{n, beat_rate, avg_excess}, double(쌍끌이 2일↑ 참고), dates, active(감점할지)}"""
    rows = []
    for sym, s in _mem.items():
        c = closes.get(sym) or {}
        cd = sorted(c)
        if len(cd) <= horizon + 1:
            continue
        pos = {d: i for i, d in enumerate(cd)}
        fd = sorted(s)
        for j in range(4, len(fd)):
            d = fd[j]
            if d not in pos:
                continue
            i = pos[d]
            if i + 1 + horizon >= len(cd):
                continue
            win = fd[j - 4: j + 1]
            q5 = {k: sum((s[x].get(k) or 0) for x in win) for k in KEYS}
            streak = 0
            for x in reversed(fd[: j + 1]):
                v = s[x]
                if (v.get("frgn_qty") or 0) > 0 and (v.get("orgn_qty") or 0) > 0:
                    streak += 1
                else:
                    break
            p0, p1 = c[cd[i + 1]], c[cd[i + 1 + horizon]]
            if p0 and p1:
                rows.append((d, sym, p1 / p0 - 1, _is_retail_only(q5), streak >= 2))
    if not rows:
        return {"retail": {"n": 0}, "double": {"n": 0}, "dates": 0, "active": False, "horizon": horizon,
                "rule": "개인 5일 순매수 > 0 이고 외국인+기관 5일 순매수 < 0"}
    df = pd.DataFrame(rows, columns=["date", "symbol", "ret", "retail", "double"])
    df["excess"] = df["ret"] - df.groupby("date")["ret"].transform("median")

    def st(g):
        n = int(len(g))
        return {"n": n, "beat_rate": round(float((g["excess"] > 0).mean()) * 100, 1) if n else None,
                "avg_excess": round(float(g["excess"].mean()) * 100, 2) if n else None}
    r, dbl = st(df[df["retail"]]), st(df[df["double"]])
    dates = int(df[df["retail"]]["date"].nunique())
    active = bool(r["n"] >= RETAIL_MIN_N and dates >= RETAIL_MIN_DATES and r["avg_excess"] is not None
                  and r["avg_excess"] <= RETAIL_MAX_EXCESS and r["beat_rate"] <= RETAIL_MAX_BEAT)
    return {"retail": r, "double": dbl, "others": st(df[~df["retail"]]), "dates": dates, "active": active,
            "horizon": horizon, "penalty": RETAIL_PENALTY,
            "rule": "개인 5일 순매수 > 0 이고 외국인+기관 5일 순매수 < 0",
            "need": f"표본 {RETAIL_MIN_N}↑·날짜 {RETAIL_MIN_DATES}↑·평균 초과 {RETAIL_MAX_EXCESS}%p 이하·이긴 비율 {RETAIL_MAX_BEAT}% 이하"}


def retail_only_now() -> set:
    """지금(마지막 수집일까지 5거래일) 개인만 순매수인 종목"""
    out = set()
    for sym, s in _mem.items():
        fd = sorted(s)[-5:]
        if len(fd) == 5 and _is_retail_only({k: sum((s[x].get(k) or 0) for x in fd) for k in KEYS}):
            out.add(sym)
    return out
