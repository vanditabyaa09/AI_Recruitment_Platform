import pytest
import pytest_asyncio


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: marks tests requiring a database")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _create_schema():
    """The in-memory DB starts empty and httpx's ASGITransport does not run the
    app lifespan, so create the schema before each test (and drop it after for
    isolation)."""
    import app.models  # noqa: F401 — register tables on Base
    from app.database import engine, Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
