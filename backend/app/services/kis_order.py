"""KIS 모의투자 서버 주문 API (국내 주식) — 가상 자금 계좌로 진짜 주문 API 를 씀.

- **모의투자 서버(openapivts…:29443) 전용**. 주소가 다르면 주문 함수가 바로 거부 (실거래 계좌로 주문이 나가는 일이 없게)
- 매수는 지정가(앱이 현재가 + 여유로 정함), 매도는 시장가 (손절은 빨리 팔아야 해서)
- 키: .env 의 KIS_MOCK_APP_KEY / KIS_MOCK_APP_SECRET / KIS_MOCK_ACCOUNT_NO. 비어 있고 KIS_IS_REAL=false 면 시세용 키·계좌를 씀
- 주문(POST)은 다시 보내지 않음 — KIS 가 받기 전에 거절한 경우(초당 제한·토큰 만료)만 kis_api._request 가 다시 보냄
- TR(거래 ID)은 2024년에 새 번호가 생겨서 새 번호 → 안 되면 예전 번호 순서로 (조회만. 주문은 '없는 TR' 응답일 때만 예전 번호)
"""
import math
import re
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.services.kis_api import KISClient, KISError, KIS_MOCK_BASE, _int, _float

_TOKEN_FILE = Path(__file__).resolve().parents[2] / ".kis_mock_token.json"

# (새 TR, 예전 TR)
TR = {
    "buy": ("VTTC0012U", "VTTC0802U"),
    "sell": ("VTTC0011U", "VTTC0801U"),
    "cancel": ("VTTC0013U", "VTTC0803U"),
    "balance": ("VTTC8434R",),
    "ccld": ("VTTC0081R", "VTTC8001R"),
}
_tr_ok: dict = {}          # 종류 → 실제로 된 TR (한 번 되면 계속 그 번호)
_UNKNOWN_TR = ("OPSQ0002", "EGW00205")   # '없는 서비스/TR' 계열 응답 (이때만 예전 번호로). OPSQ2000 은 입력값 오류라 넣지 않음


class NotConfigured(KISError):
    pass


class AccountRejected(KISError):
    """모의투자 서버가 계좌번호를 거부 (INVALID_CHECK_ACNO) — 계좌번호·앱키 설정 문제"""
    pass


def account_source() -> str | None:
    """계좌번호를 어디서 읽었는지: KIS_MOCK_ACCOUNT_NO / KIS_ACCOUNT_NO(모의 키가 비어 있어 시세용 계좌) / None"""
    if settings.kis_mock_app_key.strip() and settings.kis_mock_app_secret.strip() and settings.kis_mock_account_no.strip():
        return "KIS_MOCK_ACCOUNT_NO"
    return "KIS_ACCOUNT_NO" if creds() else None


def _account_help(err: str) -> str:
    acc = masked_account()
    if account_source() == "KIS_ACCOUNT_NO":
        return (f"모의투자 서버가 계좌번호 {acc} 를 거부했습니다 (INVALID_CHECK_ACNO). 지금은 backend/.env 의 KIS_MOCK_* 가 비어 있어 "
                f"KIS_ACCOUNT_NO(시세용 계좌번호)를 쓰는 중입니다 — 실전 계좌번호는 모의투자 서버에서 안 됩니다. "
                f"KIS_MOCK_APP_KEY·KIS_MOCK_APP_SECRET·KIS_MOCK_ACCOUNT_NO(모의투자 계좌번호)를 넣고 서버를 다시 켜세요")
    return (f"모의투자 서버가 계좌번호 {acc} 를 거부했습니다 (INVALID_CHECK_ACNO) — ① KIS_MOCK_ACCOUNT_NO 가 모의투자 계좌번호인지 "
            f"(실전 계좌번호 아님, 8자리-2자리) ② KIS_MOCK_APP_KEY 를 이 모의투자 계좌로 발급받았는지 (KIS Developers 에서 앱을 신청할 때 고른 계좌) "
            f"③ 모의투자 신청 기간이 끝나지 않았는지 확인하세요. (KIS 응답: {err[:120]})")


def creds() -> tuple | None:
    """→ (앱키, 시크릿, 계좌번호) 또는 None (주문 기능 꺼짐)"""
    k, s, a = settings.kis_mock_app_key.strip(), settings.kis_mock_app_secret.strip(), settings.kis_mock_account_no.strip()
    if k and s and a:
        return k, s, a
    if not settings.kis_is_real and not (k or s or a):
        return settings.kis_app_key, settings.kis_app_secret, settings.kis_account_no
    return None


def split_account(no: str) -> tuple:
    """'50123456-01' / '5012345601' → ('50123456', '01')"""
    digits = re.sub(r"\D", "", no or "")
    if len(digits) == 8:
        return digits, "01"
    if len(digits) != 10:
        raise NotConfigured("모의투자 계좌번호 형식이 틀림 — 예: 50123456-01 (숫자 8자리 + 2자리)")
    return digits[:8], digits[8:]


def masked_account() -> str | None:
    c = creds()
    if not c:
        return None
    try:
        cano, prdt = split_account(c[2])
    except NotConfigured:
        return "형식 오류"
    return f"****{cano[-4:]}-{prdt}"


_client: KISClient | None = None
_client_key = None


def client() -> KISClient:
    global _client, _client_key
    c = creds()
    if not c:
        raise NotConfigured("KIS 모의투자 키가 없음 — backend/.env 에 KIS_MOCK_APP_KEY·KIS_MOCK_APP_SECRET·KIS_MOCK_ACCOUNT_NO 를 넣고 서버를 다시 켜세요")
    if _client is None or _client_key != c[:2]:
        _client = KISClient(app_key=c[0], app_secret=c[1], base_url=KIS_MOCK_BASE, token_file=_TOKEN_FILE, interval=0.55)
        _client_key = c[:2]
    return _client


def _guard(cl: KISClient):
    if cl.base_url != KIS_MOCK_BASE:   # 코드가 바뀌어도 실거래 서버로는 못 나가게 한 번 더
        raise KISError("실거래 서버 주문은 막혀 있음 — 지금은 모의투자 서버만")


def _account() -> tuple:
    return split_account(creds()[2])


async def _call(kind: str, method: str, path: str, payload: dict) -> dict:
    cl = client()
    _guard(cl)
    trs = (_tr_ok[kind],) if kind in _tr_ok else TR[kind]
    last = None
    for i, tr in enumerate(trs):
        try:
            data = await (cl._get(path, tr, payload) if method == "GET" else cl._post(path, tr, payload))
            _tr_ok[kind] = tr
            return data
        except KISError as e:
            if "INVALID_CHECK_ACNO" in str(e):
                raise AccountRejected(_account_help(str(e))) from e
            last = e
            if i + 1 < len(trs) and any(c in str(e) for c in _UNKNOWN_TR):
                continue
            raise
    raise last


def tick_size(price: float) -> int:
    """국내 주식 호가 단위 (2023년부터 코스피·코스닥 같음). ETF(2천원↑ 5원)도 이 단위의 배수라 그대로 맞음"""
    for limit, tick in ((2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50), (200_000, 100), (500_000, 500)):
        if price < limit:
            return tick
    return 1_000


def tick_up(price: float) -> int:
    """호가 단위로 올림 (매수 지정가 — 정한 가격보다 낮아지지 않게)"""
    t = tick_size(price)
    return int(math.ceil(price / t - 1e-9) * t)


async def order(side: str, symbol: str, qty: int, price: float | None = None) -> dict:
    """주문 → {odno, orgno, time}. side: buy/sell. price 가 있으면 지정가(호가 단위로 맞춘 값), 없으면 시장가"""
    if side not in ("buy", "sell"):
        raise ValueError("side 는 buy/sell")
    if not re.fullmatch(r"[0-9A-Z]{6}", symbol or "") or int(qty) < 1:
        raise ValueError("종목코드(6자리)·수량(1주 이상) 확인")
    if price is not None and (price <= 0 or int(price) != price or int(price) % tick_size(price)):
        raise ValueError(f"지정가 {price} 가 호가 단위({tick_size(price or 1)}원)에 안 맞음")
    cano, prdt = _account()
    data = await _call(side, "POST", "/uapi/domestic-stock/v1/trading/order-cash", {
        "CANO": cano, "ACNT_PRDT_CD": prdt, "PDNO": symbol,
        "ORD_DVSN": "00" if price else "01",            # 00 = 지정가, 01 = 시장가
        "ORD_QTY": str(int(qty)), "ORD_UNPR": str(int(price)) if price else "0",
    })
    o = data.get("output") or {}
    odno = (o.get("ODNO") or o.get("odno") or "").strip()
    if not odno:
        raise KISError(f"KIS 주문 응답에 주문번호가 없음: {data.get('msg1') or str(o)[:150]}")
    return {"odno": odno, "orgno": (o.get("KRX_FWDG_ORD_ORGNO") or o.get("krx_fwdg_ord_orgno") or "").strip(),
            "time": (o.get("ORD_TMD") or o.get("ord_tmd") or "").strip(), "msg": data.get("msg1", "")}


async def cancel(odno: str, orgno: str) -> dict:
    """안 체결된 주문 전량 취소"""
    cano, prdt = _account()
    data = await _call("cancel", "POST", "/uapi/domestic-stock/v1/trading/order-rvsecncl", {
        "CANO": cano, "ACNT_PRDT_CD": prdt, "KRX_FWDG_ORD_ORGNO": orgno, "ORGN_ODNO": odno,
        "ORD_DVSN": "01", "RVSE_CNCL_DVSN_CD": "02", "ORD_QTY": "0", "ORD_UNPR": "0", "QTY_ALL_ORD_YN": "Y",
    })
    return {"msg": data.get("msg1", "")}


async def balance() -> dict:
    """잔고 → {cash, d2_cash, total, stock_value, prev_total, pnl, holdings: [{symbol, name, qty, sellable, avg, price, value, pnl, pnl_pct}]}"""
    cano, prdt = _account()
    # 한 번에 오는 만큼만 (모의투자 한 쪽 = 약 20종목. 개인 계좌라 다음 쪽 조회는 안 함 — 넘으면 오류로 알림)
    data = await _call("balance", "GET", "/uapi/domestic-stock/v1/trading/inquire-balance", {
        "CANO": cano, "ACNT_PRDT_CD": prdt, "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
    })
    holdings = []
    for r in data.get("output1") or []:
        qty = _int(r.get("hldg_qty"))
        if qty <= 0:
            continue
        holdings.append({"symbol": (r.get("pdno") or "").strip(), "name": (r.get("prdt_name") or "").strip(),
                         "qty": qty, "sellable": _int(r.get("ord_psbl_qty")), "avg": _float(r.get("pchs_avg_pric")),
                         "price": _int(r.get("prpr")), "value": _int(r.get("evlu_amt")),
                         "pnl": _int(r.get("evlu_pfls_amt")), "pnl_pct": _float(r.get("evlu_pfls_rt"))})
    if len(data.get("output1") or []) >= 20:
        raise KISError("모의투자 보유 종목이 20개 이상 — 잔고를 끝까지 못 읽어 대조할 수 없음 (종목 수를 줄이세요)")
    o2 = data.get("output2") or []
    if isinstance(o2, dict):
        o2 = [o2]
    summary = o2[0] if o2 else {}
    if not summary:
        raise KISError("KIS 잔고 응답에 계좌 합계(output2)가 없음")
    return {
        "cash": _int(summary.get("dnca_tot_amt")),
        "d2_cash": _int(summary.get("prvs_rcdl_excc_amt")),     # D+2 예수금 (산 돈이 빠진 뒤 실제로 쓸 수 있는 돈)
        "total": _int(summary.get("tot_evlu_amt")),
        "stock_value": _int(summary.get("scts_evlu_amt")),
        "prev_total": _int(summary.get("bfdy_tot_asst_evlu_amt")),
        "pnl": _int(summary.get("evlu_pfls_smtl_amt")),
        "holdings": holdings,
    }


async def executions(day: date | None = None) -> list:
    """그날 주문·체결 (한 번에 오는 만큼 — 하루 주문 횟수 한도가 그보다 작음) → [{odno, side, symbol, name, qty, filled, avg_price, amount, remain, cancelled, cancel_qty, time}]"""
    cano, prdt = _account()
    d = (day or date.today()).strftime("%Y%m%d")
    data = await _call("ccld", "GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld", {
        "CANO": cano, "ACNT_PRDT_CD": prdt, "INQR_STRT_DT": d, "INQR_END_DT": d, "SLL_BUY_DVSN_CD": "00",
        "INQR_DVSN": "00", "PDNO": "", "CCLD_DVSN": "00", "ORD_GNO_BRNO": "", "ODNO": "", "INQR_DVSN_3": "00",
        "INQR_DVSN_1": "", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
    })
    out = []
    for r in data.get("output1") or []:
        odno = (r.get("odno") or "").strip()
        if not odno:
            continue
        out.append({"odno": odno, "side": "sell" if r.get("sll_buy_dvsn_cd") == "01" else "buy",
                    "symbol": (r.get("pdno") or "").strip(), "name": (r.get("prdt_name") or "").strip(),
                    "qty": _int(r.get("ord_qty")), "filled": _int(r.get("tot_ccld_qty")),
                    "avg_price": _float(r.get("avg_prvs")), "amount": _int(r.get("tot_ccld_amt")),
                    "remain": _int(r.get("rmn_qty")), "cancelled": (r.get("cncl_yn") or "").strip() == "Y",
                    "cancel_qty": _int(r.get("cncl_cfrm_qty")),     # 원주문 줄의 취소 확인 수량
                    "time": (r.get("ord_tmd") or "").strip()})
    return out
