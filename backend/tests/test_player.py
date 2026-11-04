from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.config import settings
from app.routes.player import router
from app.security.dependencies import get_current_active_subscription
from app.services.devices import DeviceLimitError

DEVICE_HEADERS = {
    "X-Device-Id": "test-device-0001",
    "X-Device-Name": "Aparelho de teste",
}


class FakeSubscription:
    def __init__(self, days: int = 20) -> None:
        self.status = "active"
        self.current_period_end = datetime.now(UTC) + timedelta(days=days)


def build_client(days: int = 20) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_subscription] = lambda: FakeSubscription(days)
    return TestClient(app)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    async def noop_bind(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routes.player.bind_device", noop_bind)
    return build_client()


def test_playlist_access_returns_configured_source(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_USER_AGENT", "VLC/3.0.20 LibVLC/3.0.20")
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_REFERER", None)

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["playlist_url"] == "https://provider.example/list.m3u"
    assert body["user_agent"] == "VLC/3.0.20 LibVLC/3.0.20"
    assert body["refresh_in"] == settings.IPTV_PLAYLIST_REFRESH_SECONDS
    assert body["offline_grace_seconds"] == settings.OFFLINE_GRACE_MINUTES * 60
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["days_remaining"] >= 19


def test_playlist_requires_device_id(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")

    response = client.get("/player/playlist")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"]["code"] == "device_id_missing"


def test_playlist_rejects_when_device_limit_reached(monkeypatch):
    async def deny_bind(*args, **kwargs):
        raise DeviceLimitError()

    monkeypatch.setattr("app.routes.player.bind_device", deny_bind)
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")

    response = build_client().get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"]["code"] == "device_limit"


def test_playlist_not_configured_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "")

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_playlist_requires_active_subscription():
    app = FastAPI()
    app.include_router(router)

    def deny():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura expirada ou cancelada",
        )

    app.dependency_overrides[get_current_active_subscription] = deny

    response = TestClient(app).get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_403_FORBIDDEN
