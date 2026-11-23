"""매집·바닥 다지기 탐지 — 급등 전에 흔히 보이는 '조용히 모으는' 패턴을 점수로 (국내 전 종목, 하루 1회)

점수 (100점, 그날까지의 데이터만 사용 — 미래 데이터 안 씀):
  횡보 25        최근 60거래일 가격 범위(고가-저가)/평균가 — 좁을수록 (20% 이하 만점)
  변동성 축소 15  최근 20일 하루 변동폭 / 그 전 40일 — 줄어들수록 (0.7배 이하 만점)
  OBV 매집 20    60일 동안 가격은 제자리(±10%)인데 OBV(상승일 거래량 - 하락일 거래량 누적)가 늘어남
  거래량 꿈틀 15  최근 5일 거래량이 60일 평균의 1.5배 이상인데 가격은 아직 ±8% 안
  저점 상승 10    최근 20일 최저가 > 그 전 20일 최저가
  바닥권 15       200일 가격 범위에서 아래쪽 35% 안
제외: 최근 20일 이미 +25% 넘게 오른 종목(이미 출발), 20일 평균 거래대금 1억 원 미만, 상장 120거래일 미만

검증 (validation): 같은 점수를 최근 몇 달의 각 날짜에 계산해 보고, 그 뒤 20거래일 안에 +20% 이상 오른 적이 있는지
→ 점수 구간별 적중률을 전체 평균(기준)과 비교. 점수가 높을수록 적중률이 기준보다 높아야 의미가 있음.

데이터: KIS 국내 일봉 200개 (종목당 2~3회 호출). 전 종목 약 2,500개 → 실서버 7~10분, 모의서버는 1시간 이상.
백그라운드 우선순위(화면 요청에 양보)로 국내 장 마감 후 하루 1회 + 결과가 없거나 오래됐으면 서버 시작 후 실행.
결과: app/data/accumulation.json
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from app.services import stock_master, quant

_FILE = Path(__file__).resolve().parents[1] / "data" / "accumulation.json"
CANDLES = 200
WINDOW, SHORT = 60, 20
HIT_UP, HORIZON = 0.20, 20          # 20거래일 안에 +20% 도달 = 적중
MAX_RET20, MIN_TV = 0.25, 1e8        # 이미 +25% 오른 종목, 거래대금 1억 미만 제외
BUCKETS = [0, 50, 60, 70, 80]

PARTS = [("횡보", 25), ("변동성 축소", 15), ("OBV 매집", 20), ("거래량 꿈틀", 15), ("저점 상승", 10), ("바닥권", 15)]

_status: dict = {"running": False, "done": 0, "total": 0, "errors": 0, "error_samples": [], "started_at": None,
                 "finished_at": None, "message": None}
_result: dict | None = None


# ---------------- 점수 ----------------

def score_frame(candles: list) -> pd.DataFrame:
    """날짜별 매집 점수·요소 (각 날짜는 그날까지의 데이터만 사용)"""
    df = pd.DataFrame(candles)
    c, h, l, v = (df[k].astype(float) for k in ("close", "high", "low", "volume"))
    out = pd.DataFrame({"date": df["date"], "close": c})

    mean60 = c.rolling(WINDOW).mean()
    range60 = (h.rolling(WINDOW).max() - l.rolling(WINDOW).min()) / mean60
    out["횡보"] = np.select([range60 <= 0.20, range60 <= 0.30, range60 <= 0.40], [25, 15, 5], 0)

    tr = (h - l) / c
    vc = tr.rolling(SHORT).mean() / tr.shift(SHORT).rolling(WINDOW - SHORT).mean()
    out["변동성 축소"] = np.select([vc <= 0.7, vc <= 0.85, vc <= 1.0], [15, 10, 5], 0)

    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    obv_slope = (obv - obv.shift(WINDOW)) / v.rolling(WINDOW).sum().replace(0, np.nan)
    ret60 = c / c.shift(WINDOW) - 1
    out["OBV 매집"] = np.select([(obv_slope > 0.10) & (ret60.abs() < 0.10), (obv_slope > 0.05) & (ret60.abs() < 0.15)], [20, 10], 0)

    vr = v.rolling(5).mean() / v.rolling(WINDOW).mean().replace(0, np.nan)
    ret5 = c / c.shift(5) - 1
    calm = ret5.abs() <= 0.08
    out["거래량 꿈틀"] = np.select([(vr >= 1.5) & calm, (vr >= 1.2) & calm], [15, 8], 0)

    out["저점 상승"] = np.where(l.rolling(SHORT).min() > l.shift(SHORT).rolling(SHORT).min(), 10, 0)

    hi, lo = h.rolling(CANDLES, min_periods=120).max(), l.rolling(CANDLES, min_periods=120).min()
    pos = (c - lo) / (hi - lo).replace(0, np.nan)
    out["바닥권"] = np.select([pos <= 0.35, pos <= 0.5], [15, 8], 0)

    out["score"] = out[[p for p, _ in PARTS]].sum(axis=1)
    out.loc[out.index < 119, "score"] = np.nan   # 120거래일 이상 있어야 계산
    out["ret20"] = c / c.shift(SHORT) - 1
    out["tv20"] = (c * v).rolling(SHORT).mean()
    out["eligible"] = (out["ret20"] <= MAX_RET20) & (out["tv20"] >= MIN_TV)
    # 검증용: 다음날부터 20거래일 안의 최고가 (미래 — 점수 계산에는 안 씀)
    fwd_max = h.iloc[::-1].rolling(HORIZON, min_periods=HORIZON).max().iloc[::-1].shift(-1)
    out["hit"] = np.where(fwd_max.isna(), np.nan, (fwd_max / c - 1 >= HIT_UP).astype(float))
    out["fwd_ret"] = c.shift(-HORIZON) / c - 1
    # 설명용 값
    out["range60"], out["vc"], out["obv_slope"], out["vr"], out["pos"], out["ret60"] = range60, vc, obv_slope, vr, pos, ret60
    return out


def _detail(row) -> list:
    def pct(x):
        return "-" if pd.isna(x) else f"{x * 100:.0f}%"
    txt = {
        "횡보": f"60일 가격 범위 {pct(row['range60'])}",
        "변동성 축소": f"하루 변동폭 {'-' if pd.isna(row['vc']) else f"{row['vc']:.2f}배"} (최근 20일 / 그 전 40일)",
        "OBV 매집": f"OBV 증가 {'-' if pd.isna(row['obv_slope']) else f"{row['obv_slope']:+.2f}"} · 60일 가격 {pct(row['ret60'])}",
        "거래량 꿈틀": f"5일 거래량 {'-' if pd.isna(row['vr']) else f"{row['vr']:.1f}배"} (60일 평균 대비)",
        "저점 상승": "최근 20일 저점이 그 전보다 높음" if row["저점 상승"] else "저점 상승 없음",
        "바닥권": f"200일 범위 중 {pct(row['pos'])} 위치",
    }
    return [{"name": p, "score": int(row[p]), "max": m, "detail": txt[p]} for p, m in PARTS]


def _empty_val() -> dict:
    return {str(b): {"n": 0, "hits": 0, "ret_sum": 0.0} for b in BUCKETS}


def _add_val(val: dict, f: pd.DataFrame):
    """검증: 점수가 있고 미래 결과가 있는 날짜만 (조건: 제외 기준 통과한 날)"""
    g = f[f["score"].notna() & f["hit"].notna() & f["eligible"]]
    for b in BUCKETS:
        s = g[g["score"] >= b]
        val[str(b)]["n"] += int(len(s))
        val[str(b)]["hits"] += int(s["hit"].sum())
        val[str(b)]["ret_sum"] += float(s["fwd_ret"].fillna(0).sum())


def _finish_val(val: dict) -> list:
    base = val["0"]
    base_rate = base["hits"] / base["n"] if base["n"] else None
    rows = []
    for b in BUCKETS:
        d = val[str(b)]
        rate = d["hits"] / d["n"] if d["n"] else None
        rows.append({"min_score": b, "n": d["n"], "hits": d["hits"],
                     "hit_rate": round(rate * 100, 1) if rate is not None else None,
                     "avg_ret20": round(d["ret_sum"] / d["n"] * 100, 2) if d["n"] else None,
                     "lift": round(rate / base_rate, 2) if rate is not None and base_rate else None})
    return rows


def analyze_one(symbol: str, candles: list):
    """→ (오늘 결과 dict 또는 None, 검증용 frame)"""
    if len(candles) < 120:
        return None, None
    f = score_frame(candles)
    last = f.iloc[-1]
    if pd.isna(last["score"]):
        return None, f
    m = stock_master.get("KR", symbol) or {}
    prev = f["close"].iloc[-2]
    row = {
        "symbol": symbol, "name": m.get("name", symbol), "exchange": m.get("exchange"),
        "price": float(last["close"]), "change_rate": round((last["close"] / prev - 1) * 100, 2) if prev else 0.0,
        "score": int(last["score"]), "eligible": bool(last["eligible"]),
        "ret20": None if pd.isna(last["ret20"]) else round(float(last["ret20"]) * 100, 1),
        "ret60": None if pd.isna(last["ret60"]) else round(float(last["ret60"]) * 100, 1),
        "tv20_eok": round(float(last["tv20"]) / 1e8, 1) if not pd.isna(last["tv20"]) else None,
        "date": str(last["date"])[:10], "parts": _detail(last),
    }
    if not row["eligible"]:
        row["excluded"] = ("최근 20일 이미 +25% 넘게 상승" if row["ret20"] is not None and row["ret20"] > MAX_RET20 * 100
                           else "거래대금 부족 (20일 평균 1억 원 미만)")
    return row, f


# ---------------- 전 종목 스캔 ----------------

def universe() -> list:
    return [i["symbol"] for i in stock_master._items
            if i["market"] == "KR" and i.get("type") == "stock" and stock_master.category(i) != "spac"]


async def scan(force: bool = False) -> dict:
    """국내 전 종목 매집 점수 계산 (백그라운드). 이미 실행 중이면 상태만 반환"""
    from app.services.kis_api import kis_client, mark_background
    if _status["running"]:
        return status()
    mark_background()   # 화면 요청보다 KIS 호출 순서를 뒤로
    syms = universe()
    _status.update(running=True, done=0, total=len(syms), errors=0, error_samples=[],
                   started_at=datetime.now().isoformat(timespec="seconds"), finished_at=None, message=None)
    rows, scores, val = [], {}, _empty_val()
    qframes: dict = {}   # 퀀트 점수용 요인 (같은 일봉으로 계산 — KIS 추가 호출 없음)
    sem = asyncio.Semaphore(4)
    loop = asyncio.get_event_loop()

    async def one(sym):
        async with sem:
            try:
                chart = await kis_client.get_kr_chart(sym, CANDLES)
                row, f = await loop.run_in_executor(None, analyze_one, sym, chart["candles"])
                qframes[sym] = await loop.run_in_executor(None, quant.factor_frame, chart["candles"])
                if f is not None:
                    _add_val(val, f)
                if row:
                    scores[sym] = row["score"]
                    rows.append(row)
            except Exception as e:
                _status["errors"] += 1
                if len(_status["error_samples"]) < 5:
                    _status["error_samples"].append(f"{sym}: {str(e)[:120]}")
            finally:
                _status["done"] += 1

    try:
        await asyncio.gather(*[one(s) for s in syms])
        if not rows:
            raise RuntimeError("계산된 종목이 없음 — " + " / ".join(_status["error_samples"][:2]))
        dates = pd.Series([r["date"] for r in rows])
        cands = sorted((r for r in rows if r["eligible"] and r["score"] >= 50), key=lambda r: -r["score"])
        result = {
            "base_date": dates.mode().iloc[0], "finished_at": datetime.now().isoformat(timespec="seconds"),
            "universe": len(syms), "scanned": len(rows), "errors": _status["errors"],
            "error_samples": _status["error_samples"],
            "candidates": cands[:200], "scores": scores, "validation": _finish_val(val),
            "rules": {"hit_up_pct": int(HIT_UP * 100), "horizon_days": HORIZON, "max_ret20_pct": int(MAX_RET20 * 100),
                      "min_tv_eok": MIN_TV / 1e8},
        }
        try:
            names = {s: (stock_master.get("KR", s) or {}).get("name", s) for s in qframes}
            result["quant"] = await loop.run_in_executor(None, quant.build, qframes, names)
            if result["quant"] is None:
                result["quant_error"] = "퀀트 점수를 계산할 종목이 없음 (거래대금·데이터 기간 부족)"
        except Exception as e:   # 퀀트 점수 실패가 매집 결과 저장을 막지 않게
            result["quant"], result["quant_error"] = None, f"퀀트 점수 계산 실패: {e}"
            print(f"[accumulation] {result['quant_error']}")
        _save(result)
        _status["message"] = f"{len(rows)}/{len(syms)}종목 계산, 후보 {len(cands)}개" + (
            f" · 실패 {_status['errors']}건" if _status["errors"] else "")
        print(f"[accumulation] {_status['message']}")
    except Exception as e:
        _status["message"] = f"실패: {e}"
        print(f"[accumulation] 스캔 실패: {e}")
    finally:
        _status.update(running=False, finished_at=datetime.now().isoformat(timespec="seconds"))
    return status()


def _save(result: dict):
    global _result
    _result = result
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"[accumulation] 결과 저장 실패: {e}")


def result() -> dict | None:
    global _result
    if _result is None and _FILE.exists():
        try:
            _result = json.loads(_FILE.read_text(encoding="utf-8"))
        except ValueError:
            _result = None
    return _result


def quant_of(symbol: str) -> dict | None:
    """국내 종목의 퀀트 점수 (마지막 스캔 기준) — 없으면 None"""
    q = (result() or {}).get("quant") or {}
    v = (q.get("scores") or {}).get(symbol)
    return {**v, "date": q.get("date"), "universe": q.get("universe")} if v else None


def score_of(symbol: str):
    r = result()
    return (r or {}).get("scores", {}).get(symbol)


def status() -> dict:
    return dict(_status)


def stale() -> bool:
    """결과가 없거나 최근 국내 거래일보다 오래됐으면 True"""
    from app.services.market_calendar import last_session_date
    r = result()
    return not r or r.get("base_date", "") < last_session_date("KR").isoformat()


async def startup():
    """서버 시작 후 결과가 없거나 오래됐으면 2분 뒤 스캔 (장중에는 어제 결과로 충분하므로 결과가 아예 없을 때만)"""
    from app.services.market_calendar import is_market_open
    await asyncio.sleep(120)
    r = result()
    # 퀀트 점수가 없는 예전 결과도 다시 계산 (업데이트 직후 한 번)
    if r is None or "quant" not in r or (stale() and not is_market_open("KR")):
        await scan()
