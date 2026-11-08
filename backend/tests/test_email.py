import pytest

from app.services import email_service as email_module
from app.services.email_service import EmailService, parse_email_from


def _service() -> EmailService:
    """Instancia sem carregar o provedor real das settings."""
    service = EmailService.__new__(EmailService)
    service.from_email = "EFTV <no-reply@example.com>"
    service.frontend_url = "https://evertonfagundes.github.io/eftv"
    return service


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("EFTV <no-reply@example.com>", ("EFTV", "no-reply@example.com")),
        ('"EFTV TV" <contato@example.com>', ("EFTV TV", "contato@example.com")),
        ("  <contato@example.com> ", ("contato@example.com", "contato@example.com")),
        ("contato@example.com", ("contato@example.com", "contato@example.com")),
    ],
)
def test_parse_email_from(raw, expected):
    assert parse_email_from(raw) == expected


def test_brevo_payload_has_sender_recipient_text_and_html():
    service = _service()
    payload = service._brevo_payload(
        "cliente@example.com", "Assunto", "corpo texto", "<p>corpo html</p>"
    )
    assert payload == {
        "sender": {"name": "EFTV", "email": "no-reply@example.com"},
        "to": [{"email": "cliente@example.com"}],
        "subject": "Assunto",
        "textContent": "corpo texto",
        "htmlContent": "<p>corpo html</p>",
    }


def test_brevo_payload_omits_html_when_absent():
    service = _service()
    payload = service._brevo_payload("cliente@example.com", "Assunto", "corpo")
    assert "htmlContent" not in payload


def test_provider_auto_prefers_brevo(monkeypatch):
    monkeypatch.setattr(email_module.settings, "EMAIL_PROVIDER", "auto")
    monkeypatch.setattr(email_module.settings, "BREVO_API_KEY", "brevo-key")
    monkeypatch.setattr(email_module.settings, "RESEND_API_KEY", "resend-key")
    assert EmailService().provider == "brevo"


def test_provider_auto_falls_back_to_resend(monkeypatch):
    monkeypatch.setattr(email_module.settings, "EMAIL_PROVIDER", "auto")
    monkeypatch.setattr(email_module.settings, "BREVO_API_KEY", None)
    monkeypatch.setattr(email_module.settings, "RESEND_API_KEY", "resend-key")
    assert EmailService().provider == "resend"


def test_provider_auto_without_keys_is_dev(monkeypatch):
    monkeypatch.setattr(email_module.settings, "EMAIL_PROVIDER", "auto")
    monkeypatch.setattr(email_module.settings, "BREVO_API_KEY", None)
    monkeypatch.setattr(email_module.settings, "RESEND_API_KEY", None)
    assert EmailService().provider == "dev"


def test_provider_explicit_dev_wins_over_keys(monkeypatch):
    monkeypatch.setattr(email_module.settings, "EMAIL_PROVIDER", "dev")
    monkeypatch.setattr(email_module.settings, "BREVO_API_KEY", "brevo-key")
    assert EmailService().provider == "dev"


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, response: _FakeResponse, calls: list[dict]) -> None:
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.response


@pytest.mark.asyncio
async def test_send_via_brevo_posts_to_api_with_key(monkeypatch):
    calls: list[dict] = []
    seen: dict[str, str] = {}

    def fake_client_factory(*args, **kwargs):
        return _FakeClient(_FakeResponse(201), calls)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)

    service = _service()
    service.brevo_api_key = "brevo-key"
    seen["ok"] = await service._send_via_brevo(
        "cliente@example.com", "Assunto", "texto", "<p>html</p>"
    )

    assert seen["ok"] is True
    assert calls[0]["url"] == "https://api.brevo.com/v3/smtp/email"
    assert calls[0]["headers"]["api-key"] == "brevo-key"
    assert calls[0]["json"]["to"] == [{"email": "cliente@example.com"}]


@pytest.mark.asyncio
async def test_send_via_brevo_returns_false_on_rejection(monkeypatch):
    def fake_client_factory(*args, **kwargs):
        return _FakeClient(_FakeResponse(401, "unauthorized"), [])

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)

    service = _service()
    service.brevo_api_key = "brevo-key"
    assert await service._send_via_brevo("cliente@example.com", "Assunto", "texto") is False
