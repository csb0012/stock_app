"""예측 검증 결과로 지표 비중 조정 — 과거에 잘 안 맞은 지표(RSI·MACD·볼린저·이평)의 비중을 줄임.

- 자료: 과거 1년 백테스트 기록(prediction_backtest — 그날 전까지의 데이터로만 예측하고 다음 날 실제 등락으로 채점)의 지표별 점수
- 지표 적중률 = 그 지표가 '상승 신호'(점수 60%↑)일 때 실제 상승 비율과 '하락 신호'(30%↓)일 때 실제 하락 비율의 평균
  (시장이 많이 오른 해엔 상승 신호가 저절로 잘 맞으므로 두 쪽을 평균 — 한쪽만 보면 속음)
- 비중: 적중률 51% 이상이면 그대로(1배), 46% 이하면 0.3배, 그 사이는 비례. **줄이기만 하고 늘리지 않음** (짧은 기록에 과하게 맞추지 않게)
  신호가 MIN_N 건보다 적은 지표는 그대로
- 채택 검증(walk-forward): 날짜마다 '그 전날까지 결과가 나온 기록'만으로 비중을 정해 그날 확률을 다시 계산 →
  원래 비중 확률과 같은 기록에서 방향 적중률 비교. 조정이 MIN_GAIN %p 이상 나을 때만 실시간 예측에 씀 (아니면 원래 비중 그대로)
- 실시간 예측(quote.analyze_candles)에만 씀. 백테스트·과거 시뮬레이션은 원래 비중 (그 날짜 이후 결과로 정한 비중을 쓰면 미래를 보는 것)
- 결과 app/data/factor_weights.json — 백테스트가 끝날 때마다(하루 1번) 다시 계산
"""
import json
import time
from pathlib import Path

FACTORS = ("RSI", "MACD", "볼린저밴드", "이동평균")
UP_RATIO, DOWN_RATIO = 0.6, 0.3    # analysis.predict_next_day 의 상승/하락 신호 기준과 같음
KEEP_ACC, FLOOR_ACC = 51.0, 46.0   # 이 적중률 이상 = 1배, 이하 = 최저 배율
MIN_WEIGHT = 0.3
MIN_N = 150                        # 지표 신호(상승+하락)가 이보다 적으면 그대로
SIDE_MIN = 30                      # 상승·하락 신호가 각각 이만큼은 있어야 두 쪽 평균을 씀
WARMUP_ROWS = 500                  # walk-forward: 이만큼 결과가 쌓인 뒤 날짜부터 비교
MIN_TEST = 300                     # 비교한 기록이 이보다 적으면 채택 안 함
MIN_GAIN = 0.3                     # 조정이 이만큼(%p) 나아야 채택

_FILE = Path(__file__).resolve().parents[1] / "data" / "factor_weights.json"
_cache: dict = {"data": None, "loaded": False, "version": 0}


# ---------------- 계산 (DB·파일 없음) ----------------

def _signal(f: dict):
    """지표 하나 → 'up' / 'down' / None"""
    full = f.get("max") or 0
    if not full:
        return None
    r = (f.get("score") or 0) / full
    return "up" if r >= UP_RATIO else "down" if r <= DOWN_RATIO else None


class Stats:
    """지표별 상승·하락 신호 수와 맞은 수 (누적)"""

    def __init__(self):
        self.c = {n: [0, 0, 0, 0] for n in FACTORS}   # up_n, up_hit, down_n, down_hit

    def add(self, factors: list, change: float):
        if change is None or change == 0:
            return
        for f in factors:
            n = f.get("name")
            if n not in self.c:
                continue
            s = _signal(f)
            if s == "up":
                self.c[n][0] += 1
                self.c[n][1] += change > 0
            elif s == "down":
                self.c[n][2] += 1
                self.c[n][3] += change < 0

    def accuracy(self, name: str) -> tuple:
        """→ (적중률 %, 신호 수) — 두 쪽 다 SIDE_MIN 이상이면 평균, 아니면 전체"""
        un, uh, dn, dh = self.c[name]
        n = un + dn
        if not n:
            return None, 0
        if un >= SIDE_MIN and dn >= SIDE_MIN:
            return (uh / un + dh / dn) / 2 * 100, n
        return (uh + dh) / n * 100, n

    def weights(self) -> dict:
        out = {}
        for name in FACTORS:
            acc, n = self.accuracy(name)
            out[name] = weight_for(acc, n)
        return out


def weight_for(acc, n: int) -> float:
    if acc is None or n < MIN_N or acc >= KEEP_ACC:
        return 1.0
    if acc <= FLOOR_ACC:
        return MIN_WEIGHT
    return round(MIN_WEIGHT + (1 - MIN_WEIGHT) * (acc - FLOOR_ACC) / (KEEP_ACC - FLOOR_ACC), 2)


def probability(factors: list, weights: dict | None = None) -> int:
    """지표 점수 → 상승 확률 (analysis.predict_next_day 와 같은 식: 점수 비율 × 60 + 20, 15~85). weights 는 지표별 배율"""
    w = weights or {}
    score = sum((f.get("score") or 0) * w.get(f.get("name"), 1.0) for f in factors if f.get("max"))
    full = sum(f["max"] * w.get(f.get("name"), 1.0) for f in factors if f.get("max"))
    if full <= 0:
        return 50
    return max(15, min(85, int(score / full * 60 + 20)))


def _dir_hit(p: int, change: float):
    if p == 50 or change is None or change == 0:
        return None
    return (p > 50) == (change > 0)


def evaluate(rows: list, trace: list | None = None) -> dict:
    """rows: [(대상일, 지표 목록, 실제 등락률)] (한 시장) → 지표별 적중률·최종 비중·walk-forward 비교·채택 여부.
    trace 를 주면 날짜마다 (날짜, 그날 쓴 비중) 을 넣음 (미래 데이터 미사용 테스트용)"""
    rows = sorted((r for r in rows if r[2] is not None), key=lambda r: r[0])
    stats, seen = Stats(), 0
    test = {"n": 0, "base_hit": 0, "adj_hit": 0, "base_conf": 0, "base_conf_hit": 0, "adj_conf": 0, "adj_conf_hit": 0, "changed": 0}
    i = 0
    while i < len(rows):
        day = rows[i][0]
        j = i
        while j < len(rows) and rows[j][0] == day:
            j += 1
        if seen >= WARMUP_ROWS:          # 이 날짜 전에 결과가 나온 기록만으로 정한 비중
            w = stats.weights()
            if trace is not None:
                trace.append((day, dict(w)))
            for _, factors, change in rows[i:j]:
                pb, pa = probability(factors), probability(factors, w)
                hb, ha = _dir_hit(pb, change), _dir_hit(pa, change)
                if hb is None or ha is None:
                    continue
                test["n"] += 1
                test["base_hit"] += hb
                test["adj_hit"] += ha
                test["changed"] += pb != pa
                for p, k in ((pb, "base"), (pa, "adj")):
                    if p >= 55 or p <= 45:
                        test[k + "_conf"] += 1
                        test[k + "_conf_hit"] += _dir_hit(p, change)
        for _, factors, change in rows[i:j]:   # 이 날짜 결과는 다음 날짜부터 씀
            stats.add(factors, change)
            seen += 1
        i = j

    pct = lambda a, b: round(a / b * 100, 1) if b else None  # noqa: E731
    wf = {"n": test["n"], "changed": test["changed"],
          "base_accuracy": pct(test["base_hit"], test["n"]), "weighted_accuracy": pct(test["adj_hit"], test["n"]),
          "base_conf_accuracy": pct(test["base_conf_hit"], test["base_conf"]), "weighted_conf_accuracy": pct(test["adj_conf_hit"], test["adj_conf"]),
          "base_conf_n": test["base_conf"], "weighted_conf_n": test["adj_conf"]}
    final = stats.weights()
    factors = []
    for name in FACTORS:
        un, uh, dn, dh = stats.c[name]
        acc, n = stats.accuracy(name)
        factors.append({"name": name, "n": n, "accuracy": round(acc, 1) if acc is not None else None,
                        "up_n": un, "up_rate": pct(uh, un), "down_n": dn, "down_rate": pct(dh, dn), "weight": final[name]})
    if all(v == 1.0 for v in final.values()):
        adopted, reason = False, f"줄일 지표 없음 — 모든 지표 적중률 {KEEP_ACC:g}% 이상이거나 신호가 {MIN_N}건 미만"
    elif wf["n"] < MIN_TEST:
        adopted, reason = False, f"검증 기록 {wf['n']}건 — {MIN_TEST}건 이상 쌓이면 판단"
    elif wf["weighted_accuracy"] - wf["base_accuracy"] < MIN_GAIN:
        adopted, reason = False, (f"조정해도 덜 맞음/비슷함 (방향 적중률 {wf['weighted_accuracy']}% vs 원래 {wf['base_accuracy']}%, "
                                  f"{MIN_GAIN}%p 이상 나아야 씀)")
    else:
        adopted, reason = True, f"조정이 더 잘 맞음 (방향 적중률 {wf['weighted_accuracy']}% vs 원래 {wf['base_accuracy']}%, {wf['n']:,}건)"
    return {"factors": factors, "weights": final, "walk_forward": wf, "adopted": adopted, "reason": reason,
            "rows": len(rows), "from": rows[0][0] if rows else None, "to": rows[-1][0] if rows else None}


# ---------------- 저장 · 실시간 ----------------

def _load():
    if not _cache["loaded"]:
        try:
            _cache["data"] = json.loads(_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            _cache["data"] = None
        _cache["loaded"] = True
    return _cache["data"]


def report() -> dict | None:
    """예측 검증 화면용 — {computed_at, markets: {KR: evaluate 결과, US: ...}}"""
    return _load()


def live(market: str) -> dict | None:
    """실시간 예측에 쓸 지표 배율 (채택된 시장만, 1배가 아닌 것만) — 없으면 None (원래 비중)"""
    d = (_load() or {}).get("markets", {}).get(market)
    if not d or not d.get("adopted"):
        return None
    w = {k: v for k, v in d["weights"].items() if v < 1.0}
    return w or None


def version() -> int:
    """분석 결과 메모(quote._memo_key)용 — 비중이 바뀌면 다시 계산"""
    return _cache["version"]


def save(markets: dict):
    data = {"computed_at": time.time(), "markets": markets}
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _cache.update(data=data, loaded=True, version=_cache["version"] + 1)


async def recompute() -> dict:
    """백테스트 기록으로 다시 계산 → 저장 (backtest.run 끝에서 하루 1번)"""
    import asyncio
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.prediction import BacktestLog
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(BacktestLog.market, BacktestLog.target_date, BacktestLog.factors, BacktestLog.actual_change)
                               .where(BacktestLog.evaluated.is_(True), BacktestLog.actual_change.isnot(None)))
        raw = res.all()
    by_m: dict = {}
    for m, t, f, ch in raw:
        try:
            fs = [x for x in json.loads(f or "[]") if x.get("name") in FACTORS]
        except ValueError:
            continue
        if fs:
            by_m.setdefault(m, []).append((t, fs, ch))
    markets = {m: await asyncio.to_thread(evaluate, rows) for m, rows in by_m.items()}
    save(markets)
    return markets
