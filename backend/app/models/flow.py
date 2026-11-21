from sqlalchemy import Column, Integer, String, Float, UniqueConstraint
from app.core.database import Base


class InvestorFlow(Base):
    """국내 종목 일별 투자자별 순매수 (KIS 주식현재가 투자자) — 외국인·기관·개인
    KIS 는 최근 약 30일만 주므로 매일 장 마감 후 받아서 쌓는다 (학습 모델의 수급 특징값용)"""
    __tablename__ = "investor_flow"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_flow"),)

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False)        # YYYY-MM-DD
    frgn_qty = Column(Float, nullable=True)      # 외국인 순매수 수량 (주)
    orgn_qty = Column(Float, nullable=True)      # 기관 순매수 수량
    prsn_qty = Column(Float, nullable=True)      # 개인 순매수 수량
