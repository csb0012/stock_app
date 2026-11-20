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


settings = Settings()
