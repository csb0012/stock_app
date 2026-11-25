"""이메일 6자리 인증 코드 — 발급·확인

- 코드는 HMAC 해시로만 DB 에 저장 (DB 가 새어도 코드를 못 읽음)
- 유효 10분, 코드당 5번 틀리면 무효, 같은 메일·용도는 60초에 한 번만 다시 보냄
- 같은 IP 는 1시간에 10번까지만 보냄 (메일 폭탄·발송 계정 차단 방지)
"""
import hashlib
import hmac
import re
import secrets
import time

from sqlalchemy import delete, select

from app.core.config import settings
from app.models.user import EmailCode

TTL = 600
MAX_ATTEMPTS = 5
COOLDOWN = 60
IP_LIMIT, IP_WINDOW = 10, 3600
PURPOSES = {"signup": "회원가입", "reset": "비밀번호 찾기", "change": "이메일 인증"}
_ip_sent: dict = {}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class CodeError(ValueError):
    """화면에 그대로 보여줄 문구"""


def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if len(e) > 254 or not EMAIL_RE.match(e):
        raise CodeError("이메일 주소 형식이 올바르지 않습니다")
    return e


def _hash(email: str, purpose: str, code: str) -> str:
    return hmac.new(settings.secret_key.encode(), f"{email}|{purpose}|{code}".encode(), hashlib.sha256).hexdigest()


def _check_ip(ip: str | None):
    if not ip:
        return
    now = time.time()
    sent = [t for t in _ip_sent.get(ip, []) if now - t < IP_WINDOW]
    if len(sent) >= IP_LIMIT:
        raise CodeError("인증 메일을 너무 많이 요청했습니다 — 1시간 뒤 다시 시도하세요")
    _ip_sent[ip] = sent


async def issue(db, email: str, purpose: str, ip: str | None = None) -> str:
    """새 코드 발급(이전 코드는 지움) → 코드 문자열 반환 (메일은 호출한 쪽이 보냄)"""
    _check_ip(ip)
    now = time.time()
    last = (await db.execute(select(EmailCode).where(EmailCode.email == email, EmailCode.purpose == purpose)
                             .order_by(EmailCode.created_at.desc()).limit(1))).scalar_one_or_none()
    if last and now - last.created_at < COOLDOWN:
        raise CodeError(f"인증 메일은 {int(COOLDOWN - (now - last.created_at)) + 1}초 뒤에 다시 받을 수 있습니다")
    await db.execute(delete(EmailCode).where(EmailCode.email == email, EmailCode.purpose == purpose))
    await db.execute(delete(EmailCode).where(EmailCode.expires_at < now))   # 지난 코드 정리
    code = f"{secrets.randbelow(10 ** 6):06d}"
    db.add(EmailCode(email=email, purpose=purpose, code_hash=_hash(email, purpose, code),
                     expires_at=now + TTL, attempts=0, created_at=now, ip=ip))
    await db.commit()
    if ip:
        _ip_sent.setdefault(ip, []).append(now)
    return code


async def verify(db, email: str, purpose: str, code: str, consume: bool = True):
    """맞으면 통과(consume 이면 코드 삭제), 틀리면 CodeError"""
    code = (code or "").strip()
    row = (await db.execute(select(EmailCode).where(EmailCode.email == email, EmailCode.purpose == purpose)
                            .order_by(EmailCode.created_at.desc()).limit(1))).scalar_one_or_none()
    if not row or row.expires_at < time.time():
        raise CodeError("인증 코드가 없거나 만료됐습니다 (10분) — 코드를 다시 받으세요")
    if row.attempts >= MAX_ATTEMPTS:
        raise CodeError("인증 코드를 5번 틀려서 무효가 됐습니다 — 코드를 다시 받으세요")
    if not re.fullmatch(r"\d{6}", code) or not hmac.compare_digest(row.code_hash, _hash(email, purpose, code)):
        row.attempts += 1
        await db.commit()
        left = MAX_ATTEMPTS - row.attempts
        raise CodeError(f"인증 코드가 틀렸습니다" + (f" (남은 기회 {left}번)" if left else " — 코드를 다시 받으세요"))
    if consume:
        await db.delete(row)
        await db.commit()


def mail_text(purpose: str, code: str) -> tuple:
    what = PURPOSES[purpose]
    subject = f"[{settings.totp_issuer or 'StockApp'}] {what} 인증 코드 {code}"
    body = (f"{what} 인증 코드: {code}\n\n"
            f"화면에 이 6자리를 입력하세요. 10분 동안만 쓸 수 있습니다.\n"
            f"직접 요청하지 않았다면 이 메일을 무시하세요 (비밀번호는 바뀌지 않습니다).\n")
    return subject, body
