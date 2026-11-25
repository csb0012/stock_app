import time
from datetime import datetime, timedelta, timezone
from typing import Optional
import pyotp
import qrcode
import io
import base64
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    # iat(발급 시각): 비밀번호를 바꾸면 그 전에 발급된 토큰을 무효로 하기 위해
    to_encode.update({"exp": expire, "iat": int(datetime.now(timezone.utc).timestamp())})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=settings.totp_issuer)


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def _now() -> float:
    return time.time()   # 테스트에서 시각을 고정하려고 따로 둠


def totp_step(secret: str, code: str, now: float | None = None) -> int | None:
    """맞는 코드면 그 코드의 30초 칸 번호 (앞뒤 한 칸 허용 = verify_totp 와 같은 범위), 틀리면 None.
    같은 칸 번호를 두 번 받지 않으면 코드 재사용(엿본 코드로 다시 로그인)을 막을 수 있음"""
    code = (code or "").strip()
    if not secret or not code.isdigit() or len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    t = now if now is not None else _now()
    for off in (0, -1, 1):
        at = t + off * totp.interval
        if totp.at(at) == code:
            return int(at // totp.interval)
    return None


def generate_qr_code_base64(uri: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
