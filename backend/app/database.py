from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def _normalize_db_url(raw_url: str) -> tuple[str, dict]:
    """Make a managed-Postgres URL usable by SQLAlchemy + asyncpg.

    Handles the common shapes that Neon / Supabase / Render / Heroku emit:
    - `postgres://` or bare `postgresql://`  -> `postgresql+asyncpg://`
    - libpq query params asyncpg doesn't accept (`sslmode`, `channel_binding`,
      `ssl`) are stripped and translated into a `connect_args={"ssl": True}`.
    Returns (clean_url, connect_args).
    """
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))

    sslmode = (query.pop("sslmode", "") or "").lower()
    ssl_flag = (query.pop("ssl", "") or "").lower()
    query.pop("channel_binding", None)  # asyncpg does not accept this kwarg

    connect_args: dict = {}
    if sslmode in ("require", "verify-ca", "verify-full", "prefer", "allow") or ssl_flag in ("true", "require", "1"):
        connect_args["ssl"] = True

    clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return clean_url, connect_args


_db_url, _connect_args = _normalize_db_url(settings.database_url)

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_pre_ping=True,   # drop dead connections (managed PG closes idle ones)
    pool_recycle=1800,    # recycle before provider-side idle timeouts
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
