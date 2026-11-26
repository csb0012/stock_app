"""투자 대가 · 가치주 찾기 · 수급(쌍끌이·개미) 화면 API"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.bg import spawn
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.core.swr import SWRCache
from app.services import gurus, fundamentals, signals, flows

router = APIRouter(tags=["signals"])

_us_screen_cache = SWRCache("value_us", fresh=600, max_stale=3600)


# ---------------- 투자 대가 ----------------

@router.get("/gurus")
async def guru_list(current_user: User = Depends(get_current_user)):
    """대가 목록 (최근 1년 추정 수익률 높은 순) + 따라 사기 검증 + 수집 상태"""
    r = gurus.result()
    st = {**gurus.status(), "stale": gurus.stale()}
    if not r:
        return {"gurus": [], "validation": None, "validation_ai": None, "validation_recent": None, "validation_recent_ai": None,
                "status": st, "updated_at": None, "errors": []}
    return {"gurus": r["gurus"], "validation": r.get("validation"), "validation_ai": r.get("validation_ai"),
            "validation_recent": r.get("validation_recent"), "validation_recent_ai": r.get("validation_recent_ai"), "status": st,
            "updated_at": r.get("updated_at"), "errors": r.get("errors", []), "unmapped": r.get("unmapped")}


@router.get("/gurus/stocks")
async def guru_stocks(sort: str = "holders", limit: int = Query(100, ge=1, le=300), current_user: User = Depends(get_current_user)):
    """대가들이 많이 보유한·이번 분기에 많이 산 종목 (sort = holders | buyers | sellers)"""
    r = gurus.result() or {}
    rows = list((r.get("stocks") or {}).values())
    key = {"buyers": "n_buyers", "sellers": "n_sellers", "recent": "n_recent_buys"}.get(sort, "n_holders")
    rows.sort(key=lambda s: (-s.get(key, 0), -s["n_holders"], -sum(h["weight"] for h in s["holders"])))
    rows = [s for s in rows if s.get(key, 0) > 0][:limit]
    return {"items": rows, "updated_at": r.get("updated_at"), "sort": sort}


@router.get("/gurus/{key}")
async def guru_one(key: str, current_user: User = Depends(get_current_user)):
    """대가 1명의 보유 종목 전체 (비중·직전 분기 대비 변화·전량 매도)"""
    d = await asyncio.get_event_loop().run_in_executor(None, gurus.guru_detail, key)
    if d is None:
        raise HTTPException(status_code=404, detail="없는 투자 대가입니다")
    return d


@router.post("/gurus/refresh")
async def guru_refresh(current_user: User = Depends(get_current_user)):
    """SEC 13F 다시 받기 (백그라운드 — 처음엔 티커 변환 때문에 5~10분)"""
    if not gurus.status()["running"]:
        spawn(gurus.refresh())
        await asyncio.sleep(0)
    return gurus.status()


# ---------------- 가치주 찾기 ----------------

def _kr_screen_meta():
    return [{"key": k, "name": n, "about": a} for k, n, a, _, _ in fundamentals.KR_SCREENS]


@router.get("/value/screens")
async def value_screens(current_user: User = Depends(get_current_user)):
    """조건 목록 (국내·미국) + 국내 재무 수집 상태"""
    return {"KR": _kr_screen_meta(), "US": fundamentals.us_screen_meta(), "status": fundamentals.status()}


@router.get("/value/{market}/{key}")
async def value_screen(market: str, key: str, limit: int = Query(100, ge=1, le=250),
                       current_user: User = Depends(get_current_user)):
    market = market.upper()
    if market == "KR":
        if key not in {s[0] for s in fundamentals.KR_SCREENS}:
            raise HTTPException(status_code=404, detail="없는 조건입니다")
        rows = await asyncio.get_event_loop().run_in_executor(None, signals.kr_value_rows)
        st = fundamentals.status()
        if not rows:
            msg = "국내 재무 데이터가 아직 없습니다 — 서버 시작 5분 뒤부터 네이버 증권에서 받습니다 (전 종목 약 5~10분)."
            if st.get("running"):
                msg = f"국내 재무 데이터를 받는 중입니다 ({st['done']}/{st['total']})"
            elif (st.get("message") or "").startswith("실패"):
                raise HTTPException(status_code=502, detail=st["message"])
            return {"items": [], "total": 0, "message": msg, "status": st}
        items = fundamentals.run_screen(rows, key, limit)
        return {"items": items, "total": len(fundamentals.run_screen(rows, key, 10_000)), "universe": len(rows), "status": st}
    if market == "US":
        if key not in fundamentals.US_SCREEN_KEYS:
            raise HTTPException(status_code=404, detail="없는 조건입니다")
        try:
            return await _us_screen_cache.get(f"{key}:{limit}", lambda: asyncio.get_event_loop().run_in_executor(
                None, fundamentals.us_screen_sync, key, limit))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Yahoo 스크리너 실패: {e}")
    raise HTTPException(status_code=400, detail="market 은 KR 또는 US")


# ---------------- 수급 (쌍끌이·개미 동향) ----------------

@router.get("/flows/overview")
async def flow_overview(limit: int = Query(50, ge=1, le=200), current_user: User = Depends(get_current_user)):
    """국내 수급 순위(쌍끌이·외국인·기관·개인) + 날짜별 시장 합계(개미 투자 동향) + 수집 상태"""
    return await asyncio.get_event_loop().run_in_executor(None, signals.flow_overview, limit)


@router.get("/signals/status")
async def signal_status(current_user: User = Depends(get_current_user)):
    return {**signals.status(), "flows": flows.status()}
