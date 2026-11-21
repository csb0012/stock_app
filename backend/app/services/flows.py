"""국내 종목 투자자별 수급(외국인·기관·개인 순매수) — KIS 에서 받아 DB(investor_flow)에 쌓고 메모리에 보관

- KIS 주식현재가 투자자 API 는 최근 약 30거래일만 줌 → 처음엔 30일치, 이후 매일 장 마감 후(18:10~) 추가
- 학습 모델의 수급 특징값(ml_model: frgn1·frgn5·orgn1·orgn5)과 AI 추천 카드의 "수급(5일)" 표시에 사용
- 수집 실패는 부가 기능이라 로그 + status() 로 남기고, 수급 없는 모델로 예측 (가짜 값으로 채우지 않음)
"""
import time

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.flow import InvestorFlow

_mem: dict = {}          # symbol -> {date: {"frgn_qty", "orgn_qty", "prsn_qty"}}
_status = {"loaded": 0, "last_collect": None, "collected": 0, "errors": []}


def status() -> dict:
    return {**_status, "symbols": len(_mem), "rows": sum(len(v) for v in _mem.values())}


async def load_all():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(InvestorFlow))).scalars().all()
    for r in rows:
        _mem.setdefault(r.symbol, {})[r.date] = {"frgn_qty": r.frgn_qty, "orgn_qty": r.orgn_qty, "prsn_qty": r.prsn_qty}
    _status["loaded"] = len(rows)


async def collect(symbols: list) -> dict:
    """KIS 에서 최근 30일 수급을 받아 저장 (이미 있는 날짜는 최신 값으로 덮어씀)"""
    from app.services.kis_api import kis_client  # 순환 import 방지
    added, errors = 0, []
    for s in symbols:
        try:
            rows = await kis_client.get_kr_investor(s)
        except Exception as e:
            errors.append(f"{s}: {str(e)[:100]}")
            continue
        async with AsyncSessionLocal() as db:
            have = {r.date: r for r in (await db.execute(select(InvestorFlow).where(InvestorFlow.symbol == s))).scalars().all()}
            for r in rows:
                row = have.get(r["date"])
                if row is None:
                    row = InvestorFlow(symbol=s, date=r["date"])
                    db.add(row)
                    added += 1
                row.frgn_qty, row.orgn_qty, row.prsn_qty = r["frgn_qty"], r["orgn_qty"], r["prsn_qty"]
                _mem.setdefault(s, {})[r["date"]] = {k: r[k] for k in ("frgn_qty", "orgn_qty", "prsn_qty")}
            await db.commit()
    _status.update(last_collect=time.strftime("%Y-%m-%d %H:%M"), collected=added, errors=errors[:10])
    if errors:
        print(f"[flows] 수급 수집 실패 {len(errors)}건: {errors[0]}")
    return {"added": added, "errors": errors}


def series(symbol: str) -> dict:
    return _mem.get(symbol, {})


def summary(symbol: str, days: int = 5) -> dict | None:
    """화면용: 최근 N거래일 외국인·기관·개인 순매수 합계(주)"""
    s = _mem.get(symbol)
    if not s:
        return None
    dates = sorted(s)[-days:]
    tot = {k: sum((s[d].get(k) or 0) for d in dates) for k in ("frgn_qty", "orgn_qty", "prsn_qty")}
    return {"days": len(dates), "from": dates[0], "to": dates[-1], **tot}
