from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from annos.config import settings


class Base(DeclarativeBase):
    """Declarative base for Annos-owned tables only.

    Better Auth manages its own tables (user, session, account, verification,
    oauthApplication, oauthAccessToken, oauthConsent) in the same database via
    its own CLI. Alembic must never touch them — see alembic/env.py.
    """


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
