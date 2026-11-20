import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import (
    verify_password, get_password_hash, create_access_token,
    decode_token, generate_totp_secret, get_totp_uri,
    verify_totp, generate_qr_code_base64,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# 로그인 실패 제한 (클라우드에 올리면 인터넷에서 비밀번호를 무작정 대입하는 공격을 막아야 함)
_FAIL_MAX = 5            # 이 횟수만큼 틀리면
_FAIL_WINDOW = 600       # (10분 안에)
_LOCK_SECONDS = 900      # 15분 동안 로그인 차단
_fails: dict = {}        # ip -> [실패 시각...]
_locked: dict = {}       # ip -> 차단 해제 시각


def _client_ip(request: Request) -> str:
    # 클라우드에선 Caddy 가 앞에서 받아 X-Forwarded-For 로 실제 IP 를 넘겨줌 (백엔드는 Caddy 로만 접근 가능)
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _check_lock(ip: str):
    until = _locked.get(ip, 0)
    if until > time.time():
        raise HTTPException(status_code=429, detail=f"로그인 실패가 많아 {int((until - time.time()) // 60) + 1}분 동안 차단됨")


def _record_fail(ip: str):
    now = time.time()
    fails = [t for t in _fails.get(ip, []) if now - t < _FAIL_WINDOW] + [now]
    _fails[ip] = fails
    if len(fails) >= _FAIL_MAX:
        _locked[ip] = now + _LOCK_SECONDS
        _fails.pop(ip, None)
        print(f"[auth] 로그인 {len(fails)}회 실패 → {ip} 15분 차단")


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None


class TOTPVerifyRequest(BaseModel):
    totp_code: str


class RegisterRequest(BaseModel):
    username: str
    password: str


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.username == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # 개인용 앱: 계정이 하나라도 있으면 외부에서 새 계정을 만들 수 없게 막음
    # (같은 네트워크의 다른 사람이 가입해서 KIS 키로 조회하는 것 방지). 추가 계정은 create_admin.py 로.
    if (await db.execute(select(User).limit(1))).scalar_one_or_none():
        raise HTTPException(status_code=403, detail="이미 계정이 있습니다. 추가 계정은 backend 에서 python create_admin.py 로 만드세요")
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(username=req.username, hashed_password=get_password_hash(req.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "User created", "username": user.username}


@router.post("/login")
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    _check_lock(ip)
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        _record_fail(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # TOTP 검증
    if user.totp_enabled:
        if not req.totp_code:
            return {"requires_totp": True}
        if not verify_totp(user.totp_secret, req.totp_code):
            _record_fail(ip)
            raise HTTPException(status_code=401, detail="Invalid TOTP code")

    _fails.pop(ip, None)
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer", "totp_enabled": user.totp_enabled}


@router.post("/setup-totp")
async def setup_totp(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)
    qr_base64 = generate_qr_code_base64(uri)

    # 임시 저장 (아직 활성화 안 함)
    current_user.totp_secret = secret
    await db.commit()

    return {"qr_code": qr_base64, "secret": secret, "uri": uri}


@router.post("/enable-totp")
async def enable_totp(
    req: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP not set up")
    if not verify_totp(current_user.totp_secret, req.totp_code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    current_user.totp_enabled = True
    await db.commit()
    return {"message": "TOTP enabled successfully"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "totp_enabled": current_user.totp_enabled,
    }
