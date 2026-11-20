"""한국투자증권 KIS API 서비스"""
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from app.core.config import settings

KIS_REAL_BASE = "https://openapi.koreainvestment.com:9443"
KIS_MOCK_BASE = "https://openapivts.koreainvestment.com:29443"


class KISClient:
    def __init__(self):
        self.base_url = KIS_REAL_BASE if settings.kis_is_real else KIS_MOCK_BASE
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    async def _get_token(self) -> str:
        if self._access_token and self._token_expires and datetime.now() < self._token_expires:
            return self._access_token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": settings.kis_app_key,
                    "appsecret": settings.kis_app_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires = datetime.now() + timedelta(hours=23)
            return self._access_token

    async def _headers(self, tr_id: str, is_websocket: bool = False) -> dict:
        token = await self._get_token()
        return {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    async def get_kr_stock_price(self, symbol: str) -> dict:
        """국내 주식 현재가 조회"""
        headers = await self._headers("FHKST01010100")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=headers,
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            output = data.get("output", {})
            return {
                "symbol": symbol,
                "market": "KR",
                "price": int(output.get("stck_prpr", 0)),
                "change": int(output.get("prdy_vrss", 0)),
                "change_rate": float(output.get("prdy_ctrt", 0)),
                "volume": int(output.get("acml_vol", 0)),
                "open": int(output.get("stck_oprc", 0)),
                "high": int(output.get("stck_hgpr", 0)),
                "low": int(output.get("stck_lwpr", 0)),
                "market_cap": int(output.get("hts_avls", 0)),
                "per": float(output.get("per", 0)),
                "pbr": float(output.get("pbr", 0)),
                "timestamp": datetime.now().isoformat(),
            }

    async def get_us_stock_price(self, symbol: str, exchange: str = "NAS") -> dict:
        """해외 주식 현재가 조회 (NAS=나스닥, NYS=뉴욕, AMS=아멕스)"""
        headers = await self._headers("HHDFS00000300")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/overseas-price/v1/quotations/price",
                headers=headers,
                params={"AUTH": "", "EXCD": exchange, "SYMB": symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            output = data.get("output", {})
            return {
                "symbol": symbol,
                "market": "US",
                "price": float(output.get("last", 0)),
                "change": float(output.get("diff", 0)),
                "change_rate": float(output.get("rate", 0)),
                "volume": int(output.get("tvol", 0)),
                "open": float(output.get("open", 0)),
                "high": float(output.get("high", 0)),
                "low": float(output.get("low", 0)),
                "timestamp": datetime.now().isoformat(),
            }

    async def get_kr_stock_history(self, symbol: str, period: str = "D", count: int = 100) -> list:
        """국내 주식 일봉/주봉/월봉 조회"""
        headers = await self._headers("FHKST03010100")
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                headers=headers,
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_DATE_1": start_date,
                    "FID_INPUT_DATE_2": end_date,
                    "FID_PERIOD_DIV_CODE": period,
                    "FID_ORG_ADJ_PRC": "0",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            candles = []
            for item in data.get("output2", []):
                candles.append({
                    "date": item.get("stck_bsop_date", ""),
                    "open": int(item.get("stck_oprc", 0)),
                    "high": int(item.get("stck_hgpr", 0)),
                    "low": int(item.get("stck_lwpr", 0)),
                    "close": int(item.get("stck_clpr", 0)),
                    "volume": int(item.get("acml_vol", 0)),
                })
            return candles[:count]

    async def get_us_stock_history(self, symbol: str, exchange: str = "NAS", count: int = 100) -> list:
        """해외 주식 일봉 조회"""
        headers = await self._headers("HHDFS76240000")
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/overseas-price/v1/quotations/dailyprice",
                headers=headers,
                params={
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": symbol,
                    "GUBN": "0",
                    "BYMD": end_date,
                    "MODP": "0",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            candles = []
            for item in data.get("output2", []):
                candles.append({
                    "date": item.get("xymd", ""),
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("clos", 0)),
                    "volume": int(item.get("tvol", 0)),
                })
            return candles[:count]

    async def get_volume_surge_kr(self) -> list:
        """국내 거래량 급증 종목"""
        headers = await self._headers("FHPST01710000")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank",
                headers=headers,
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_COND_SCR_DIV_CODE": "20171",
                    "FID_INPUT_ISCD": "0001",
                    "FID_DIV_CLS_CODE": "0",
                    "FID_BLNG_CLS_CODE": "0",
                    "FID_TRGT_CLS_CODE": "111111111",
                    "FID_TRGT_EXLS_CLS_CODE": "000000",
                    "FID_INPUT_PRICE_1": "1000",
                    "FID_INPUT_PRICE_2": "999999999",
                    "FID_VOL_CNT": "100000",
                    "FID_INPUT_DATE_1": "",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in (data.get("output", []) or [])[:30]:
                results.append({
                    "symbol": item.get("mksc_shrn_iscd", ""),
                    "name": item.get("hts_kor_isnm", ""),
                    "price": int(item.get("stck_prpr", 0)),
                    "change_rate": float(item.get("prdy_ctrt", 0)),
                    "volume": int(item.get("acml_vol", 0)),
                    "volume_ratio": float(item.get("vol_inrt", 0)),
                    "trading_value": int(item.get("acml_tr_pbmn", 0)),
                })
            return results

    async def get_trading_value_kr(self) -> list:
        """국내 거래대금 상위 종목"""
        headers = await self._headers("FHPST01710000")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank",
                headers=headers,
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_COND_SCR_DIV_CODE": "20171",
                    "FID_INPUT_ISCD": "0001",
                    "FID_DIV_CLS_CODE": "1",  # 1 = 거래대금
                    "FID_BLNG_CLS_CODE": "0",
                    "FID_TRGT_CLS_CODE": "111111111",
                    "FID_TRGT_EXLS_CLS_CODE": "000000",
                    "FID_INPUT_PRICE_1": "1000",
                    "FID_INPUT_PRICE_2": "999999999",
                    "FID_VOL_CNT": "100000",
                    "FID_INPUT_DATE_1": "",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in (data.get("output", []) or [])[:30]:
                tv = int(item.get("acml_tr_pbmn", 0))
                results.append({
                    "symbol": item.get("mksc_shrn_iscd", ""),
                    "name": item.get("hts_kor_isnm", ""),
                    "price": int(item.get("stck_prpr", 0)),
                    "change_rate": float(item.get("prdy_ctrt", 0)),
                    "volume": int(item.get("acml_vol", 0)),
                    "trading_value": tv,
                    "trading_value_display": f"{tv // 100_000_000}억" if tv >= 100_000_000 else f"{tv // 1_000_000}백만",
                })
            return results

    async def get_gainers_kr(self) -> list:
        """국내 등락률 상위(급등) 종목"""
        headers = await self._headers("FHPST01700000")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/ranking/fluctuation",
                headers=headers,
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_cond_scr_div_code": "20170",
                    "fid_input_iscd": "0001",
                    "fid_rank_sort_cls_code": "0",  # 0 = 상승률
                    "fid_input_cnt_1": "0",
                    "fid_prc_cls_code": "0",
                    "fid_input_price_1": "1000",
                    "fid_input_price_2": "999999999",
                    "fid_vol_cnt": "100000",
                    "fid_trgt_cls_code": "0",
                    "fid_trgt_exls_cls_code": "0",
                    "fid_div_cls_code": "0",
                    "fid_rsfl_rate1": "",
                    "fid_rsfl_rate2": "",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in (data.get("output", []) or [])[:30]:
                results.append({
                    "symbol": item.get("stck_shrn_iscd", ""),
                    "name": item.get("hts_kor_isnm", ""),
                    "price": int(item.get("stck_prpr", 0)),
                    "change_rate": float(item.get("prdy_ctrt", 0)),
                    "volume": int(item.get("acml_vol", 0)),
                })
            return results

    async def get_losers_kr(self) -> list:
        """국내 등락률 하위(급하향) 종목"""
        headers = await self._headers("FHPST01700000")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/ranking/fluctuation",
                headers=headers,
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_cond_scr_div_code": "20170",
                    "fid_input_iscd": "0001",
                    "fid_rank_sort_cls_code": "1",  # 1 = 하락률
                    "fid_input_cnt_1": "0",
                    "fid_prc_cls_code": "0",
                    "fid_input_price_1": "1000",
                    "fid_input_price_2": "999999999",
                    "fid_vol_cnt": "100000",
                    "fid_trgt_cls_code": "0",
                    "fid_trgt_exls_cls_code": "0",
                    "fid_div_cls_code": "0",
                    "fid_rsfl_rate1": "",
                    "fid_rsfl_rate2": "",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in (data.get("output", []) or [])[:30]:
                results.append({
                    "symbol": item.get("stck_shrn_iscd", ""),
                    "name": item.get("hts_kor_isnm", ""),
                    "price": int(item.get("stck_prpr", 0)),
                    "change_rate": float(item.get("prdy_ctrt", 0)),
                    "volume": int(item.get("acml_vol", 0)),
                })
            return results


kis_client = KISClient()
