import gzip
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.models.playlist_cache import PlaylistCache
from app.routes.admin import router as admin_router
from app.security.dependencies import require_admin
from app.security.middleware import BodySizeLimitMiddleware
from app.services import playlist_cache

M3U = b"#EXTM3U\n#EXTINF:-1,Canal\nhttp://provider.example/live/user/pass/1.ts\n"


@pytest.fixture(autouse=True)
def _clean_memory():
    playlist_cache.clear_memory_cache()
    yield
    playlist_cache.clear_memory_cache()


@pytest.mark.asyncio
async def test_admin_upload_and_read_cache():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(PlaylistCache.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:

        async def override_db():
            yield session

        app = FastAPI()
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_bytes=1024,
            large_paths={"/admin/playlist/cache": 10 * 1024 * 1024},
        )
        app.include_router(admin_router)
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
            id="admin-1", email="admin@example.com"
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/admin/playlist/cache",
                content=gzip.compress(M3U),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["size_bytes"] == len(M3U)

            status = await client.get("/admin/playlist/cache")
            assert status.status_code == 200
            assert status.json()["cached"] is True
            assert status.json()["size_bytes"] == len(M3U)

            removed = await client.delete("/admin/playlist/cache")
            assert removed.status_code == 200
            assert removed.json()["cached"] is False

            status = await client.get("/admin/playlist/cache")
            assert status.json()["cached"] is False

    await engine.dispose()
