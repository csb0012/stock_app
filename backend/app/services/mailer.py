"""메일 발송 (SMTP) — 회원가입·비밀번호 찾기·이메일 변경 인증 코드

설정 (backend/.env): SMTP_HOST · SMTP_PORT · SMTP_USER · SMTP_PASSWORD · SMTP_FROM
- 네이버: SMTP_HOST=smtp.naver.com, SMTP_PORT=465(SSL) 또는 587(STARTTLS).
  네이버 메일 → 환경설정 → POP3/IMAP 설정 → 'SMTP 사용: 사용함' 을 켜야 함. 네이버 2단계 인증을 쓰면 '애플리케이션 비밀번호'.
- Gmail 도 같은 방식 (smtp.gmail.com, 465, 앱 비밀번호).
설정이 없으면 보낸 척하지 않고 오류 (오류 처리 원칙). 오류 문구에 비밀번호를 넣지 않음.
"""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


class MailError(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def _build(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    # 네이버는 보내는 주소가 로그인 계정과 같아야 함 → 기본은 SMTP_USER
    msg["From"] = formataddr((settings.totp_issuer or "StockApp", settings.smtp_from or settings.smtp_user))
    msg["To"] = to
    msg.set_content(body)
    return msg


def _send_sync(msg: EmailMessage):
    host, port = settings.smtp_host, int(settings.smtp_port)
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ctx) as s:
                s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                if s.has_extn("starttls"):
                    s.starttls(context=ctx)
                    s.ehlo()
                s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise MailError("메일 계정 로그인 실패 — SMTP_USER/SMTP_PASSWORD 와 네이버 'SMTP 사용' 설정(2단계 인증이면 애플리케이션 비밀번호)을 확인하세요")
    except smtplib.SMTPRecipientsRefused:
        raise MailError("받는 메일 주소를 메일 서버가 거부했습니다 — 주소를 확인하세요")
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"메일 발송 실패 ({host}:{port}) — {type(e).__name__}: {str(e)[:120]}")


async def send(to: str, subject: str, body: str):
    if not configured():
        raise MailError("메일 발송 설정이 없습니다 — 관리자가 backend/.env 에 SMTP_HOST·SMTP_USER·SMTP_PASSWORD 를 넣어야 합니다")
    msg = _build(to, subject, body)
    await asyncio.get_event_loop().run_in_executor(None, _send_sync, msg)
