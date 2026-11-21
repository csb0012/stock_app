"""한국투자증권 KIS API 서비스

- 모든 호출은 _get() 을 거친다: 초당 호출 제한, HTTP 오류, KIS 응답 오류(rt_cd != "0")를
  KISError 로 올려 보낸다. 실패를 빈 목록으로 숨기지 않는다.
"""
import time
import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.core.config import settings

KIS_REAL_BASE = "https://openapi.koreainvestment.com:9443"
KIS_MOCK_BASE = "https://openapivts.koreainvestment.com:29443"


# 발급받은 토큰 저장 파일 (git 제외)
_TOKEN_FILE = Path(__file__).resolve().parents[2] / ".kis_token.json"


class KISError(RuntimeError):
    pass


class KISRateLimitError(KISError):
    """초당 호출 제한(EGW00201)을 재시도 후에도 넘김 — 잠시 뒤 다시 하면 되는 오류"""
    pass


_RATE_RETRIES = 6      # EGW00201 재시도 횟수 (대기 1·2·3·4·5초 → 최대 약 15초 기다림)
_SLOW_SECONDS = 60     # EGW00201 이 나면 이 시간 동안 호출 간격을 2배로


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _tv_display(tv: int) -> str:
    return f"{tv // 100_000_000:,}억" if tv >= 100_000_000 else f"{tv // 1_000_000:,}백만"


class KISClient:
    def __init__(self):
        self.base_url = KIS_REAL_BASE if settings.kis_is_real else KIS_MOCK_BASE
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._token_lock = asyncio.Lock()
        # 실서버 초당 20건, 모의서버 초당 2건 제한 → 여유 두고 간격 유지
        self._base_interval = 0.07 if settings.kis_is_real else 0.55
        self._min_interval = self._base_interval
        self._slow_until = 0.0
        self._rate_lock = asyncio.Lock()
        self._last_call = 0.0
        self._http: Optional[httpx.AsyncClient] = None

    def _client(self) -> httpx.AsyncClient:
        # 연결 재사용(keep-alive) — 요청마다 새로 TLS 연결을 맺으면 호출당 0.1~0.3초씩 더 걸림
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=15.0,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=20),
            )
        return self._http

    def _load_saved_token(self):
        """재시작해도 토큰 재사용 (KIS는 토큰 발급이 1분에 1회로 제한되고, 발급에 시간이 걸림)"""
        try:
            saved = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
            if saved.get("key") != self._token_key():
                return
            expires = datetime.fromisoformat(saved["expires"])
            if datetime.now() < expires:
                self._access_token, self._token_expires = saved["token"], expires
        except (FileNotFoundError, ValueError, KeyError):
            pass

    def _token_key(self) -> str:
        return hashlib.sha256(f"{self.base_url}|{settings.kis_app_key}".encode()).hexdigest()[:16]

    async def _get_token(self) -> str:
        async with self._token_lock:
            if self._access_token is None:
                self._load_saved_token()
            if self._access_token and self._token_expires and datetime.now() < self._token_expires:
                return self._access_token
            resp = await self._client().post(
                f"{self.base_url}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": settings.kis_app_key,
                    "appsecret": settings.kis_app_secret,
                },
            )
            try:
                data = resp.json() if resp.content else {}
            except ValueError:
                data = {}
            if resp.status_code != 200 or "access_token" not in data:
                raise KISError(
                    f"KIS 토큰 발급 실패 (HTTP {resp.status_code}): "
                    f"{data.get('error_description') or data.get('msg1') or resp.text[:200]}"
                )
            self._access_token = data["access_token"]
            self._token_expires = datetime.now() + timedelta(hours=23)
            _TOKEN_FILE.write_text(json.dumps({
                "key": self._token_key(), "token": self._access_token,
                "expires": self._token_expires.isoformat(),
            }), encoding="utf-8")
            return self._access_token

    async def _throttle(self):
        async with self._rate_lock:
            if self._min_interval != self._base_interval and time.monotonic() > self._slow_until:
                self._min_interval = self._base_interval  # 제한 걸린 뒤 1분 지나면 원래 속도로
            wait = self._last_call + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = max(self._last_call, time.monotonic())

    async def _rate_limited(self, attempt: int):
        """EGW00201: 다른 요청들도 같이 멈추고(한 앱키 기준 제한이라) 점점 길게 기다린 뒤 느린 속도로 재개"""
        wait = float(attempt + 1)
        async with self._rate_lock:
            self._last_call = max(self._last_call, time.monotonic() + wait)
            self._min_interval = self._base_interval * 2
            self._slow_until = time.monotonic() + _SLOW_SECONDS
        print(f"[KIS] 초당 호출 제한 — {wait:.0f}초 후 재시도 ({attempt + 1}/{_RATE_RETRIES - 1})")

    async def _get(self, path: str, tr_id: str, params: dict) -> dict:
        token = await self._get_token()
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        for attempt in range(_RATE_RETRIES):
            await self._throttle()
            resp = await self._client().get(f"{self.base_url}{path}", headers=headers, params=params)
            try:
                data = resp.json() if resp.content else {}
            except ValueError:  # 점검 시간 등 HTML 오류 페이지
                data = {}
            # 초당 호출 초과(EGW00201)는 기다렸다가 재시도
            if data.get("msg_cd") == "EGW00201":
                if attempt < _RATE_RETRIES - 1:
                    await self._rate_limited(attempt)
                    continue
                raise KISRateLimitError(
                    f"KIS {tr_id} 실패 (HTTP {resp.status_code}, EGW00201): "
                    f"{data.get('msg1') or '초당 거래건수를 초과하였습니다.'} ({_RATE_RETRIES - 1}회 재시도 후)"
                )
            # 토큰 만료/무효(EGW00123, EGW00121)는 토큰을 새로 받아 재시도
            if data.get("msg_cd") in ("EGW00123", "EGW00121") and attempt < _RATE_RETRIES - 1:
                self._access_token = None
                self._token_expires = None
                _TOKEN_FILE.unlink(missing_ok=True)
                headers["authorization"] = f"Bearer {await self._get_token()}"
                continue
            if resp.status_code != 200 or data.get("rt_cd") != "0":
                raise KISError(
                    f"KIS {tr_id} 실패 (HTTP {resp.status_code}, {data.get('msg_cd', '')}): "
                    f"{data.get('msg1') or resp.text[:200]}"
                )
            return data
        raise KISError(f"KIS {tr_id} 실패: 재시도 횟수 초과")

    # ---------------- 국내 ----------------

    async def get_kr_stock_price(self, symbol: str) -> dict:
        """국내 주식 현재가 조회"""
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price", "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        o = data.get("output", {})
        return {
            "symbol": symbol,
            "market": "KR",
            "price": _int(o.get("stck_prpr")),
            "change": _int(o.get("prdy_vrss")),
            "change_rate": _float(o.get("prdy_ctrt")),
            "volume": _int(o.get("acml_vol")),
            "open": _int(o.get("stck_oprc")),
            "high": _int(o.get("stck_hgpr")),
            "low": _int(o.get("stck_lwpr")),
            "market_cap": _int(o.get("hts_avls")),
            "per": _float(o.get("per")),
            "pbr": _float(o.get("pbr")),
            "timestamp": datetime.now().isoformat(),
        }

    async def get_kr_chart(self, symbol: str, count: int = 120) -> dict:
        """국내 일봉 + 현재가 정보.

        KIS 일봉 API는 한 번에 최대 100개, 최신순으로 준다 → 필요한 개수만큼 기간을 나눠 받고
        날짜 오름차순(오래된 것 → 최신)으로 정렬해서 돌려준다. 장중이면 오늘 봉의 종가 = 현재가.
        """
        rows: dict = {}
        info: dict = {}
        end = datetime.now()
        for _ in range((count + 99) // 100 + 2):  # 연휴로 구간에 100일이 안 찰 수 있어 여유 1회
            start = end - timedelta(days=150)
            data = await self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100",
                {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                    "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "0",  # 0 = 수정주가
                },
            )
            if not info:
                info = data.get("output1", {}) or {}
            batch = [r for r in (data.get("output2") or []) if r.get("stck_bsop_date")]
            for r in batch:
                rows[r["stck_bsop_date"]] = r
            if not batch or len(rows) >= count:
                break
            oldest = min(r["stck_bsop_date"] for r in batch)
            end = datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)

        candles = []
        for d in sorted(rows):
            r = rows[d]
            close = _int(r.get("stck_clpr"))
            if close <= 0:
                continue
            candles.append({
                "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                "open": _int(r.get("stck_oprc")) or close,
                "high": _int(r.get("stck_hgpr")) or close,
                "low": _int(r.get("stck_lwpr")) or close,
                "close": close,
                "volume": _int(r.get("acml_vol")),
            })
        candles = candles[-count:]
        if not candles:
            raise KISError(f"KIS 일봉 데이터 없음: {symbol}")
        return {
            "name": (info.get("hts_kor_isnm") or "").strip(),
            "price": _int(info.get("stck_prpr")) or candles[-1]["close"],
            "change_rate": _float(info.get("prdy_ctrt")),
            "per": _float(info.get("per")),
            "pbr": _float(info.get("pbr")),
            "candles": candles,
        }

    async def get_kr_stock_history(self, symbol: str, count: int = 120) -> list:
        """국내 일봉 (오래된 것 → 최신 순)"""
        return (await self.get_kr_chart(symbol, count))["candles"]

    async def _volume_rank(self, market_iscd: str, blng: str) -> list:
        """거래량순위 (FHPST01710000)
        FID_BLNG_CLS_CODE: 0 평균거래량, 1 거래증가율, 2 평균거래회전율, 3 거래금액순, 4 평균거래금액회전율
        """
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/volume-rank", "FHPST01710000",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_COND_SCR_DIV_CODE": "20171",
                "FID_INPUT_ISCD": market_iscd,
                "FID_DIV_CLS_CODE": "0",           # 0 전체 (보통주+우선주)
                "FID_BLNG_CLS_CODE": blng,
                "FID_TRGT_CLS_CODE": "111111111",
                "FID_TRGT_EXLS_CLS_CODE": "0000000000",
                "FID_INPUT_PRICE_1": "",
                "FID_INPUT_PRICE_2": "",
                "FID_VOL_CNT": "",
                "FID_INPUT_DATE_1": "",
            },
        )
        out = []
        for item in data.get("output") or []:
            tv = _int(item.get("acml_tr_pbmn"))
            out.append({
                "symbol": item.get("mksc_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "market": "KR",
                "price": _int(item.get("stck_prpr")),
                "change_rate": _float(item.get("prdy_ctrt")),
                "volume": _int(item.get("acml_vol")),
                "volume_ratio": _float(item.get("vol_inrt")),
                "trading_value": tv,
                "trading_value_display": _tv_display(tv),
            })
        return out

    async def _fluctuation_rank(self, market_iscd: str, sort: str) -> list:
        """등락률순위 (FHPST01700000) — sort: 0 상승률순, 1 하락률순 (전일 종가 대비)"""
        data = await self._get(
            "/uapi/domestic-stock/v1/ranking/fluctuation", "FHPST01700000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20170",
                "fid_input_iscd": market_iscd,
                "fid_rank_sort_cls_code": sort,
                "fid_input_cnt_1": "0",
                "fid_prc_cls_code": "1",  # 1 = 종가대비
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_trgt_cls_code": "0",
                "fid_trgt_exls_cls_code": "0",
                "fid_div_cls_code": "0",
                "fid_rsfl_rate1": "",
                "fid_rsfl_rate2": "",
            },
        )
        out = []
        for item in data.get("output") or []:
            out.append({
                "symbol": item.get("stck_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "market": "KR",
                "price": _int(item.get("stck_prpr")),
                "change_rate": _float(item.get("prdy_ctrt")),
                "volume": _int(item.get("acml_vol")),
            })
        return out

    async def _both_markets(self, fn, *args) -> list:
        """KOSPI(0001) + KOSDAQ(1001) 순위를 합친다 (API 한 번에 최대 30개라서)."""
        kospi = await fn("0001", *args)
        kosdaq = await fn("1001", *args)
        seen, merged = set(), []
        for r in kospi + kosdaq:
            if r["symbol"] and r["symbol"] not in seen:
                seen.add(r["symbol"])
                merged.append(r)
        return merged

    async def get_volume_surge_kr(self) -> list:
        """거래량 급증 (거래증가율순)"""
        rows = await self._both_markets(self._volume_rank, "1")
        return sorted(rows, key=lambda r: r["volume_ratio"], reverse=True)

    async def get_trading_value_kr(self) -> list:
        """거래대금 상위"""
        rows = await self._both_markets(self._volume_rank, "3")
        return sorted(rows, key=lambda r: r["trading_value"], reverse=True)

    async def get_gainers_kr(self) -> list:
        rows = await self._both_markets(self._fluctuation_rank, "0")
        return sorted(rows, key=lambda r: r["change_rate"], reverse=True)

    async def get_losers_kr(self) -> list:
        rows = await self._both_markets(self._fluctuation_rank, "1")
        return sorted(rows, key=lambda r: r["change_rate"])

    # ---------------- 해외 ----------------

    async def get_us_stock_price(self, symbol: str, exchange: str = "NAS") -> dict:
        """해외 주식 현재가 조회 (NAS=나스닥, NYS=뉴욕, AMS=아멕스)"""
        data = await self._get(
            "/uapi/overseas-price/v1/quotations/price", "HHDFS00000300",
            {"AUTH": "", "EXCD": exchange, "SYMB": symbol},
        )
        o = data.get("output", {})
        return {
            "symbol": symbol,
            "market": "US",
            "price": _float(o.get("last")),
            "change": _float(o.get("diff")),
            "change_rate": _float(o.get("rate")),
            "volume": _int(o.get("tvol")),
            "open": _float(o.get("open")),
            "high": _float(o.get("high")),
            "low": _float(o.get("low")),
            "timestamp": datetime.now().isoformat(),
        }


    async def get_kr_multi_price(self, symbols: list) -> dict:
        """관심종목(멀티종목) 시세 (FHKST11300006) — 최대 30종목을 호출 1번에. {코드: {price, change_rate, volume}}"""
        if not symbols or len(symbols) > 30:
            raise ValueError("멀티종목 시세는 1~30종목")
        params = {}
        for i, s in enumerate(symbols, 1):
            params[f"FID_COND_MRKT_DIV_CODE_{i}"] = "J"
            params[f"FID_INPUT_ISCD_{i}"] = s
        data = await self._get("/uapi/domestic-stock/v1/quotations/intstock-multprice", "FHKST11300006", params)
        rows = data.get("output") or []
        if isinstance(rows, dict):
            rows = [rows]
        out = {}
        for r in rows:
            code, price = (r.get("inter_shrn_iscd") or "").strip(), _int(r.get("inter2_prpr"))
            if code and price > 0:
                out[code] = {"price": price, "change_rate": _float(r.get("prdy_ctrt")), "volume": _int(r.get("acml_vol"))}
        return out

    async def get_kr_index(self, code: str) -> dict:
        """국내 업종 현재지수 (FHPUP02100000) — code: 0001 코스피, 1001 코스닥, 2001 코스피200"""
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-price", "FHPUP02100000",
            {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": code},
        )
        o = data.get("output") or {}
        price = _float(o.get("bstp_nmix_prpr"))
        if price <= 0:
            raise KISError(f"KIS 지수({code}) 응답에 현재지수(bstp_nmix_prpr)가 없음: {str(o)[:150]}")
        change, rate = _float(o.get("bstp_nmix_prdy_vrss")), _float(o.get("bstp_nmix_prdy_ctrt"))
        if o.get("prdy_vrss_sign") in ("4", "5"):  # 하한·하락인데 부호 없이 오는 경우
            change, rate = -abs(change), -abs(rate)
        return {"price": price, "change": change, "change_rate": rate}

    async def get_us_valuation(self, symbol: str, exchange: str = "NAS") -> dict:
        """해외주식 현재가상세(HHDFS76200200) — PER·PBR·시가총액 (미국 종목은 yfinance 에 PER 이 없어서)"""
        data = await self._get(
            "/uapi/overseas-price/v1/quotations/price-detail", "HHDFS76200200",
            {"AUTH": "", "EXCD": exchange, "SYMB": symbol},
        )
        o = data.get("output", {}) or {}
        return {"per": _float(o.get("perx")), "pbr": _float(o.get("pbrx")), "market_cap": _float(o.get("tomv"))}


kis_client = KISClient()
