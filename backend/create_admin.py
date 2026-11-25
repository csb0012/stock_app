"""계정 만들기 · 2단계 인증 해제 (서버/PC 에서 직접 실행 — 서버에 접속할 수 있는 사람만 가능)

  python create_admin.py <아이디> <비밀번호>          계정 만들기
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
        db.add(User(username=username, hashed_password=get_password_hash(password)))
        await db.commit()
        print(f"계정 생성 완료: {username}")
        print("로그인 후 오른쪽 위 내 아이디(마이페이지) → 이메일 인증 · 2단계 인증 켜기 (인터넷에 열린 서버면 강력 권장)")
        return 0


async def reset_totp(username: str):
    await init_db()
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user:
            print(f"없는 아이디입니다: {username}")
            return 1
        user.totp_enabled, user.totp_secret = False, None
        await db.commit()
        print(f"{username} 의 2단계 인증을 껐습니다 — 비밀번호만으로 로그인한 뒤 마이페이지에서 다시 켜세요")
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
    if len(sys.argv) == 3 and sys.argv[1] == "--reset-totp":
        sys.exit(asyncio.run(reset_totp(sys.argv[2])))
    if len(sys.argv) != 3 or sys.argv[1].startswith("--"):
        print(__doc__)
        sys.exit(1)
    sys.exit(asyncio.run(create_admin(sys.argv[1], sys.argv[2])))
