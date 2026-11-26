"""휴대폰 푸시 알림 (ntfy) — 날씨 알림과 같은 JSON 방식 · 주제 이름은 오류 문구에 안 나옴 · 설정 없으면 안 보냄"""
import json

import httpx
import pytest

from tests.conftest import run
from app.core.config import settings
from app.services import notify, kis_trade

TOPIC = "stockapp-Zq8xK2p9WmR4tLs7"


@pytest.fixture
def ntfy(monkeypatch):
    sent = []
    resp = {"status": 200, "body": {"id": "x"}}

    def handler(req: httpx.Request):
        sent.append({"url": str(req.url), "json": json.loads(req.content), "auth": req.headers.get("authorization")})
        return httpx.Response(resp["status"], json=resp["body"])
    real = httpx.AsyncClient
    monkeypatch.setattr(notify.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, "ntfy_topic", TOPIC)
    monkeypatch.setattr(settings, "ntfy_server", "https://ntfy.sh")
    monkeypatch.setattr(settings, "ntfy_token", "")
    monkeypatch.setattr(settings, "ntfy_click_url", "")
    monkeypatch.setattr(settings, "domain", "")
    return sent, resp


def test_send_json_like_weather_app(ntfy, monkeypatch):
    sent, _ = ntfy
    run(notify.send("AI 주문 제안 2건", "- 매수 삼성전자(005930) 2,000,000원어치", 4, ["chart_with_upwards_trend"]))
    assert sent[0]["url"] == "https://ntfy.sh" and sent[0]["auth"] is None
    assert sent[0]["json"] == {"topic": TOPIC, "title": "AI 주문 제안 2건", "message": "- 매수 삼성전자(005930) 2,000,000원어치",
                               "priority": 4, "tags": ["chart_with_upwards_trend"]}
    monkeypatch.setattr(settings, "ntfy_token", "tk_secret123")
    monkeypatch.setattr(settings, "ntfy_click_url", "https://mystock.duckdns.org/kis")
    monkeypatch.setattr(settings, "ntfy_server", "https://ntfy.example.com/")
    run(notify.send("t", "m", 9))
    assert sent[1]["url"] == "https://ntfy.example.com" and sent[1]["auth"] == "Bearer tk_secret123"
    assert sent[1]["json"]["click"] == "https://mystock.duckdns.org/kis" and sent[1]["json"]["priority"] == 5
    st = notify.status()
    assert st == {**st, "configured": True, "server": "ntfy.example.com", "token": True} and TOPIC not in json.dumps(st)
    assert st["last"]["ok"] is True


def test_errors_never_show_topic(ntfy, monkeypatch):
    sent, resp = ntfy
    resp.update(status=403, body={"error": "forbidden"})
    with pytest.raises(notify.NotifyError) as e:
        run(notify.send("t", "m"))
    assert "403" in str(e.value) and "NTFY_TOKEN" in str(e.value) and TOPIC not in str(e.value)
    assert notify.status()["last"]["ok"] is False and TOPIC not in notify.status()["last"]["error"]
    monkeypatch.setattr(settings, "ntfy_topic", "bad topic/../x")
    with pytest.raises(notify.NotifyError, match="영문"):
        run(notify.send("t", "m"))
    monkeypatch.setattr(settings, "ntfy_topic", "")
    with pytest.raises(notify.NotifyError, match="NTFY_TOPIC"):
        run(notify.send("t", "m"))
    assert notify.configured() is False
    notify.send_bg("t", "m")          # 설정이 없으면 아무것도 안 함 (오류도 없음)
    assert len(sent) == 1


def test_kis_events_go_to_phone(monkeypatch):
    """KIS 모의투자: 제안·정지는 푸시 + 메일, 체결·막힘은 푸시만"""
    pushed = []
    monkeypatch.setattr(notify, "send_bg", lambda title, body, priority=3, tags=None, click=None: pushed.append((title, priority, body)))
    from app.services import mailer
    monkeypatch.setattr(mailer, "configured", lambda: False)
    kis_trade._alert_admins("[StockApp] AI 주문 제안 1건 — 승인 대기", "- 매수 삼성전자(005930)", priority=4)
    kis_trade._push("체결 — 매수 삼성전자", "삼성전자(005930) 14주 · 평균 70,000원 (모의투자)")
    assert pushed == [("AI 주문 제안 1건 — 승인 대기", 4, "- 매수 삼성전자(005930)"),
                      ("체결 — 매수 삼성전자", 3, "삼성전자(005930) 14주 · 평균 70,000원 (모의투자)")]



def test_click_opens_web_page(ntfy, monkeypatch):
    """알림을 누르면 웹 화면: 사이트 주소(NTFY_CLICK_URL 의 주소 부분 또는 클라우드 DOMAIN) + 경로 (/kis?order=12)"""
    sent, _ = ntfy
    assert notify.app_url("/kis") is None                        # 주소를 모르면 링크 없이
    run(notify.send("t", "m", click="/kis?order=12"))
    assert "click" not in sent[-1]["json"]
    monkeypatch.setattr(settings, "domain", "mystock.duckdns.org")   # 클라우드: deploy/.env 의 DOMAIN
    assert notify.app_url("/kis?order=12") == "https://mystock.duckdns.org/kis?order=12"
    run(notify.send("t", "m", click="/kis?order=12"))
    assert sent[-1]["json"]["click"] == "https://mystock.duckdns.org/kis?order=12"
    run(notify.send("t", "m"))                                    # 경로 없으면 첫 화면
    assert sent[-1]["json"]["click"] == "https://mystock.duckdns.org/"
    monkeypatch.setattr(settings, "ntfy_click_url", "https://other.example.com:8443/kis")   # 직접 넣은 주소가 우선, 뒤 경로는 무시
    assert notify.app_url("kis") == "https://other.example.com:8443/kis"
    run(notify.send("t", "m", click="/kis?order=3"))
    assert sent[-1]["json"]["click"] == "https://other.example.com:8443/kis?order=3"
    run(notify.send("t", "m"))                                    # 예전 설정(경로 포함)은 그대로
    assert sent[-1]["json"]["click"] == "https://other.example.com:8443/kis"
    assert notify.status()["link"] == "https://other.example.com:8443/kis"
    monkeypatch.setattr(settings, "ntfy_click_url", "")
    for bad in ("evil.com/x", "a b", "javascript:alert(1)", "https://x.com"):
        monkeypatch.setattr(settings, "domain", bad)
        assert notify.app_url("/kis") is None, bad


def test_kis_pushes_link_to_order(monkeypatch):
    got = []
    monkeypatch.setattr(notify, "send_bg", lambda title, body, priority=3, tags=None, click=None: got.append(click))
    kis_trade._push("t", "b", 4, order_id=12)
    kis_trade._push("t", "b")
    assert got == ["/kis?order=12", "/kis"]
