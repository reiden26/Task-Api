"""
Sistema de caché con Redis.

Proporciona decoradores y funciones utilitarias para cachear resultados.
"""

import json
from functools import wraps
from typing import Any, Callable, TypeVar

import redis.asyncio as redis
import structlog
from fastapi.encoders import jsonable_encoder

from app.core.config import settings

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CacheManager:
    """
    Manager de caché con Redis.

    Soporta operaciones básicas y serialización JSON.
    """

    def __init__(self):
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        """Obtiene o crea la conexión a Redis."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_CONNECTION_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def get(self, key: str) -> Any | None:
        """
        Obtiene un valor de la caché.

        Args:
            key: Clave a buscar

        Returns:
            Valor deserializado o None si no existe
        """
        try:
            redis_client = await self._get_redis()
            value = await redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("cache_get_error", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: int = 300,
    ) -> bool:
        """
        Guarda un valor en la caché.

        Args:
            key: Clave para almacenar
            value: Valor a almacenar (se serializa a JSON)
            expire: Tiempo de expiración en segundos (default: 5 min)

        Returns:
            True si se guardó correctamente
        """
        try:
            redis_client = await self._get_redis()
            serialized = json.dumps(jsonable_encoder(value))
            await redis_client.setex(key, expire, serialized)
            logger.debug("cache_set", key=key, expire=expire)
            return True
        except Exception as e:
            logger.error("cache_set_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Elimina una clave de la caché.

        Args:
            key: Clave a eliminar

        Returns:
            True si se eliminó
        """
        try:
            redis_client = await self._get_redis()
            await redis_client.delete(key)
            logger.debug("cache_delete", key=key)
            return True
        except Exception as e:
            logger.error("cache_delete_error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Elimina todas las claves que coincidan con un patrón.

        Args:
            pattern: Patrón de búsqueda (ej: "task:*")

        Returns:
            Número de claves eliminadas
        """
        try:
            redis_client = await self._get_redis()
            keys = await redis_client.keys(pattern)
            if keys:
                await redis_client.delete(*keys)
                logger.debug("cache_delete_pattern", pattern=pattern, count=len(keys))
                return len(keys)
            return 0
        except Exception as e:
            logger.error("cache_delete_pattern_error", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        """
        Verifica si una clave existe en la caché.

        Args:
            key: Clave a verificar

        Returns:
            True si existe
        """
        try:
            redis_client = await self._get_redis()
            return await redis_client.exists(key) > 0
        except Exception:
            return False

    async def clear(self) -> bool:
        """
        Limpia toda la caché (usar con precaución).

        Returns:
            True si se limpió correctamente
        """
        try:
            redis_client = await self._get_redis()
            await redis_client.flushdb()
            logger.warning("cache_cleared")
            return True
        except Exception as e:
            logger.error("cache_clear_error", error=str(e))
            return False


# Instancia global del manager de caché
cache_manager = CacheManager()


# =============================================================================
# Decoradores de caché
# =============================================================================

def cached(key_prefix: str, expire: int = 300):
    """
    Decorador para cachear resultados de funciones async.

    Args:
        key_prefix: Prefijo para la clave de caché
        expire: Tiempo de expiración en segundos

    Example:
        @cached(key_prefix="task", expire=300)
        async def get_task(task_id: UUID) -> Task:
            return await task_repo.get_by_id(task_id)
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Generar clave de caché
            cache_key = f"{key_prefix}:{args[1:] if len(args) > 1 else kwargs.get('task_id', '')}"

            # Intentar obtener de caché
            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                logger.debug("cache_hit", key=cache_key)
                return cached_value

            # Ejecutar función y guardar en caché
            result = await func(*args, **kwargs)
            if result is not None:
                await cache_manager.set(cache_key, result, expire)
                logger.debug("cache_miss", key=cache_key)

            return result

        # Agregar método para invalidar caché
        async def invalidate_cache(*args, **kwargs) -> None:
            cache_key = f"{key_prefix}:{args[0] if args else kwargs.get('task_id', '')}"
            await cache_manager.delete(cache_key)

        wrapper.invalidate_cache = invalidate_cache  # type: ignore
        return wrapper
    return decorator


def cache_invalidate(key_prefix: str):
    """
    Decorador para invalidar caché después de ejecutar una función.

    Args:
        key_prefix: Prefijo de la clave a invalidar

    Example:
        @cache_invalidate(key_prefix="task")
        async def update_task(task_id: UUID, ...) -> Task:
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            result = await func(*args, **kwargs)

            # Invalidar caché
            task_id = kwargs.get('task_id') or (args[0] if args else None)
            if task_id:
                cache_key = f"{key_prefix}:{task_id}"
                await cache_manager.delete(cache_key)
                logger.debug("cache_invalidated", key=cache_key)

            return result
        return wrapper
    return decorator