"""투자 대가 포트폴리오 — 미국 SEC 13F 공시 (운용자산 1억 달러 이상 기관이 분기마다 내는 미국 주식 보유 목록)

흐름 (하루 한 번, 뒤에서):
1. SEC EDGAR (data.sec.gov) 에서 대가별 최근 13F-HR 공시 목록 → 새 공시만 받아 보유 목록(XML) 파싱 → 디스크 캐시
   (공시는 바뀌지 않으므로 한 번 받은 건 다시 안 받음). 같은 종목(CUSIP)이 여러 줄이면 합침, 옵션(put/call)·채권은 뺌
2. CUSIP(미국 증권 번호) → 티커: OpenFIGI (키 없이 1분 25번 · 한 번에 10개) → 디스크 캐시 (번호는 안 바뀜)
3. 대가별: 비중·직전 분기 대비 변화(신규/추가/축소/전량 매도)·지금 보유 종목의 최근 1년 주가 수익률(가중 평균, 추정 — 토스 방식)
4. 종목별: 몇 명이 보유·이번 분기에 누가 샀고 팔았나 → AI 추천·종목 상세의 '투자 대가' 근거
5. 검증 (따라 사기): 과거 공시마다 '의미 있게 산 종목'(신규·25%↑ 추가, 비중 1%↑)을 **공시 다음 거래일 종가**에 샀다고 보고
   63거래일(약 3개월) 뒤 수익률을 S&P500(SPY) 과 비교. 공시는 분기 끝 45일 뒤에 나오므로 그 전 정보는 안 씀 (미래 데이터 미사용).
   이 검증이 '시장보다 나았다'(표본 30↑ · 평균 초과수익 > 0 · 이긴 비율 50%↑) 일 때만 AI 장기 점수에 가산점, 아니면 참고로만 표시

한계: 13F 는 분기 말 기준·최대 45일 늦게 공개 → 지금은 이미 팔았을 수 있음. 미국 상장 주식만 (현금·채권·해외 주식·공매도 없음).
SEC 는 User-Agent 에 연락처를 요구 → SEC_USER_AGENT 로 바꿀 수 있음 (기본값은 앱 이름만).
"""
import asyncio
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date
from pathlib import Path

import httpx

from app.core.config import settings

_DATA = Path(__file__).resolve().parents[1] / "data"
_FILINGS_FILE = _DATA / "guru_filings.json"
_CUSIP_FILE = _DATA / "cusip_map.json"
_RESULT_FILE = _DATA / "gurus.json"

MAX_Q = 8                 # 대가별 최근 공시 몇 분기까지 (검증용 — 2년)
KEEP_MIN_W = 0.0001       # 비중 0.01% 미만 줄은 저장 안 함 (파일 크기)
KEEP_MAX = 1500
HOLD_MIN_W = 0.002        # '보유'로 셈: 비중 0.2% 이상
BUY_MIN_W = 0.01          # 검증 '의미 있게 산 종목': 공시 비중 1% 이상
ADD_RATIO = 0.25          # 25% 이상 늘리면 '추가 매수'
HORIZON = 63              # 따라 사기 보유 기간 (거래일, 약 3개월)
REFRESH_SEC = 24 * 3600

# (key, 이름, 운용사, CIK, 투자 방식) — CIK 는 SEC 회사 번호. 받을 때 SEC 가 준 회사 이름을 같이 보여줌
GURUS = [
    ("buffett", "워런 버핏", "버크셔 해서웨이", 1067983, "좋은 기업을 적정 가격에 사서 오래 보유하는 가치투자"),
    ("pabrai", "모니시 파브라이", "달랄 스트리트", 1549575, "저평가 주식을 소수만 골라 집중 투자하는 전략"),
    ("paulson", "존 폴슨", "폴슨 앤 코", 1035674, "인수합병·구조조정 등 기업 이벤트에 투자하는 전략"),
    ("marks", "하워드 막스", "오크트리 캐피털", 949509, "부실채권·신용 자산 중심 (여기는 주식 보유분)"),
    ("wood", "캐시 우드", "ARK 인베스트", 1697748, "AI·바이오 등 혁신 기술 기업에 투자하는 전략"),
    ("lilu", "리 루", "히말라야 캐피털", 1709323, "중국·아시아 기업에 집중 투자하는 가치투자"),
    ("tweedy", "트위디 브라운", "트위디 브라운", 732905, "저평가 주식에 투자하는 정통 가치투자"),
    ("dalio", "레이 달리오", "브리지워터", 1350694, "금리·환율 등 거시경제를 분석하는 전략"),
    ("fisher", "켄 피셔", "피셔 인베스트먼트", 850529, "거시경제와 기업 분석을 결합하는 전략"),
    ("greenblatt", "조엘 그린블랫", "고담 자산운용", 1510387, "수익성 높고 싼 기업을 사는 '마법 공식'"),
    ("klarman", "세스 클라만", "바우포스트", 1061768, "안전마진을 가장 중시하는 가치투자"),
    ("ackman", "빌 애크먼", "퍼싱 스퀘어", 1336528, "소수 우량주 집중 + 경영 개선을 요구하는 행동주의"),
    ("tepper", "데이비드 테퍼", "아팔루사", 1656456, "위기 때 싸게 사는 역발상 투자"),
    ("druckenmiller", "스탠리 드러켄밀러", "듀케인 패밀리오피스", 1536411, "거시 흐름에 맞춰 크게 집중하는 투자"),
    ("loeb", "대니얼 로브", "서드 포인트", 1040273, "경영 개선을 요구하는 행동주의 투자"),
    ("icahn", "칼 아이칸", "아이칸 엔터프라이즈", 921669, "지분을 사서 경영에 개입하는 행동주의"),
    ("akre", "척 애크리", "애크리 캐피털", 1112520, "복리로 성장하는 기업을 오래 보유"),
    ("gayner", "토머스 게이너", "마켈 그룹", 1096343, "우량 기업 장기 보유 ('작은 버크셔')"),
    ("smith", "테리 스미스", "펀드스미스", 1569205, "좋은 회사를 사서 아무것도 하지 않기"),
    ("munger", "데일리 저널 (찰리 멍거)", "데일리 저널", 783412, "멍거 방식 — 소수 종목 장기 보유"),
    ("gates", "빌 게이츠 재단", "게이츠 재단 신탁", 1166559, "재단 자산 — 우량주 장기 보유"),
    ("soros", "조지 소로스", "소로스 펀드", 1029160, "거시경제 흐름에 베팅하는 전략"),
    ("hawkins", "메이슨 호킨스", "사우스이스턴", 807985, "내재가치보다 크게 싼 기업을 사는 가치투자"),
    ("nygren", "빌 나이그렌", "해리스 어소시에이츠", 813917, "오크마크 펀드 — 저평가 우량주"),
    ("yacktman", "야크트만", "야크트만 자산운용", 905567, "우량 기업을 할인된 가격에 사는 전략"),
    ("davis", "크리스 데이비스", "데이비스 어드바이저", 1036325, "금융·우량 성장주 장기 보유"),
    ("dodge", "다지 앤 콕스", "다지 앤 콕스", 200217, "오래된 가치투자 운용사"),
    ("firsteagle", "퍼스트 이글", "퍼스트 이글", 1325447, "글로벌 가치투자 운용사"),
    ("polen", "폴렌 캐피털", "폴렌 캐피털", 1034524, "고품질 성장주 집중"),
    ("coleman", "체이스 콜먼", "타이거 글로벌", 1167483, "기술·인터넷 성장주"),
    ("halvorsen", "안드레아스 할보르센", "바이킹 글로벌", 1103804, "기업 분석 기반 롱숏 (여기는 매수 보유분)"),
    ("mandel", "스티븐 맨델", "론 파인", 1061165, "성장주 롱숏 (여기는 매수 보유분)"),
    ("laffont", "필립 라퐁", "코튜 매니지먼트", 1135730, "기술 성장주"),
]
_BY_KEY = {g[0]: g for g in GURUS}

_status = {"running": False, "step": None, "done": 0, "total": 0, "started_at": None, "finished_at": None,
           "message": None, "errors": [], "cusip_pending": 0}
_result: dict | None = None
_lock = asyncio.Lock()


def _ua() -> str:
    # SEC 는 연락처 없는 User-Agent 를 일부 주소(company_tickers.json 등)에서 막음 → 기본값은 예시 주소. 본인 연락처로 바꾸길 권장
    return (getattr(settings, "sec_user_agent", "") or "").strip() or "StockApp/1.0 personal-research contact@example.com"


# ---------------- 파싱 (순수 함수) ----------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_info_table(xml_text: str) -> list:
    """13F 정보 표 XML → [{cusip, name, cls, value, shares}] (CUSIP 별 합계, 옵션·채권 제외, 값 큰 순)"""
    root = ET.fromstring(xml_text)
    agg: dict = {}
    for row in root.iter():
        if _local(row.tag) != "infoTable":
            continue
        f = {}
        for el in row.iter():
            t = _local(el.tag)
            if t in ("nameOfIssuer", "titleOfClass", "cusip", "value", "putCall", "sshPrnamt", "sshPrnamtType"):
                f[t] = (el.text or "").strip()
        if f.get("putCall") or (f.get("sshPrnamtType") or "SH").upper() != "SH":
            continue
        cusip = (f.get("cusip") or "").upper()
        if len(cusip) != 9:
            continue
        try:
            value, shares = float(f.get("value") or 0), float(f.get("sshPrnamt") or 0)
        except ValueError:
            continue
        a = agg.setdefault(cusip, {"cusip": cusip, "name": f.get("nameOfIssuer", ""), "cls": f.get("titleOfClass", ""),
                                   "value": 0.0, "shares": 0.0})
        a["value"] += value
        a["shares"] += shares
    return sorted(agg.values(), key=lambda r: -r["value"])


def compact(rows: list) -> dict:
    """저장용: 비중 0.01% 미만 줄은 버림 (합계는 전체 기준)"""
    total = sum(r["value"] for r in rows)
    keep = [r for r in rows if total > 0 and r["value"] / total >= KEEP_MIN_W][:KEEP_MAX]
    return {"total_value": total, "n_total": len(rows), "rows": keep}


def _ticker(cmap: dict, cusip: str):
    m = cmap.get(cusip)
    return m.get("t") if isinstance(m, dict) else None


def portfolio(filing: dict, prev: dict | None, cmap: dict) -> dict:
    """공시 1건 → 비중·직전 분기 대비 변화 (prev 없으면 변화 표시 없음)"""
    total = filing.get("total_value") or 0
    prev_rows = {r["cusip"]: r for r in (prev or {}).get("rows", [])}
    prev_total = (prev or {}).get("total_value") or 0
    out = []
    for r in filing.get("rows", []):
        w = r["value"] / total if total else 0
        p = prev_rows.get(r["cusip"])
        if prev is None:
            change, chg = None, None
        elif p is None:
            change, chg = "new", None
        else:
            chg = (r["shares"] / p["shares"] - 1) if p["shares"] else None
            change = "add" if chg is not None and chg >= 0.05 else "reduce" if chg is not None and chg <= -0.05 else "same"
        out.append({"cusip": r["cusip"], "ticker": _ticker(cmap, r["cusip"]), "issuer": r["name"], "cls": r["cls"],
                    "weight": round(w * 100, 2), "value": r["value"], "shares": r["shares"],
                    "change": change, "share_change_pct": round(chg * 100, 1) if chg is not None else None,
                    "prev_weight": round(p["value"] / prev_total * 100, 2) if p and prev_total else None})
    sold = []
    if prev is not None:
        cur = {r["cusip"] for r in filing.get("rows", [])}
        for c, p in prev_rows.items():
            pw = p["value"] / prev_total if prev_total else 0
            if c not in cur and pw >= 0.001:
                sold.append({"cusip": c, "ticker": _ticker(cmap, c), "issuer": p["name"], "prev_weight": round(pw * 100, 2)})
        sold.sort(key=lambda x: -x["prev_weight"])
    return {"holdings": out, "sold": sold}


def build(filings: dict, cmap: dict, quotes: dict, names: dict | None = None) -> dict:
    """filings: {key: [공시(최신 먼저) {acc, period, filed, total_value, n_total, rows}]} → 화면·AI 용 결과 (외부 호출 없음)"""
    names = names or {}
    gurus, stocks = [], {}
    for key, name, firm, cik, style in GURUS:
        fl = filings.get(key) or []
        if not fl:
            continue
        cur, prev = fl[0], (fl[1] if len(fl) > 1 else None)
        pf = portfolio(cur, prev, cmap)
        hold = pf["holdings"]
        # 지금 보유 종목의 최근 1년 주가 수익률 (비중 가중 평균) — 실제 펀드 수익률이 아님 (토스의 '추정 수익률'과 같은 방식)
        num = cov = 0.0
        for h in hold:
            q = quotes.get(h["ticker"] or "")
            if q and q.get("change_52w") is not None:
                num += h["weight"] * q["change_52w"]
                cov += h["weight"]
        est = round(num / cov, 1) if cov >= 50 else None
        stale = (date.today() - date.fromisoformat(cur["period"])).days > 200
        gurus.append({
            "key": key, "name": name, "firm": firm, "sec_name": cur.get("sec_name"), "style": style,
            "period": cur["period"], "filed": cur["filed"], "prev_period": prev["period"] if prev else None,
            "stale": stale, "n_holdings": cur.get("n_total"), "total_value": cur.get("total_value"),
            "est_return_1y": est, "est_coverage": round(cov, 1),
            "top": [{"ticker": h["ticker"], "issuer": h["issuer"], "weight": h["weight"], "change": h["change"]} for h in hold[:5]],
            "n_new": sum(1 for h in hold if h["change"] == "new" and h["weight"] >= HOLD_MIN_W * 100),
            "n_sold": len(pf["sold"]),
        })
        if stale:
            continue   # 오래된 공시(분기 1개 넘게 안 냄)는 종목별 합계에 안 넣음
        for h in hold:
            t = h["ticker"]
            if not t or h["weight"] < HOLD_MIN_W * 100:
                continue
            s = stocks.setdefault(t, {"ticker": t, "name": names.get(t) or h["issuer"], "holders": [], "buyers": [], "sellers": []})
            item = {"key": key, "name": name, "weight": h["weight"], "change": h["change"], "share_change_pct": h["share_change_pct"]}
            s["holders"].append(item)
            if h["change"] == "new" or (h["change"] == "add" and (h["share_change_pct"] or 0) >= ADD_RATIO * 100):
                s["buyers"].append(item)
            elif h["change"] == "reduce":
                s["sellers"].append(item)
        for x in pf["sold"]:
            t = x["ticker"]
            if t and x["prev_weight"] >= HOLD_MIN_W * 100:
                s = stocks.setdefault(t, {"ticker": t, "name": names.get(t) or x["issuer"], "holders": [], "buyers": [], "sellers": []})
                s["sellers"].append({"key": key, "name": name, "weight": 0, "change": "sold", "prev_weight": x["prev_weight"]})
    for s in stocks.values():
        s["holders"].sort(key=lambda h: -h["weight"])
        s["n_holders"], s["n_buyers"], s["n_sellers"] = len(s["holders"]), len(s["buyers"]), len(s["sellers"])
        q = quotes.get(s["ticker"]) or {}
        s.update(price=q.get("price"), change_52w=q.get("change_52w"), per=q.get("per"), pbr=q.get("pbr"))
    gurus.sort(key=lambda g: (g["est_return_1y"] is None, -(g["est_return_1y"] or 0)))
    return {"gurus": gurus, "stocks": stocks}


# ---------------- 따라 사기 검증 (순수 함수) ----------------

def buy_signals(filings: dict, cmap: dict) -> list:
    """과거 공시마다 의미 있게 산 종목 [{key, ticker, filed, period, weight}] — 공시일 이후에 산 것으로 봄"""
    out = []
    for key, fl in filings.items():
        for i in range(len(fl) - 1):
            cur, prev = fl[i], fl[i + 1]
            for h in portfolio(cur, prev, cmap)["holdings"]:
                big = h["weight"] >= BUY_MIN_W * 100
                bought = h["change"] == "new" or (h["change"] == "add" and (h["share_change_pct"] or 0) >= ADD_RATIO * 100)
                if big and bought and h["ticker"]:
                    out.append({"key": key, "ticker": h["ticker"], "filed": cur["filed"], "period": cur["period"], "weight": h["weight"]})
    return out


def _stats(xs: list) -> dict:
    if not xs:
        return {"n": 0, "avg_excess": None, "beat_rate": None, "avg_return": None}
    return {"n": len(xs), "avg_excess": round(sum(x["excess"] for x in xs) / len(xs) * 100, 2),
            "beat_rate": round(sum(1 for x in xs if x["excess"] > 0) / len(xs) * 100, 1),
            "avg_return": round(sum(x["ret"] for x in xs) / len(xs) * 100, 2)}


def validate(signals: list, closes: dict, bench: str = "SPY") -> dict:
    """closes: {ticker: [(날짜 'YYYY-MM-DD', 종가)] 오름차순}. 공시일 **다음** 거래일 종가에 사서 HORIZON 거래일 보유"""
    b = closes.get(bench) or []
    bdates = [d for d, _ in b]
    bmap = dict(b)
    done, pending, missing = [], 0, 0
    for s in signals:
        px = closes.get(s["ticker"])
        if not px or not bdates:
            missing += 1
            continue
        pmap = dict(px)
        # 공시 다음 거래일 (공시가 장 마감 뒤에 나올 수 있어서 그날은 안 씀)
        idx = next((i for i, d in enumerate(bdates) if d > s["filed"]), None)
        if idx is None:
            pending += 1
            continue
        if idx + HORIZON >= len(bdates):
            pending += 1
            continue
        d0, d1 = bdates[idx], bdates[idx + HORIZON]
        p0, p1 = pmap.get(d0), pmap.get(d1)
        if not p0 or not p1 or p0 <= 0:
            missing += 1
            continue
        ret, bret = p1 / p0 - 1, bmap[d1] / bmap[d0] - 1
        done.append({**s, "entry": d0, "exit": d1, "ret": ret, "excess": ret - bret})
    by_guru = {}
    for k in {x["key"] for x in done}:
        by_guru[k] = _stats([x for x in done if x["key"] == k])
    # 같은 분기에 대가 2명 이상이 같이 산 종목
    cnt: dict = {}
    for x in done:
        cnt.setdefault((x["ticker"], x["period"]), set()).add(x["key"])
    multi = [x for x in done if len(cnt[(x["ticker"], x["period"])]) >= 2]
    total = _stats(done)
    validated = bool(total["n"] >= 30 and (total["avg_excess"] or 0) > 0 and (total["beat_rate"] or 0) >= 50)
    recent = sorted(done, key=lambda x: x["entry"], reverse=True)[:30]
    return {"horizon_days": HORIZON, "benchmark": bench, **total, "pending": pending, "missing": missing,
            "by_guru": by_guru, "multi": _stats(multi), "validated": validated,
            "recent": [{k: (round(v * 100, 2) if k in ("ret", "excess") else v) for k, v in x.items()} for x in recent]}


# ---------------- 외부 호출 ----------------

async def _sec_get(client: httpx.AsyncClient, url: str):
    await asyncio.sleep(0.15)       # SEC: 초당 10회 이하
    r = await client.get(url)
    if r.status_code != 200:
        raise RuntimeError(f"SEC HTTP {r.status_code} ({url.split('/')[-1][:40]})")
    return r


async def _filing_list(client, cik: int) -> tuple:
    d = (await _sec_get(client, f"https://data.sec.gov/submissions/CIK{cik:010d}.json")).json()
    r = d.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(r.get("form", [])):
        if form == "13F-HR":     # 정정(13F-HR/A)은 일부만 고친 것도 있어 원본만
            out.append({"acc": r["accessionNumber"][i], "filed": r["filingDate"][i], "period": r["reportDate"][i]})
    out.sort(key=lambda x: x["period"], reverse=True)
    seen, uniq = set(), []
    for f in out:                 # 같은 분기에 원본이 두 번이면 최신 것만
        if f["period"] not in seen:
            seen.add(f["period"])
            uniq.append(f)
    return d.get("name", ""), uniq[:MAX_Q]


async def _load_filing(client, cik: int, acc: str) -> dict:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
    idx = (await _sec_get(client, f"{base}/index.json")).json()
    xmls = [it for it in idx.get("directory", {}).get("item", [])
            if it.get("name", "").lower().endswith(".xml") and it["name"].lower() != "primary_doc.xml"]
    if not xmls:
        raise RuntimeError(f"보유 목록 XML 없음 ({acc})")
    best = max(xmls, key=lambda it: int(it.get("size") or 0))
    text = (await _sec_get(client, f"{base}/{best['name']}")).text
    return compact(parse_info_table(text))


async def map_cusips(cusips: list, cmap: dict, save=None) -> int:
    """OpenFIGI 로 CUSIP → 티커 (키 없이 1분 25번 × 10개). 못 찾은 건 30일 뒤 다시. 반환: 남은 개수"""
    today = date.today().isoformat()
    todo = [c for c in cusips if c not in cmap or (cmap[c].get("t") is None and cmap[c].get("d", "") < _days_ago(30))]
    # (이름으로 찾은 것도 OpenFIGI 결과로 덮지 않음 — t 가 있으면 다시 안 물음)
    _status["cusip_pending"] = len(todo)
    async with httpx.AsyncClient(timeout=20.0) as client:
        for i in range(0, len(todo), 10):
            part = todo[i:i + 10]
            r = await client.post("https://api.openfigi.com/v3/mapping",
                                  json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in part])
            if r.status_code == 429:
                await asyncio.sleep(61)
                r = await client.post("https://api.openfigi.com/v3/mapping",
                                      json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in part])
            if r.status_code != 200:
                raise RuntimeError(f"OpenFIGI HTTP {r.status_code}: {r.text[:120]}")
            for c, res in zip(part, r.json()):
                data = (res or {}).get("data") or []
                pick = next((x for x in data if (x.get("marketSector") == "Equity")), data[0] if data else None)
                t = (pick or {}).get("ticker")
                cmap[c] = {"t": t.replace("/", "-").replace(" ", "-") if t else None, "n": (pick or {}).get("name"), "d": today}
            _status["cusip_pending"] = max(0, len(todo) - i - 10)
            if save:
                save()
            if i + 10 < len(todo):
                await asyncio.sleep(2.6)
    return 0


# ---------------- 이름으로 티커 찾기 (OpenFIGI 가 못 찾은 외국 등록 회사 등) ----------------

_ABBR = {"HLDG": "HOLDING", "HLDGS": "HOLDING", "HOLDINGS": "HOLDING", "INTL": "INTERNATIONAL", "FINL": "FINANCIAL",
         "CORPORATION": "CORP", "INCORPORATED": "INC", "LIMITED": "LTD", "COMPANY": "CO", "GRP": "GROUP",
         "TECHNOLOGIES": "TECHNOLOGY", "TECHS": "TECHNOLOGY", "SVCS": "SERVICES", "MGMT": "MANAGEMENT", "PPTYS": "PROPERTIES",
         "INDL": "INDUSTRIAL", "HLDNGS": "HOLDING", "HLDNG": "HOLDING", "INTERNATL": "INTERNATIONAL", "COS": "COMPANIES"}
_TAIL = {"INC", "CORP", "LTD", "PLC", "PL", "NV", "N", "V", "SA", "AG", "CO", "LP", "LLC", "NEW", "THE", "DEL", "COM", "SE", "AB", "ASA"}


def norm_name(name: str) -> str:
    """회사 이름 비교용: 대문자·약어 통일·끝의 법인 형태(INC·LTD·PLC…) 제거"""
    t = [_ABBR.get(w, w) for w in "".join(ch if ch.isalnum() or ch == " " else " " for ch in (name or "").upper().replace("&", " AND ")).split()]
    while t and t[-1] in _TAIL:
        t.pop()
    while t and t[0] == "THE":
        t.pop(0)
    return " ".join(t)


def name_index(tickers_json: dict) -> dict:
    """SEC company_tickers.json → {정규화 이름: (첫 티커, 그 회사 티커 수)}. 다른 회사가 같은 이름이면 None (모호)"""
    by_cik: dict = {}
    for v in tickers_json.values():
        by_cik.setdefault(v["cik_str"], {"title": v["title"], "tickers": []})["tickers"].append(v["ticker"])
    idx: dict = {}
    for cik, v in by_cik.items():
        k = norm_name(v["title"])
        if not k:
            continue
        idx[k] = None if k in idx else (v["tickers"][0].replace(".", "-"), len(v["tickers"]))
    return idx


def match_name(idx: dict, issuer: str, cls: str = "") -> str | None:
    """13F 회사 이름 → 티커. 여러 종류 주식이 있는 회사인데 A 가 아닌 클래스(CL B·CL C)면 모호해서 None"""
    hit = idx.get(norm_name(issuer))
    if not hit:
        return None
    t, n = hit
    c = (cls or "").upper()
    if n > 1 and any(x in c for x in ("CL B", "CL C", "CLASS B", "CLASS C", "CL K", "SER B", "SER C")):
        return None
    return t


async def _sec_tickers(client) -> dict:
    """SEC 공식 회사-티커 목록 (7일 캐시)"""
    f = _DATA / "sec_tickers.json"
    try:
        if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
            return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    d = (await _sec_get(client, "https://www.sec.gov/files/company_tickers.json")).json()
    _write(f, d)
    return d


def _days_ago(n: int) -> str:
    from datetime import timedelta
    return (date.today() - timedelta(days=n)).isoformat()


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, ValueError):
        return default


def _write(path: Path, obj):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        print(f"[gurus] 저장 실패 {path.name}: {e}")


def _us_name(ticker: str) -> str | None:
    from app.services import stock_master
    for t in (ticker, ticker.replace("-", "/"), ticker.replace("-", ".")):
        it = stock_master.get("US", t)
        if it:
            return it.get("name")
    return None


def _ohlcv_sync(tickers: list) -> dict:
    """yfinance 일봉 (3년, 배당·분할 반영 수정주가) → {ticker: [{date, open, high, low, close, volume}] 오름차순}"""
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), 200):
        part = tickers[i:i + 200]
        df = yf.download(part, period="3y", interval="1d", auto_adjust=True, progress=False, threads=True, group_by="ticker")
        if df is None or df.empty:
            continue
        for t in part:
            try:
                d = (df[t] if len(part) > 1 else df).dropna(subset=["Close"])
            except KeyError:
                continue
            out[t] = [{"date": ix.strftime("%Y-%m-%d"), "open": float(r["Open"]), "high": float(r["High"]), "low": float(r["Low"]),
                       "close": float(r["Close"]), "volume": float(r["Volume"] or 0)} for ix, r in d.iterrows()]
    return out


def _closes_of(ohlcv: dict) -> dict:
    return {t: [(c["date"], c["close"]) for c in cs] for t, cs in ohlcv.items()}


# AI 필터 (사용자 결정 2026-11-26: 대가를 무조건 따라가지 않고 AI 가 다시 보고 좋은 것만) —
# 실시간 AI 모의투자·KIS 주문의 매수 조건과 같게: AI 점수(상승확률 45% + 퀀트 35%) ≥ 60 · 상승확률 ≥ 55% · 50일선 위.
# 판단은 공시일 종가까지의 데이터로만 (공시 다음 거래일 종가에 삼 — validate 와 같은 진입). 퀀트는 같은 날 대가 종목들 안의 순위(요인 같은 비중)
AI_BUY_SCORE, AI_MIN_PROB = 60, 55


def ai_filter(signals: list, ohlcv: dict) -> list:
    """대가가 산 종목 중 그날 AI 매수 조건을 통과한 것만 (+ ai 칸: 점수·확률·퀀트)"""
    import pandas as pd
    from app.services import quant, paper_engine as pe
    from app.services.analysis import calc_technical_indicators, predict_next_day
    frames = []
    for t, cs in ohlcv.items():
        if len(cs) >= quant.MIN_ROWS:
            f = quant.factor_frame(cs)
            if not f.empty:
                frames.append(f.assign(symbol=t))
    qp = {}
    if frames:
        df = pd.concat(frames, ignore_index=True).dropna(subset=["rs"])
        for k in quant.KEYS:
            df[f"p_{k}"] = df.groupby("date")[k].rank(pct=True).mul(98).add(1)
        df["raw"] = sum(df[f"p_{k}"].fillna(50) for k in quant.KEYS) / len(quant.KEYS)
        df["comp"] = df.groupby("date")["raw"].rank(pct=True).mul(98).add(1)
        qp = {(d, s): float(c) for d, s, c in zip(df["date"], df["symbol"], df["comp"])}
    out = []
    for s in signals:
        cs = ohlcv.get(s["ticker"]) or []
        idx = [i for i, c in enumerate(cs) if c["date"] <= s["filed"]]
        if not idx or idx[-1] < 59:
            continue
        i = idx[-1]
        hist = cs[max(0, i + 1 - pe.WINDOW): i + 1]
        try:
            prob = int(predict_next_day(hist, calc_technical_indicators(hist))["probability"])
        except Exception:   # noqa: BLE001 — 계산 못 하면 통과 안 함
            continue
        closes = [c["close"] for c in cs[i - 49: i + 1]]
        ma50 = sum(closes) / len(closes)
        q = qp.get((cs[i]["date"], s["ticker"]))
        score = pe.ai_score(prob, q, None, False)
        if score >= AI_BUY_SCORE and prob >= AI_MIN_PROB and cs[i]["close"] >= ma50:
            out.append({**s, "ai": {"score": score, "prob": prob, "quant": round(q) if q is not None else None}})
    return out


async def refresh(force: bool = False) -> dict:
    """13F 다시 받기 → 결과 저장 (이미 실행 중이면 상태만)"""
    global _result
    if _lock.locked():
        return status()
    async with _lock:
        _status.update(running=True, step="SEC 공시 목록", done=0, total=len(GURUS), errors=[],
                       started_at=datetime.now().isoformat(timespec="seconds"), finished_at=None, message=None)
        try:
            cache = _read(_FILINGS_FILE, {})       # acc -> 저장본
            cmap = _read(_CUSIP_FILE, {})
            filings: dict = {}
            async with httpx.AsyncClient(headers={"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"},
                                         timeout=30.0, follow_redirects=True) as client:
                for key, name, firm, cik, style in GURUS:
                    try:
                        sec_name, lst = await _filing_list(client, cik)
                        got = []
                        for f in lst:
                            if f["acc"] not in cache:
                                cache[f["acc"]] = {**await _load_filing(client, cik, f["acc"]), "filed": f["filed"], "period": f["period"]}
                            got.append({**cache[f["acc"]], "acc": f["acc"], "filed": f["filed"], "period": f["period"], "sec_name": sec_name})
                        if got:
                            filings[key] = got
                    except Exception as e:
                        _status["errors"].append(f"{name}: {str(e)[:120]}")
                    _status["done"] += 1
            keep = {f["acc"] for fl in filings.values() for f in fl}
            cache = {a: v for a, v in cache.items() if a in keep or not filings}
            _write(_FILINGS_FILE, cache)
            if not filings:
                raise RuntimeError("SEC 13F 를 하나도 못 받음 — " + " / ".join(_status["errors"][:2]))

            # CUSIP → 티커 (최근 2분기 보유 0.2%↑ + 검증용 1%↑)
            _status["step"] = "CUSIP → 티커 변환 (OpenFIGI)"
            need = set()
            for fl in filings.values():
                for j, f in enumerate(fl):
                    tot = f["total_value"] or 1
                    th = HOLD_MIN_W if j < 2 else BUY_MIN_W
                    need.update(r["cusip"] for r in f["rows"] if r["value"] / tot >= th)
            try:
                await map_cusips(sorted(need), cmap, save=lambda: _write(_CUSIP_FILE, cmap))
            except Exception as e:
                _status["errors"].append(f"티커 변환: {str(e)[:150]}")   # 일부만 변환돼도 계속 (남은 건 다음에)
            # OpenFIGI 가 못 찾은 것 → SEC 공식 회사 목록에서 이름으로 (외국 등록 회사·이름 바뀐 회사 등)
            left: dict = {}     # CUSIP -> 공시마다 다르게 적힌 이름들 (약어가 달라서 하나만으론 못 찾을 수 있음)
            for fl in filings.values():
                for f in fl:
                    for r in f["rows"]:
                        if r["cusip"] in need and not _ticker(cmap, r["cusip"]):
                            left.setdefault(r["cusip"], {})[r["name"]] = r["cls"]
            if left:
                try:
                    async with httpx.AsyncClient(headers={"User-Agent": _ua()}, timeout=30.0) as client:
                        idx = name_index(await _sec_tickers(client))
                    for c, nm in left.items():
                        t = next((x for x in (match_name(idx, n, cl) for n, cl in nm.items()) if x), None)
                        if t:
                            cmap[c] = {"t": t, "n": next(iter(nm)), "d": date.today().isoformat(), "by": "name"}
                except Exception as e:
                    _status["errors"].append(f"이름으로 티커 찾기: {str(e)[:150]}")
            _write(_CUSIP_FILE, cmap)

            # 지금 가격·1년 수익률 (Yahoo)
            _status["step"] = "현재가 (Yahoo)"
            from app.services import fundamentals
            latest = {_ticker(cmap, r["cusip"]) for fl in filings.values() for r in fl[0]["rows"]
                      if r["value"] / (fl[0]["total_value"] or 1) >= HOLD_MIN_W}
            latest.discard(None)
            try:
                quotes = await fundamentals.yahoo_quotes(sorted(latest))
            except Exception as e:
                quotes = {}
                _status["errors"].append(f"Yahoo 현재가: {str(e)[:150]}")
            names = {t: _us_name(t) for t in latest}
            res = build(filings, cmap, quotes, {t: n for t, n in names.items() if n})

            # 검증 (따라 사기)
            _status["step"] = "따라 사기 검증 (과거 주가)"
            sigs = buy_signals(filings, cmap)
            try:
                tick = sorted({s["ticker"] for s in sigs} | {"SPY"})
                ohlcv = await asyncio.get_event_loop().run_in_executor(None, _ohlcv_sync, tick)
                closes = _closes_of(ohlcv)
                res["validation"] = validate(sigs, closes)
                # 대가가 산 종목 + AI 필터 → 통과한 것만 따라 샀다면 (이게 통과해야 AI 모의투자·KIS 미국 후보에 넣음)
                passed = await asyncio.get_event_loop().run_in_executor(None, ai_filter, sigs, ohlcv)
                res["validation_ai"] = {**validate(passed, closes), "rule": f"AI 점수 {AI_BUY_SCORE}↑ · 상승확률 {AI_MIN_PROB}%↑ · 50일선 위",
                                        "signals": len(sigs), "passed": len(passed)}
            except Exception as e:
                res["validation"], res["validation_ai"] = None, None
                _status["errors"].append(f"검증 주가: {str(e)[:150]}")
            res["accs"] = {k: [f["acc"] for f in fl] for k, fl in filings.items()}
            res.update(updated_at=datetime.now().isoformat(timespec="seconds"), errors=_status["errors"][:10],
                       unmapped=sum(1 for c in need if not _ticker(cmap, c)))
            _result = res
            _write(_RESULT_FILE, res)
            _status["message"] = f"대가 {len(res['gurus'])}명 · 종목 {len(res['stocks'])}개" + (
                f" · 오류 {len(_status['errors'])}건" if _status["errors"] else "")
            print(f"[gurus] {_status['message']}")
        except Exception as e:
            _status["message"] = f"실패: {e}"
            print(f"[gurus] 실패: {e}")
        finally:
            _status.update(running=False, step=None, finished_at=datetime.now().isoformat(timespec="seconds"))
    return status()


# ---------------- 조회 ----------------

def result() -> dict | None:
    global _result
    if _result is None:
        _result = _read(_RESULT_FILE, None)
    return _result


def status() -> dict:
    return dict(_status)


def stale() -> bool:
    r = result()
    if not r:
        return True
    try:
        return (datetime.now() - datetime.fromisoformat(r["updated_at"])).total_seconds() > REFRESH_SEC
    except (KeyError, ValueError):
        return True


def guru_detail(key: str) -> dict | None:
    """대가 1명의 전체 보유 목록 (저장된 공시로 바로 계산). 없는 대가면 None"""
    g = _BY_KEY.get(key)
    if not g:
        return None
    r = result() or {}
    summary = next((x for x in r.get("gurus", []) if x["key"] == key), None)
    accs = (r.get("accs") or {}).get(key) or []
    if not summary or not accs:
        return {"guru": summary or {"key": key, "name": g[1], "firm": g[2], "style": g[4]}, "holdings": [], "sold": []}
    cache, cmap = _read(_FILINGS_FILE, {}), _read(_CUSIP_FILE, {})
    fl = [cache[a] for a in accs[:2] if a in cache]
    if not fl:
        return {"guru": summary, "holdings": [], "sold": []}
    pf = portfolio(fl[0], fl[1] if len(fl) > 1 else None, cmap)
    stocks = r.get("stocks") or {}
    for h in pf["holdings"] + pf["sold"]:
        t = h.get("ticker")
        if t:
            h["name"] = _us_name(t)
            s = stocks.get(t) or {}
            h["change_52w"], h["price"], h["n_holders"] = s.get("change_52w"), s.get("price"), s.get("n_holders")
    return {"guru": summary, **pf}


def signal(symbol: str) -> dict | None:
    """미국 종목의 대가 신호 — AI 추천·종목 상세용. 대가가 하나도 없으면 None"""
    r = result()
    if not r:
        return None
    s = (r.get("stocks") or {}).get(symbol) or (r.get("stocks") or {}).get(symbol.replace("/", "-"))
    if not s:
        return None
    v = r.get("validation") or {}
    pts = boost_points(s, v)
    va = r.get("validation_ai") or {}
    return {"n_holders": s["n_holders"], "n_buyers": s["n_buyers"], "n_sellers": s["n_sellers"],
            "ai_validated": bool(va.get("validated")),
            "holders": s["holders"][:6], "buyers": s["buyers"][:6], "sellers": s["sellers"][:6],
            "period": max((g["period"] for g in r.get("gurus", []) if not g.get("stale")), default=None),
            "points": pts, "validated": bool(v.get("validated")),
            "validation": {k: v.get(k) for k in ("n", "avg_excess", "beat_rate", "horizon_days")} if v else None}


def boost_points(s: dict, v: dict) -> int:
    """AI 장기 점수 가산점 (0~10) — 따라 사기 검증이 시장보다 나았을 때만. 아니면 0 (참고로만 표시)
    이번 분기에 산 대가 1명당 4점 + 보유 대가 수(최대 4) − 판 대가 1명당 2점"""
    if not s or not (v or {}).get("validated"):
        return 0
    pts = 4 * s.get("n_buyers", 0) + min(s.get("n_holders", 0), 4) - 2 * s.get("n_sellers", 0)
    return int(max(0, min(10, pts)))


async def loop():
    """하루 한 번 (서버 시작 3분 뒤 첫 확인). 13F 는 분기마다 2월·5월·8월·11월 중순에 몰림"""
    await asyncio.sleep(180)
    while True:
        if stale():
            await refresh()
        await asyncio.sleep(3600)

