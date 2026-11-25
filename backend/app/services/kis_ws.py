"""KIS 실시간 체결가 웹소켓 (국내 주식 H0STCNT0) — 현재가를 KIS 가 밀어 주는 대로 받아 메모리에 둠.

- 연결: 국내 장 시간(08:55~15:35, 거래일)에 '누가 보고 있는 종목'이 있을 때만 1개 연결. 보는 종목이 없거나 장이 끝나면 끊음
- 구독: 화면이 /api/stocks/live 로 묻거나 quote.live_prices 가 부른 국내 종목 (2분 동안 안 물으면 구독 해제), 한 연결에 최대 MAX_SUBS 종목
  (KIS 한도는 한 앱키당 41건 — 여유 둠). 넘으면 최근에 물은 종목 우선
- 받은 값: 종목별 현재가·전일 대비·등락률·누적 거래량·체결 시각 → get(종목). FRESH 초가 지나면 오래된 값으로 봄 (REST 로 다시)
- 접속키(approval_key)는 REST /oauth2/Approval 로 받음 (시세용 키와 같은 앱키). KIS 의 PINGPONG 은 그대로 돌려보냄
- 끊기면 5·10·30·60초 뒤 다시 연결. 실패해도 화면은 예전처럼 REST 현재가(15초·1분 갱신)로 동작
- 미국 종목은 아직 REST·yfinance 그대로 (KIS 해외 실시간은 별도 신청이 필요)
"""
import asyncio
import json
import re
import time
from datetime import datetime

from app.core.config import settings
from app.services.market_calendar import _TZ, is_trading_day

WS_REAL = "ws://ops.koreainvestment.com:21000"
WS_MOCK = "ws://ops.koreainvestment.com:31000"
TR = "H0STCNT0"            # 국내주식 실시간체결가 (KRX)
MAX_SUBS = 40
INTEREST_TTL = 120         # 이 시간(초) 동안 안 물은 종목은 구독 해제
FRESH = 10                 # 이 시간(초) 안에 받은 값만 '실시간'으로 씀
OPEN_HM, CLOSE_HM = 8 * 60 + 55, 15 * 60 + 35
BACKOFF = (5, 10, 30, 60)
_CODE = re.compile(r"^[0-9A-Z]{6}$")

_prices: dict = {}         # 종목 → {price, change, change_rate, volume, time, at}
_interest: dict = {}       # 종목 → 마지막으로 물은 시각
_status: dict = {"connected": False, "subscribed": 0, "last_message": None, "last_error": None, "reconnects": 0,
                 "approval_at": None}
_approval: dict = {"key": None, "at": 0.0}


def _now() -> float:
    return time.time()


def _kst() -> datetime:
    return datetime.now(_TZ["KR"])


def in_session(now: datetime | None = None) -> bool:
    now = now or _kst()
    hm = now.hour * 60 + now.minute
    return is_trading_day("KR", now.date()) and OPEN_HM <= hm <= CLOSE_HM


def want(symbols) -> None:
    """이 종목들의 실시간 가격을 원함 (구독 목록에 올림)"""
    t = _now()
    for s in symbols:
        if s and _CODE.fullmatch(str(s)):
            _interest[str(s)] = t


def get(symbol: str, max_age: float = FRESH) -> dict | None:
    """최근 FRESH 초 안에 받은 실시간 가격 (없으면 None)"""
    p = _prices.get(symbol)
    if p and _now() - p["at"] <= max_age:
        return p
    return None


def status() -> dict:
    return {**_status, "watching": len(desired()), "session": in_session()}


def desired() -> list:
    """구독할 종목 — 최근 INTEREST_TTL 초 안에 물은 것, 최근 순 MAX_SUBS 개"""
    t = _now()
    for s in [s for s, at in _interest.items() if t - at > INTEREST_TTL]:
        _interest.pop(s, None)
    return [s for s, _ in sorted(_interest.items(), key=lambda kv: -kv[1])[:MAX_SUBS]]


def _num(v, f=float):
    try:
        return f(v)
    except (TypeError, ValueError):
        return None


def parse(msg: str) -> list:
    """실시간 데이터 '0|H0STCNT0|건수|필드^필드^…' → [{symbol, price, change, change_rate, volume, time}]
    (한 메시지에 여러 건이 붙어 올 수 있음 — 필드 수 ÷ 건수로 나눔). 암호화(1|…)·다른 TR 은 무시"""
    if not msg or msg[0] != "0":
        return []
    parts = msg.split("|", 3)
    if len(parts) < 4 or parts[1] != TR:
        return []
    n = _num(parts[2], int) or 1
    fields = parts[3].split("^")
    size = len(fields) // n if n else 0
    out = []
    for i in range(n):
        r = fields[i * size:(i + 1) * size]
        if len(r) < 14:
            continue
        price = _num(r[2], int)
        if not price or price <= 0:
            continue
        out.append({"symbol": r[0], "time": r[1], "price": price, "change": _num(r[4]),
                    "change_rate": _num(r[5]), "volume": _num(r[13], int)})
    return out


def _store(rows: list):
    t = _now()
    for r in rows:
        _prices[r["symbol"]] = {**{k: v for k, v in r.items() if k != "symbol"}, "at": t}
    if rows:
        _status["last_message"] = datetime.now().isoformat(timespec="seconds")


def _sub_msg(key: str, symbol: str, on: bool) -> str:
    return json.dumps({"header": {"approval_key": key, "custtype": "P", "tr_type": "1" if on else "2", "content-type": "utf-8"},
                       "body": {"input": {"tr_id": TR, "tr_key": symbol}}})


async def approval_key() -> str:
    """웹소켓 접속키 (하루 쓰고 다시 받음)"""
    from app.services.kis_api import kis_client
    if _approval["key"] and _now() - _approval["at"] < 20 * 3600:
        return _approval["key"]
    r = await kis_client._client().post(f"{kis_client.base_url}/oauth2/Approval", json={
        "grant_type": "client_credentials", "appkey": kis_client.app_key, "secretkey": kis_client.app_secret})
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code != 200 or not d.get("approval_key"):
        raise RuntimeError(f"KIS 웹소켓 접속키 발급 실패 (HTTP {r.status_code}): {d.get('error_description') or d.get('msg1') or r.text[:120]}")
    _approval.update(key=d["approval_key"], at=_now())
    _status["approval_at"] = datetime.now().isoformat(timespec="seconds")
    return _approval["key"]


def ws_url() -> str:
    return WS_REAL if settings.kis_is_real else WS_MOCK


async def _handle_control(ws, raw: str):
    """JSON 메시지: PINGPONG 돌려보내기 · 구독 응답 오류 기록"""
    try:
        d = json.loads(raw)
    except ValueError:
        return
    h = d.get("header") or {}
    if h.get("tr_id") == "PINGPONG":
        await ws.send(raw)
        return
    b = d.get("body") or {}
    if b.get("rt_cd") not in (None, "0") and "ALREADY" not in (b.get("msg1") or ""):
        _status["last_error"] = f"{datetime.now().isoformat(timespec='seconds')} 구독 실패 {h.get('tr_key')}: {b.get('msg1')}"


async def session(connect=None):
    """연결 하나를 장이 끝나거나 볼 종목이 없어질 때까지 유지 (connect = 테스트용 대체)"""
    import websockets
    key = await approval_key()
    connect = connect or (lambda url: websockets.connect(url, ping_interval=None, open_timeout=10))
    async with connect(ws_url()) as ws:
        _status.update(connected=True, last_error=None)
        subs: set = set()
        idle_since = None
        try:
            while True:
                want_now = set(desired())
                for s in sorted(want_now - subs):
                    await ws.send(_sub_msg(key, s, True))
                    subs.add(s)
                for s in sorted(subs - want_now):
                    await ws.send(_sub_msg(key, s, False))
                    subs.discard(s)
                _status["subscribed"] = len(subs)
                if not in_session():
                    return "장 시간 끝"
                if not subs:
                    idle_since = idle_since or _now()
                    if _now() - idle_since > 60:
                        return "보는 종목 없음"
                else:
                    idle_since = None
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "replace")
                if raw[:1] in ("0", "1"):
                    _store(parse(raw))
                else:
                    await _handle_control(ws, raw)
        finally:
            _status.update(connected=False, subscribed=0)


async def loop():
    fails = 0
    await asyncio.sleep(5)
    while True:
        if not in_session() or not desired():
            await asyncio.sleep(5)
            continue
        try:
            await session()
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:   # noqa: BLE001 — 끊김·접속키 실패: 기다렸다가 다시 (그동안 화면은 REST 가격)
            _status["last_error"] = f"{datetime.now().isoformat(timespec='seconds')} {type(e).__name__}: {str(e)[:200]}"
            _status["reconnects"] += 1
            wait = BACKOFF[min(fails, len(BACKOFF) - 1)]
            fails += 1
            print(f"[kis_ws] 실시간 연결 실패 — {wait}초 뒤 다시: {str(e)[:150]}")
            await asyncio.sleep(wait)
