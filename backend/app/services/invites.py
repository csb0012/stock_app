"""회원가입 초대 코드 — 관리자가 만든 1회용 코드가 있어야 가입 (내가 믿는 사람만 가입하게).

- 코드: 헷갈리는 글자(0·O·1·I·L)를 뺀 12글자, 4글자씩 하이픈 (예: K7QM-2XRA-9PWD) → 약 60비트라 맞혀서 들어올 수 없음
- DB 에는 HMAC(SECRET_KEY) 해시만 저장. 코드는 만들 때 한 번만 보여줌 (목록에는 끝 4글자만)
- 1회용 · 기본 3일 유효(1~14일) · 사용 전이면 취소 가능 · 사용 가능한 코드는 관리자당 최대 10개
"""
import hashlib
import hmac
import secrets
import time

from sqlalchemy import select, update

from app.core.config import settings
from app.models.user import Invite

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
DAYS_DEFAULT, DAYS_MIN, DAYS_MAX = 3, 1, 14
MAX_ACTIVE = 10


class InviteError(Exception):
    pass


def normalize(code: str) -> str:
    """사용자가 친 코드 → 비교용 (대소문자·하이픈·띄어쓰기 무시)"""
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def _hash(code: str) -> str:
    return hmac.new(settings.secret_key.encode(), ("invite:" + normalize(code)).encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def status_of(inv: Invite, now: float | None = None) -> str:
    now = now or time.time()
    if inv.used_by:
        return "used"
    if inv.revoked:
        return "revoked"
    if inv.expires_at <= now:
        return "expired"
    return "active"


async def create(db, admin_id: int, memo: str | None = None, days: int = DAYS_DEFAULT) -> tuple[Invite, str]:
    """새 초대 코드 → (기록, 코드 원문). 호출한 쪽이 commit"""
    if not (DAYS_MIN <= int(days) <= DAYS_MAX):
        raise InviteError(f"유효 기간은 {DAYS_MIN}~{DAYS_MAX}일입니다")
    now = time.time()
    mine = (await db.execute(select(Invite).where(Invite.created_by == admin_id))).scalars().all()
    if sum(1 for i in mine if status_of(i, now) == "active") >= MAX_ACTIVE:
        raise InviteError(f"아직 안 쓴 초대 코드가 {MAX_ACTIVE}개입니다 — 안 쓸 코드를 취소한 뒤 만드세요")
    code = new_code()
    memo = (memo or "").strip()[:40] or None
    inv = Invite(code_hash=_hash(code), hint=code[-4:], memo=memo, created_by=admin_id, created_at=now,
                 expires_at=now + int(days) * 86400)
    db.add(inv)
    return inv, code


async def find_active(db, code: str) -> Invite:
    """쓸 수 있는 초대 코드 기록 (없거나·썼거나·만료·취소면 InviteError — 이유는 구분하지 않음)"""
    if len(normalize(code)) != 12:
        raise InviteError("초대 코드가 틀렸거나 만료됐습니다 — 초대한 사람에게 새 코드를 받으세요")
    inv = (await db.execute(select(Invite).where(Invite.code_hash == _hash(code)))).scalar_one_or_none()
    if not inv or status_of(inv) != "active":
        raise InviteError("초대 코드가 틀렸거나 만료됐습니다 — 초대한 사람에게 새 코드를 받으세요")
    return inv


async def consume(db, inv: Invite, user_id: int):
    """사용 처리 — 같은 코드로 동시에 두 명이 가입하면 한 명만 성공 (조건부 UPDATE). 호출한 쪽이 commit/rollback"""
    res = await db.execute(update(Invite).where(Invite.id == inv.id, Invite.used_by.is_(None), Invite.revoked.isnot(True),
                                                Invite.expires_at > time.time())
                           .values(used_by=user_id, used_at=time.time()))
    if res.rowcount != 1:
        raise InviteError("초대 코드가 방금 사용됐거나 만료됐습니다 — 새 코드를 받으세요")
