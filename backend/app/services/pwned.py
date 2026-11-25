"""유출된 비밀번호 확인 — Have I Been Pwned 'Pwned Passwords' (무료, 키 불필요, k-익명성)

비밀번호를 SHA-1 로 바꾼 뒤 **앞 5글자만** 보내고(api.pwnedpasswords.com/range/ABCDE),
돌아온 수백 개 목록에서 나머지 35글자를 이 서버 안에서 비교한다 → 비밀번호도 전체 해시도 밖으로 나가지 않음.
Add-Padding 으로 응답 크기에서도 무엇을 찾았는지 알 수 없게 함.

Chrome 의 '비밀번호 유출' 경고와 같은 종류의 목록(다른 사이트에서 털린 비밀번호 모음)이다. 거기 있는 비밀번호는
공격자가 맨 먼저 대입해 보는 목록이라, 가입·변경 때 막고 로그인 때 바꾸라고 알린다.
조회가 안 되면(인터넷 차단·시간 초과) 막지 않고 None — 이 기능 때문에 가입·로그인이 멈추면 안 되므로.
"""
import hashlib

import httpx

from app.core.config import settings

URL = "https://api.pwnedpasswords.com/range/"
_cache: dict = {}   # 앞 5글자 → {나머지: 횟수} (같은 요청 반복 방지, 비밀번호 자체는 저장 안 함)


def _split(password: str) -> tuple:
    h = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    return h[:5], h[5:]


async def _fetch(prefix: str) -> dict:
    async with httpx.AsyncClient(timeout=4) as client:
        r = await client.get(URL + prefix, headers={"Add-Padding": "true", "User-Agent": "StockApp-password-check"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    out = {}
    for line in r.text.splitlines():
        suffix, _, count = line.strip().partition(":")
        if suffix and count.isdigit() and int(count) > 0:   # 패딩 줄은 횟수 0
            out[suffix.upper()] = int(count)
    return out


async def leak_count(password: str) -> int | None:
    """유출 목록에 나온 횟수 (0 = 없음), 확인 못 하면 None"""
    if not settings.pwned_check or not password:
        return None
    prefix, rest = _split(password)
    try:
        if prefix not in _cache:
            if len(_cache) > 500:
                _cache.clear()
            _cache[prefix] = await _fetch(prefix)
        return _cache[prefix].get(rest, 0)
    except Exception as e:   # noqa: BLE001 — 확인 못 해도 가입·로그인은 진행
        print(f"[pwned] 유출 비밀번호 확인 실패 (건너뜀): {type(e).__name__}: {str(e)[:80]}")
        return None
