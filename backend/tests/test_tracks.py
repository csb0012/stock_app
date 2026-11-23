"""종목별 예측 적중 기록: 50% 기준 적중 · 확신 예측 · 실제 예측 우선 · 표본 부족 표시"""
from tests.conftest import run
from app.services import prediction_log as pl


def test_build_tracks():
    rows = [
        ("KR", "005930", "2026-11-02", 60, 1.2, "backtest"),   # 상승 예측·상승 → 적중 (확신)
        ("KR", "005930", "2026-11-03", 40, -0.5, "backtest"),  # 하락 예측·하락 → 적중 (확신)
        ("KR", "005930", "2026-11-04", 52, -1.0, "backtest"),  # 상승 예측·하락 → 틀림 (확신 아님)
        ("KR", "005930", "2026-11-04", 45, -1.0, "live"),      # 같은 날 실제 예측이 우선 → 하락 예측 적중
        ("KR", "005930", "2026-11-05", 50, 2.0, "live"),       # 50% → 채점 제외
        ("KR", "005930", "2026-11-06", 70, None, "live"),      # 아직 결과 없음
        ("US", "AVGO", "2026-11-20", 30, 1.0, "backtest"),
    ]
    t = pl.build_tracks(rows)
    s = t[("KR", "005930")]
    assert (s["hit"], s["miss"], s["n"]) == (3, 0, 3) and s["accuracy"] == 100.0
    assert s["conf_n"] == 3 and s["conf_accuracy"] == 100.0 and s["live"] == 2
    assert s["enough"] is False                                 # 10건 미만
    a = t[("US", "AVGO")]
    assert a["miss"] == 1 and a["accuracy"] == 0.0
    assert pl.build_tracks([]) == {}


def test_attach_tracks(monkeypatch):
    async def fake():
        return {("US", "AVGO"): {"n": 12, "accuracy": 58.3}}
    monkeypatch.setattr(pl, "tracks", fake)
    rows = [{"market": "US", "symbol": "AVGO"}, {"market": "KR", "symbol": "000000"}, "x"]
    out = run(pl.attach_tracks(rows))
    assert out[0]["track"]["accuracy"] == 58.3 and out[1]["track"] is None and out[2] == "x"
    assert "track" not in rows[0]                                 # 원본은 그대로
