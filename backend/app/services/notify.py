"""휴대폰 푸시 알림 (ntfy) — KIS 모의투자 주문 제안·체결·정지 등을 관리자 휴대폰으로.

- ntfy 앱(안드로이드·아이폰)에서 .env 의 NTFY_TOPIC 을 구독하면 받음. 서버는 NTFY_SERVER (기본 ntfy.sh)
- JSON 으로 보냄 (제목에 한글을 그대로 쓰려고 — 헤더 방식은 한글 제목이 깨짐)
- 주제 이름은 비밀번호처럼 다룸: 로그·오류 문구·화면에 넣지 않음. 보내는 내용에도 토큰·계좌번호 같은 비밀은 안 넣음
- 실패해도 주문 흐름을 막지 않음 (send_bg). 설정이 없으면 아무것도 안 함 (보낸 척 안 함)
"""
import re
from urllib.parse import urlparse

import httpx

from app.core.bg import spawn
from app.core.config import settings

_TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_last: dict = {"ok": None, "error": None, "at": None}


class NotifyError(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.ntfy_topic.strip())


def status() -> dict:
    """화면용 — 주제 이름은 안 보여줌 (켜짐 여부·서버·마지막 결과만)"""
    url = settings.ntfy_server.strip().rstrip("/") or "https://ntfy.sh"
    return {"configured": configured(), "server": re.sub(r"^https?://", "", url), "token": bool(settings.ntfy_token.strip()),
            "link": app_url("/kis"), "last": dict(_last)}


_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(:\d{1,5})?$")


def app_url(path: str = "/") -> str | None:
    """알림을 누르면 열 웹 주소 = 사이트 주소 + path (예: /kis?order=12).
    사이트 주소: NTFY_CLICK_URL(뒤에 붙은 경로는 무시하고 주소만) → 없으면 클라우드 DOMAIN(https://DOMAIN). 둘 다 없으면 None (링크 없이 보냄)"""
    base = settings.ntfy_click_url.strip()
    if base.startswith(("https://", "http://")):
        u = urlparse(base)
        if not u.netloc:
            return None
        origin = f"{u.scheme}://{u.netloc}"
    elif _HOST_RE.fullmatch(settings.domain.strip()):
        origin = f"https://{settings.domain.strip()}"
    else:
        return None
    return origin + (path if path.startswith("/") else "/" + path)


async def send(title: str, message: str, priority: int = 3, tags: list | None = None, click: str | None = None):
    """보내기 (실패하면 NotifyError — 주제 이름이 든 주소는 문구에 안 넣음)"""
    import time
    topic = settings.ntfy_topic.strip()
    if not topic:
        raise NotifyError("NTFY_TOPIC 이 없음 — backend/.env 에 넣고 서버를 다시 켜세요")
    if not _TOPIC_RE.fullmatch(topic):
        raise NotifyError("NTFY_TOPIC 은 영문·숫자·-·_ 64자 이하여야 함")
    url = settings.ntfy_server.strip().rstrip("/") or "https://ntfy.sh"
    if not url.startswith(("https://", "http://")):
        raise NotifyError("NTFY_SERVER 는 https:// 로 시작해야 함")
    body = {"topic": topic, "title": title[:120], "message": message[:3500], "priority": max(1, min(5, int(priority)))}
    if tags:
        body["tags"] = tags
    # click: '/kis?order=12' 같은 경로면 사이트 주소를 붙임. 없으면 NTFY_CLICK_URL 그대로(예전 설정) 또는 사이트 첫 화면
    if click and click.startswith("/"):
        link = app_url(click)
    elif click:
        link = click
    else:
        link = settings.ntfy_click_url.strip() or app_url("/")
    if link and link.startswith(("https://", "http://")):
        body["click"] = link
    headers = {"Authorization": f"Bearer {settings.ntfy_token.strip()}"} if settings.ntfy_token.strip() else {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        _last.update(ok=False, error=f"ntfy 연결 실패: {type(e).__name__}", at=time.time())
        raise NotifyError(_last["error"])
    if r.status_code >= 300:
        try:
            why = r.json().get("error") or ""
        except ValueError:
            why = ""
        hint = " — 토큰(NTFY_TOKEN)이나 주제 권한 확인" if r.status_code in (401, 403) else ""
        _last.update(ok=False, error=f"ntfy 거부 (HTTP {r.status_code}) {why[:100]}{hint}".strip(), at=time.time())
        raise NotifyError(_last["error"])
    _last.update(ok=True, error=None, at=time.time())


def send_bg(title: str, message: str, priority: int = 3, tags: list | None = None, click: str | None = None):
    """뒤에서 보내기 — 실패해도 호출한 쪽은 계속 (로그만)"""
    if not configured():
        return

    async def go():
        try:
            await send(title, message, priority, tags, click)
        except Exception as e:   # noqa: BLE001
            print(f"[notify] ntfy 알림 실패: {str(e)[:150]}")
    try:
        spawn(go())
    except RuntimeError:
        pass
