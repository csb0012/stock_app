"""테마별 종목 묶음 — 네이버 증권 테마 분류 (KIS 에는 테마 분류가 없음)

- 테마 목록: finance.naver.com/sise/theme.naver?page=N (페이지마다 약 40개)
- 테마 종목: finance.naver.com/sise/sise_group_detail.naver?type=theme&no=번호
- 하루 1번 다시 받아 app/data/themes.json 에 저장 (테마 구성은 자주 안 바뀜). 종목코드는 KIS 종목마스터로 확인한 것만 남김
- 테마별 오늘 등락(평균·상승/하락 수·주도주)은 KIS 멀티종목 시세로 직접 계산 (네이버 시세는 안 씀)
네이버는 공식 API 가 아니라 화면(HTML)을 읽는 방식 → 형식이 바뀌면 "테마 목록을 읽지 못함" 오류로 표시.
"""
import asyncio
import html
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

from app.services import stock_master

_FILE = Path(__file__).resolve().parents[1] / "data" / "themes.json"
_BASE = "https://finance.naver.com"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
_REFRESH_SEC = 24 * 3600

_LIST_RE = re.compile(r'href="/sise/sise_group_detail\.naver\?type=theme&(?:amp;)?no=(\d+)"[^>]*>\s*([^<]+?)\s*</a>')
_CODE_RE = re.compile(r'/item/main\.naver\?code=([0-9A-Z]{6})')

_data: dict | None = None      # {"updated_at", "themes": [{"no", "name", "symbols": [...]}]}
_by_symbol: dict = {}          # symbol -> [테마 이름]
_status: dict = {"running": False, "done": 0, "total": 0, "error": None, "finished_at": None}


def parse_list(page_html: str) -> list:
    """테마 목록 페이지 → [(번호, 이름)]"""
    out, seen = [], set()
    for no, name in _LIST_RE.findall(page_html):
        if no not in seen:
            seen.add(no)
            out.append((no, re.sub(r"\s+", " ", html.unescape(name)).strip()))
    return out


def parse_detail(page_html: str) -> list:
    """테마 상세 페이지 → [종목코드] (순서 유지, 중복 제거)"""
    out = []
    for code in _CODE_RE.findall(page_html):
        if code not in out:
            out.append(code)
    return out


async def _get(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url)
    r.raise_for_status()
    return r.content.decode("cp949", errors="replace")   # 네이버 증권 PC 화면은 EUC-KR


async def refresh() -> dict:
    """네이버에서 테마·종목을 다시 받음 (약 2~3분, 페이지마다 0.3초 간격)"""
    if _status["running"]:
        return status()
    _status.update(running=True, done=0, total=0, error=None)
    try:
        await stock_master.load()
        async with httpx.AsyncClient(headers=_UA, timeout=10.0, follow_redirects=True) as client:
            themes: dict = {}
            for page in range(1, 21):
                found = parse_list(await _get(client, f"{_BASE}/sise/theme.naver?&page={page}"))
                new = [(no, nm) for no, nm in found if no not in themes]
                if not new:
                    break
                themes.update(new)
                await asyncio.sleep(0.3)
            if len(themes) < 10:
                raise RuntimeError(f"테마 목록을 읽지 못함 ({len(themes)}개) — 네이버 화면 형식이 바뀌었을 수 있음")
            _status["total"] = len(themes)
            out, fails = [], []
            for no, name in themes.items():
                try:
                    codes = parse_detail(await _get(client, f"{_BASE}/sise/sise_group_detail.naver?type=theme&no={no}"))
                    syms = [c for c in codes if stock_master.get("KR", c)]   # KIS 종목마스터에 있는 코드만
                    if syms:
                        out.append({"no": no, "name": name, "symbols": syms})
                except Exception as e:
                    fails.append(f"{name}: {type(e).__name__}")
                _status["done"] += 1
                await asyncio.sleep(0.3)
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
        raise RuntimeError("테마 데이터가 아직 없습니다 — " + (_status.get("error") or "서버 시작 후 1~3분 뒤 자동으로 받습니다"))
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
            "other_themes": [n for n in themes_of(s) if n != t["name"]][:4],
        })
    rows.sort(key=lambda r: -(r["change_rate"] if r["change_rate"] is not None else -999))
    return {"no": t["no"], "name": t["name"], "items": rows, "price_errors": px["errors"][:3]}
