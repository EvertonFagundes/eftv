# tests/test_app_client.py - Versao do app (atualizacao por APK) e erros do cliente
import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError

from app.config import settings
from app.models.client_error import ClientError
from app.routes import app_client


def make_request(ip: str = "203.0.113.7") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/app/crashes",
            "headers": [],
            "client": (ip, 50000),
        }
    )


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


async def test_version_reports_configured_update(monkeypatch):
    monkeypatch.setattr(settings, "APP_LATEST_VERSION_CODE", 12)
    monkeypatch.setattr(settings, "APP_LATEST_VERSION_NAME", "1.2.0")
    monkeypatch.setattr(settings, "APP_APK_URL", "https://exemplo/eftv-1.2.0.apk")
    monkeypatch.setattr(settings, "APP_UPDATE_NOTES", "Correcoes")
    monkeypatch.setattr(settings, "APP_UPDATE_MANDATORY", True)

    response = await app_client.app_version()

    assert response.version_code == 12
    assert response.version_name == "1.2.0"
    assert response.apk_url.endswith(".apk")
    assert response.notes == "Correcoes"
    assert response.mandatory is True
    assert response.update_available_from is True


async def test_version_says_nothing_when_no_apk_published(monkeypatch):
    monkeypatch.setattr(settings, "APP_LATEST_VERSION_CODE", 0)
    monkeypatch.setattr(settings, "APP_APK_URL", "")

    response = await app_client.app_version()

    assert response.update_available_from is False


async def test_tv_download_redirects_to_apk(monkeypatch):
    """A TV recebe 302 direto no APK: app de download da TV nao abre HTML."""
    monkeypatch.setattr(settings, "APP_APK_URL", "https://exemplo/eftv-1.4.7.apk")

    response = await app_client.apk_download()

    assert response.status_code == 302
    assert response.headers["location"] == "https://exemplo/eftv-1.4.7.apk"


async def test_tv_download_without_apk_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "APP_APK_URL", "   ")

    with pytest.raises(HTTPException) as exc:
        await app_client.apk_download()

    assert exc.value.status_code == 503


async def test_crash_report_is_stored(monkeypatch):
    monkeypatch.setattr(settings, "CLIENT_ERRORS_ENABLED", True)
    db = FakeSession()

    async def no_limit(*args, **kwargs):
        return 0

    monkeypatch.setattr(app_client.rate_limit, "hit", no_limit)

    payload = app_client.CrashReportRequest(
        message="NullPointerException",
        stacktrace="at com.eftv.android.PlayerActivity.onCreate(PlayerActivity.kt:1)",
        app_version="1.1.8",
        device="Xiaomi 24117RN76G",
        android="14",
    )

    result = await app_client.report_crash(payload, make_request(), db=db)

    assert result == {"accepted": True}
    assert db.commits == 1
    error = db.added[0]
    assert isinstance(error, ClientError)
    assert error.app_version == "1.1.8"
    assert "NullPointer" in error.message


def test_oversized_payloads_are_rejected():
    """Nada de um cliente malicioso encher o banco com megabytes de stacktrace."""
    with pytest.raises(ValidationError):
        app_client.CrashReportRequest(message="x" * 10_000)
    with pytest.raises(ValidationError):
        app_client.CrashReportRequest(stacktrace="y" * 50_000)


async def test_crash_report_disabled_does_nothing(monkeypatch):
    monkeypatch.setattr(settings, "CLIENT_ERRORS_ENABLED", False)
    db = FakeSession()

    result = await app_client.report_crash(
        app_client.CrashReportRequest(message="erro"), make_request(), db=db
    )

    assert result == {"accepted": False}
    assert db.added == []


def test_client_error_repr_is_safe():
    error = ClientError(app_version="1.1.8", message="boom")
    assert "1.1.8" in repr(error)
