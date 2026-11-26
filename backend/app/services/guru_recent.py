"""투자 대가의 '13F 이후' 최근 매매 — 분기마다 45일 늦는 13F 보다 빠른 공시 (사용자 요청 2026-11-26)

1. SEC Form 4 (내부자·10%↑ 주주 매매, 거래 뒤 2영업일 안 공시): 대가(운용사 CIK)가 보고자인 공시만, 장내 매수(P)·매도(S)만
   — 대가 자기 회사 주식(예: 버크셔 이사들의 BRK 거래)은 뺌. 종목 티커·가격·거래 후 보유 수량이 공시에 그대로 있음
2. SEC 13D/13G (5%↑ 지분 신고, 13D 는 5영업일 안·13G 는 분기 끝 45일 안): 처음 신고 = 새로 5%↑, 정정 = 지분율 변화
3. ARK(캐시 우드) 매일 보유 파일 (ark-funds.com, 펀드 6개): 하루 전과 비교한 수량 변화 = 매일 매매. 서버가 받은 날부터 쌓임

모두 그 날짜에 공개된 정보 — 검증(따라 사기)엔 공시일(ARK 는 파일 날짜) **다음 거래일**부터 산 것으로 셈 (gurus.validate 와 같음).
"""
import csv
import io
import re
from datetime import date, timedelta

RECENT_DAYS = 365          # 검증용 1년 (화면엔 최근 13F 기준일 이후만)
MAX_PER_GURU = 40          # 대가당 최근 공시 최대 (버크셔처럼 자기 회사 Form 4 가 많은 곳 — 받아 봐야 앎)
FORMS_4 = {"4"}
FORMS_13 = {"SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A", "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}
ARK_FUNDS = {
    "ARKK": ["ARK_INNOVATION_ETF_ARKK_HOLDINGS"],
    "ARKW": ["ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS"],
    "ARKG": ["ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS"],
    "ARKQ": ["ARK_AUTONOMOUS_TECH._%26_ROBOTICS_ETF_ARKQ_HOLDINGS"],
    "ARKF": ["ARK_BLOCKCHAIN_%26_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS"],
    "ARKX": ["ARK_SPACE_%26_DEFENSE_INNOVATION_ETF_ARKX_HOLDINGS", "ARK_SPACE_EXPLORATION_%26_INNOVATION_ETF_ARKX_HOLDINGS"],
}
ARK_URL = "https://assets.ark-funds.com/fund-documents/funds-etf-csv/{}.csv"
ARK_KEEP_DAYS = 120
ARK_MIN_CHANGE = 0.05      # 하루 수량 변화 5%↑ 만 '매매'로 (작은 조정은 뺌)


def recent_filings(sub: dict, since: str) -> list:
    """submissions JSON → since 이후 Form 4·13D/13G [{form, acc, filed, doc}] 최신 순"""
    r = (sub or {}).get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(r.get("form", [])):
        if (form in FORMS_4 or form in FORMS_13) and r["filingDate"][i] >= since:
            out.append({"form": form, "acc": r["accessionNumber"][i], "filed": r["filingDate"][i],
                        "doc": (r.get("primaryDocument") or [""] * (i + 1))[i]})
    out.sort(key=lambda x: x["filed"], reverse=True)
    return out


def _vals(xml: str, tag: str) -> list:
    """<tag>값</tag> 또는 <tag><value>값</value></tag> 의 값들 (이름공간 접두어 무시)"""
    return [v.strip() for v in re.findall(rf"<(?:\w+:)?{tag}>\s*(?:<(?:\w+:)?value>)?\s*([^<]*)", xml)]


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def clean_ticker(t) -> str | None:
    """공시에 적힌 티커 → 미국 상장 티커 모양만 (N/A·NONE·비상장 표시는 None). BRK.B → BRK-B"""
    t = (t or "").strip().upper().replace(".", "-").replace("/", "-")
    if t in ("", "NONE", "N-A", "NA", "N/A") or not re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", t):
        return None
    return t


def parse_form4(xml: str, owner_cik: int) -> list:
    """Form 4 → 대가가 보고자인 장내 매수·매도 [{date, ticker, issuer, issuer_cik, side, shares, price, after}].
    대가가 보고자가 아니거나(그 회사가 '발행회사'인 공시), 자기 회사 주식이면 빈 목록"""
    owners = {int(c) for c in _vals(xml, "rptOwnerCik") if c.isdigit()}
    issuer_cik = int((_vals(xml, "issuerCik") or ["0"])[0] or 0)
    if owner_cik not in owners or issuer_cik == owner_cik:
        return []
    ticker = clean_ticker((_vals(xml, "issuerTradingSymbol") or [""])[0])
    issuer = (_vals(xml, "issuerName") or [""])[0]
    out = []
    for block in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", xml, flags=re.S):
        code = (_vals(block, "transactionCode") or [""])[0]
        if code not in ("P", "S"):
            continue
        out.append({"date": (_vals(block, "transactionDate") or [""])[0][:10], "ticker": ticker, "issuer": issuer,
                    "issuer_cik": issuer_cik, "side": "buy" if code == "P" else "sell",
                    "shares": _num((_vals(block, "transactionShares") or [None])[0]),
                    "price": _num((_vals(block, "transactionPricePerShare") or [None])[0]),
                    "after": _num((_vals(block, "sharesOwnedFollowingTransaction") or [None])[0])})
    return out


def parse_13dg(xml: str, owner_cik: int) -> dict | None:
    """13D/13G (2024.12~ XML) → {issuer, issuer_cik, cusip, pct, shares, event_date}. 대가 자기 회사면 None"""
    ic = [c for c in _vals(xml, "issuerCik") + _vals(xml, "issuerCIK") if c.isdigit()]
    issuer_cik = int(ic[0]) if ic else 0
    if issuer_cik == owner_cik:
        return None
    pct = next((p for p in (_num(v) for t in ("classPercent", "percentOfClass", "percentClass") for v in _vals(xml, t)) if p is not None), None)
    shares = next((s for s in (_num(v) for t in ("reportingPersonBeneficiallyOwnedAggregateNumberOfShares", "aggregateAmountOwned",
                                                   "amountBeneficiallyOwned") for v in _vals(xml, t)) if s is not None), None)
    ev = (_vals(xml, "eventDateRequiresFilingThisStatement") or _vals(xml, "dateOfEvent") or [""])[0]
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", ev)
    issuer = (_vals(xml, "issuerName") or [""])[0]
    if not issuer:
        return None
    return {"issuer": issuer, "issuer_cik": issuer_cik, "cusip": ((_vals(xml, "issuerCusipNumber") or [""])[0] or "").upper(),
            "pct": pct, "shares": shares, "event_date": f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else ev}


def moves_from(parsed: list, tickers_by_cik: dict) -> list:
    """대가 1명의 파싱된 공시들 [{form, filed, data}] (오래된 순) → 화면·신호용 매매 목록 (최신 순).
    13D/13G 는 같은 회사의 앞 신고와 지분율을 비교 (처음 = 새로 5%↑)"""
    out, last_pct = [], {}
    for p in sorted(parsed, key=lambda x: (x["filed"], x.get("acc", ""))):
        if p["form"] in FORMS_4:
            for t in p["data"]:
                out.append({"date": p["filed"], "trade_date": t["date"], "form": "Form 4", "kind": t["side"],
                            "ticker": clean_ticker(t["ticker"]) or clean_ticker(tickers_by_cik.get(t["issuer_cik"])), "issuer": t["issuer"],
                            "shares": t["shares"], "price": t["price"], "after": t["after"]})
        else:
            d = p["data"]
            if not d:
                continue
            prev = last_pct.get(d["issuer_cik"] or d["issuer"])
            amended = p["form"].endswith("/A")
            if not amended:
                kind = "stake_new"
            elif prev is None or d["pct"] is None:
                kind = "stake"
            else:
                kind = "stake_up" if d["pct"] > prev + 1e-9 else "stake_down" if d["pct"] < prev - 1e-9 else "stake"
            last_pct[d["issuer_cik"] or d["issuer"]] = d["pct"]
            out.append({"date": p["filed"], "trade_date": d["event_date"], "form": p["form"].replace("SCHEDULE ", "").replace("SC ", ""),
                        "kind": kind, "ticker": clean_ticker(tickers_by_cik.get(d["issuer_cik"])), "issuer": d["issuer"],
                        "pct": d["pct"], "pct_prev": prev, "shares": d["shares"]})
    out.sort(key=lambda m: m["date"], reverse=True)
    return out


def buy_moves(moves: list) -> list:
    """검증·신호에 쓰는 '샀다' 공시: Form 4 장내 매수 · 13D/13G 새 5%↑ · 지분율 증가 (티커가 있는 것만, 같은 날 같은 종목 1건)"""
    seen, out = set(), []
    for m in moves:
        if m["kind"] in ("buy", "stake_new", "stake_up") and m.get("ticker") and (m["ticker"], m["date"]) not in seen:
            seen.add((m["ticker"], m["date"]))
            out.append(m)
    return out


# ---------------- ARK 매일 보유 ----------------

def parse_ark_csv(text: str) -> tuple:
    """ARK 보유 CSV → (날짜 'YYYY-MM-DD', {티커: {shares, value, company, weight}}). 티커 없는 줄(비상장·현금)은 뺌"""
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    day, out = None, {}
    for r in rows:
        d = (r.get("date") or "").strip()
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", d)
        if not m:
            continue
        day = day or f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        t = (r.get("ticker") or "").strip().upper()
        sh = _num(r.get("shares"))
        if not t or sh is None or " " in t:
            continue
        a = out.setdefault(t, {"shares": 0.0, "value": 0.0, "company": (r.get("company") or "").strip(), "weight": 0.0})
        a["shares"] += sh
        a["value"] += _num((r.get("market value ($)") or "").replace("$", "")) or 0.0
        a["weight"] += _num(r.get("weight (%)")) or 0.0
    return day, out


def merge_funds(parts: list) -> dict:
    """펀드별 {티커: 값} 목록 → 합계 (같은 종목이 여러 펀드에)"""
    out: dict = {}
    for h in parts:
        for t, v in h.items():
            a = out.setdefault(t, {"shares": 0.0, "value": 0.0, "company": v["company"]})
            a["shares"] += v["shares"]
            a["value"] += v["value"]
    return out


def ark_moves(snapshots: dict) -> list:
    """날짜별 합계 보유 {날짜: {티커: {shares, value, company}}} → 날마다 앞날과 비교한 매매 (최신 순).
    새로 생김 = buy(new), 없어짐 = sell(exit), 수량 ±5%↑ = buy/sell"""
    days = sorted(snapshots)
    out = []
    for a, b in zip(days, days[1:]):
        pa, pb = snapshots[a], snapshots[b]
        for t in sorted(set(pa) | set(pb)):
            sa, sb = (pa.get(t) or {}).get("shares", 0.0), (pb.get(t) or {}).get("shares", 0.0)
            company = (pb.get(t) or pa.get(t) or {}).get("company", "")
            if sa <= 0 < sb:
                kind, chg = "buy", None
            elif sb <= 0 < sa:
                kind, chg = "sell", -100.0
            elif sa > 0 and abs(sb / sa - 1) >= ARK_MIN_CHANGE:
                kind, chg = ("buy" if sb > sa else "sell"), round((sb / sa - 1) * 100, 1)
            else:
                continue
            out.append({"date": b, "trade_date": b, "form": "ARK 매일", "kind": kind, "ticker": t, "issuer": company,
                        "shares": sb, "change_pct": chg, "new": sa <= 0, "exit": sb <= 0})
    out.sort(key=lambda m: m["date"], reverse=True)
    return out


def trim_snapshots(snapshots: dict, keep_days: int = ARK_KEEP_DAYS) -> dict:
    cut = (date.today() - timedelta(days=keep_days)).isoformat()
    return {d: v for d, v in snapshots.items() if d >= cut}


def since_date(days: int = RECENT_DAYS) -> str:
    return (date.today() - timedelta(days=days)).isoformat()

