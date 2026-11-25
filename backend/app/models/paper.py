"""AI 모의투자 — 과거 시뮬레이션 결과 / 실시간 모의투자 계좌·체결·일별 자산"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class PaperSim(Base):
    """과거 시뮬레이션 1회 (결과 전체를 JSON 으로)"""
    __tablename__ = "paper_sim"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    market = Column(String, nullable=False)            # KR / US
    capital = Column(Float, nullable=False)
    months = Column(Integer, nullable=False)
    params = Column(Text, nullable=False)              # JSON
    status = Column(String, nullable=False, default="running")   # running / done / failed
    error = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)              # JSON (목록용)
    result = Column(Text, nullable=True)               # JSON (자산 곡선·거래·판단 기록)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)


class PaperAccount(Base):
    """실시간 모의투자 계좌. 보유 종목·대기 주문·판단 기록은 state(JSON) 한 곳에 (계좌별 잠금으로 순서대로 고침)"""
    __tablename__ = "paper_account"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=True)
    market = Column(String, nullable=False)
    capital = Column(Float, nullable=False)
    params = Column(Text, nullable=False)              # JSON
    state = Column(Text, nullable=False)               # JSON {cash, positions, pending, log, last_close}
    active = Column(Boolean, nullable=False, default=True)
    bench_start = Column(Float, nullable=True)         # 시작 때 지수 종가 (비교용)
    last_decision_day = Column(String, nullable=True)  # 장 마감 후 판단을 한 거래일
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaperTrade(Base):
    __tablename__ = "paper_trade"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("paper_account.id"), nullable=False, index=True)
    ts = Column(String, nullable=False)                # 체결 시각 (현지 시장 시간, ISO)
    symbol = Column(String, nullable=False)
    name = Column(String, nullable=True)
    side = Column(String, nullable=False)              # buy / sell
    qty = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    fee = Column(Float, nullable=False, default=0.0)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)


class PaperEquity(Base):
    """거래일 종가 기준 자산 (그래프용)"""
    __tablename__ = "paper_equity"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("paper_account.id"), nullable=False, index=True)
    date = Column(String, nullable=False)
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    bench = Column(Float, nullable=True)               # 같은 날 지수 종가
