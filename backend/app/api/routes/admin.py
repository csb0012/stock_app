"""관리자(앱 주인) 전용: 초대 코드 · 회원 목록 · 회원 차단.

초대 코드 만들기·회원 차단은 지금 앱에 보이는 2단계 인증 코드를 한 번 더 받음 (로그인 토큰만 훔친 사람이 못 하게)."""
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_admin, _use_totp, _event
from app.core.database import get_db
from app.models.user import User, Invite, AccountEvent
from app.services import invites

router = APIRouter(prefix="/admin", tags=["admin"])


class InviteRequest(BaseModel):
    memo: Optional[str] = None
    days: int = invites.DAYS_DEFAULT
    totp_code: str = ""


class ActiveRequest(BaseModel):
    active: bool
    totp_code: str = ""


async def _step_up(db, admin: User, code: str):
    """민감한 관리 작업 전 2단계 코드 다시 확인 (재사용 불가). 2단계를 안 켠 관리자(REQUIRE_TOTP=false)는 통과"""
    if not admin.totp_enabled:
        return
    if not _use_totp(admin, code or ""):
        raise HTTPException(status_code=400, detail="2단계 인증 코드가 틀렸거나 이미 쓴 코드입니다 — 앱의 새 코드를 입력하세요")
    await db.commit()


async def _names(db, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = (await db.execute(select(User.id, User.username, User.nickname).where(User.id.in_(ids)))).all()
    return {r[0]: r[2] or r[1] for r in rows}


@router.get("/invites")
async def list_invites(admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Invite).order_by(Invite.created_at.desc()).limit(50))).scalars().all()
    names = await _names(db, [r.used_by for r in rows])
    now = time.time()
    return {"items": [{"id": r.id, "hint": r.hint, "memo": r.memo, "created_at": r.created_at, "expires_at": r.expires_at,
                       "used_at": r.used_at, "used_by": names.get(r.used_by), "status": invites.status_of(r, now)} for r in rows],
            "days_default": invites.DAYS_DEFAULT, "days_max": invites.DAYS_MAX}


@router.post("/invites")
async def create_invite(req: InviteRequest, request: Request, admin: User = Depends(get_admin),
                        db: AsyncSession = Depends(get_db)):
    """초대 코드 만들기 — 코드 원문은 이 응답에서 한 번만 보여줌 (DB 에는 해시만)"""
    await _step_up(db, admin, req.totp_code)
    try:
        inv, code = await invites.create(db, admin.id, req.memo, req.days)
    except invites.InviteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    await _event(db, admin.id, "invite_create", request, detail=f"…{inv.hint}" + (f" · {inv.memo}" if inv.memo else ""))
    return {"id": inv.id, "code": code, "expires_at": inv.expires_at, "memo": inv.memo,
            "message": "초대 코드를 만들었습니다 — 지금만 보이니 믿는 사람에게 직접 전달하세요 (1회용)"}


@router.delete("/invites/{invite_id}")
async def revoke_invite(invite_id: int, request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    inv = await db.get(Invite, invite_id)
    if not inv:
        raise HTTPException(status_code=404, detail="없는 초대 코드입니다")
    if inv.used_by:
        raise HTTPException(status_code=400, detail="이미 가입에 쓴 코드입니다 — 그 회원을 막으려면 회원 목록에서 차단하세요")
    inv.revoked = True
    await db.commit()
    await _event(db, admin.id, "invite_revoke", request, detail=f"…{inv.hint}")
    return {"message": "초대 코드를 취소했습니다"}


@router.get("/users")
async def list_users(admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    last = dict((await db.execute(select(AccountEvent.user_id, sa_func.max(AccountEvent.at))
                                  .where(AccountEvent.kind == "login").group_by(AccountEvent.user_id))).all())
    names = await _names(db, [u.invited_by for u in users])
    return {"items": [{"id": u.id, "username": u.username, "display_name": u.nickname or u.username,
                       "is_admin": bool(u.is_admin), "is_active": u.is_active is not False, "totp_enabled": bool(u.totp_enabled),
                       "verified": bool(u.email_verified or u.phone_verified), "invited_by": names.get(u.invited_by),
                       "created_at": u.created_at.isoformat() if u.created_at else None, "last_login": last.get(u.id),
                       "me": u.id == admin.id} for u in users]}


@router.put("/users/{user_id}/active")
async def set_user_active(user_id: int, req: ActiveRequest, request: Request, admin: User = Depends(get_admin),
                          db: AsyncSession = Depends(get_db)):
    """회원 차단/해제 — 차단하면 바로 모든 기기에서 끊기고 로그인 못 함 (데이터는 남음)"""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="내 계정은 차단할 수 없습니다")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="없는 회원입니다")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="관리자 계정은 차단할 수 없습니다")
    await _step_up(db, admin, req.totp_code)
    user.is_active = bool(req.active)
    if not req.active:
        user.session_epoch = time.time()   # 이미 로그인한 기기도 끊김
    await db.commit()
    await _event(db, admin.id, "user_unblock" if req.active else "user_block", request, detail=user.username)
    return {"message": f"{user.username} 차단을 풀었습니다" if req.active else f"{user.username} 을(를) 차단했습니다 (모든 기기 로그아웃)"}
