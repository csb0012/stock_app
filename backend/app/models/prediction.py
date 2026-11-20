from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class _PredictionColumns:
    """실시간 예측 기록과 백테스트 기록이 같이 쓰는 컬럼"""
    id = Column(Integer, primary_key=True, index=True)
    market = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    name = Column(String, nullable=True)
    sources = Column(String, nullable=True)        # 어디서 예측했는지 (추천/투자종목/관심종목/백테스트, 콤마 구분)
    base_date = Column(String, nullable=False)     # 예측에 쓴 마지막 일봉 날짜
    target_date = Column(String, nullable=False)   # 예측 대상 거래일
    base_price = Column(Float, nullable=False)
    probability = Column(Integer, nullable=False)  # 상승 확률 (%) — 대상일 전 마지막 값
    signal = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    factors = Column(Text, nullable=True)          # JSON
    # 예측 방식별 확률 — 방식별 적중률 비교용 (probability 는 화면에 보여준/채점한 값)
    method = Column(String, nullable=True)                 # model:KR / model:KR_base / model:US / rules
    rule_probability = Column(Integer, nullable=True)      # 규칙 점수(RSI·MACD·볼린저·이평…) 확률
    model_probability = Column(Integer, nullable=True)     # 학습 모델 확률 (국내는 간밤 미국장 반영 전 KR_base)
    preopen_probability = Column(Integer, nullable=True)   # 국내: 간밤 미국장 반영 후(장 시작 전) 학습 모델 확률
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 채점 결과
    evaluated = Column(Boolean, nullable=False, default=False)
    outcome = Column(String, nullable=True)        # hit / miss / neutral / no_data
    actual_close = Column(Float, nullable=True)
    actual_change = Column(Float, nullable=True)   # 대상일 등락률 (%)
    gap_pct = Column(Float, nullable=True)         # 시가 갭 (%)
    volume_ratio = Column(Float, nullable=True)    # 20일 평균 대비 거래량 배수
    index_name = Column(String, nullable=True)
    index_change = Column(Float, nullable=True)
    review = Column(Text, nullable=True)           # JSON: 맞은/틀린 이유 목록
    evaluated_at = Column(DateTime(timezone=True), nullable=True)


class PredictionLog(_PredictionColumns, Base):
    """실시간 예측 기록 — 종목·예측 대상일(다음 거래일)마다 1건, 대상일이 지나면 실제 결과로 채점"""
    __tablename__ = "prediction_log"
    __table_args__ = (UniqueConstraint("market", "symbol", "target_date", name="uq_pred_target"),)


class BacktestLog(_PredictionColumns, Base):
    """과거 백테스트 기록 — 대상일 전날까지의 일봉만으로 예측한 뒤 대상일 실제 등락으로 채점 (최근 90일)

    뉴스·FRED·Finnhub·DART 는 과거 시점 데이터가 없어 기술적 지표(RSI·MACD·볼린저·이평)만 사용한다.
    """
    __tablename__ = "prediction_backtest"
    __table_args__ = (UniqueConstraint("market", "symbol", "target_date", name="uq_backtest_target"),)
