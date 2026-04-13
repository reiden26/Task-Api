"""
Configuración de pytest y fixtures.

Proporciona fixtures para testing async con FastAPI, PostgreSQL y Redis.
"""

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

# Configurar entorno de testing ANTES de importar la app
os.environ["ENVIRONMENT"] = "testing"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["DEBUG"] = "false"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.repositories.task import task_repository
from app.repositories.user import user_repository

# =============================================================================
# Configuración de Base de Datos de Prueba
# =============================================================================

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://taskapi:taskapi_secret@postgres:5432/taskdb_test"
)


# =============================================================================
# Fixtures de Session y Event Loop
# =============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Crea un event loop para la sesión de tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database() -> AsyncGenerator[None, None]:
    """
    Configura la base de datos de prueba.
    Crea todas las tablas antes de los tests y las elimina después.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Limpiar después de todos los tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Fixture para sesión de base de datos aislada.
    Crea una nueva sesión para cada test y hace rollback al final.
    """
    # Crear engine nuevo para cada test para evitar problemas de event loop
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        poolclass=None,  # Usar NullPool implícitamente para tests
        pool_pre_ping=True,
    )

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()
            await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture para cliente HTTP async.
    Overridea la dependencia de BD para usar la sesión de prueba.
    """
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Reemplazar dependencia
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Limpiar override
    app.dependency_overrides.clear()


# =============================================================================
# Fixtures de Limpieza
# =============================================================================

@pytest_asyncio.fixture(autouse=True)
async def reset_redis_connections() -> AsyncGenerator[None, None]:
    """
    Reinicia las conexiones de Redis antes de cada test.
    Esto evita errores de 'Event loop is closed'.
    """
    # Reiniciar conexiones Redis en los servicios
    from app.core.cache import cache_manager
    from app.core.rate_limit import rate_limiter
    from app.services.auth import auth_service

    cache_manager._redis = None
    rate_limiter._redis = None
    auth_service._redis = None

    yield

    # Limpiar Redis después del test si hay conexión
    try:
        if cache_manager._redis:
            await cache_manager._redis.close()
    except Exception:
        pass
    try:
        if rate_limiter._redis:
            await rate_limiter._redis.close()
    except Exception:
        pass
    try:
        if auth_service._redis:
            await auth_service._redis.close()
    except Exception:
        pass

    cache_manager._redis = None
    rate_limiter._redis = None
    auth_service._redis = None


@pytest_asyncio.fixture(autouse=True)
async def cleanup_database(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """
    Limpia todos los datos de prueba antes de cada test.
    Esto evita violaciones de constraints únicos entre ejecuciones.
    """
    from sqlalchemy import delete

    # Limpiar tareas primero (dependen de usuarios)
    await db_session.execute(delete(Task))
    # Luego limpiar usuarios
    await db_session.execute(delete(User))
    await db_session.commit()

    yield

    # Limpiar después del test también
    await db_session.execute(delete(Task))
    await db_session.execute(delete(User))
    await db_session.commit()


# =============================================================================
# Fixtures de Usuarios
# =============================================================================

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """
    Fixture que crea un usuario de prueba estándar.
    """
    user_data = {
        "email": "test@example.com",
        "hashed_password": get_password_hash("TestPassword123"),
        "full_name": "Test User",
        "is_active": True,
        "is_superuser": False,
    }

    user = await user_repository.create(db_session, obj_in=user_data)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession) -> User:
    """
    Fixture que crea un segundo usuario de prueba.
    """
    user_data = {
        "email": "test2@example.com",
        "hashed_password": get_password_hash("TestPassword123"),
        "full_name": "Test User 2",
        "is_active": True,
        "is_superuser": False,
    }

    user = await user_repository.create(db_session, obj_in=user_data)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession) -> User:
    """
    Fixture que crea un usuario inactivo.
    """
    user_data = {
        "email": "inactive@example.com",
        "hashed_password": get_password_hash("TestPassword123"),
        "full_name": "Inactive User",
        "is_active": False,
        "is_superuser": False,
    }

    user = await user_repository.create(db_session, obj_in=user_data)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def deleted_user(db_session: AsyncSession) -> User:
    """
    Fixture que crea un usuario eliminado (soft delete).
    """
    user_data = {
        "email": "deleted@example.com",
        "hashed_password": get_password_hash("TestPassword123"),
        "full_name": "Deleted User",
        "is_active": True,
        "is_superuser": False,
    }

    user = await user_repository.create(db_session, obj_in=user_data)
    user.soft_delete()
    await db_session.commit()
    return user


# =============================================================================
# Fixtures de Autenticación
# =============================================================================

@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user: User) -> dict[str, str]:
    """
    Fixture que retorna headers de autenticación para el usuario de prueba.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123",
        },
    )

    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_headers_user_2(client: AsyncClient, test_user_2: User) -> dict[str, str]:
    """
    Fixture que retorna headers de autenticación para el segundo usuario.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test2@example.com",
            "password": "TestPassword123",
        },
    )

    assert response.status_code == 200
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def refresh_token_data(client: AsyncClient, test_user: User) -> dict[str, Any]:
    """
    Fixture que retiene los tokens del login para tests de refresh.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123",
        },
    )

    assert response.status_code == 200
    data = response.json()

    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_in": data["expires_in"],
    }


# =============================================================================
# Fixtures de Tareas
# =============================================================================

@pytest_asyncio.fixture
async def sample_task(db_session: AsyncSession, test_user: User) -> Task:
    """
    Fixture que crea una tarea de ejemplo.
    """
    task_data = {
        "title": "Sample Task",
        "description": "This is a sample task",
        "status": TaskStatus.TODO.value,
        "priority": TaskPriority.MEDIUM.value,
        "owner_id": test_user.id,
    }

    task = await task_repository.create(db_session, obj_in=task_data)
    await db_session.commit()
    return task


@pytest_asyncio.fixture
async def sample_tasks(db_session: AsyncSession, test_user: User) -> list[Task]:
    """
    Fixture que crea múltiples tareas de ejemplo.
    """
    tasks = []
    statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]
    priorities = [TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH]

    for i in range(9):
        task_data = {
            "title": f"Task {i}",
            "description": f"Description for task {i}",
            "status": statuses[i % 3].value,
            "priority": priorities[i % 3].value,
            "owner_id": test_user.id,
        }

        task = await task_repository.create(db_session, obj_in=task_data)
        tasks.append(task)

    await db_session.commit()
    return tasks


@pytest_asyncio.fixture
async def other_user_task(db_session: AsyncSession, test_user_2: User) -> Task:
    """
    Fixture que crea una tarea perteneciente a otro usuario.
    """
    task_data = {
        "title": "Other User Task",
        "description": "This task belongs to user 2",
        "status": TaskStatus.TODO.value,
        "priority": TaskPriority.HIGH.value,
        "owner_id": test_user_2.id,
    }

    task = await task_repository.create(db_session, obj_in=task_data)
    await db_session.commit()
    return task


@pytest_asyncio.fixture
async def deleted_task(db_session: AsyncSession, test_user: User) -> Task:
    """
    Fixture que crea una tarea eliminada (soft delete).
    """
    task_data = {
        "title": "Deleted Task",
        "description": "This task has been deleted",
        "status": TaskStatus.DONE.value,
        "priority": TaskPriority.LOW.value,
        "owner_id": test_user.id,
    }

    task = await task_repository.create(db_session, obj_in=task_data)
    task.soft_delete()
    await db_session.commit()
    return task


@pytest_asyncio.fixture
async def overdue_task(db_session: AsyncSession, test_user: User) -> Task:
    """
    Fixture que crea una tarea vencida.
    """
    from datetime import timedelta

    task_data = {
        "title": "Overdue Task",
        "description": "This task is overdue",
        "status": TaskStatus.TODO.value,
        "priority": TaskPriority.URGENT.value,
        "due_date": datetime.now(timezone.utc) - timedelta(days=1),
        "owner_id": test_user.id,
    }

    task = await task_repository.create(db_session, obj_in=task_data)
    await db_session.commit()
    return task


# =============================================================================
# Fixtures de Datos
# =============================================================================

@pytest.fixture
def user_create_data() -> dict[str, Any]:
    """Datos válidos para crear un usuario."""
    return {
        "email": "newuser@example.com",
        "password": "NewPassword123",
        "full_name": "New User",
    }


@pytest.fixture
def user_create_data_weak_password() -> dict[str, Any]:
    """Datos con contraseña débil para tests de validación."""
    return {
        "email": "weak@example.com",
        "password": "weak",
        "full_name": "Weak Password User",
    }


@pytest.fixture
def user_create_data_no_uppercase() -> dict[str, Any]:
    """Datos con contraseña sin mayúsculas."""
    return {
        "email": "noupper@example.com",
        "password": "password123",
        "full_name": "No Uppercase User",
    }


@pytest.fixture
def task_create_data() -> dict[str, Any]:
    """Datos válidos para crear una tarea."""
    return {
        "title": "Test Task",
        "description": "Test description",
        "priority": "MEDIUM",
        "status": "TODO",
    }


@pytest.fixture
def task_update_data() -> dict[str, Any]:
    """Datos para actualizar una tarea."""
    return {
        "title": "Updated Task",
        "description": "Updated description",
        "priority": "HIGH",
        "status": "IN_PROGRESS",
    }


@pytest.fixture
def task_partial_update_data() -> dict[str, Any]:
    """Datos para actualización parcial de tarea."""
    return {
        "description": "Only description updated",
    }


@pytest.fixture
def invalid_uuid() -> str:
    """Retorna un UUID inválido para tests de error."""
    return "12345678-1234-5678-1234-567812345678"
