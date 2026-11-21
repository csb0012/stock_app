"""과거 예측 백테스트 — 최근 90일 동안 매 거래일마다 "그날까지의 일봉만 보고" 다음 거래일을 예측해 채점

예) 대상일 11/19 → 11/18 종가까지의 일봉(최근 130개)으로 지표·확률 계산 → 11/19 실제 등락과 비교.
대상일 이후 데이터는 절대 쓰지 않는다 (미래 정보 누설 방지).

- 결과는 prediction_backtest 테이블(stock_app.db)에 저장 → 이미 계산한 날짜는 다시 계산하지 않음 (증분)
- 대상 종목: AI 추천 후보(국내 장기·미국 장기·미국 단기) + 관심종목 + 투자종목
- 뉴스·FRED·Finnhub·DART 는 과거 시점 기록이 없어 빼고, 가격·거래량·지수 데이터만 사용
- 방식 두 가지를 같이 계산해 비교: 규칙 점수(analysis.predict_next_day) / 학습 모델(ml_model, walk-forward)
  → 학습 모델이 규칙보다 적중률이 높을 때만 '채택'되어 실제 화면에 쓰임
- 서버 시작 후, 그리고 하루 한 번(30분 채점 주기에 확인) 자동 실행. 예측 검증 화면의 버튼으로도 실행
"""
import asyncio
import json

import numpy as np
import pandas as pd
from datetime import date, datetime

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.prediction import BacktestLog
from app.models.watchlist import WatchlistItem
from app.models.portfolio import PortfolioItem
from app.services import stock_master
from app.services.kis_api import KISRateLimitError, kis_client
from app.services import ml_model
from app.services.analysis import calc_technical_indicators, predict_next_day
from app.services.market_calendar import market_today, is_market_open, _after_close

RETRY_WAITS = (10, 30, 60)  # 초당 호출 제한으로 실패한 종목만 이만큼 기다렸다가 다시 계산 (초)
DAYS = 90        # 대상일 기준 최근 90일 (달력 기준)
WINDOW = 130     # 예측에 쓰는 일봉 개수 (실시간 AI 추천과 같음)
KR_COUNT = 500   # 학습용 약 2년치 일봉 (KIS 100개씩 5~6회 호출)

_lock = asyncio.Lock()
_status = {
    "running": False, "done": 0, "total": 0, "current": None, "added": 0,
    "started_at": None, "finished_at": None, "last_run_date": None, "errors": [], "retry_wait": None,
    "phase": None, "model_report": None,
}


def status() -> dict:
    return dict(_status)


def _closed(market: str, d: str) -> bool:
    """그 날짜 일봉이 확정됐는지 (오늘 장중이면 아직 미확정)"""
    today = market_today(market).isoformat()
    if d < today:
        return True
    return d == today and not is_market_open(market) and _after_close(market)


async def _universe() -> list:
    from app.api.routes.stocks import KR_LONGTERM, US_LONGTERM, US_SHORTTERM_EXTRA  # 순환 import 방지
    seen, out = set(), []

    def add(market, symbol, name):
        if (market, symbol) in seen:
            return
        seen.add((market, symbol))
        out.append({"market": market, "symbol": symbol, "name": name})

    for c in KR_LONGTERM + US_LONGTERM + US_SHORTTERM_EXTRA:
        m = stock_master.get(c["market"], c["symbol"]) or {}
        add(c["market"], c["symbol"], m.get("name") or c["name"])
    async with AsyncSessionLocal() as db:
        for model in (WatchlistItem, PortfolioItem):
            for r in (await db.execute(select(model))).scalars().all():
                add(r.market, r.symbol, r.name)
    return out


def _rule_preds(stock: dict, candles: list, cutoff: str) -> dict:
    """CPU 작업 (스레드): 대상일마다 전날까지의 일봉 130개로 규칙 점수 예측 → {대상일: (ti, 예측)}"""
    out = {}
    for ti in range(1, len(candles)):
        t = candles[ti]["date"][:10]
        if t < cutoff or not _closed(stock["market"], t):
            continue
        hist = candles[max(0, ti - WINDOW):ti]  # 대상일 전날까지만
        if len(hist) < 30:
            continue
        out[t] = (ti, predict_next_day(hist, calc_technical_indicators(hist)))  # 뉴스·외부데이터 없음
    return out


def _model_stage(stocks: list, data: dict, idx: dict, cutoff: str) -> dict:
    """CPU 작업 (스레드): 시장별로 특징값을 모아 walk-forward 로 학습·예측, 규칙과 적중률 비교 후 최종 모델 저장

    반환: {(market, symbol, 대상일): {"KR_base"/"KR"/"US": 확률}} 와 시장별 성적
    """
    from app.services.prediction_log import index_key
    frames = {"KR": [], "US": []}
    for st in stocks:
        d = data.get((st["market"], st["symbol"]))
        if not d:
            continue
        own = idx.get(ml_model.IDX_TICKERS[index_key(st["market"], st["symbol"])])
        spx = idx.get(ml_model.IDX_TICKERS["US"]) if st["market"] == "KR" else None
        ndx = idx.get(ml_model.IDX_TICKERS["NDX"]) if st["market"] == "KR" else None
        s = ml_model.samples(d["candles"], ml_model.feature_frame(d["candles"], own, spx, ndx))
        s = s[s["target_date"].map(lambda t: _closed(st["market"], t))]
        s["market"], s["symbol"] = st["market"], st["symbol"]
        # 같은 날짜의 규칙 점수 확률 (채택 비교용)
        s["rule_p"] = s["target_date"].map(lambda t: d["rules"][t][1]["probability"] / 100 if t in d["rules"] else None)
        frames[st["market"]].append(s)

    probs: dict = {}
    report: dict = {}
    for market, variants in (("KR", ("KR_base", "KR")), ("US", ("US",))):
        if not frames[market]:
            continue
        df = pd.concat(frames[market], ignore_index=True)
        for v in variants:
            feats = ml_model.VARIANT_FEATURES[v]
            wf = ml_model.walk_forward(df, feats, cutoff)
            test = df.loc[wf.dropna().index]
            test = test[test["rule_p"].notna()].copy()
            test["rule_p"] = test["rule_p"].astype(float)
            m_acc = ml_model._acc(wf.loc[test.index], test["change"])
            r_acc = ml_model._acc(test["rule_p"], test["change"])
            # 모델 + 규칙 결합·보정 (앞 구간으로 결합 → 다음 구간 예측)
            combo, stack, s_acc = ml_model.stack_fit(test, wf)
            final = ml_model.train_final(df, v, m_acc, r_acc, stack, s_acc)
            if final:
                ml_model.save(final)
            report[v] = {"model": m_acc, "rules": r_acc, "combo": s_acc, "adopted": bool(final and final["adopted"]),
                         "combo_usable": bool(final and final["stack_usable"]), "trained": bool(final)}
            for i, p in wf.dropna().items():
                r = df.loc[i]
                d = probs.setdefault((market, r["symbol"], r["target_date"]), {})
                d[v] = float(p)
                if i in combo.index and not np.isnan(combo.loc[i]):
                    d[v + "_combo"] = float(combo.loc[i])
    return {"probs": probs, "report": report}


async def run(force: bool = False) -> dict:
    """백테스트 실행 (이미 실행 중이면 상태만 반환). force=True 면 기존 기록을 지우고 다시 계산"""
    if _lock.locked():
        return status()
    async with _lock:
        _status.update(running=True, done=0, total=0, current=None, added=0, errors=[], retry_wait=None,
                       phase=None, started_at=datetime.now().isoformat(timespec="seconds"), finished_at=None)
        try:
            await _run(force)
            _status["last_run_date"] = date.today().isoformat()
        except Exception as e:
            _status["errors"].append(f"백테스트 실패: {e}")
            print(f"[backtest] 실패: {e}")
        finally:
            _status.update(running=False, current=None, phase=None,
                           finished_at=datetime.now().isoformat(timespec="seconds"))
    return status()


async def _fetch_all(stocks: list, us_hist: dict) -> dict:
    """종목별 일봉 (국내는 KIS 약 2년치 — 초당 호출 제한으로 실패한 종목은 기다렸다가 그 종목만 다시)"""
    data: dict = {}

    async def one(st: dict):
        _status["current"] = st["name"] or st["symbol"]
        if st["market"] == "KR":
            # 캐시(kr_chart)를 거치지 않음 — 2년치가 캐시에 남으면 다른 화면 응답이 커짐
            candles = (await kis_client.get_kr_chart(st["symbol"], KR_COUNT))["candles"]
        else:
            candles = us_hist.get(st["symbol"], [])
        if len(candles) < 80:
            raise ValueError(f"일봉 {len(candles)}개 — 데이터 부족")
        data[(st["market"], st["symbol"])] = {"candles": candles}

    def fail(st: dict, e: Exception):
        _status["errors"].append(f"{st['name'] or st['symbol']}({st['symbol']}): {e}")
        print(f"[backtest] {st['symbol']} 실패: {e}")

    retry = []
    for st in stocks:
        try:
            await one(st)
            _status["done"] += 1
        except KISRateLimitError:
            retry.append(st)  # 나중에 이 종목만 다시
        except Exception as e:
            fail(st, e)
            _status["done"] += 1

    # 초당 호출 제한으로 실패한 종목: 호출이 풀릴 때까지 기다렸다가 그 종목만 다시
    for n, wait in enumerate(RETRY_WAITS):
        if not retry:
            break
        names = ", ".join(s["name"] or s["symbol"] for s in retry[:3]) + (" 외" if len(retry) > 3 else "")
        _status["retry_wait"] = {"seconds": wait, "count": len(retry), "names": names, "round": n + 1}
        _status["current"] = f"초당 호출 제한 — {wait}초 후 {len(retry)}종목 다시 받기 ({names})"
        print(f"[backtest] {_status['current']}")
        await asyncio.sleep(wait)
        _status["retry_wait"] = None
        pending, retry = retry, []
        for st in pending:
            try:
                await one(st)
                _status["done"] += 1
            except KISRateLimitError as e:
                if n == len(RETRY_WAITS) - 1:
                    fail(st, e)
                    _status["done"] += 1
                else:
                    retry.append(st)
            except Exception as e:
                fail(st, e)
                _status["done"] += 1
    return data


async def _run(force: bool):
    # 순환 import 방지
    from app.services.quote import batch_yf_history
    from app.services.prediction_log import grade, index_change_fn

    cutoff = date.fromordinal(date.today().toordinal() - DAYS).isoformat()
    stocks = await _universe()
    _status["total"] = len(stocks)

    async with AsyncSessionLocal() as db:
        # 학습 모델 도입 전 기록(method 없음)은 비교 정보가 없으므로 지우고 다시 계산
        q = delete(BacktestLog) if force else delete(BacktestLog).where(
            BacktestLog.method.is_(None) | (BacktestLog.combo_probability.is_(None) & BacktestLog.model_probability.isnot(None)))
        await db.execute(q)
        await db.commit()
        existing = {(m, s, t) for m, s, t in (await db.execute(
            select(BacktestLog.market, BacktestLog.symbol, BacktestLog.target_date))).all()}

    _status["phase"] = "일봉 받는 중"
    idx_hist = await batch_yf_history(list(ml_model.IDX_TICKERS.values()), "2y")
    for t, cs in idx_hist.items():
        if len(cs) < 100:
            raise RuntimeError(f"지수 {t} 일봉 {len(cs)}개 — yfinance 조회 실패 (학습 모델에 필요)")
    idx = {t: ml_model.index_returns(cs) for t, cs in idx_hist.items()}
    idx_change = index_change_fn(idx_hist)
    us_syms = [s["symbol"] for s in stocks if s["market"] == "US"]
    us_hist = await batch_yf_history(us_syms, "2y") if us_syms else {}
    data = await _fetch_all(stocks, us_hist)

    _status["phase"] = "규칙 점수 계산 중"
    for st in stocks:
        d = data.get((st["market"], st["symbol"]))
        if d:
            _status["current"] = st["name"] or st["symbol"]
            d["rules"] = await asyncio.to_thread(_rule_preds, st, d["candles"], cutoff)

    _status["phase"] = "학습 모델 walk-forward 검증 중"
    _status["current"] = "학습·검증"
    stage = await asyncio.to_thread(_model_stage, stocks, data, idx, cutoff)
    probs, report = stage["probs"], stage["report"]
    _status["model_report"] = report

    _status["phase"] = "저장 중"
    adopted = {v: r["adopted"] for v, r in report.items()}
    combo_ok = {v: r["combo_usable"] for v, r in report.items()}
    async with AsyncSessionLocal() as db:
        for st in stocks:
            d = data.get((st["market"], st["symbol"]))
            if not d:
                continue
            for t, (ti, p) in d["rules"].items():
                key = (st["market"], st["symbol"], t)
                if key in existing:
                    continue
                mp = probs.get(key, {})
                rule_p = int(p["probability"])
                # 화면에 보일 확률: 실시간과 같은 순서 — 국내는 장 시작 전 자동 갱신(간밤 미국장 반영) 모델 우선
                order = ("KR", "KR_base") if st["market"] == "KR" else ("US",)
                # 실시간과 같은 순서: 결합(검증 통과) → 학습 모델(엄격한 채택) → 규칙 점수
                main_v, shown_p = None, rule_p
                for v in order:
                    if combo_ok.get(v) and v + "_combo" in mp:
                        main_v, shown_p = v + "_combo", round(mp[v + "_combo"] * 100)
                        break
                    if adopted.get(v) and v in mp:
                        main_v, shown_p = v, round(mp[v] * 100)
                        break
                use_model = main_v is not None
                base_v = "KR_base" if st["market"] == "KR" else "US"
                model_p = round(mp[base_v] * 100) if base_v in mp else None
                pct = lambda k: round(mp[k] * 100) if k in mp else None  # noqa: E731
                log = BacktestLog(
                    market=st["market"], symbol=st["symbol"], name=st["name"], sources="백테스트",
                    base_date=d["candles"][ti - 1]["date"][:10], target_date=t,
                    base_price=float(d["candles"][ti - 1]["close"]),
                    probability=shown_p,
                    method=(f"combo:{main_v[:-6]}" if main_v and main_v.endswith("_combo") else
                            f"model:{main_v}" if use_model else "rules"),
                    rule_probability=rule_p, model_probability=model_p,
                    preopen_probability=pct("KR"),
                    combo_probability=pct(base_v + "_combo"),
                    preopen_combo_probability=pct("KR_combo"),
                    signal=p.get("signal"),
                    summary=(f"학습 모델({main_v}) {shown_p}% · 지표 점수 {rule_p}% — {p.get('summary')}" if use_model
                             else p.get("summary")),
                    factors=json.dumps(p.get("factors", []), ensure_ascii=False),
                )
                grade(log, d["candles"], ti, idx_change)
                db.add(log)
                _status["added"] += 1
        await db.commit()


def due() -> bool:
    """오늘 아직 안 돌았으면 True"""
    return not _status["running"] and _status["last_run_date"] != date.today().isoformat()
