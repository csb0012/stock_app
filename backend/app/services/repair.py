"""저장된 종목코드 자동 복구

예전 버전은 손으로 적은 종목코드표를 써서, 이름은 맞는데 코드가 다른 종목으로 저장된 경우가 있다
(예: 'SOL AI반도체TOP2플러스' 가 441800(TIME Korea플러스배당액티브) 코드로 저장).
서버 시작 시 공식 종목마스터와 대조해서, 저장된 이름과 정확히 같은 종목이 하나뿐이면 코드를 고친다.
여러 개거나 없으면 건드리지 않고 화면 경고로 남긴다.
"""
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.portfolio import PortfolioItem
from app.models.watchlist import WatchlistItem
from app.services import stock_master


async def repair_symbols() -> list:
    fixed = []
    async with AsyncSessionLocal() as db:
        for model in (PortfolioItem, WatchlistItem):
            rows = (await db.execute(select(model))).scalars().all()
            for row in rows:
                m = stock_master.get(row.market, row.symbol)
                if m and stock_master._norm(m["name"]) == stock_master._norm(row.name or m["name"]):
                    continue
                matches = stock_master.find_by_name(row.market, row.name or "")
                if len(matches) != 1:
                    continue
                # 같은 사용자에게 이미 올바른 코드가 있으면 중복이 되므로 건너뜀
                dup = (await db.execute(select(model).where(
                    model.user_id == row.user_id, model.symbol == matches[0]["symbol"]))).scalar_one_or_none()
                if dup:
                    continue
                fixed.append(f"{model.__tablename__}: {row.name} {row.symbol} → {matches[0]['symbol']}")
                row.symbol = matches[0]["symbol"]
        await db.commit()
    for f in fixed:
        print(f"[repair] 종목코드 복구 {f}")
    return fixed
