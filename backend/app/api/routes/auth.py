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
from app.models.watchlist import WatchlistItem
from app.models.portfolio import PortfolioItem
from app.services import mailer, email_codes
from app.services.email_codes import CodeError, normalize_email
from app.core.config import settings
from sqlalchemy import delete, func as sa_func
import re

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
    if not user or user.is_active is False:
        raise HTTPException(status_code=401, detail="계정을 찾을 수 없습니다 — 다시 로그인하세요")
    # 비밀번호를 바꾸면 그 전에 발급된 토큰(다른 기기·탈취된 토큰)은 무효 — 토큰의 pwv(비밀번호 버전)가 지금 값과 같아야 함
    if user.password_changed_at and payload.get("pwv") != user.password_changed_at:
        raise HTTPException(status_code=401, detail="비밀번호가 바뀌어 다시 로그인해야 합니다")
    return user


def token_for(user: User) -> str:
    return create_access_token({"sub": user.username, "pwv": user.password_changed_at or 0})


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def check_password(pw: str, username: str = "") -> str:
    """비밀번호 규칙: 8~128자, 영문+숫자 포함, 아이디가 들어가면 안 됨"""
    if not (8 <= len(pw or "") <= 128):
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        raise HTTPException(status_code=400, detail="비밀번호에 영문과 숫자를 함께 넣으세요")
    if username and username.lower() in pw.lower():
        raise HTTPException(status_code=400, detail="비밀번호에 아이디를 넣을 수 없습니다")
    return pw


def _email(e: str) -> str:
    try:
        return normalize_email(e)
    except CodeError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


async def _email_owner(db, email: str):
    return (await db.execute(select(User).where(sa_func.lower(User.email) == email, User.email_verified.is_(True))
                             .limit(1))).scalar_one_or_none()


async def _send_code(db, email: str, purpose: str, ip: str):
    """코드 발급 + 메일 발송. 발송이 실패하면 코드를 지워서 바로 다시 시도할 수 있게"""
    if not mailer.configured():
        raise HTTPException(status_code=503, detail="메일 발송 설정이 없어 인증 메일을 보낼 수 없습니다 — 관리자가 backend/.env 의 SMTP_* 를 설정해야 합니다")
    try:
        code = await email_codes.issue(db, email, purpose, ip)
    except CodeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    try:
        await mailer.send(email, *email_codes.mail_text(purpose, code))
    except mailer.MailError as e:
        await db.execute(delete(email_codes.EmailCode).where(email_codes.EmailCode.email == email,
                                                             email_codes.EmailCode.purpose == purpose))
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))


async def _check_code(db, email: str, purpose: str, code: str):
    try:
        await email_codes.verify(db, email, purpose, code)
    except CodeError as e:
        raise HTTPException(status_code=400, detail=str(e))


class EmailRequest(BaseModel):
    email: str


class SignupRequest(BaseModel):
    username: str
    password: str
    email: str
    code: str


class ResetRequest(BaseModel):
    email: str
    code: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class EmailVerifyRequest(BaseModel):
    email: str
    code: str


class DeleteAccountRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None


@router.get("/options")
async def auth_options():
    """로그인 화면용: 회원가입·비밀번호 찾기를 쓸 수 있는지 (메일 설정 여부)"""
    return {"signup_open": settings.signup_open, "mail_configured": mailer.configured()}


@router.post("/signup/send-code")
async def signup_send_code(req: EmailRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.signup_open:
        raise HTTPException(status_code=403, detail="회원가입이 닫혀 있습니다")
    email = _email(req.email)
    if await _email_owner(db, email):
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다 — 로그인하거나 비밀번호 찾기를 쓰세요")
    await _send_code(db, email, "signup", _client_ip(request))
    return {"message": f"{email} 로 인증 코드를 보냈습니다 (10분 유효)"}


@router.post("/register")
async def register(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    """회원가입: 아이디·비밀번호 + 이메일 인증 코드. 가입하면 바로 로그인 토큰을 줌"""
    if not settings.signup_open:
        raise HTTPException(status_code=403, detail="회원가입이 닫혀 있습니다")
    username = (req.username or "").strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="아이디는 영문·숫자·밑줄 3~20자로 만드세요")
    check_password(req.password, username)
    email = _email(req.email)
    if (await db.execute(select(User).where(sa_func.lower(User.username) == username.lower()))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 있는 아이디입니다")
    if await _email_owner(db, email):
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다")
    await _check_code(db, email, "signup", req.code)
    user = User(username=username, hashed_password=get_password_hash(req.password), email=email, email_verified=True)
    db.add(user)
    await db.commit()
    return {"message": "가입 완료", "username": username, "access_token": token_for(user),
            "token_type": "bearer"}


@router.post("/password/forgot")
async def password_forgot(req: EmailRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """비밀번호 찾기: 인증된 이메일로 코드 발송. 가입 여부를 알려주지 않도록 항상 같은 답"""
    email = _email(req.email)
    msg = {"message": f"{email} 가 가입된 이메일이면 인증 코드를 보냈습니다 (10분 유효). 메일이 안 오면 스팸함도 확인하세요"}
    if not await _email_owner(db, email):
        return msg
    await _send_code(db, email, "reset", _client_ip(request))
    return msg


@router.post("/password/reset")
async def password_reset(req: ResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = _email(req.email)
    user = await _email_owner(db, email)
    if not user:
        raise HTTPException(status_code=400, detail="인증 코드가 없거나 만료됐습니다 — 코드를 다시 받으세요")
    check_password(req.new_password, user.username)
    await _check_code(db, email, "reset", req.code)
    user.hashed_password = get_password_hash(req.new_password)
    user.password_changed_at = time.time()
    await db.commit()
    _fails.pop(_client_ip(request), None)
    return {"message": "비밀번호를 바꿨습니다 — 새 비밀번호로 로그인하세요", "username": user.username}


@router.post("/login")
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    _check_lock(ip)
    name = (req.username or "").strip()
    if "@" in name:   # 인증된 이메일로도 로그인
        user = await _email_owner(db, name.lower())
    else:
        user = (await db.execute(select(User).where(User.username == name))).scalar_one_or_none()

    if not user or user.is_active is False or not verify_password(req.password, user.hashed_password):
        _record_fail(ip)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다")

    # TOTP 검증
    if user.totp_enabled:
        if not req.totp_code:
            return {"requires_totp": True}
        if not verify_totp(user.totp_secret, req.totp_code):
            _record_fail(ip)
            raise HTTPException(status_code=401, detail="인증 코드가 틀렸습니다 (Google Authenticator 의 6자리, 30초마다 바뀜)")

    _fails.pop(ip, None)
    token = token_for(user)
    return {"access_token": token, "token_type": "bearer", "totp_enabled": user.totp_enabled, "username": user.username}


@router.post("/setup-totp")
async def setup_totp(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # 이미 켜져 있는데 새 비밀값으로 덮으면 휴대폰 앱의 코드와 안 맞아 로그인을 못 하게 됨 → 먼저 끄게 함
    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2단계 인증이 이미 켜져 있습니다 — 다시 등록하려면 먼저 끄세요")
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
        raise HTTPException(status_code=400, detail="먼저 QR 코드를 만드세요 (setup-totp)")
    if not verify_totp(current_user.totp_secret, req.totp_code):
        raise HTTPException(status_code=400, detail="인증 코드가 틀렸습니다 — 앱에 보이는 6자리를 다시 입력하세요")

    current_user.totp_enabled = True
    await db.commit()
    return {"message": "2단계 인증을 켰습니다"}


@router.post("/disable-totp")
async def disable_totp(
    req: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2단계 인증 끄기 — 지금 앱에 보이는 코드가 맞아야 함 (로그인 토큰만 훔친 사람이 끄지 못하게)"""
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2단계 인증이 꺼져 있습니다")
    if not verify_totp(current_user.totp_secret, req.totp_code):
        raise HTTPException(status_code=400, detail="인증 코드가 틀렸습니다")
    current_user.totp_enabled = False
    current_user.totp_secret = None
    await db.commit()
    return {"message": "2단계 인증을 껐습니다"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "totp_enabled": bool(current_user.totp_enabled),
        "email": current_user.email if current_user.email_verified else None,
        "email_verified": bool(current_user.email_verified),
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "password_changed_at": current_user.password_changed_at,
    }


@router.post("/password/change")
async def password_change(req: ChangePasswordRequest, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """비밀번호 변경 — 다른 기기의 로그인은 끊기고, 지금 화면은 새 토큰으로 계속"""
    if not verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 틀렸습니다")
    if req.current_password == req.new_password:
        raise HTTPException(status_code=400, detail="새 비밀번호가 지금 비밀번호와 같습니다")
    check_password(req.new_password, current_user.username)
    current_user.hashed_password = get_password_hash(req.new_password)
    current_user.password_changed_at = time.time()
    await db.commit()
    return {"message": "비밀번호를 바꿨습니다 (다른 기기는 다시 로그인해야 함)",
            "access_token": token_for(current_user), "token_type": "bearer"}


@router.post("/email/send-code")
async def email_send_code(req: EmailRequest, request: Request, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """내 이메일 등록·변경: 새 주소로 코드 발송"""
    email = _email(req.email)
    owner = await _email_owner(db, email)
    if owner and owner.id != current_user.id:
        raise HTTPException(status_code=400, detail="다른 계정이 쓰는 이메일입니다")
    if owner and owner.id == current_user.id:
        raise HTTPException(status_code=400, detail="이미 이 이메일로 인증돼 있습니다")
    await _send_code(db, email, "change", _client_ip(request))
    return {"message": f"{email} 로 인증 코드를 보냈습니다 (10분 유효)"}


@router.post("/email/verify")
async def email_verify(req: EmailVerifyRequest, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    email = _email(req.email)
    owner = await _email_owner(db, email)
    if owner and owner.id != current_user.id:
        raise HTTPException(status_code=400, detail="다른 계정이 쓰는 이메일입니다")
    await _check_code(db, email, "change", req.code)
    current_user.email, current_user.email_verified = email, True
    await db.commit()
    return {"message": "이메일을 인증했습니다 — 이제 비밀번호 찾기에 이 주소를 씁니다", "email": email}


@router.post("/delete-account")
async def delete_account(req: DeleteAccountRequest, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """회원 탈퇴 — 비밀번호(+2단계 인증이면 코드) 확인 후 관심종목·투자종목과 함께 삭제. 되돌릴 수 없음"""
    if not verify_password(req.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="비밀번호가 틀렸습니다")
    if current_user.totp_enabled and not verify_totp(current_user.totp_secret, req.totp_code or ""):
        raise HTTPException(status_code=400, detail="2단계 인증 코드가 틀렸습니다")
    uid = current_user.id
    await db.execute(delete(WatchlistItem).where(WatchlistItem.user_id == uid))
    await db.execute(delete(PortfolioItem).where(PortfolioItem.user_id == uid))
    await db.execute(delete(User).where(User.id == uid))
    await db.commit()
    return {"message": "탈퇴했습니다 — 관심종목·투자종목도 지웠습니다"}
