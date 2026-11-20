"""최초 관리자 계정 생성 스크립트"""
import asyncio
from app.core.database import init_db, AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User


async def create_admin(username: str, password: str):
    await init_db()
    async with AsyncSessionLocal() as db:
        user = User(username=username, hashed_password=get_password_hash(password))
        db.add(user)
        await db.commit()
        print(f"계정 생성 완료: {username}")
        print("로그인 후 설정 → Google Authenticator 등록 (강력 권장)")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("사용법: python create_admin.py <username> <password>")
        sys.exit(1)
    asyncio.run(create_admin(sys.argv[1], sys.argv[2]))
