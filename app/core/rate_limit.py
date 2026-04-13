"""
Rate limiting implementado con Redis.

Protege la API contra abuso y ataques de fuerza bruta.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import redis.asyncio as redis
import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = structlog.get_logger(__name__)


class RateLimitType(Enum):
    """Tipos de rate limiting."""

    GENERAL = "general"
    LOGIN = "login"


@dataclass
class RateLimitConfig:
    """Configuración de rate limiting."""

    requests: int = 60
    window: int = 60  # segundos
    block_duration: int = 0  # segundos (0 = no bloquear, solo rate limit)
    key_prefix: str = "rl"


class RateLimiter:
    """
    Rate limiter basado en Redis con algoritmo sliding window.

    Soporta rate limiting general y específico para login.
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self._redis = redis_client
        self._configs = {
            RateLimitType.GENERAL: RateLimitConfig(
                requests=60,  # 60 requests per minute
                window=60,
                key_prefix="rl:general",
            ),
            RateLimitType.LOGIN: RateLimitConfig(
                requests=5,  # 5 login attempts
                window=900,  # per 15 minutes (900 seconds)
                block_duration=900,
                key_prefix="rl:login",
            ),
        }

    async def _get_redis(self) -> redis.Redis:
        """Obtiene o crea la conexión a Redis."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_CONNECTION_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_key(
        self,
        request: Request,
        rate_type: RateLimitType,
        identifier: Optional[str] = None,
    ) -> str:
        """
        Genera la clave de rate limit para una petición.

        Args:
            request: Request de FastAPI
            rate_type: Tipo de rate limiting
            identifier: Identificador opcional (ej: user_id)
        """
        config = self._configs[rate_type]

        if identifier and rate_type == RateLimitType.GENERAL:
            return f"{config.key_prefix}:user:{identifier}"

        # Obtener IP real (considerando proxies)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        if rate_type == RateLimitType.LOGIN:
            return f"{config.key_prefix}:{client_ip}"

        return f"{config.key_prefix}:ip:{client_ip}"

    async def is_allowed(
        self,
        request: Request,
        rate_type: RateLimitType = RateLimitType.GENERAL,
        identifier: Optional[str] = None,
    ) -> tuple[bool, dict, Optional[int]]:
        """
        Verifica si una petición está dentro del límite permitido.

        Args:
            request: Objeto Request de FastAPI
            rate_type: Tipo de rate limiting
            identifier: Identificador opcional (ej: user_id)

        Returns:
            Tupla de (permitido, headers_info, retry_after)
        """
        if not settings.RATE_LIMIT_ENABLED:
            return True, {
                "X-RateLimit-Limit": "unlimited",
                "X-RateLimit-Remaining": "unlimited",
            }, None

        try:
            redis_client = await self._get_redis()
            config = self._configs[rate_type]
            key = self._get_key(request, rate_type, identifier)
            now = int(__import__("time").time())
            window_start = now - config.window

            # Remover entradas antiguas (sliding window)
            await redis_client.zremrangebyscore(key, 0, window_start)

            # Verificar si está bloqueado (para login)
            block_key = f"{key}:blocked"
            is_blocked = await redis_client.get(block_key)
            if is_blocked:
                ttl = await redis_client.ttl(block_key)
                headers = {
                    "X-RateLimit-Limit": str(config.requests),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(ttl),
                }
                logger.warning(
                    "rate_limit_blocked",
                    key=key,
                    type=rate_type.value,
                    retry_after=ttl,
                )
                return False, headers, ttl

            # Contar peticiones actuales en la ventana
            current_count = await redis_client.zcard(key)

            if current_count >= config.requests:
                # Calcular tiempo hasta la próxima ventana
                oldest = await redis_client.zrange(key, 0, 0, withscores=True)
                reset_time = int(oldest[0][1]) + config.window if oldest else now
                retry_after = reset_time - now

                headers = {
                    "X-RateLimit-Limit": str(config.requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(retry_after),
                }

                # Bloquear para login attempts
                if rate_type == RateLimitType.LOGIN and config.block_duration > 0:
                    await redis_client.setex(
                        block_key,
                        config.block_duration,
                        "blocked",
                    )

                logger.warning(
                    "rate_limit_exceeded",
                    key=key,
                    type=rate_type.value,
                    count=current_count,
                    path=request.url.path,
                )

                return False, headers, retry_after

            # Agregar petición actual
            await redis_client.zadd(key, {str(now): now})
            await redis_client.expire(key, config.window)

            remaining = config.requests - current_count - 1

            headers = {
                "X-RateLimit-Limit": str(config.requests),
                "X-RateLimit-Remaining": str(max(0, remaining)),
                "X-RateLimit-Window": str(config.window),
            }

            return True, headers, None

        except Exception as e:
            logger.error("rate_limit_error", error=str(e), key=key)
            # En caso de error de Redis, permitir la petición
            return True, {}, None

    async def record_failed_login(self, request: Request) -> tuple[bool, Optional[int]]:
        """
        Registra un intento de login fallido.

        Args:
            request: Request de FastAPI

        Returns:
            Tupla de (permitido, retry_after)
        """
        allowed, headers, retry_after = await self.is_allowed(
            request,
            rate_type=RateLimitType.LOGIN,
        )
        return allowed, retry_after

    async def reset(self, request: Request, rate_type: RateLimitType) -> bool:
        """
        Resetea el rate limit para una IP.

        Args:
            request: Request de FastAPI
            rate_type: Tipo de rate limiting a resetear

        Returns:
            True si se reseteó correctamente
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_key(request, rate_type)
            await redis_client.delete(key)
            await redis_client.delete(f"{key}:blocked")
            return True
        except Exception as e:
            logger.error("rate_limit_reset_error", error=str(e))
            return False


# Instancia global del rate limiter
rate_limiter = RateLimiter()


async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware de rate limiting para FastAPI.

    Aplica rate limiting general a todos los endpoints excepto health checks.
    """
    # Excluir health checks y docs
    excluded_paths = {"/health", "/docs", "/redoc", "/openapi.json"}
    if request.url.path in excluded_paths:
        return await call_next(request)

    # Determinar tipo de rate limiting
    rate_type = RateLimitType.LOGIN if "/login" in request.url.path else RateLimitType.GENERAL

    # Obtener user_id si está autenticado (para rate limiting por usuario)
    user_id = getattr(request.state, "user_id", None)

    allowed, headers, retry_after = await rate_limiter.is_allowed(
        request,
        rate_type=rate_type,
        identifier=user_id,
    )

    if not allowed:
        response = JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Please try again later.",
                "type": "rate_limit_error",
                "retry_after": retry_after,
            },
        )
        for key, value in headers.items():
            response.headers[key] = str(value)
        return response

    response = await call_next(request)

    # Agregar headers informativos
    for key, value in headers.items():
        response.headers[key] = str(value)

    return response