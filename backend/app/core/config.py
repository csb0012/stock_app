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
    # KIS 모의투자 주문 (AI 제안 → 관리자 승인 → 모의투자 서버로 주문). 시세용 키와 따로 — 비우면 주문 기능 꺼짐.
    # KIS_IS_REAL=false (시세용 키가 모의투자 키) 면 비워 둬도 위 키·계좌를 그대로 씀. 실거래 서버로는 절대 주문하지 않음
    kis_mock_app_key: str = ""
    kis_mock_app_secret: str = ""
    kis_mock_account_no: str = ""    # 모의투자 계좌번호 (예: 50123456-01)

    # Auth
    secret_key: str = "change-this-secret-key-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720   # 12시간 (예전 24시간 — 브라우저를 뺏겼을 때 쓸 수 있는 시간을 줄임)
    totp_issuer: str = "StockApp"

    # External APIs
    finnhub_api_key: str = ""
    dart_api_key: str = ""
    fred_api_key: str = ""
    # 투자 대가(13F) — SEC 는 자동 요청에 '이름 연락처' 를 적으라고 권함 (예: "StockApp myname@example.com"). 비우면 앱 이름만
    sec_user_agent: str = ""

    # 메일 발송 (회원가입·비밀번호 찾기 인증 코드) — 네이버: smtp.naver.com, 465 (SSL) 또는 587 (STARTTLS)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""              # 보내는 계정 (예: myid@naver.com)
    smtp_password: str = ""          # 네이버 2단계 인증을 쓰면 '애플리케이션 비밀번호'
    smtp_from: str = ""              # 비우면 smtp_user
    signup_open: bool = True         # false 면 회원가입 막음 (기존 계정의 비밀번호 찾기·마이페이지는 그대로)
    invite_only: bool = True         # 관리자가 만든 초대 코드가 있어야 가입 (내가 믿는 사람만). false 면 인증만 하면 누구나
    require_totp: bool = True        # 2단계 인증(Google Authenticator) 필수 — 켜기 전에는 2단계 설정 화면만 쓸 수 있음
    pwned_check: bool = True         # 가입·비밀번호 변경 때 유출 비밀번호 목록(HIBP, 앞 5글자만 전송) 확인. false 면 끔
    login_alert: bool = True         # 처음 보는 IP 로 로그인하면 인증된 이메일로 알림 (메일 설정이 있을 때)

    # 휴대폰 푸시 알림 (ntfy — ntfy.sh 또는 직접 띄운 ntfy 서버). 주제(topic)를 비우면 끔.
    # 주제 이름은 아는 사람 누구나 구독할 수 있으니 길고 무작위로 (다른 앱 알림과 따로)
    ntfy_server: str = "https://ntfy.sh"   # 날씨 알림(weather-app)과 같은 이름·방식 (JSON 으로 보냄)
    ntfy_topic: str = ""
    ntfy_token: str = ""             # 선택 — 주제를 예약·비공개로 했으면 액세스 토큰 (tk_...)
    ntfy_click_url: str = ""         # 선택 — 알림을 누르면 열 웹 사이트 주소 (예: https://mystock.duckdns.org). 비우면 클라우드 DOMAIN
    domain: str = ""                 # 클라우드: deploy/.env 의 DOMAIN (docker-compose.cloud.yml 이 backend 에도 넘김) → 알림 링크 https://DOMAIN/...

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
