import gzip

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.playlist_cache import PlaylistCache
from app.services import playlist_cache

M3U = b"#EXTM3U\n#EXTINF:-1,Canal\nhttp://provider.example/live/user/pass/1.ts\n"


@pytest.fixture(autouse=True)
def _clean_memory():
    playlist_cache.clear_memory_cache()
    yield
    playlist_cache.clear_memory_cache()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(PlaylistCache.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_and_load_roundtrip(db):
    info = await playlist_cache.save_playlist(db, M3U, source="teste")
    assert info.size_bytes == len(M3U)
    assert info.compressed_bytes > 0
    assert info.sha256

    cached = await playlist_cache.load_cached_playlist(db)
    assert cached is not None
    raw, loaded = cached
    assert raw == M3U
    assert loaded.sha256 == info.sha256
    assert "provider.example" not in str(loaded.to_dict())


@pytest.mark.asyncio
async def test_load_uses_memory_after_first_read(db):
    await playlist_cache.save_playlist(db, M3U)
    first = await playlist_cache.load_cached_playlist(db)
    second = await playlist_cache.load_cached_playlist(db)
    assert first is not None and second is not None
    assert first[0] is second[0]


@pytest.mark.asyncio
async def test_clear_removes_cache(db):
    await playlist_cache.save_playlist(db, M3U)
    await playlist_cache.clear_playlist(db)
    assert await playlist_cache.cache_metadata(db) is None
    assert await playlist_cache.load_cached_playlist(db) is None


@pytest.mark.asyncio
async def test_rejects_non_m3u(db):
    with pytest.raises(playlist_cache.PlaylistCacheError):
        await playlist_cache.save_playlist(db, b"<html>nginx</html>")


def test_decode_upload_accepts_gzip_and_raw():
    assert playlist_cache.decode_upload(gzip.compress(M3U)) == M3U
    assert playlist_cache.decode_upload(M3U) == M3U


def test_decode_upload_rejects_invalid_gzip():
    with pytest.raises(playlist_cache.PlaylistCacheError):
        playlist_cache.decode_upload(b"\x1f\x8bnot-gzip")


def test_decode_upload_rejects_oversized(monkeypatch):
    monkeypatch.setattr(settings, "PLAYLIST_CACHE_MAX_BYTES", 256)
    raw = b"#EXTM3U\n" + b"x" * 512
    with pytest.raises(playlist_cache.PlaylistCacheError):
        playlist_cache.decode_upload(gzip.compress(raw))
