"""계정 만들기 · 2단계 인증 해제 · 초대 코드 (서버/PC 에서 직접 실행 — 서버에 접속할 수 있는 사람만 가능)

  python create_admin.py <아이디> <비밀번호>          계정 만들기 (관리자가 아직 없으면 이 계정이 관리자)
  python create_admin.py --invite [메모]              초대 코드 만들기 (3일 유효, 1회용) — 화면에 들어갈 수 없을 때
  python create_admin.py --list                      계정 목록 (누가 관리자인지 · 2단계 등록 · 차단 여부)
  python create_admin.py --admin <아이디>             관리자를 이 계정으로 바꾸기 (다른 관리자는 해제)
  python create_admin.py --reset-totp <아이디>        2단계 인증 끄기 (휴대폰 분실 등 — 관심종목·투자종목은 그대로)
  python create_admin.py --reset-password <아이디> <새 비밀번호>
                                                    비밀번호 바꾸기 (이메일 인증을 안 해서 '비밀번호 찾기'를 못 쓸 때)
"""
import time
import asyncio
import sys

from sqlalchemy import select

from app.core.database import init_db, AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User


async def create_admin(username: str, password: str):
    await init_db()
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
            print(f"이미 있는 아이디입니다: {username}")
            return 1
        has_admin = (await db.execute(select(User.id).where(User.is_admin.is_(True)).limit(1))).first()
        db.add(User(username=username, hashed_password=get_password_hash(password), is_admin=not has_admin,
                    session_epoch=time.time()))   # 같은 아이디로 예전에 있던 계정의 토큰은 안 통하게
        await db.commit()
        print(f"계정 생성 완료: {username}" + ("" if has_admin else " (관리자)"))
        print("로그인하면 먼저 2단계 인증(Google Authenticator) QR 등록 화면이 나옵니다 — 등록해야 다른 화면을 쓸 수 있음")
        return 0


async def make_invite(memo: str | None):
    from app.services import invites
    await init_db()
    async with AsyncSessionLocal() as db:
        admin = (await db.execute(select(User).where(User.is_admin.is_(True)).limit(1))).scalar_one_or_none()
        if not admin:
            print("관리자 계정이 없습니다 — 먼저 python create_admin.py <아이디> <비밀번호>")
            return 1
        try:
            inv, code = await invites.create(db, admin.id, memo)
        except invites.InviteError as e:
            print(e)
            return 1
        await db.commit()
        print(f"초대 코드: {code}   (1회용, {invites.DAYS_DEFAULT}일 유효 — 믿는 사람에게 직접 전달)")
        return 0


async def list_users():
    await init_db()   # 관리자가 없으면 여기서 가장 먼저 만든 계정이 관리자가 됨 (서버 시작 때와 같음)
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    if not users:
        print("계정이 없습니다 — python create_admin.py <아이디> <비밀번호>")
        return 1
    print(f"{'번호':>4}  {'아이디':<20} {'관리자':<6} {'2단계':<6} {'상태':<6} 가입일")
    for u in users:
        print(f"{u.id:>4}  {u.username:<20} {'관리자' if u.is_admin else '-':<6} {'등록' if u.totp_enabled else '미등록':<6} "
              f"{'차단' if u.is_active is False else '정상':<6} {u.created_at.strftime('%Y-%m-%d') if u.created_at else '-'}")
    admins = [u.username for u in users if u.is_admin]
    print(f"\n관리자: {', '.join(admins)}  — 관리자 페이지는 이 계정으로 로그인해야 보입니다."
          f" 바꾸려면 python create_admin.py --admin <아이디>")
    return 0


async def set_admin(username: str):
    await init_db()
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user:
            print(f"없는 아이디입니다: {username}")
            return 1
        for u in (await db.execute(select(User).where(User.is_admin.is_(True)))).scalars().all():
            u.is_admin = False
        user.is_admin = True
        await db.commit()
        print(f"{username} 을(를) 관리자로 정했습니다 (다른 계정의 관리자 권한은 해제) — 화면을 새로고침하면 왼쪽 메뉴 아래 '관리자 전용'이 보입니다")
        return 0


async def reset_totp(username: str):
    await init_db()
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user:
            print(f"없는 아이디입니다: {username}")
            return 1
        user.totp_enabled, user.totp_secret, user.totp_last_step = False, None, None
        await db.commit()
        print(f"{username} 의 2단계 인증을 지웠습니다 — 로그인하면 새 휴대폰으로 QR 등록 화면이 나옵니다")
        return 0


async def reset_password(username: str, password: str):
    from fastapi import HTTPException
    from app.api.routes.auth import check_password
    try:
        check_password(password, username)
    except HTTPException as e:
        print(e.detail)
        return 1
    await init_db()
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user:
            print(f"없는 아이디입니다: {username}")
            return 1
        user.hashed_password = get_password_hash(password)
        user.password_changed_at = time.time()   # 다른 기기의 로그인은 끊김
        await db.commit()
        print(f"{username} 의 비밀번호를 바꿨습니다 — 모든 기기에서 새 비밀번호로 다시 로그인하세요")
        return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--reset-password":
        sys.exit(asyncio.run(reset_password(sys.argv[2], sys.argv[3])))
    if len(sys.argv) in (2, 3) and sys.argv[1] == "--invite":
        sys.exit(asyncio.run(make_invite(sys.argv[2] if len(sys.argv) == 3 else None)))
    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        sys.exit(asyncio.run(list_users()))
    if len(sys.argv) == 3 and sys.argv[1] == "--admin":
        sys.exit(asyncio.run(set_admin(sys.argv[2])))
    if len(sys.argv) == 3 and sys.argv[1] == "--reset-totp":
        sys.exit(asyncio.run(reset_totp(sys.argv[2])))
    if len(sys.argv) != 3 or sys.argv[1].startswith("--"):
        print(__doc__)
        sys.exit(1)
    sys.exit(asyncio.run(create_admin(sys.argv[1], sys.argv[2])))
