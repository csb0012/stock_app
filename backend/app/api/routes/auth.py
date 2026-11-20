from fastapi import APIRouter, Depends, HTTPException, status
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
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(username=req.username, hashed_password=get_password_hash(req.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "User created", "username": user.username}


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # TOTP 검증
    if user.totp_enabled:
        if not req.totp_code:
            return {"requires_totp": True}
        if not verify_totp(user.totp_secret, req.totp_code):
            raise HTTPException(status_code=401, detail="Invalid TOTP code")

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
