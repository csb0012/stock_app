"""KIS 모의투자 주문 (관리자 전용) — AI 제안 → 2단계 코드로 승인 → 모의투자 서버 주문. 로직은 services/kis_trade.py

승인·다시 시작·기준 맞추기·설정 변경은 2단계 코드를 매번 다시 받음 (재사용 불가). 긴급 정지·거절·취소는 위험을 줄이는 일이라 바로."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_admin, _use_totp
from app.core.database import get_db
from app.models.user import User
from app.services import kis_trade, kis_order
from app.services.kis_api import KISError

router = APIRouter(prefix="/kis", tags=["kis"])


class CodeRequest(BaseModel):
    totp_code: str = ""


class IdsRequest(BaseModel):
    ids: list[int]
    totp_code: str = ""


class HaltRequest(BaseModel):
    reason: str = ""


class ConfigRequest(BaseModel):
    limits: Optional[dict] = None
    params: Optional[dict] = None
    totp_code: str = ""


async def _step_up(db, admin: User, code: str):
    """주문 관련 확인 — 2단계를 켠 관리자만, 지금 코드로 (REQUIRE_TOTP=false 라도 주문은 2단계 필수)"""
    if not admin.totp_enabled:
        raise HTTPException(status_code=403, detail="주문 승인은 2단계 인증을 켠 관리자만 할 수 있습니다 — 마이페이지에서 2단계 인증을 켜세요")
    if not _use_totp(admin, code or ""):
        raise HTTPException(status_code=400, detail="2단계 인증 코드가 틀렸거나 이미 쓴 코드입니다 — 앱의 새 코드를 입력하세요")
    await db.commit()


def _err(e: Exception):
    if isinstance(e, HTTPException):
        raise e
    if isinstance(e, kis_order.NotConfigured):
        raise HTTPException(status_code=503, detail=str(e))
    if isinstance(e, kis_trade.TradeError):
        raise HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(e, LookupError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, KISError):
        raise HTTPException(status_code=502, detail=str(e))
    raise HTTPException(status_code=502, detail=f"처리 실패: {str(e)[:300]}")


@router.get("/status")
async def status(admin: User = Depends(get_admin)):
    """연결 상태·정지 여부·한도·오늘 주문 수·KIS 잔고·대조 결과·최근 판단 기록"""
    return await kis_trade.overview()


@router.get("/orders")
async def orders(kind: str = "open", limit: int = 100, admin: User = Depends(get_admin)):
    if kind not in ("open", "all"):
        raise HTTPException(status_code=422, detail="kind 는 open 또는 all")
    return {"items": await kis_trade.list_orders(kind, limit), "status_labels": kis_trade.STATUS_LABELS}


@router.get("/log")
async def log(limit: int = 100, admin: User = Depends(get_admin)):
    return {"items": await kis_trade.list_log(limit)}


@router.post("/propose")
async def propose(admin: User = Depends(get_admin)):
    """지금 제안 만들기 (확정된 마지막 종가 기준, 예전 승인 대기 제안은 만료) — 제안만, 주문은 안 함"""
    try:
        return await kis_trade.propose(user_id=admin.id)
    except Exception as e:
        _err(e)


@router.post("/orders/approve")
async def approve(req: IdsRequest, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    if not req.ids or len(req.ids) > 20:
        raise HTTPException(status_code=422, detail="승인할 제안을 1~20건 고르세요")
    await _step_up(db, admin, req.totp_code)
    try:
        return {"results": await kis_trade.approve(list(dict.fromkeys(req.ids)), admin.id)}
    except Exception as e:
        _err(e)


@router.post("/orders/reject")
async def reject(req: IdsRequest, admin: User = Depends(get_admin)):
    n = await kis_trade.reject(list(dict.fromkeys(req.ids)), admin.id)
    return {"message": f"{n}건 거절했습니다"}


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: int, admin: User = Depends(get_admin)):
    try:
        return {"message": await kis_trade.cancel_sent(order_id, admin.id)}
    except Exception as e:
        _err(e)


@router.post("/notify-test")
async def notify_test(admin: User = Depends(get_admin)):
    """휴대폰 푸시(ntfy) 시험 — 설정이 맞으면 바로 휴대폰에 알림"""
    from app.services import notify
    if not notify.configured():
        raise HTTPException(status_code=503, detail="NTFY_TOPIC 이 없습니다 — backend/.env 에 넣고 서버를 다시 켜세요 (docs/kis-mock-trading.md)")
    try:
        await notify.send("StockApp 알림 시험", "이 알림이 보이면 KIS 모의투자 주문 제안·체결·정지 알림을 휴대폰으로 받을 수 있습니다.", 3, ["bell"])
    except notify.NotifyError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "시험 알림을 보냈습니다 — 휴대폰 ntfy 앱을 확인하세요"}


@router.post("/halt")
async def halt(req: HaltRequest, admin: User = Depends(get_admin)):
    """긴급 정지 — 2단계 코드 없이 바로"""
    return await kis_trade.halt(admin.id, req.reason)


@router.post("/resume")
async def resume(req: CodeRequest, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    await _step_up(db, admin, req.totp_code)
    return await kis_trade.resume(admin.id)


@router.post("/baseline")
async def baseline(req: CodeRequest, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    """지금 KIS 잔고를 앱 기록 기준으로 (HTS·KIS 앱에서 직접 사고팔았을 때)"""
    await _step_up(db, admin, req.totp_code)
    try:
        return await kis_trade.rebaseline(admin.id)
    except Exception as e:
        _err(e)


@router.put("/config")
async def config(req: ConfigRequest, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    try:   # 입력 확인 먼저 (틀린 값에 2단계 코드를 쓰지 않게)
        kis_trade.clean_limits(req.limits or {})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _step_up(db, admin, req.totp_code)
    try:
        return await kis_trade.set_config(admin.id, req.limits, req.params)
    except Exception as e:
        _err(e)
