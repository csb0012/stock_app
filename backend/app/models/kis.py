"""KIS 모의투자 주문 (AI 제안 → 관리자 승인 → 모의투자 서버 주문) — 설정·상태 / 주문 / 감사 로그"""
from sqlalchemy import Column, Integer, String, Float, Text, Boolean
from app.core.database import Base


class KisTrade(Base):
    """설정·상태 1행 (id=1). 한 서버에 모의투자 계좌 하나 (.env 의 KIS_MOCK_ACCOUNT_NO)"""
    __tablename__ = "kis_trade"

    id = Column(Integer, primary_key=True)
    halted = Column(Boolean, nullable=False, default=False)     # 긴급 정지 / 하루 손실 한도 자동 정지
    halted_reason = Column(Text, nullable=True)
    halted_at = Column(Float, nullable=True)
    limits = Column(Text, nullable=False, default="{}")        # JSON — 1회 한도·하루 주문 수·하루 손실·가격 변동 허용
    params = Column(Text, nullable=False, default="{}")        # JSON — AI 매매 규칙 (AI 모의투자와 같은 항목)
    state = Column(Text, nullable=False, default="{}")         # JSON — expected(앱 기록 보유 수량)·meta(손절·목표·보유일)·log·day_start
    last_proposal_day = Column(String, nullable=True)          # 장 마감 후 자동 제안을 만든 날 (한국 날짜)
    last_error = Column(Text, nullable=True)


class KisOrder(Base):
    """주문 제안 1건 → 승인 → 주문 → 체결. 상태:
    proposed(승인 대기) / approved(승인 — 장 열리면 주문) / submitting(보내는 중) / submitted(주문 접수) /
    filled(체결) / partial(일부 체결) / unfilled(안 체결) / unknown(결과 모름 — 직접 확인) /
    rejected(거절) / expired(기한 지남) / cancelled(취소) / blocked(안전장치로 안 보냄) / failed(KIS 거부)"""
    __tablename__ = "kis_orders"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(Float, nullable=False)
    base_date = Column(String, nullable=True)        # 판단에 쓴 종가 날짜
    source = Column(String, nullable=False, default="ai")   # ai(장 마감 후 판단) / exit(장중 손절·목표)
    side = Column(String, nullable=False)            # buy / sell
    symbol = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    qty = Column(Integer, nullable=True)             # 매도 = 제안 수량, 매수 = 주문할 때 정함
    budget = Column(Float, nullable=True)            # 매수 금액 (1회 한도로 깎일 수 있음)
    ref_price = Column(Float, nullable=True)         # 제안 때 가격 (종가)
    reason = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="proposed", index=True)
    expires_at = Column(Float, nullable=False)
    decided_by = Column(Integer, nullable=True)
    decided_at = Column(Float, nullable=True)
    submitted_at = Column(Float, nullable=True)
    order_price = Column(Float, nullable=True)       # 주문 직전 현재가
    odno = Column(String, nullable=True)             # KIS 주문번호
    orgno = Column(String, nullable=True)            # KIS 주문 조직번호 (취소에 필요)
    filled_qty = Column(Integer, nullable=False, default=0)
    filled_price = Column(Float, nullable=True)
    message = Column(Text, nullable=True)


class KisLog(Base):
    """감사 로그 — 제안·승인·거절·주문·체결·정지·설정 변경을 모두 남김 (지우지 않음)"""
    __tablename__ = "kis_log"

    id = Column(Integer, primary_key=True, index=True)
    at = Column(Float, nullable=False, index=True)
    user_id = Column(Integer, nullable=True)          # 사람이 한 일이면 그 사람, 자동이면 비움
    action = Column(String, nullable=False)
    order_id = Column(Integer, nullable=True)
    ok = Column(Boolean, nullable=False, default=True)
    detail = Column(Text, nullable=True)
