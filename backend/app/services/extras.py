"""추가 데이터 요인 — .env 의 FRED / Finnhub / DART 키로 예측을 보강

- 거시 환경 (FRED, 전 종목 공통): VIX, 하이일드 스프레드, 미 10년 금리, 장단기 금리차 → 위험선호/회피
- 애널리스트 의견 (Finnhub, 미국): 최근 매수/보유/매도 의견 수
- 실적 서프라이즈 (Finnhub, 미국): 최근 4분기 EPS 예상 대비 실제 + 7일 내 실적발표 예정 여부
- 공시 (DART, 국내 일반 주식): 최근 14일 공시 제목 → 호재/악재 공시

외부 API 는 호출 제한이 있어서(Finnhub 무료 분당 60회) 화면 요청 안에서 기다리지 않는다.
없는 데이터는 백그라운드 작업 큐에 넣고, 그동안 해당 요인은 "수집 중 — 중립" 으로 표시된다.
키가 .env 에 없으면 해당 요인은 아예 빠진다.
"""
import asyncio
import io
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import httpx

from app.core.config import settings
from app.services import stock_master

_DATA = Path(__file__).resolve().parents[1] / "data"
_DART_CORP_FILE = _DATA / "dart_corp.json"
_CACHE_FILE = _DATA / "extras_cache.json"   # 재시작해도 다시 수집하지 않도록 (성공한 값만, 유효기간은 TTL 그대로)

TTL = {"macro": 6 * 3600, "analyst": 12 * 3600, "earnings": 12 * 3600, "disclosure": 3 * 3600}
_cache: dict = {}            # (kind, key) -> {"ts", "data"}  data 는 dict 또는 {"error": ...}
_queue: asyncio.Queue | None = None
_pending: set = set()
_dart_corp: dict = {}        # stock_code -> corp_code
_last_call = {"finnhub": 0.0, "dart": 0.0, "fred": 0.0}
_MIN_GAP = {"finnhub": 1.1, "dart": 0.15, "fred": 0.2}
_http: httpx.AsyncClient | None = None


def enabled() -> dict:
    return {"fred": bool(settings.fred_api_key), "finnhub": bool(settings.finnhub_api_key),
            "dart": bool(settings.dart_api_key)}


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
    return _http


async def _get(provider: str, url: str, params: dict) -> httpx.Response:
    wait = _last_call[provider] + _MIN_GAP[provider] - time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)
    _last_call[provider] = time.monotonic()
    resp = await _client().get(url, params=params)
    if resp.status_code == 429:
        await asyncio.sleep(30)
        resp = await _client().get(url, params=params)
    resp.raise_for_status()
    return resp


# ---------------- 개별 수집기 ----------------

async def _fred_series(series_id: str, n: int = 40) -> list:
    resp = await _get("fred", "https://api.stlouisfed.org/fred/series/observations", {
        "series_id": series_id, "api_key": settings.fred_api_key, "file_type": "json",
        "sort_order": "desc", "limit": n,
    })
    vals = []
    for o in resp.json().get("observations", []):
        try:
            vals.append(float(o["value"]))
        except (ValueError, KeyError):
            pass  # 휴일 값 "."
    if not vals:
        raise RuntimeError(f"FRED {series_id} 데이터 없음")
    return vals  # 최신 → 과거


async def _collect_macro() -> dict:
    vix = await _fred_series("VIXCLS")
    hy = await _fred_series("BAMLH0A0HYM2")
    t10 = await _fred_series("DGS10")
    curve = await _fred_series("T10Y2Y", 5)
    score, notes = 5, []
    v = vix[0]
    v_avg = sum(vix[:20]) / min(20, len(vix))
    if v < 15:
        score += 2; notes.append(f"VIX {v:.1f} 낮음(안정)")
    elif v < 20:
        score += 1; notes.append(f"VIX {v:.1f} 보통")
    elif v < 25:
        score -= 1; notes.append(f"VIX {v:.1f} 경계")
    else:
        score -= 3; notes.append(f"VIX {v:.1f} 공포 구간")
    if v > v_avg * 1.1:
        score -= 1; notes.append("VIX 상승 중")
    hy_chg = hy[0] - hy[min(19, len(hy) - 1)]
    if hy_chg > 0.3:
        score -= 2; notes.append(f"하이일드 스프레드 확대 {hy_chg:+.2f}%p(신용 위험↑)")
    elif hy_chg < -0.2:
        score += 1; notes.append(f"하이일드 스프레드 축소 {hy_chg:+.2f}%p")
    t_chg = t10[0] - t10[min(19, len(t10) - 1)]
    if t_chg > 0.3:
        score -= 1; notes.append(f"미 10년 금리 급등 {t_chg:+.2f}%p")
    elif t_chg < -0.3:
        score += 1; notes.append(f"미 10년 금리 하락 {t_chg:+.2f}%p")
    if curve[0] < 0:
        notes.append(f"장단기 금리 역전({curve[0]:+.2f}%p)")
    return {"score": max(0, min(10, score)), "notes": notes, "vix": v, "us10y": t10[0]}


async def _collect_analyst(symbol: str) -> dict:
    resp = await _get("finnhub", "https://finnhub.io/api/v1/stock/recommendation",
                      {"symbol": symbol, "token": settings.finnhub_api_key})
    rows = resp.json() or []
    if not rows:
        return {"total": 0}
    r = rows[0]  # 최신 월
    sb, b, h, s, ss = (int(r.get(k, 0) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
    total = sb + b + h + s + ss
    return {"period": r.get("period"), "strong_buy": sb, "buy": b, "hold": h, "sell": s, "strong_sell": ss,
            "total": total, "bull_ratio": (sb + b) / total if total else None,
            "bear_ratio": (s + ss) / total if total else None}


async def _collect_earnings(symbol: str) -> dict:
    resp = await _get("finnhub", "https://finnhub.io/api/v1/stock/earnings",
                      {"symbol": symbol, "token": settings.finnhub_api_key})
    hist = [e for e in (resp.json() or []) if e.get("actual") is not None and e.get("estimate") is not None]
    today = date.today()
    cal = await _get("finnhub", "https://finnhub.io/api/v1/calendar/earnings", {
        "symbol": symbol, "from": today.isoformat(), "to": (today + timedelta(days=7)).isoformat(),
        "token": settings.finnhub_api_key,
    })
    upcoming = [e.get("date") for e in (cal.json() or {}).get("earningsCalendar", []) if e.get("date")]
    beats = sum(1 for e in hist[:4] if e["actual"] > e["estimate"])
    misses = sum(1 for e in hist[:4] if e["actual"] < e["estimate"])
    last = hist[0] if hist else None
    return {"quarters": len(hist[:4]), "beats": beats, "misses": misses,
            "last_surprise_pct": round(last.get("surprisePercent") or 0, 1) if last else None,
            "last_period": last.get("period") if last else None,
            "upcoming": upcoming[0] if upcoming else None}


async def _load_dart_corp():
    """DART 고유번호 목록 (종목코드 → corp_code). 7일마다 갱신"""
    global _dart_corp
    if _DART_CORP_FILE.exists():
        saved = json.loads(_DART_CORP_FILE.read_text(encoding="utf-8"))
        if time.time() - saved["ts"] < 7 * 86400:
            _dart_corp = saved["map"]
            return
    resp = await _get("dart", "https://opendart.fss.or.kr/api/corpCode.xml", {"crtfc_key": settings.dart_api_key})
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            root = ET.fromstring(z.read(z.namelist()[0]))
    except zipfile.BadZipFile:
        raise RuntimeError(f"DART 고유번호 다운로드 실패: {resp.text[:150]}")
    m = {}
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        if sc:
            m[sc] = el.findtext("corp_code")
    _DATA.mkdir(parents=True, exist_ok=True)
    _DART_CORP_FILE.write_text(json.dumps({"ts": time.time(), "map": m}), encoding="utf-8")
    _dart_corp = m


# 공시 제목(report_nm) 키워드 — 악재 키워드를 먼저 본다 (예: "자기주식처분" 은 악재)
DISC_POS = ["자기주식취득", "자기주식 취득", "단일판매", "공급계약", "무상증자", "현금ㆍ현물배당", "현금배당", "주식소각",
            "특허", "수주", "자기주식취득신탁", "기술이전", "품목허가", "임상시험계획승인"]
DISC_NEG = ["유상증자", "전환사채", "신주인수권부사채", "교환사채", "최대주주변경", "소송", "감자", "불성실공시",
            "관리종목", "횡령", "배임", "영업정지", "자기주식처분", "자기주식 처분", "상장폐지", "회생", "부도", "거래정지",
            "의견거절", "부적정", "한정의견", "투자경고", "투자위험", "투자주의환기", "실질심사", "채무불이행", "파산",
            "손상차손", "임상시험중단", "공급계약해지", "계약해지"]


async def _collect_disclosure(stock_code: str) -> dict:
    if not _dart_corp:
        await _load_dart_corp()
    corp = _dart_corp.get(stock_code)
    if not corp:
        return {"total": 0, "na": True}  # ETF 등 DART 대상 아님
    end = date.today()
    resp = await _get("dart", "https://opendart.fss.or.kr/api/list.json", {
        "crtfc_key": settings.dart_api_key, "corp_code": corp,
        "bgn_de": (end - timedelta(days=14)).strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
        "page_count": 50,
    })
    j = resp.json()
    if j.get("status") not in ("000", "013"):  # 013 = 조회된 데이터 없음
        raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
    items = []
    for d in j.get("list", []) or []:
        nm = d.get("report_nm", "")
        tone = "neg" if any(k in nm for k in DISC_NEG) else "pos" if any(k in nm for k in DISC_POS) else None
        items.append({"title": nm.strip(), "date": d.get("rcept_dt", ""), "tone": tone})
    return {"total": len(items), "pos": sum(1 for i in items if i["tone"] == "pos"),
            "neg": sum(1 for i in items if i["tone"] == "neg"), "items": items[:10]}


_COLLECTORS = {
    "macro": lambda key: _collect_macro(),
    "analyst": _collect_analyst,
    "earnings": _collect_earnings,
    "disclosure": _collect_disclosure,
}


# ---------------- 큐 / 조회 ----------------

def _fresh(kind: str, key: str):
    hit = _cache.get((kind, key))
    if hit and time.time() - hit["ts"] < (TTL[kind] if "error" not in hit["data"] else 600):
        return hit["data"]
    return None


def _enqueue(kind: str, key: str):
    if _queue is None or (kind, key) in _pending:
        return
    _pending.add((kind, key))
    _queue.put_nowait((kind, key))


def _peek(kind: str, key: str):
    """캐시에 있으면 반환, 없거나 오래됐으면 수집 예약 후 (있으면) 이전 값 반환"""
    data = _fresh(kind, key)
    if data is None:
        _enqueue(kind, key)
        hit = _cache.get((kind, key))
        return hit["data"] if hit else None
    return data


def get_extra(market: str, symbol: str) -> dict:
    """예측에 넘길 추가 요인. 값: dict(데이터) / {"error"} / {"pending": True}. 키가 없으면 해당 항목 없음."""
    on = enabled()
    out: dict = {}

    def val(kind, key):
        d = _peek(kind, key)
        return d if d is not None else {"pending": True}

    if on["fred"]:
        out["macro"] = val("macro", "global")
    if market == "US" and on["finnhub"]:
        m = stock_master.get("US", symbol) or {}
        if m.get("type") != "etf":  # ETF 는 애널리스트·실적 없음
            out["analyst"] = val("analyst", symbol)
            out["earnings"] = val("earnings", symbol)
    if market == "KR" and on["dart"]:
        m = stock_master.get("KR", symbol) or {}
        if m.get("type") == "stock":
            out["disclosure"] = val("disclosure", symbol)
    return out


def warm(items: list):
    """[(market, symbol)] — 미리 수집 예약 (추천 종목 목록 등)"""
    for m, s in items:
        get_extra(m, s)


def _load_disk():
    try:
        saved = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return
    n = 0
    for row in saved:
        kind, key, ts, data = row["kind"], row["key"], row["ts"], row["data"]
        if kind in TTL and time.time() - ts < TTL[kind] and (kind, key) not in _cache:
            _cache[(kind, key)] = {"ts": ts, "data": data}
            n += 1
    if n:
        print(f"[extras] 저장된 수집 결과 {n}건 불러옴")


def _save_disk():
    try:
        rows = [{"kind": k, "key": key, "ts": v["ts"], "data": v["data"]}
                for (k, key), v in _cache.items() if "error" not in v["data"]]
        _DATA.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_CACHE_FILE)
    except OSError as e:  # 부가 기능 — 저장 실패해도 수집은 계속
        print(f"[extras] 수집 결과 저장 실패: {e}")


async def worker():
    """백그라운드: 큐의 수집 작업을 호출 제한에 맞춰 처리"""
    global _queue
    _queue = asyncio.Queue()
    _load_disk()
    if enabled()["fred"]:
        _enqueue("macro", "global")
    while True:
        kind, key = await _queue.get()
        try:
            if _fresh(kind, key) is None:
                data = await _COLLECTORS[kind](key)
                _cache[(kind, key)] = {"ts": time.time(), "data": data}
                _save_disk()
        except Exception as e:
            _cache[(kind, key)] = {"ts": time.time(), "data": {"error": f"{type(e).__name__}: {str(e)[:150]}"}}
            print(f"[extras] {kind} {key} 수집 실패: {e}")
        finally:
            _pending.discard((kind, key))


def status() -> dict:
    """점검용: 키 설정 여부, 수집 현황"""
    counts: dict = {}
    for (kind, _), v in _cache.items():
        c = counts.setdefault(kind, {"ok": 0, "error": 0})
        c["error" if "error" in v["data"] else "ok"] += 1
    return {"enabled": enabled(), "collected": counts, "queue": len(_pending),
            "macro": (_cache.get(("macro", "global")) or {}).get("data")}
