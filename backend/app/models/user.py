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
    # 닉네임 (화면에 보이는 이름, 비우면 아이디). 대소문자 무시 중복 금지는 코드에서 검사
    nickname = Column(String, nullable=True, index=True)
    # 휴대폰 번호 (숫자만, 예: 01012345678) — 문자 인증을 마쳐야 phone_verified
    phone = Column(String, nullable=True, index=True)
    phone_verified = Column(Boolean, default=False)
    # '모든 기기에서 로그아웃' 한 시각 — 토큰의 sev 가 이 값과 다르면 무효
    session_epoch = Column(Float, nullable=True)
    # 2단계 인증 코드 재사용 방지: 마지막으로 쓴 코드의 30초 칸 번호 (같은 코드·이전 코드는 다시 못 씀)
    totp_last_step = Column(Integer, nullable=True)
    # 로그인 때 확인한 비밀번호가 유출 목록(HIBP)에 있으면 True → 화면 위에 바꾸라는 경고. 비밀번호를 바꾸면 False
    password_leaked = Column(Boolean, default=False)
    # 관리자(앱 주인) — 초대 코드 만들기·회원 차단. 처음 만든 계정(가장 작은 id)이 자동으로 관리자 (database.init_db)
    is_admin = Column(Boolean, default=False)
    # 누가 초대했는지 (초대 코드를 만든 관리자 id)
    invited_by = Column(Integer, nullable=True)
    # 로그인 실패가 많아 잠긴 시각까지(유닉스 초) — DB 에 남겨서 서버를 다시 켜도 잠금 유지
    locked_until = Column(Float, nullable=True)


class AccountEvent(Base):
    """계정 활동 기록 (로그인 성공·실패, 비밀번호 변경, 연락처 변경, 모든 기기 로그아웃 …) — 사용자당 최근 100개"""
    __tablename__ = "account_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    at = Column(Float, nullable=False)                # 유닉스 초
    kind = Column(String, nullable=False)             # login / login_fail / password_change / ...
    ok = Column(Boolean, default=True)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    detail = Column(String, nullable=True)


class EmailCode(Base):
    """6자리 인증 코드 (가입·비밀번호 찾기·연락처 변경). email 칸 = 받는 곳 (이메일 주소 또는 휴대폰 번호). 코드는 해시로만 저장"""
    __tablename__ = "email_codes"

    id = Column(Integer, primary_key=True)
    email = Column(String, index=True, nullable=False)
    purpose = Column(String, nullable=False)          # signup / reset / change
    code_hash = Column(String, nullable=False)
    expires_at = Column(Float, nullable=False)        # 유닉스 초
    attempts = Column(Integer, default=0)
    created_at = Column(Float, nullable=False)
    ip = Column(String, nullable=True)


class Invite(Base):
    """회원가입 초대 코드 — 관리자가 만든 1회용 코드가 있어야 가입 가능. 코드는 해시로만 저장 (만들 때 한 번만 보여줌)"""
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True)
    code_hash = Column(String, unique=True, index=True, nullable=False)
    hint = Column(String, nullable=True)              # 코드 끝 4글자 (목록에서 구분용)
    memo = Column(String, nullable=True)              # 누구에게 줬는지 (관리자 메모)
    created_by = Column(Integer, nullable=False)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False)
    used_by = Column(Integer, nullable=True)          # 가입한 사용자 id
    used_at = Column(Float, nullable=True)
    revoked = Column(Boolean, default=False)
