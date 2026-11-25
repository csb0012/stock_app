from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    totp_secret = Column(String, nullable=True)
    totp_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # 이메일 (회원가입·비밀번호 찾기용). 예전 계정은 비어 있음 → 마이페이지에서 인증해서 등록
    email = Column(String, nullable=True, index=True)
    email_verified = Column(Boolean, default=False)
    # 비밀번호를 바꾼 시각(유닉스 초) — 이 전에 발급된 로그인 토큰은 무효 (다른 기기 로그아웃)
    password_changed_at = Column(Float, nullable=True)


class EmailCode(Base):
    """이메일 6자리 인증 코드 (가입·비밀번호 찾기·이메일 변경). 코드는 해시로만 저장"""
    __tablename__ = "email_codes"

    id = Column(Integer, primary_key=True)
    email = Column(String, index=True, nullable=False)
    purpose = Column(String, nullable=False)          # signup / reset / change
    code_hash = Column(String, nullable=False)
    expires_at = Column(Float, nullable=False)        # 유닉스 초
    attempts = Column(Integer, default=0)
    created_at = Column(Float, nullable=False)
    ip = Column(String, nullable=True)
