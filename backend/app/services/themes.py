"""테마별 종목 묶음 — 네이버 증권 테마 분류 (KIS 에는 테마 분류가 없음)

- 네이버 증권 모바일 API (JSON) — 예전 PC 화면(finance.naver.com/sise/theme.naver)은 2026-11 새 사이트(stock.naver.com)로 옮겨져
  HTML 을 읽을 수 없게 됨 → 같은 데이터를 주는 모바일 API 사용 (뉴스도 같은 m.stock.naver.com API 를 씀)
  - 테마 목록:  m.stock.naver.com/api/stocks/theme?page=N&pageSize=100   → groups[{no, name, totalCount}], totalCount
  - 테마 종목:  m.stock.naver.com/api/stocks/theme/{no}?page=N&pageSize=100 → stocks[{itemCode, stockName}],
                themeDescription(테마 설명), themeItemInfoMap({코드: 편입 사유})
- 하루 1번 다시 받아 app/data/themes.json 에 저장 (테마 구성은 자주 안 바뀜). 종목코드는 KIS 종목마스터로 확인한 것만 남김
- 테마별 오늘 등락(평균·상승/하락 수·주도주)은 KIS 멀티종목 시세로 직접 계산 (네이버 시세는 안 씀)
공식 공개 API 가 아니라 형식이 바뀔 수 있음 → 바뀌면 "테마 목록을 읽지 못함" 오류로 표시.
"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import httpx

from app.services import stock_master

_FILE = Path(__file__).resolve().parents[1] / "data" / "themes.json"
_API = "https://m.stock.naver.com/api/stocks/theme"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
       "Referer": "https://m.stock.naver.com/"}
_REFRESH_SEC = 24 * 3600
_PAGE = 100

_data: dict | None = None      # {"updated_at", "themes": [{"no", "name", "symbols", "description", "reasons"}]}
_by_symbol: dict = {}          # symbol -> [테마 이름]
_status: dict = {"running": False, "done": 0, "total": 0, "error": None, "finished_at": None}


def parse_list(j: dict) -> tuple:
    """테마 목록 응답 → ([(번호, 이름)], 전체 개수)"""
    groups = j.get("groups") or []
    return [(str(g["no"]), str(g["name"]).strip()) for g in groups if g.get("no") is not None and g.get("name")], \
        int(j.get("totalCount") or 0)


def parse_detail(j: dict) -> tuple:
    """테마 종목 응답 → ([종목코드], 전체 개수, 테마 설명, {코드: 편입 사유})"""
    codes = []
    for st in j.get("stocks") or []:
        c = str(st.get("itemCode") or "").strip()
        if c and c not in codes and st.get("stockEndType", "stock") == "stock":
            codes.append(c)
    info = j.get("themeItemInfoMap") or {}
    return codes, int(j.get("totalCount") or 0), (j.get("themeDescription") or "").strip(), \
        {str(k): str(v).strip() for k, v in info.items() if v}


async def _get_json(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url)
    r.raise_for_status()
    if not r.content.strip():
        return {}   # 마지막 페이지 다음은 빈 응답
    return r.json()


async def _paged(client: httpx.AsyncClient, url: str, key: str) -> dict:
    """page=1,2,... 를 전체 개수(totalCount)만큼 받아 key 목록을 합침"""
    items, total = [], None
    first: dict = {}
    for page in range(1, 30):
        j = await _get_json(client, f"{url}{'&' if '?' in url else '?'}page={page}&pageSize={_PAGE}")
        if page == 1:
            first = j
        batch = j.get(key) or []
        items += batch
        total = int(j.get("totalCount") or 0) if total is None else total
        if not batch or len(items) >= total:
            break
        await asyncio.sleep(0.2)
    return {**first, key: items}


async def refresh() -> dict:
    """네이버에서 테마·종목을 다시 받음 (테마 약 260개, 1~2분)"""
    if _status["running"]:
        return status()
    _status.update(running=True, done=0, total=0, error=None)
    try:
        await stock_master.load()
        async with httpx.AsyncClient(headers=_UA, timeout=10.0, follow_redirects=True) as client:
            listing = await _paged(client, _API, "groups")
            themes, _ = parse_list(listing)
            if len(themes) < 10:
                raise RuntimeError(f"테마 목록을 읽지 못함 ({len(themes)}개) — 네이버 응답 형식이 바뀌었을 수 있음")
            _status["total"] = len(themes)
            out, fails = [], []
            for no, name in themes:
                try:
                    j = await _paged(client, f"{_API}/{no}", "stocks")
                    codes, _, desc, reasons = parse_detail(j)
                    syms = [c for c in codes if stock_master.get("KR", c)]   # KIS 종목마스터에 있는 코드만
                    if syms:
                        out.append({"no": no, "name": name, "symbols": syms, "description": desc,
                                    "reasons": {s: reasons[s] for s in syms if s in reasons}})
                except Exception as e:
                    fails.append(f"{name}: {type(e).__name__}")
                _status["done"] += 1
                await asyncio.sleep(0.2)
        if not out:
            raise RuntimeError("테마 종목을 하나도 읽지 못함 — " + ", ".join(fails[:3]))
        data = {"updated_at": datetime.now().isoformat(timespec="seconds"), "themes": out,
                "failed": fails[:20]}
        _set(data)
        try:
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            _FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            print(f"[themes] 저장 실패: {e}")
        print(f"[themes] 테마 {len(out)}개 갱신" + (f" (실패 {len(fails)}개)" if fails else ""))
    except Exception as e:
        _status["error"] = str(e)
        print(f"[themes] 테마 갱신 실패: {e}")
    finally:
        _status.update(running=False, finished_at=datetime.now().isoformat(timespec="seconds"))
    return status()


def _set(data: dict):
    global _data, _by_symbol
    _data = data
    m: dict = {}
    for t in data["themes"]:
        for s in t["symbols"]:
            m.setdefault(s, []).append(t["name"])
    _by_symbol = m


def load() -> dict | None:
    if _data is None and _FILE.exists():
        try:
            _set(json.loads(_FILE.read_text(encoding="utf-8")))
        except (ValueError, KeyError):
            pass
    return _data


def themes_of(symbol: str) -> list:
    load()
    return _by_symbol.get(symbol, [])


def get(no: str) -> dict | None:
    d = load()
    return next((t for t in (d or {}).get("themes", []) if t["no"] == no), None)


def status() -> dict:
    d = load()
    return {**_status, "theme_count": len((d or {}).get("themes", [])), "updated_at": (d or {}).get("updated_at")}


def _age() -> float:
    d = load()
    if not d:
        return float("inf")
    try:
        return time.time() - datetime.fromisoformat(d["updated_at"]).timestamp()
    except (KeyError, ValueError):
        return float("inf")


async def loop():
    """하루 1번 테마 구성 갱신 (없으면 시작 1분 뒤)"""
    await asyncio.sleep(60)
    while True:
        if _age() > _REFRESH_SEC:
            await refresh()
        await asyncio.sleep(3600)


# ---------------- 테마별 오늘 등락 (KIS 시세) ----------------

async def prices(symbols: list) -> dict:
    """KIS 멀티종목 시세 30개씩 → {코드: {price, change_rate, volume}} (실패한 묶음은 건너뛰고 오류 목록)"""
    from app.services.kis_api import kis_client
    out, errors = {}, []
    for i in range(0, len(symbols), 30):
        chunk = symbols[i:i + 30]
        try:
            out.update(await kis_client.get_kr_multi_price(chunk))
        except Exception as e:
            errors.append(str(e)[:120])
    if symbols and not out:
        raise RuntimeError("KIS 시세 조회 실패: " + (errors[0] if errors else "응답 없음"))
    return {"prices": out, "errors": errors}


async def overview() -> dict:
    """테마 전체: 평균 등락률·상승/하락 종목 수·주도주 3개 (평균 등락률 높은 순)"""
    d = load()
    if not d:
        if _status["running"]:
            raise RuntimeError(f"테마 구성을 받는 중입니다 ({_status['done']}/{_status['total'] or '?'}) — 1~2분 뒤 자동으로 표시됩니다")
        raise RuntimeError("테마 데이터가 아직 없습니다 — " + (_status.get("error") or "서버 시작 1분 뒤 자동으로 받습니다 (1~2분 걸림)"))
    syms = sorted({s for t in d["themes"] for s in t["symbols"]})
    px = await prices(syms)
    p = px["prices"]
    rows = []
    for t in d["themes"]:
        got = [(s, p[s]) for s in t["symbols"] if s in p]
        if not got:
            continue
        rates = [v["change_rate"] for _, v in got]
        leaders = sorted(got, key=lambda x: -x[1]["change_rate"])[:3]
        rows.append({
            "no": t["no"], "name": t["name"], "count": len(t["symbols"]), "priced": len(got),
            "avg_change": round(sum(rates) / len(rates), 2),
            "up": sum(1 for r in rates if r > 0), "down": sum(1 for r in rates if r < 0),
            "strong": sum(1 for r in rates if r >= 5),
            "leaders": [{"symbol": s, "name": (stock_master.get("KR", s) or {}).get("name", s), "change_rate": v["change_rate"]}
                        for s, v in leaders],
        })
    rows.sort(key=lambda r: -r["avg_change"])
    return {"themes": rows, "themes_updated_at": d.get("updated_at"), "price_errors": px["errors"][:3]}


async def detail(no: str) -> dict:
    """테마 하나의 종목: 현재가·등락률·거래량·매집 점수·다른 테마"""
    from app.services import accumulation
    t = get(no)
    if not t:
        raise LookupError(f"테마 {no} 없음")
    px = await prices(t["symbols"])
    rows = []
    for s in t["symbols"]:
        m = stock_master.get("KR", s) or {}
        v = px["prices"].get(s)
        rows.append({
            "symbol": s, "name": m.get("name", s), "market": "KR", "exchange": m.get("exchange"),
            "price": v["price"] if v else None, "change_rate": v["change_rate"] if v else None,
            "volume": v["volume"] if v else None,
            "accum_score": accumulation.score_of(s),
            "reason": (t.get("reasons") or {}).get(s),
            "other_themes": [n for n in themes_of(s) if n != t["name"]][:4],
        })
    rows.sort(key=lambda r: -(r["change_rate"] if r["change_rate"] is not None else -999))
    return {"no": t["no"], "name": t["name"], "description": t.get("description") or "", "items": rows,
            "price_errors": px["errors"][:3]}
