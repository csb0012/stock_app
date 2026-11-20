from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)
    market = Column(String, nullable=False)  # KR / US
    name = Column(String, nullable=True)
    memo = Column(String, nullable=True)            # 메모 (관심 이유 등)
    target_price = Column(Float, nullable=True)     # 목표 매수가 — 현재가가 이 아래로 오면 표시
    added_at = Column(DateTime(timezone=True), server_default=func.now())
