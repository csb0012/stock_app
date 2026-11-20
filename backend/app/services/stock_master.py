"""종목 마스터 — 한국투자증권이 매일 배포하는 공식 종목코드 파일 사용

국내: kospi_code.mst / kosdaq_code.mst (주식·ETF·ETN 전체, 고정폭 cp949)
미국: nasmst.cod / nysmst.cod / amsmst.cod (탭 구분 cp949)

손으로 적은 종목코드표를 쓰면 코드가 틀려도 다른 종목 시세가 조용히 표시되므로
(예: SOL AI반도체TOP2플러스 가격 오류) 반드시 이 공식 파일로만 검색·검증한다.
하루 한 번 다시 받으며, 받은 파일은 backend/app/data/master_cache.json 에 저장한다.
"""
import io
import json
import time
import zipfile
import asyncio
from pathlib import Path

import httpx

_BASE = "https://new.real.download.dws.co.kr/common/master"
_CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "master_cache.json"
_REFRESH_SEC = 24 * 3600

# 국내 마스터: 뒤쪽 고정폭 영역 길이 (줄바꿈 제외) — KIS 공식 샘플 기준
_KR_FILES = {
    "KOSPI": ("kospi_code.mst.zip", "kospi_code.mst", 227),
    "KOSDAQ": ("kosdaq_code.mst.zip", "kosdaq_code.mst", 221),
}
_US_FILES = {"NAS": "nasmst.cod.zip", "NYS": "nysmst.cod.zip", "AMS": "amsmst.cod.zip"}

# 신주인수권증권/증서, ELW 는 검색 대상에서 제외
_KR_EXCLUDE_GROUPS = {"SW", "SR", "EW"}

_items: list = []
_by_key: dict = {}
_loaded_at: float = 0.0
_lock = asyncio.Lock()


class MasterError(RuntimeError):
    pass


def _download(name: str) -> bytes:
    resp = httpx.get(f"{_BASE}/{name}", timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        return z.read(z.namelist()[0])


def _parse_kr(raw: bytes, market: str, tail_len: int) -> list:
    out = []
    for row in raw.decode("cp949", errors="replace").splitlines():
        row = row.rstrip("\r\n")
        if len(row) <= tail_len + 21:
            continue
        head, tail = row[: len(row) - tail_len], row[len(row) - tail_len:]
        code = head[0:9].strip()
        name = head[21:].strip()
        group = tail[0:2]
        if not code or not name or group in _KR_EXCLUDE_GROUPS:
            continue
        out.append({
            "symbol": code,
            "name": name,
            "market": "KR",
            "exchange": market,  # KOSPI / KOSDAQ
            "type": "etf" if group == "EF" else "etn" if group == "EN" else "stock",
            "yf": f"{code}.KS" if market == "KOSPI" else f"{code}.KQ",
        })
    # 형식 검증 — 삼성전자가 정확한 이름으로 안 나오면 파일 형식이 바뀐 것
    if market == "KOSPI" and not any(i["symbol"] == "005930" and i["name"] == "삼성전자" for i in out):
        raise MasterError("KOSPI 종목마스터 형식이 예상과 다릅니다 (삼성전자 005930 확인 실패)")
    return out


def _parse_us(raw: bytes, exchange: str) -> list:
    out = []
    for line in raw.decode("cp949", errors="replace").splitlines():
        cols = line.split("\t")
        if len(cols) < 9:
            continue
        sec_type = cols[8].strip()
        if sec_type not in ("2", "3"):  # 2=주식, 3=ETF  (지수·워런트 제외)
            continue
        sym = cols[4].strip()
        if not sym:
            continue
        ticker = sym.replace("/", "-").replace(".", "-")  # BRK/B → BRK-B (yfinance 표기)
        out.append({
            "symbol": ticker,
            "name": cols[6].strip() or cols[7].strip() or ticker,
            "name_en": cols[7].strip(),
            "market": "US",
            "exchange": exchange,  # NAS / NYS / AMS (KIS 해외시세 EXCD)
            "type": "etf" if sec_type == "3" else "stock",
            "yf": ticker,
        })
    return out


def _build_sync() -> list:
    items = []
    for market, (zname, _, tail_len) in _KR_FILES.items():
        items += _parse_kr(_download(zname), market, tail_len)
    for exchange, zname in _US_FILES.items():
        items += _parse_us(_download(zname), exchange)
    if not any(i["symbol"] == "AAPL" for i in items):
        raise MasterError("미국 종목마스터 형식이 예상과 다릅니다 (AAPL 확인 실패)")
    return items


def _set(items: list, ts: float):
    global _items, _by_key, _loaded_at
    _items = items
    _by_key = {(i["market"], i["symbol"]): i for i in items}
    _loaded_at = ts


async def load(force: bool = False):
    """마스터 로드: 캐시가 오늘 것이면 캐시, 아니면 KIS 서버에서 새로 받음."""
    async with _lock:
        if _items and not force and time.time() - _loaded_at < _REFRESH_SEC:
            return
        cache = None
        if _CACHE_PATH.exists():
            cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if not force and time.time() - cache["ts"] < _REFRESH_SEC:
                _set(cache["items"], cache["ts"])
                return
        try:
            items = await asyncio.get_event_loop().run_in_executor(None, _build_sync)
        except Exception as e:
            if cache:
                # 하루 지난 캐시라도 공식 파일이므로 사용 (신규 상장 종목만 빠짐)
                _set(cache["items"], cache["ts"])
                print(f"[stock_master] 종목마스터 갱신 실패, 이전 파일 사용: {e}")
                return
            raise MasterError(f"종목마스터 다운로드 실패 ({_BASE}): {e}") from e
        ts = time.time()
        # data/ 폴더는 git에 빈 폴더로 남지 않으므로 없으면 만든다
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps({"ts": ts, "items": items}, ensure_ascii=False), encoding="utf-8")
        _set(items, ts)


def _norm(s: str) -> str:
    return s.replace(" ", "").lower()


def search(q: str, market: str = "ALL", limit: int = 30) -> list:
    nq = _norm(q)
    if not nq:
        return []
    exact, prefix, contains = [], [], []
    for i in _items:
        if market != "ALL" and i["market"] != market:
            continue
        sym = i["symbol"].lower()
        name = _norm(i["name"])
        name_en = _norm(i.get("name_en", ""))
        if sym == nq or name == nq:
            exact.append(i)
        elif sym.startswith(nq) or name.startswith(nq) or name_en.startswith(nq):
            prefix.append(i)
        elif nq in name or (name_en and nq in name_en):
            contains.append(i)
    # 같은 그룹 안에서는 이름이 짧은 것(대표 종목)이 먼저
    prefix.sort(key=lambda i: len(i["name"]))
    contains.sort(key=lambda i: len(i["name"]))
    return (exact + prefix + contains)[:limit]


def get(market: str, symbol: str) -> dict | None:
    return _by_key.get((market, symbol))


def require(market: str, symbol: str) -> dict:
    item = get(market, symbol)
    if not item:
        raise MasterError(f"종목마스터에 없는 종목입니다: {market} {symbol}")
    return item


def find_by_name(market: str, name: str) -> list:
    """이름이 정확히 같은 종목 (띄어쓰기·대소문자 무시)"""
    n = _norm(name or "")
    if not n:
        return []
    return [i for i in _items if i["market"] == market and _norm(i["name"]) == n]


def category(item: dict) -> str:
    """추천 분류: stock(일반 주식) / spac(스팩) / etf(ETF·ETN)"""
    if item.get("type") in ("etf", "etn"):
        return "etf"
    if item.get("market") == "KR" and "스팩" in (item.get("name") or ""):
        return "spac"
    return "stock"
