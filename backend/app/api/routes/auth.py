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
from app.models.user import User, AccountEvent
from app.models.watchlist import WatchlistItem
from app.models.portfolio import PortfolioItem
from app.services import mailer, email_codes, sms
from app.services.email_codes import CodeError, normalize_email, normalize_phone, format_phone
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
    # '모든 기기에서 로그아웃' 이전에 발급된 토큰도 무효
    if user.session_epoch and payload.get("sev") != user.session_epoch:
        raise HTTPException(status_code=401, detail="모든 기기에서 로그아웃했습니다 — 다시 로그인하세요")
    return user


def token_for(user: User) -> str:
    return create_access_token({"sub": user.username, "pwv": user.password_changed_at or 0,
                                "sev": user.session_epoch or 0})


EVENT_KEEP = 100   # 사용자당 활동 기록 보관 개수


async def _event(db, user_id: int, kind: str, request: Request | None, ok: bool = True, detail: str | None = None):
    """계정 활동 기록 (마이페이지 '최근 활동'). 기록 실패가 주 동작을 막지 않게 함"""
    try:
        db.add(AccountEvent(user_id=user_id, at=time.time(), kind=kind, ok=ok, detail=detail,
                            ip=_client_ip(request) if request else None,
                            user_agent=(request.headers.get("user-agent") or "")[:300] if request else None))
        old = (await db.execute(select(AccountEvent.id).where(AccountEvent.user_id == user_id)
                                .order_by(AccountEvent.at.desc(), AccountEvent.id.desc()).offset(EVENT_KEEP))).scalars().all()
        if old:
            await db.execute(delete(AccountEvent).where(AccountEvent.id.in_(old)))
        await db.commit()
    except Exception as e:   # noqa: BLE001
        print(f"[auth] 활동 기록 실패: {type(e).__name__}: {e}")
        await db.rollback()


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


def _phone(p: str) -> str:
    try:
        return normalize_phone(p)
    except CodeError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


def _contact(email: Optional[str], phone: Optional[str]) -> tuple:
    """본인인증 수단: ('email', 주소) 또는 ('phone', 01012345678) — 둘 중 정확히 하나"""
    e, p = (email or "").strip(), (phone or "").strip()
    if bool(e) == bool(p):
        raise HTTPException(status_code=400, detail="이메일 또는 휴대폰 번호 중 하나로 인증하세요")
    return ("email", _email(e)) if e else ("phone", _phone(p))


def _shown(kind: str, target: str) -> str:
    return target if kind == "email" else format_phone(target)


async def _email_owner(db, email: str):
    return (await db.execute(select(User).where(sa_func.lower(User.email) == email, User.email_verified.is_(True))
                             .limit(1))).scalar_one_or_none()


async def _phone_owner(db, phone: str):
    return (await db.execute(select(User).where(User.phone == phone, User.phone_verified.is_(True))
                             .limit(1))).scalar_one_or_none()


async def _owner(db, kind: str, target: str):
    return await (_email_owner(db, target) if kind == "email" else _phone_owner(db, target))


def _require_channel(kind: str):
    if kind == "email" and not mailer.configured():
        raise HTTPException(status_code=503, detail="메일 발송 설정이 없어 인증 메일을 보낼 수 없습니다 — 관리자가 backend/.env 의 SMTP_* 를 설정해야 합니다")
    if kind == "phone" and not sms.configured():
        raise HTTPException(status_code=503, detail="문자 발송 설정이 없어 인증번호를 보낼 수 없습니다 — 관리자가 backend/.env 의 SMS_* 를 설정해야 합니다 (또는 이메일로 인증)")


async def _send_code(db, target: str, purpose: str, ip: str, kind: str = "email"):
    """코드 발급 + 메일/문자 발송. 발송이 실패하면 코드를 지워서 바로 다시 시도할 수 있게"""
    _require_channel(kind)
    try:
        code = await email_codes.issue(db, target, purpose, ip)
    except CodeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    try:
        if kind == "email":
            await mailer.send(target, *email_codes.mail_text(purpose, code))
        else:
            await sms.send(target, email_codes.sms_text(purpose, code))
    except (mailer.MailError, sms.SmsError) as e:
        await db.execute(delete(email_codes.EmailCode).where(email_codes.EmailCode.email == target,
                                                             email_codes.EmailCode.purpose == purpose))
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))


async def _check_code(db, target: str, purpose: str, code: str):
    try:
        await email_codes.verify(db, target, purpose, code)
    except CodeError as e:
        raise HTTPException(status_code=400, detail=str(e))


NICK_RE = re.compile(r"^[가-힣A-Za-z0-9_]{2,12}$")
_RESERVED_NICKS = {"admin", "administrator", "root", "관리자", "운영자", "stockapp"}


async def _check_nickname(db, nick: Optional[str], me_id: Optional[int] = None) -> Optional[str]:
    """닉네임 규칙: 한글·영문·숫자·밑줄 2~12자, 다른 사람의 닉네임·아이디와 같으면 안 됨(대소문자 무시). 빈 값 = 없음"""
    nick = (nick or "").strip()
    if not nick:
        return None
    if not NICK_RE.match(nick):
        raise HTTPException(status_code=400, detail="닉네임은 한글·영문·숫자·밑줄 2~12자로 만드세요 (띄어쓰기 안 됨)")
    if nick.lower() in _RESERVED_NICKS:
        raise HTTPException(status_code=400, detail="쓸 수 없는 닉네임입니다")
    low = nick.lower()
    q = select(User.id).where((sa_func.lower(User.nickname) == low) | (sa_func.lower(User.username) == low))
    if me_id is not None:
        q = q.where(User.id != me_id)
    if (await db.execute(q.limit(1))).first():
        raise HTTPException(status_code=400, detail="이미 쓰고 있는 닉네임입니다")
    return nick


class EmailRequest(BaseModel):
    email: str


class PhoneRequest(BaseModel):
    phone: str


class ContactRequest(BaseModel):
    """이메일 또는 휴대폰 번호 중 하나"""
    email: Optional[str] = None
    phone: Optional[str] = None


class SignupRequest(BaseModel):
    username: str
    password: str
    code: str
    email: Optional[str] = None
    phone: Optional[str] = None
    nickname: Optional[str] = None


class ResetRequest(BaseModel):
    code: str
    new_password: str
    email: Optional[str] = None
    phone: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class EmailVerifyRequest(BaseModel):
    email: str
    code: str


class PhoneVerifyRequest(BaseModel):
    phone: str
    code: str


class ProfileRequest(BaseModel):
    nickname: Optional[str] = None


class RemoveContactRequest(BaseModel):
    kind: str          # email / phone
    password: str


class DeleteAccountRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None


@router.get("/options")
async def auth_options():
    """로그인 화면용: 회원가입 가능 여부 + 본인인증 수단(메일·문자) 설정 여부"""
    return {"signup_open": settings.signup_open, "mail_configured": mailer.configured(),
            "sms_configured": sms.configured()}


@router.post("/signup/send-code")
async def signup_send_code(req: ContactRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.signup_open:
        raise HTTPException(status_code=403, detail="회원가입이 닫혀 있습니다")
    kind, target = _contact(req.email, req.phone)
    if await _owner(db, kind, target):
        what = "이메일" if kind == "email" else "휴대폰 번호"
        raise HTTPException(status_code=400, detail=f"이미 가입된 {what}입니다 — 로그인하거나 비밀번호 찾기를 쓰세요")
    await _send_code(db, target, "signup", _client_ip(request), kind)
    if kind == "email":
        return {"message": f"{target} 로 인증 코드를 보냈습니다 (10분 유효)"}
    return {"message": f"{_shown(kind, target)} 로 인증번호 문자를 보냈습니다 (10분 유효)"}


@router.post("/register")
async def register(req: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """회원가입: 아이디·비밀번호 + 이메일 또는 휴대폰 인증 코드. 가입하면 바로 로그인 토큰을 줌"""
    if not settings.signup_open:
        raise HTTPException(status_code=403, detail="회원가입이 닫혀 있습니다")
    username = (req.username or "").strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="아이디는 영문·숫자·밑줄 3~20자로 만드세요")
    check_password(req.password, username)
    kind, target = _contact(req.email, req.phone)
    if (await db.execute(select(User.id).where((sa_func.lower(User.username) == username.lower())
                                               | (sa_func.lower(User.nickname) == username.lower())).limit(1))).first():
        raise HTTPException(status_code=400, detail="이미 있는 아이디입니다")   # 남의 닉네임과 같은 아이디도 막음 (사칭 방지)
    nickname = await _check_nickname(db, req.nickname)
    if nickname and nickname.lower() == username.lower():
        nickname = None   # 아이디와 같으면 따로 저장할 필요 없음
    if await _owner(db, kind, target):
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다" if kind == "email" else "이미 가입된 휴대폰 번호입니다")
    await _check_code(db, target, "signup", req.code)
    user = User(username=username, hashed_password=get_password_hash(req.password), nickname=nickname)
    if kind == "email":
        user.email, user.email_verified = target, True
    else:
        user.phone, user.phone_verified = target, True
    db.add(user)
    await db.commit()
    await _event(db, user.id, "signup", request, detail="이메일 인증" if kind == "email" else "휴대폰 인증")
    return {"message": "가입 완료", "username": username, "access_token": token_for(user),
            "token_type": "bearer"}


@router.post("/password/forgot")
async def password_forgot(req: ContactRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """비밀번호 찾기: 인증된 이메일 또는 휴대폰으로 코드 발송. 가입 여부를 알려주지 않도록 항상 같은 답"""
    kind, target = _contact(req.email, req.phone)
    _require_channel(kind)
    if kind == "email":
        msg = {"message": f"{target} 가 가입된 이메일이면 인증 코드를 보냈습니다 (10분 유효). 메일이 안 오면 스팸함도 확인하세요"}
    else:
        msg = {"message": f"{_shown(kind, target)} 가 가입된 휴대폰 번호면 인증번호 문자를 보냈습니다 (10분 유효)"}
    if not await _owner(db, kind, target):
        return msg
    await _send_code(db, target, "reset", _client_ip(request), kind)
    return msg


@router.post("/password/reset")
async def password_reset(req: ResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    kind, target = _contact(req.email, req.phone)
    user = await _owner(db, kind, target)
    if not user:
        raise HTTPException(status_code=400, detail="인증 코드가 없거나 만료됐습니다 — 코드를 다시 받으세요")
    check_password(req.new_password, user.username)
    await _check_code(db, target, "reset", req.code)
    user.hashed_password = get_password_hash(req.new_password)
    user.password_changed_at = time.time()
    await db.commit()
    _fails.pop(_client_ip(request), None)
    await _event(db, user.id, "password_reset", request, detail="이메일 인증" if kind == "email" else "휴대폰 인증")
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
        if not user:   # 인증된 휴대폰 번호로도 로그인 (010-1234-5678 / 01012345678)
            try:
                user = await _phone_owner(db, normalize_phone(name))
            except CodeError:
                user = None

    if not user or user.is_active is False or not verify_password(req.password, user.hashed_password):
        _record_fail(ip)
        if user:
            await _event(db, user.id, "login_fail", request, ok=False, detail="비밀번호 틀림")
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다")

    # TOTP 검증
    if user.totp_enabled:
        if not req.totp_code:
            return {"requires_totp": True}
        if not verify_totp(user.totp_secret, req.totp_code):
            _record_fail(ip)
            await _event(db, user.id, "login_fail", request, ok=False, detail="2단계 인증 코드 틀림")
            raise HTTPException(status_code=401, detail="인증 코드가 틀렸습니다 (Google Authenticator 의 6자리, 30초마다 바뀜)")

    _fails.pop(ip, None)
    await _event(db, user.id, "login", request)
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
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="먼저 QR 코드를 만드세요 (setup-totp)")
    if not verify_totp(current_user.totp_secret, req.totp_code):
        raise HTTPException(status_code=400, detail="인증 코드가 틀렸습니다 — 앱에 보이는 6자리를 다시 입력하세요")

    current_user.totp_enabled = True
    await db.commit()
    await _event(db, current_user.id, "totp_on", request)
    return {"message": "2단계 인증을 켰습니다"}


@router.post("/disable-totp")
async def disable_totp(
    req: TOTPVerifyRequest,
    request: Request,
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
    await _event(db, current_user.id, "totp_off", request)
    return {"message": "2단계 인증을 껐습니다"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "totp_enabled": bool(current_user.totp_enabled),
        "nickname": current_user.nickname,
        "display_name": current_user.nickname or current_user.username,
        "email": current_user.email if current_user.email_verified else None,
        "email_verified": bool(current_user.email_verified),
        "phone": format_phone(current_user.phone) if current_user.phone_verified else None,
        "phone_verified": bool(current_user.phone_verified),
        "verified": bool(current_user.email_verified or current_user.phone_verified),   # 본인인증 수단이 하나라도 있음
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "password_changed_at": current_user.password_changed_at,
    }


@router.post("/password/change")
async def password_change(req: ChangePasswordRequest, request: Request, current_user: User = Depends(get_current_user),
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
    await _event(db, current_user.id, "password_change", request)
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
async def email_verify(req: EmailVerifyRequest, request: Request, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    email = _email(req.email)
    owner = await _email_owner(db, email)
    if owner and owner.id != current_user.id:
        raise HTTPException(status_code=400, detail="다른 계정이 쓰는 이메일입니다")
    await _check_code(db, email, "change", req.code)
    current_user.email, current_user.email_verified = email, True
    await db.commit()
    await _event(db, current_user.id, "email_change", request, detail=email)
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
    await db.execute(delete(AccountEvent).where(AccountEvent.user_id == uid))
    await db.execute(delete(User).where(User.id == uid))
    await db.commit()
    return {"message": "탈퇴했습니다 — 관심종목·투자종목도 지웠습니다"}


# ---------------- 휴대폰 번호 등록 · 닉네임 · 연락처 삭제 · 모든 기기 로그아웃 · 활동 기록 ----------------

@router.post("/phone/send-code")
async def phone_send_code(req: PhoneRequest, request: Request, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """내 휴대폰 번호 등록·변경: 새 번호로 인증번호 문자 발송"""
    phone = _phone(req.phone)
    owner = await _phone_owner(db, phone)
    if owner and owner.id != current_user.id:
        raise HTTPException(status_code=400, detail="다른 계정이 쓰는 휴대폰 번호입니다")
    if owner and owner.id == current_user.id:
        raise HTTPException(status_code=400, detail="이미 이 번호로 인증돼 있습니다")
    await _send_code(db, phone, "phone", _client_ip(request), "phone")
    return {"message": f"{format_phone(phone)} 로 인증번호 문자를 보냈습니다 (10분 유효)"}


@router.post("/phone/verify")
async def phone_verify(req: PhoneVerifyRequest, request: Request, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    phone = _phone(req.phone)
    owner = await _phone_owner(db, phone)
    if owner and owner.id != current_user.id:
        raise HTTPException(status_code=400, detail="다른 계정이 쓰는 휴대폰 번호입니다")
    await _check_code(db, phone, "phone", req.code)
    current_user.phone, current_user.phone_verified = phone, True
    await db.commit()
    await _event(db, current_user.id, "phone_change", request, detail=format_phone(phone))
    return {"message": "휴대폰 번호를 인증했습니다 — 비밀번호 찾기·로그인에 이 번호를 쓸 수 있습니다", "phone": format_phone(phone)}


@router.put("/profile")
async def update_profile(req: ProfileRequest, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """닉네임 바꾸기 (빈 값이면 지우고 아이디를 보여줌)"""
    nick = await _check_nickname(db, req.nickname, current_user.id)
    current_user.nickname = nick
    await db.commit()
    return {"message": "닉네임을 바꿨습니다" if nick else "닉네임을 지웠습니다 (아이디가 보입니다)",
            "nickname": nick, "display_name": nick or current_user.username}


@router.post("/contact/remove")
async def remove_contact(req: RemoveContactRequest, request: Request, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """이메일 또는 휴대폰 번호 삭제 — 비밀번호 확인, 본인인증 수단이 하나는 남아야 함 (비밀번호 찾기용)"""
    if req.kind not in ("email", "phone"):
        raise HTTPException(status_code=400, detail="kind 는 email 또는 phone")
    if not verify_password(req.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="비밀번호가 틀렸습니다")
    has = {"email": bool(current_user.email_verified), "phone": bool(current_user.phone_verified)}
    if not has[req.kind]:
        raise HTTPException(status_code=400, detail="등록된 값이 없습니다")
    other = "phone" if req.kind == "email" else "email"
    if not has[other]:
        raise HTTPException(status_code=400, detail="본인인증 수단이 하나는 남아야 합니다 — 다른 수단을 먼저 인증한 뒤 지우세요")
    if req.kind == "email":
        current_user.email, current_user.email_verified = None, False
    else:
        current_user.phone, current_user.phone_verified = None, False
    await db.commit()
    await _event(db, current_user.id, "contact_remove", request, detail="이메일" if req.kind == "email" else "휴대폰 번호")
    return {"message": "이메일을 지웠습니다" if req.kind == "email" else "휴대폰 번호를 지웠습니다"}


@router.post("/logout-all")
async def logout_all(request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """모든 기기에서 로그아웃 — 지금까지 발급된 토큰을 모두 무효로 하고, 지금 화면은 새 토큰으로 계속"""
    current_user.session_epoch = time.time()
    await db.commit()
    await _event(db, current_user.id, "logout_all", request)
    return {"message": "다른 모든 기기·브라우저에서 로그아웃했습니다", "access_token": token_for(current_user),
            "token_type": "bearer"}


@router.get("/activity")
async def account_activity(limit: int = 30, current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """최근 계정 활동 (로그인·실패·비밀번호 변경 …) + 최근 7일 로그인 실패 횟수"""
    limit = max(1, min(int(limit), EVENT_KEEP))
    rows = (await db.execute(select(AccountEvent).where(AccountEvent.user_id == current_user.id)
                             .order_by(AccountEvent.at.desc(), AccountEvent.id.desc()).limit(limit))).scalars().all()
    week = time.time() - 7 * 86400
    fails = (await db.execute(select(sa_func.count()).select_from(AccountEvent).where(
        AccountEvent.user_id == current_user.id, AccountEvent.kind == "login_fail", AccountEvent.at >= week))).scalar()
    return {"items": [{"at": r.at, "kind": r.kind, "ok": bool(r.ok), "ip": r.ip, "user_agent": r.user_agent,
                       "detail": r.detail} for r in rows],
            "recent_failures": int(fails or 0)}
