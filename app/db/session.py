"""
Gestión de sesiones de base de datos async con SQLAlchemy.

Proporciona factory de sesiones y utilidades para transacciones.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Configuración del motor async de SQLAlchemy
# NullPool en testing para evitar conexiones persistentes
if settings.is_testing:
    from sqlalchemy.pool import NullPool
    engine = create_async_engine(
        settings.ASYNC_DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        settings.ASYNC_DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

# Factory de sesiones async
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Mantiene objetos accesibles después del commit
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency de FastAPI para obtener sesiones de BD.

    Yields:
        Sesión de base de datos async

    Example:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager para sesiones de BD fuera de endpoints.

    Útil para scripts, tareas en background, etc.

    Example:
        async with get_db_context() as db:
            user = await user_repo.get_by_id(db, user_id)
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class DatabaseManager:
    """
    Manager de base de datos para operaciones administrativas.
    """

    @staticmethod
    async def create_tables():
        """Crea todas las tablas (útil para testing)."""
        from app.db.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created")

    @staticmethod
    async def drop_tables():
        """Elimina todas las tablas (¡cuidado!)."""
        from app.db.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("database_tables_dropped")

    @staticmethod
    async def check_connection() -> bool:
        """
        Verifica que la conexión a BD funcione.

        Returns:
            True si la conexión es exitosa
        """
        from sqlalchemy import text

        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                result.fetchone()
            return True
        except Exception as e:
            logger.error("database_connection_failed", error=str(e))
            return False

    @staticmethod
    async def close():
        """Cierra el pool de conexiones."""
        await engine.dispose()
        logger.info("database_engine_disposed")


db_manager = DatabaseManager()