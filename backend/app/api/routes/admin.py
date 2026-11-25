"""관리자(앱 주인) 전용: 요약 · 초대 코드 · 회원 목록·상세(활동 기록) · 회원 차단 · 전체 보안 기록.

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
from app.models.watchlist import WatchlistItem
from app.models.portfolio import PortfolioItem
from app.models.paper import PaperAccount, PaperSim
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


SECURITY_KINDS = ("login_fail", "account_locked", "password_reset", "password_change", "totp_on", "totp_off",
                  "logout_all", "email_change", "phone_change", "contact_remove", "signup",
                  "user_block", "user_unblock", "invite_create", "invite_revoke")


def _mask_email(e: str | None) -> str | None:
    if not e or "@" not in e:
        return None
    name, dom = e.split("@", 1)
    return (name[:2] + "***" if len(name) > 2 else name[:1] + "***") + "@" + dom


def _mask_phone(p: str | None) -> str | None:
    return (p[:3] + "-****-" + p[-4:]) if p and len(p) >= 10 else None


def _ev(r: AccountEvent, names: dict | None = None) -> dict:
    d = {"at": r.at, "kind": r.kind, "ok": bool(r.ok), "ip": r.ip, "user_agent": r.user_agent, "detail": r.detail}
    if names is not None:
        d["user"] = names.get(r.user_id)
    return d


@router.get("/summary")
async def summary(admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    """관리자 첫 화면 숫자: 회원·2단계·차단·사용 가능한 초대·최근 7일 로그인 실패"""
    users = (await db.execute(select(User))).scalars().all()
    now = time.time()
    invs = (await db.execute(select(Invite))).scalars().all()
    week = now - 7 * 86400
    fails = (await db.execute(select(sa_func.count()).select_from(AccountEvent).where(
        AccountEvent.kind == "login_fail", AccountEvent.at >= week))).scalar() or 0
    active_day = (await db.execute(select(sa_func.count(sa_func.distinct(AccountEvent.user_id))).where(
        AccountEvent.kind == "login", AccountEvent.at >= now - 86400))).scalar() or 0
    return {"users": len(users), "active": sum(1 for u in users if u.is_active is not False),
            "blocked": sum(1 for u in users if u.is_active is False),
            "totp_missing": sum(1 for u in users if not u.totp_enabled and u.is_active is not False),
            "admins": sum(1 for u in users if u.is_admin), "invites_active": sum(1 for i in invs if invites.status_of(i, now) == "active"),
            "login_fail_7d": int(fails), "login_users_24h": int(active_day)}


@router.get("/users/{user_id}")
async def user_detail(user_id: int, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    """회원 상세 — 연락처(가림)·로그인 기록·활동 기록·쓰는 기능(관심·투자종목·모의투자 수). 비밀번호·2단계 비밀값은 안 보여줌"""
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="없는 회원입니다")
    evs = (await db.execute(select(AccountEvent).where(AccountEvent.user_id == user_id)
                            .order_by(AccountEvent.at.desc(), AccountEvent.id.desc()).limit(50))).scalars().all()
    week = time.time() - 7 * 86400

    async def cnt(model, col):
        return int((await db.execute(select(sa_func.count()).select_from(model).where(col == user_id))).scalar() or 0)
    names = await _names(db, [u.invited_by])
    return {
        "id": u.id, "username": u.username, "display_name": u.nickname or u.username, "is_admin": bool(u.is_admin),
        "is_active": u.is_active is not False, "totp_enabled": bool(u.totp_enabled),
        "email": _mask_email(u.email) if u.email_verified else None, "phone": _mask_phone(u.phone) if u.phone_verified else None,
        "invited_by": names.get(u.invited_by), "created_at": u.created_at.isoformat() if u.created_at else None,
        "password_leaked": bool(u.password_leaked), "locked_until": u.locked_until if (u.locked_until or 0) > time.time() else None,
        "login_fail_7d": sum(1 for e in evs if e.kind == "login_fail" and e.at >= week),
        "ips": sorted({e.ip for e in evs if e.kind == "login" and e.ip}),
        "usage": {"watchlist": await cnt(WatchlistItem, WatchlistItem.user_id), "portfolio": await cnt(PortfolioItem, PortfolioItem.user_id),
                  "paper_accounts": await cnt(PaperAccount, PaperAccount.user_id), "paper_sims": await cnt(PaperSim, PaperSim.user_id)},
        "events": [_ev(e) for e in evs],
    }


@router.get("/events")
async def security_events(limit: int = 100, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    """전체 회원의 보안 관련 기록 (로그인 실패·잠금·비밀번호·2단계·차단·초대) — 최근 순"""
    rows = (await db.execute(select(AccountEvent).where(AccountEvent.kind.in_(SECURITY_KINDS))
                             .order_by(AccountEvent.at.desc(), AccountEvent.id.desc()).limit(max(1, min(int(limit), 300))))).scalars().all()
    ids = {r.user_id for r in rows}
    names = dict((await db.execute(select(User.id, User.username).where(User.id.in_(ids)))).all()) if ids else {}
    return {"items": [_ev(r, names) for r in rows]}
