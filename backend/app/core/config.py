from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# backend/ 폴더 — 어느 위치에서 실행해도 backend/.env 를 읽도록 절대경로로 고정
BACKEND_DIR = Path(__file__).resolve().parents[2]

# .env.example 에 들어있는 자리표시자 값 — 이 값 그대로면 키를 안 넣은 것으로 본다
_PLACEHOLDERS = {"", "your_app_key_here", "your_app_secret_here", "your_account_number"}


class Settings(BaseSettings):
    # KIS API (필수 — 없으면 서버가 시작되지 않는다)
    kis_app_key: str = Field(default="", validate_default=True)
    kis_app_secret: str = Field(default="", validate_default=True)
    kis_account_no: str = Field(default="", validate_default=True)
    kis_is_real: bool = False

    # Auth
    secret_key: str = "change-this-secret-key-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24시간
    totp_issuer: str = "StockApp"

    # External APIs
    finnhub_api_key: str = ""
    dart_api_key: str = ""
    fred_api_key: str = ""

    # 메일 발송 (회원가입·비밀번호 찾기 인증 코드) — 네이버: smtp.naver.com, 465 (SSL) 또는 587 (STARTTLS)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""              # 보내는 계정 (예: myid@naver.com)
    smtp_password: str = ""          # 네이버 2단계 인증을 쓰면 '애플리케이션 비밀번호'
    smtp_from: str = ""              # 비우면 smtp_user
    signup_open: bool = True         # false 면 회원가입 막음 (기존 계정의 비밀번호 찾기·마이페이지는 그대로)

    # 휴대폰 문자 발송 (이메일 대신 휴대폰으로 본인인증) — 솔라피(solapi.com) API 키
    sms_api_key: str = ""
    sms_api_secret: str = ""
    sms_from: str = ""               # 솔라피에 등록한 발신번호 (예: 01012345678)
    sms_daily_limit: int = 50        # 하루 최대 발송 건수 (요금 폭탄 방지, 0 = 제한 없음)

    # App
    app_env: str = "development"
    frontend_url: str = "http://localhost:5173"

    @field_validator("kis_app_key", "kis_app_secret", "kis_account_no")
    @classmethod
    def _require_kis(cls, v: str, info):
        v = (v or "").strip()
        if v in _PLACEHOLDERS:
            raise ValueError(
                f"{info.field_name.upper()} 가 backend/.env 에 설정되지 않았습니다. "
                f"KIS 키 없이 서버를 실행할 수 없습니다."
            )
        return v

    class Config:
        env_file = str(BACKEND_DIR / ".env")
        case_sensitive = False
        # .env 에 더 이상 안 쓰는 값(예: 예전 ANTHROPIC_API_KEY)이 남아 있어도 서버가 멈추지 않도록 무시
        extra = "ignore"


_SECRET_PLACEHOLDERS = {"", "change-this-secret-key-in-production", "your-very-long-random-secret-key-change-this"}
_SECRET_FILE = BACKEND_DIR / ".secret_key"


def _ensure_secret_key(s: "Settings"):
    """SECRET_KEY 가 예시값이면 로그인 토큰(JWT)을 누구나 위조할 수 있다.
    → 무작위 키를 만들어 backend/.secret_key 에 저장하고 계속 그 키를 사용 (git 제외 파일)."""
    if s.secret_key not in _SECRET_PLACEHOLDERS:
        return
    import secrets
    if _SECRET_FILE.exists():
        s.secret_key = _SECRET_FILE.read_text(encoding="utf-8").strip()
    else:
        s.secret_key = secrets.token_urlsafe(48)
        _SECRET_FILE.write_text(s.secret_key, encoding="utf-8")
        print("[config] SECRET_KEY 가 예시값이라 무작위 키를 생성해 backend/.secret_key 에 저장했습니다 (한 번 다시 로그인 필요)")


settings = Settings()
_ensure_secret_key(settings)
