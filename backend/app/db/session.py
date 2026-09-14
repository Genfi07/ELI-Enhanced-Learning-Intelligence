from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from sqlalchemy.pool import NullPool   # ← import

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.env == "test":
            # NullPool: cada conexión se abre y se cierra por uso. Elimina por
            # completo la clase de bugs de greenlet que aparecen al reciclar
            # conexiones del pool entre tests con event loops distintos.
            _engine = create_async_engine(
                settings.database_url,
                poolclass=NullPool,
            )
        else:
            # En dev/prod mantenemos pool + pre_ping (protege contra conexiones
            # muertas tras largos periodos de inactividad).
            _engine = create_async_engine(
                settings.database_url,
                pool_pre_ping=True,
            )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise