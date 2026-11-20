from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # KIS API
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
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

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
