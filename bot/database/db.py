from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine
from typing import Optional, AsyncGenerator
import os
from contextlib import asynccontextmanager

from .models import Base

class Database:
    _instance: Optional['Database'] = None
    _engine: Optional[AsyncEngine] = None
    _session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """Initialize the database engine and session factory."""
        if self._engine is None:
            database_url = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///sessions.db')
            self._engine = create_async_engine(database_url, echo=False)
            self._session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a SQLAlchemy AsyncSession as an async context manager."""
        if self._session_factory is None:
            await self.initialize()
        
        if self._session_factory is None:
            raise RuntimeError("Database session factory not initialized. Call initialize() first.")

        session: AsyncSession = self._session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def close(self):
        """Close the database engine and clean up resources."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
