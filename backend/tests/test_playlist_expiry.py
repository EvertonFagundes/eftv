# tests/test_playlist_expiry.py - Vencimento da playlist licenciada
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routes import admin
from app.services import playlist_expiry as expiry

OWNER_EMAIL = "evertonfagundes1510@gmail.com"
PLAYLIST_URL = (
    "http://provider.example:8080/get.php?username=usuario&password=segredo&type=m3u_plus"
)


@pytest.fixture(autouse=True)
def reset_cache():
    expiry.clear_cache()
    yield
    expiry.clear_cache()


# --- derivacao da URL e leitura de datas -----------------------------------


def test_player_api_url_keeps_credentials_and_drops_type():
    url = expiry.build_player_api_url(PLAYLIST_URL)

    assert url == ("http://provider.example:8080/player_api.php?username=usuario&password=segredo")


def test_player_api_url_works_without_get_php():
    url = expiry.build_player_api_url("http://host:8080/?username=u&password=p")

    assert url == "http://host:8080/player_api.php?username=u&password=p"


def test_player_api_url_requires_credentials():
    assert expiry.build_player_api_url("http://host/list.m3u") is None
    assert expiry.build_player_api_url("http://host/get.php?username=u") is None
    assert expiry.build_player_api_url("") is None


def test_parse_expiry_accepts_unix_seconds_and_milliseconds():
    expected = datetime(2026, 1, 1, tzinfo=UTC)

    assert expiry.parse_expiry("1767225600") == expected
    assert expiry.parse_expiry(1767225600) == expected
    assert expiry.parse_expiry("1767225600000") == expected


def test_parse_expiry_accepts_brazilian_and_iso_dates():
    assert expiry.parse_expiry("31/12/2026 23:59") == datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    assert expiry.parse_expiry("31-12-2026") == datetime(2026, 12, 31, tzinfo=UTC)
    assert expiry.parse_expiry("2026-12-31") == datetime(2026, 12, 31, tzinfo=UTC)
    assert expiry.parse_expiry("2026-12-31T23:59:00Z") == datetime(2026, 12, 31, 23, 59, tzinfo=UTC)


@pytest.mark.parametrize("value", [None, "", "null", "0", "-1", "sem data"])
def test_parse_expiry_treats_empty_values_as_no_expiry(value):
    assert expiry.parse_expiry(value) is None


def test_extract_m3u_expiry_reads_published_date():
    text = '#EXTM3U\n#EXTINF:-1 tvg-name="VENCIMENTO 31/12/2026",Canal\nhttp://host/1'

    assert expiry.extract_m3u_expiry(text) == datetime(2026, 12, 31, tzinfo=UTC)
    assert expiry.extract_m3u_expiry("#EXTINF:-1,Validade: 31/12/2026") == datetime(
        2026, 12, 31, tzinfo=UTC
    )


def test_extract_m3u_expiry_returns_none_when_absent():
    assert expiry.extract_m3u_expiry("#EXTM3U\n#EXTINF:-1,Canal\nhttp://host/1") is None


def test_allowed_emails_are_parsed_from_comma_list(monkeypatch):
    monkeypatch.setattr(settings, "PLAYLIST_EXPIRY_EMAILS", " A@X.com , b@y.com, ")

    assert settings.playlist_expiry_emails == {"a@x.com", "b@y.com"}


def test_default_allow_list_is_the_owner():
    from app.config import Settings

    assert Settings.model_fields["PLAYLIST_EXPIRY_EMAILS"].default == OWNER_EMAIL


# --- consulta ao provedor --------------------------------------------------


def account_payload(**overrides) -> dict:
    info = {
        "auth": 1,
        "status": "Active",
        "exp_date": "1767225600",
        "max_connections": "2",
        "is_trial": "0",
    }
    info.update(overrides)
    return {"user_info": info}


async def test_check_uses_account_api(monkeypatch):
    async def fake_api(*args, **kwargs):
        return account_payload()

    async def fail_playlist(*args, **kwargs):
        raise AssertionError("nao deveria baixar o .m3u quando a API responde")

    monkeypatch.setattr(expiry, "fetch_account_info", fake_api)
    monkeypatch.setattr(expiry, "fetch_playlist_text", fail_playlist)

    result = await expiry.check_playlist_expiry(PLAYLIST_URL, now=datetime(2025, 12, 1, tzinfo=UTC))

    assert result.source == "player_api"
    assert result.status == "Active"
    assert result.max_connections == 2
    assert result.is_trial is False
    assert result.expires_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert result.days_remaining == 31
    assert result.expired is False
    assert result.active is True
    assert result.provider_host == "provider.example"
    # Nunca vazar usuario/senha para o painel.
    assert "segredo" not in str(result.to_dict())
    assert "usuario" not in str(result.to_dict())


async def test_check_caches_result_and_force_refreshes(monkeypatch):
    calls = []

    async def fake_api(*args, **kwargs):
        calls.append(1)
        return account_payload()

    monkeypatch.setattr(expiry, "fetch_account_info", fake_api)
    monkeypatch.setattr(settings, "PLAYLIST_EXPIRY_CACHE_SECONDS", 3600)

    first = await expiry.check_playlist_expiry(PLAYLIST_URL)
    second = await expiry.check_playlist_expiry(PLAYLIST_URL)

    assert len(calls) == 1
    assert first.from_cache is False
    assert second.from_cache is True

    await expiry.check_playlist_expiry(PLAYLIST_URL, force=True)
    assert len(calls) == 2


async def test_check_falls_back_to_m3u_date(monkeypatch):
    async def broken_api(*args, **kwargs):
        raise expiry.httpx.ConnectError("sem rota")

    async def fake_playlist(*args, **kwargs):
        return '#EXTM3U\n#EXTINF:-1 tvg-name="VENCIMENTO 31/12/2026",Canal'

    monkeypatch.setattr(expiry, "fetch_account_info", broken_api)
    monkeypatch.setattr(expiry, "fetch_playlist_text", fake_playlist)

    result = await expiry.check_playlist_expiry(PLAYLIST_URL)

    assert result.source == "m3u"
    assert result.expires_at == datetime(2026, 12, 31, tzinfo=UTC)
    assert result.error == "Nao foi possivel falar com o provedor"


async def test_check_reports_provider_unreachable(monkeypatch):
    async def broken_api(*args, **kwargs):
        raise expiry.httpx.ConnectError("sem rota")

    async def broken_playlist(*args, **kwargs):
        raise expiry.httpx.ConnectError("sem rota")

    monkeypatch.setattr(expiry, "fetch_account_info", broken_api)
    monkeypatch.setattr(expiry, "fetch_playlist_text", broken_playlist)

    result = await expiry.check_playlist_expiry(PLAYLIST_URL)

    assert result.source == "unavailable"
    assert result.expires_at is None
    assert "Nao foi possivel falar com o provedor" in result.error
    assert result.provider_host == "provider.example"


async def test_check_without_configured_url(monkeypatch):
    result = await expiry.check_playlist_expiry("")

    assert result.source == "unavailable"
    assert result.error == "Playlist nao configurada no servidor"


async def test_banned_or_expired_status_is_not_active(monkeypatch):
    async def fake_api(*args, **kwargs):
        return account_payload(status="Expired", exp_date="1704067200")

    monkeypatch.setattr(expiry, "fetch_account_info", fake_api)

    result = await expiry.check_playlist_expiry(PLAYLIST_URL, now=datetime(2025, 12, 1, tzinfo=UTC))

    assert result.status == "Expired"
    assert result.days_remaining == -1
    assert result.expired is True
    assert result.active is False


# --- endpoint /admin/playlist/expiry --------------------------------------


def build_client(email: str) -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin.require_admin] = lambda: SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001", email=email
    )
    return TestClient(app)


def test_expiry_endpoint_rejects_admin_outside_the_allow_list(monkeypatch):
    monkeypatch.setattr(settings, "PLAYLIST_EXPIRY_EMAILS", OWNER_EMAIL)
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", PLAYLIST_URL)

    response = build_client("outro-admin@example.com").get("/admin/playlist/expiry")

    assert response.status_code == 403


def test_expiry_endpoint_returns_owner_data(monkeypatch):
    async def fake_check(url, **kwargs):
        assert url == PLAYLIST_URL
        return expiry.PlaylistExpiry(
            checked_at=datetime(2025, 12, 1, tzinfo=UTC),
            expires_at=datetime(2026, 1, 1, tzinfo=UTC),
            status="Active",
            max_connections=2,
            is_trial=False,
            source="player_api",
            provider_host="provider.example",
        )

    monkeypatch.setattr(settings, "PLAYLIST_EXPIRY_EMAILS", OWNER_EMAIL)
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", PLAYLIST_URL)
    monkeypatch.setattr(admin, "check_playlist_expiry", fake_check)

    response = build_client(OWNER_EMAIL).get("/admin/playlist/expiry")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "player_api"
    assert body["status"] == "Active"
    assert body["days_remaining"] == 31
    assert body["active"] is True
    assert body["provider_host"] == "provider.example"
    assert body["cache_seconds"] == settings.PLAYLIST_EXPIRY_CACHE_SECONDS
    assert "segredo" not in response.text


def test_expiry_endpoint_passes_refresh(monkeypatch):
    seen = {}

    async def fake_check(url, **kwargs):
        seen.update(kwargs)
        return expiry.PlaylistExpiry(checked_at=datetime(2025, 12, 1, tzinfo=UTC))

    monkeypatch.setattr(settings, "PLAYLIST_EXPIRY_EMAILS", OWNER_EMAIL)
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", PLAYLIST_URL)
    monkeypatch.setattr(admin, "check_playlist_expiry", fake_check)

    response = build_client(OWNER_EMAIL).get("/admin/playlist/expiry?refresh=true")

    assert response.status_code == 200
    assert seen["force"] is True


def test_expiry_endpoint_requires_configured_playlist(monkeypatch):
    monkeypatch.setattr(settings, "PLAYLIST_EXPIRY_EMAILS", OWNER_EMAIL)
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "")

    response = build_client(OWNER_EMAIL).get("/admin/playlist/expiry")

    assert response.status_code == 503
