"""
Servicio de autenticación y gestión de usuarios.

Maneja el registro, login, refresh tokens y logout con Redis blacklist.
"""

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import redis.asyncio as redis
import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
    verify_token_type,
)
from app.models.user import User
from app.repositories.user import user_repository
from app.schemas.user import Token, UserCreate, UserLogin, UserRead

logger = structlog.get_logger(__name__)


class AuthService:
    """
    Servicio de autenticación.

    Gestiona el ciclo completo de autenticación:
    - Registro de usuarios
    - Login con validación de credenciales y rate limiting
    - Refresh de tokens con rotación
    - Logout e invalidación de tokens en Redis
    """

    # Redis para blacklist de tokens (TTL automático)
    REDIS_KEY_PREFIX = "token:blacklist"
    REFRESH_TOKEN_PREFIX = "refresh_token"

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

    async def register(
        self,
        db: AsyncSession,
        user_in: UserCreate,
    ) -> UserRead:
        """
        Registra un nuevo usuario.

        Args:
            db: Sesión de base de datos
            user_in: Datos del nuevo usuario

        Returns:
            Usuario creado

        Raises:
            HTTPException: Si el email ya está registrado
        """
        # Verificar si el email existe (incluyendo eliminados)
        if await user_repository.email_exists(db, user_in.email, include_deleted=True):
            logger.warning("registration_attempt_with_existing_email", email=user_in.email)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        # Crear usuario
        user_data = user_in.model_dump(exclude={"password"})
        user_data["hashed_password"] = get_password_hash(user_in.password)

        user = await user_repository.create(db, obj_in=user_data)
        await db.commit()

        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return UserRead.model_validate(user)

    async def login(
        self,
        db: AsyncSession,
        credentials: UserLogin,
    ) -> Token:
        """
        Autentica un usuario y genera tokens.

        Args:
            db: Sesión de base de datos
            credentials: Email y contraseña

        Returns:
            Token de acceso y refresh token

        Raises:
            HTTPException: Si las credenciales son inválidas
        """
        # Buscar usuario por email (solo activos y no eliminados)
        user = await user_repository.get_by_email(db, credentials.email)

        if not user or not verify_password(credentials.password, user.hashed_password):
            logger.warning(
                "login_failed_invalid_credentials",
                email=credentials.email,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            logger.warning("login_failed_inactive_user", user_id=str(user.id))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        if user.is_deleted:
            logger.warning("login_failed_deleted_user", user_id=str(user.id))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been deleted",
            )

        # Actualizar último login
        await user_repository.update_last_login(db, user)
        await db.commit()

        # Generar tokens con claims adicionales
        extra_claims = {
            "email": user.email,
            "roles": ["user"],
        }
        access_token = create_access_token(
            subject=str(user.id),
            extra_claims=extra_claims,
        )
        refresh_token_id = str(uuid.uuid4())
        refresh_token = create_refresh_token(
            subject=str(user.id),
            token_id=refresh_token_id,
        )

        # Almacenar refresh token en Redis para invalidación
        redis_client = await self._get_redis()
        await redis_client.setex(
            f"{self.REFRESH_TOKEN_PREFIX}:{user.id}:{refresh_token_id}",
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            "valid",
        )

        logger.info("user_logged_in", user_id=str(user.id))

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token: str,
    ) -> Token:
        """
        Genera un nuevo access token usando un refresh token válido.

        Args:
            db: Sesión de base de datos
            refresh_token: Token de refresco

        Returns:
            Nuevo par de tokens

        Raises:
            HTTPException: Si el refresh token es inválido o revocado
        """
        # Decodificar refresh token
        payload = decode_token(refresh_token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # Verificar tipo
        if not verify_token_type(payload, "refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = payload.get("sub")
        token_id = payload.get("jti")

        if not user_id or not token_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # Verificar que el refresh token no esté revocado
        redis_client = await self._get_redis()
        token_key = f"{self.REFRESH_TOKEN_PREFIX}:{user_id}:{token_id}"
        token_exists = await redis_client.get(token_key)

        if not token_exists:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked",
            )

        # Verificar que el usuario existe y está activo
        user = await user_repository.get_active_user(db, UUID(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found or inactive",
            )

        # Revocar el refresh token anterior (rotación de tokens)
        await redis_client.delete(token_key)

        # Generar nuevos tokens
        new_access_token = create_access_token(subject=str(user.id))
        new_refresh_token_id = str(uuid.uuid4())
        new_refresh_token = create_refresh_token(
            subject=str(user.id),
            token_id=new_refresh_token_id,
        )

        # Almacenar nuevo refresh token
        await redis_client.setex(
            f"{self.REFRESH_TOKEN_PREFIX}:{user.id}:{new_refresh_token_id}",
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            "valid",
        )

        logger.info("token_refreshed", user_id=str(user.id))

        return Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(
        self,
        token: str,
    ) -> None:
        """
        Invalida un token de acceso (logout).

        Args:
            token: Token de acceso a invalidar
        """
        payload = decode_token(token)
        if payload and payload.get("sub"):
            # Calcular TTL restante
            exp = payload.get("exp")
            if exp:
                ttl = int(exp - datetime.now(timezone.utc).timestamp())
                if ttl > 0:
                    redis_client = await self._get_redis()
                    await redis_client.setex(
                        f"{self.REDIS_KEY_PREFIX}:{token}",
                        ttl,
                        "revoked",
                    )
                    logger.info("user_logged_out", user_id=payload.get("sub"))

    async def logout_all_sessions(
        self,
        user_id: UUID,
    ) -> None:
        """
        Invalida todas las sesiones de un usuario.

        Args:
            user_id: UUID del usuario
        """
        redis_client = await self._get_redis()

        # Eliminar todos los refresh tokens del usuario
        pattern = f"{self.REFRESH_TOKEN_PREFIX}:{user_id}:*"
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
            logger.info("all_sessions_revoked", user_id=str(user_id), sessions=len(keys))

    async def is_token_revoked(
        self,
        token: str,
    ) -> bool:
        """
        Verifica si un token ha sido revocado.

        Args:
            token: Token a verificar

        Returns:
            True si está revocado, False en caso contrario
        """
        redis_client = await self._get_redis()
        result = await redis_client.get(f"{self.REDIS_KEY_PREFIX}:{token}")
        return result is not None

    async def get_current_user(
        self,
        db: AsyncSession,
        token: str,
    ) -> User:
        """
        Obtiene el usuario actual desde un token de acceso.

        Args:
            db: Sesión de base de datos
            token: Token de acceso

        Returns:
            Usuario autenticado

        Raises:
            HTTPException: Si el token es inválido o el usuario no existe
        """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        # Verificar si el token está revocado
        if await self.is_token_revoked(token):
            raise credentials_exception

        # Decodificar token
        payload = decode_token(token)
        if not payload:
            raise credentials_exception

        # Verificar tipo
        if not verify_token_type(payload, "access"):
            raise credentials_exception

        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception

        # Obtener usuario
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise credentials_exception

        user = await user_repository.get_active_user(db, user_uuid)
        if not user:
            raise credentials_exception

        return user


# Instancia global del servicio
auth_service = AuthService()