"""AI 모의투자 — 과거 시뮬레이션 / 실시간 모의투자 계좌"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_current_user
from app.core.database import get_db
from app.models.paper import PaperSim, PaperAccount
from app.models.user import User
from app.services import papertrade

router = APIRouter(prefix="/paper", tags=["paper"])


class SimIn(BaseModel):
    market: str
    capital: float | None = None
    months: int = 12
    params: dict | None = None


class AccountIn(BaseModel):
    market: str
    capital: float | None = None
    name: str | None = None
    params: dict | None = None


@router.get("/config")
async def get_config(current_user: User = Depends(get_current_user)):
    return {**papertrade.config(), "status": papertrade.status()}


# ---------------- 과거 시뮬레이션 ----------------

@router.post("/simulations")
async def start_simulation(body: SimIn, current_user: User = Depends(get_current_user)):
    try:
        sim = await papertrade.create_sim(current_user.id, body.market, body.capital, body.months, body.params)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return papertrade.sim_row(sim)


@router.get("/simulations")
async def list_simulations(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (await db.execute(select(PaperSim).where(PaperSim.user_id == current_user.id)
                             .order_by(PaperSim.id.desc()).limit(30))).scalars().all()
    return {"items": [papertrade.sim_row(s) for s in rows], "busy": papertrade.busy()}


async def _own_sim(db, sim_id: int, user: User) -> PaperSim:
    sim = await db.get(PaperSim, sim_id)
    if sim is None or sim.user_id != user.id:
        raise HTTPException(404, "시뮬레이션 없음")
    return sim


@router.get("/simulations/{sim_id}")
async def get_simulation(sim_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return papertrade.sim_row(await _own_sim(db, sim_id, current_user), full=True)


@router.post("/simulations/{sim_id}/cancel")
async def cancel_simulation(sim_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    sim = await _own_sim(db, sim_id, current_user)
    if sim.status != "running":
        raise HTTPException(409, "계산 중인 시뮬레이션이 아닙니다")
    if not papertrade.cancel_sim(sim_id):   # 서버가 다시 시작돼 실제로는 계산하지 않는 기록 → 바로 중단으로
        sim.status, sim.error = "cancelled", "서버가 다시 시작돼 중단됨"
        await db.commit()
        return {"message": "중단했습니다"}
    return {"message": "중단을 요청했습니다 — 몇 초 안에 멈춥니다"}


@router.delete("/simulations/{sim_id}")
async def delete_simulation(sim_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    sim = await _own_sim(db, sim_id, current_user)
    if sim.status == "running":
        raise HTTPException(409, "계산 중인 시뮬레이션은 끝난 뒤 지울 수 있습니다")
    await db.delete(sim)
    await db.commit()
    return {"ok": True}


# ---------------- 실시간 모의투자 ----------------

def _bg(coro, what: str):
    t = asyncio.create_task(coro)
    t.add_done_callback(lambda x: x.cancelled() or (x.exception() and print(f"[paper] {what} 실패: {x.exception()}")))


@router.get("/accounts")
async def list_accounts(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    accs = (await db.execute(select(PaperAccount).where(PaperAccount.user_id == current_user.id)
                             .order_by(PaperAccount.id))).scalars().all()
    return {"items": [await papertrade.account_view(a, db) for a in accs], "status": papertrade.status()}


@router.post("/accounts")
async def create_account(body: AccountIn, current_user: User = Depends(get_current_user)):
    try:
        acc = await papertrade.create_account(current_user.id, body.market, body.capital, body.params, body.name)
    except ValueError as e:
        raise HTTPException(422, str(e))
    _bg(papertrade.decide_account(acc.id, manual=True), f"계좌 {acc.id} 첫 판단")
    return {"id": acc.id, "message": "계좌를 만들었습니다 — AI 가 최근 종가로 판단하는 중 (1~2분)"}


async def _own_account(db, acc_id: int, user: User) -> PaperAccount:
    acc = await db.get(PaperAccount, acc_id)
    if acc is None or acc.user_id != user.id:
        raise HTTPException(404, "모의투자 계좌 없음")
    return acc


@router.get("/accounts/{acc_id}")
async def get_account(acc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await papertrade.account_view(await _own_account(db, acc_id, current_user), db, full=True)


@router.post("/accounts/{acc_id}/run")
async def run_account(acc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _own_account(db, acc_id, current_user)
    _bg(papertrade.decide_account(acc_id, manual=True), f"계좌 {acc_id} 수동 판단")
    return {"message": "AI 판단을 시작했습니다 — 1~2분 뒤 판단 기록에 표시 (장중이면 바로 체결)"}


@router.put("/accounts/{acc_id}/active")
async def set_active(acc_id: int, active: bool, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    acc = await _own_account(db, acc_id, current_user)
    acc.active = active
    await db.commit()
    return {"ok": True, "active": active}


@router.delete("/accounts/{acc_id}")
async def delete_account(acc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _own_account(db, acc_id, current_user)
    await papertrade.delete_account(acc_id)
    return {"ok": True}
