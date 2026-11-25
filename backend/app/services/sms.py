"""휴대폰 문자(SMS) 발송 — 회원가입·비밀번호 찾기·휴대폰 번호 등록 인증번호

업체: 솔라피(SOLAPI, solapi.com — 예전 쿨에스엠에스). 개인도 가입 가능, 단문 1건 약 20원(충전식).
설정 (backend/.env): SMS_API_KEY · SMS_API_SECRET · SMS_FROM
- SMS_FROM = 솔라피 콘솔에 **등록·인증한 발신번호** (내 휴대폰 번호도 가능). 등록 안 된 번호로는 통신사가 막음 (발신번호 사전등록제).
- 설정이 없으면 보낸 척하지 않고 오류 (오류 처리 원칙). 오류 문구에 키를 넣지 않음.
- 요금 폭탄 방지: 하루 SMS_DAILY_LIMIT 건(기본 50)까지만 보냄 (+ email_codes 의 IP당 1시간 10건·번호당 60초 제한).

호출 형식 (솔라피 공식 Python SDK solapi 5.x 와 같음):
  POST https://api.solapi.com/messages/v4/send-many/detail   {"messages": [{"to", "from", "text"}]}
  Authorization: HMAC-SHA256 ApiKey=<키>, Date=<ISO8601>, salt=<무작위>, signature=hex(HMAC-SHA256(secret, Date+salt))
"""
import datetime
import hashlib
import hmac
import time
import uuid

import httpx

from app.core.config import settings

API_BASE = "https://api.solapi.com"
_sent_day: dict = {}          # "YYYY-MM-DD" -> 보낸 건수 (서버 재시작하면 0부터)


class SmsError(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.sms_api_key and settings.sms_api_secret and settings.sms_from)


def _auth_header() -> str:
    date = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    salt = uuid.uuid4().hex
    sig = hmac.new(settings.sms_api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    return f"HMAC-SHA256 ApiKey={settings.sms_api_key}, Date={date}, salt={salt}, signature={sig}"


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _check_daily():
    limit = int(settings.sms_daily_limit or 0)
    if limit and _sent_day.get(_today(), 0) >= limit:
        raise SmsError(f"오늘 보낼 수 있는 인증 문자({limit}건)를 다 썼습니다 — 내일 다시 하거나 이메일 인증을 쓰세요")


async def send(to: str, text: str):
    if not configured():
        raise SmsError("문자 발송 설정이 없습니다 — 관리자가 backend/.env 에 SMS_API_KEY·SMS_API_SECRET·SMS_FROM 을 넣어야 합니다")
    _check_daily()
    body = {"messages": [{"to": to, "from": "".join(c for c in settings.sms_from if c.isdigit()), "text": text}]}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{API_BASE}/messages/v4/send-many/detail", json=body,
                             headers={"Authorization": _auth_header(), "Content-Type": "application/json"})
    except httpx.HTTPError as e:
        raise SmsError(f"문자 발송 서버에 연결하지 못했습니다 — {type(e).__name__}")
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        code = data.get("errorCode") or r.status_code
        msg = str(data.get("errorMessage") or r.text[:120])
        if r.status_code in (401, 403) or "Signature" in str(code) or "ApiKey" in str(code):
            raise SmsError(f"문자 발송 계정 인증 실패 — SMS_API_KEY/SMS_API_SECRET 을 확인하세요 ({code})")
        raise SmsError(f"문자 발송 실패 ({code}: {msg[:120]})")
    count = ((data.get("groupInfo") or {}).get("count") or {})
    failed = data.get("failedMessageList") or []
    if failed and count.get("registeredFailed", len(failed)) >= count.get("total", 1):
        f = failed[0]
        # 흔한 실패: 발신번호 미등록(1062 등), 수신번호 형식 오류, 잔액 부족
        raise SmsError(f"문자 접수 실패 — {f.get('statusMessage') or f.get('statusCode') or '원인 모름'} "
                       f"(SMS_FROM 이 솔라피에 등록한 발신번호인지, 잔액이 있는지 확인)")
    _sent_day[_today()] = _sent_day.get(_today(), 0) + 1
    for d in [k for k in _sent_day if k != _today()]:
        _sent_day.pop(d, None)
