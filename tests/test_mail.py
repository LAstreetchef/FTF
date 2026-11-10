from app import app
from utils import send_email


def test_resend_sends_over_https(monkeypatch):
    calls = {}

    class Resp:
        status_code = 200

    def fake_post(url, headers, json, timeout):
        calls["url"] = url
        calls["auth"] = headers["Authorization"]
        calls["payload"] = json
        return Resp()

    monkeypatch.setenv("RESEND_API_KEY", "re_test_example")
    monkeypatch.setenv("MAIL_DEFAULT_SENDER", "Green Truck <truck@example.com>")
    monkeypatch.setattr("requests.post", fake_post)
    app.config["MAIL_SUPPRESS_SEND"] = False
    try:
        assert send_email("pat@example.com", "Hello", "Body text") is True
    finally:
        app.config["MAIL_SUPPRESS_SEND"] = True
    assert calls["url"] == "https://api.resend.com/emails"
    assert calls["auth"] == "Bearer re_test_example"
    assert calls["payload"]["from"] == "Green Truck <truck@example.com>"
    assert calls["payload"]["to"] == ["pat@example.com"]
    assert calls["payload"]["text"] == "Body text"


def test_resend_without_a_sender_does_not_post(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_example")
    monkeypatch.delenv("MAIL_DEFAULT_SENDER", raising=False)
    app.config["MAIL_DEFAULT_SENDER"] = "noreply@localhost"
    app.config["MAIL_SUPPRESS_SEND"] = False

    def fail_post(*args, **kwargs):
        raise AssertionError("should not call Resend")

    monkeypatch.setattr("requests.post", fail_post)
    try:
        assert send_email("pat@example.com", "Hello", "Body") is False
    finally:
        app.config["MAIL_SUPPRESS_SEND"] = True
