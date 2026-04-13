"""
Módulo de seguridad: JWT tokens, hashing de contraseñas y utilidades de auth.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
import structlog
from jose import JWTError, jwt

from app.core.config import settings

logger = structlog.get_logger(__name__)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica si una contraseña en texto plano coincide con el hash almacenado.

    Args:
        plain_password: Contraseña en texto plano ingresada por el usuario
        hashed_password: Hash bcrypt almacenado en la base de datos

    Returns:
        True si coinciden, False en caso contrario
    """
    try:
        # bcrypt trunca automáticamente a 72 bytes
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception as e:
        logger.error("password_verification_failed", error=str(e))
        return False


def get_password_hash(password: str) -> str:
    """
    Genera un hash bcrypt de una contraseña.

    Args:
        password: Contraseña en texto plano

    Returns:
        Hash bcrypt de la contraseña
    """
    # bcrypt trunca automáticamente a 72 bytes
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Crea un JWT access token.

    Args:
        subject: Identificador del usuario (usualmente user_id o email)
        expires_delta: Tiempo de expiración personalizado
        extra_claims: Claims adicionales a incluir en el token

    Returns:
        Token JWT codificado
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if extra_claims:
        to_encode.update(extra_claims)

    try:
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        logger.info("access_token_created", subject=subject, expires=expire.isoformat())
        return encoded_jwt
    except Exception as e:
        logger.error("access_token_creation_failed", subject=subject, error=str(e))
        raise


def create_refresh_token(
    subject: str,
    token_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Crea un JWT refresh token.

    Args:
        subject: Identificador del usuario
        token_id: ID único del token para invalidación
        expires_delta: Tiempo de expiración personalizado

    Returns:
        Token JWT refresh codificado
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

    to_encode = {
        "sub": str(subject),
        "jti": token_id,  # JWT ID para invalidación
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    try:
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        logger.info("refresh_token_created", subject=subject, token_id=token_id)
        return encoded_jwt
    except Exception as e:
        logger.error("refresh_token_creation_failed", subject=subject, error=str(e))
        raise


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica y verifica un token JWT.

    Args:
        token: Token JWT a decodificar

    Returns:
        Payload del token si es válido, None si es inválido o expiró
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        logger.warning("token_decode_failed", error=str(e))
        return None
    except Exception as e:
        logger.error("token_decode_error", error=str(e))
        return None


def verify_token_type(payload: Dict[str, Any], expected_type: str) -> bool:
    """
    Verifica que el tipo de token sea el esperado.

    Args:
        payload: Payload decodificado del token
        expected_type: Tipo esperado ("access" o "refresh")

    Returns:
        True si el tipo coincide, False en caso contrario
    """
    token_type = payload.get("type")
    return token_type == expected_type


def get_token_expiry(token: str) -> Optional[datetime]:
    """
    Extrae la fecha de expiración de un token.

    Args:
        token: Token JWT

    Returns:
        Fecha de expiración o None si no se puede extraer
    """
    payload = decode_token(token)
    if payload and "exp" in payload:
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return None


def create_token_pair(
    user_id: str,
    email: str,
    roles: Optional[list] = None,
) -> Tuple[str, str, str]:
    """
    Crea un par de tokens (access + refresh) para un usuario.

    Args:
        user_id: ID del usuario
        email: Email del usuario
        roles: Lista de roles del usuario

    Returns:
        Tupla de (access_token, refresh_token, token_id)
    """
    import uuid

    token_id = str(uuid.uuid4())

    extra_claims = {
        "email": email,
        "roles": roles or ["user"],
    }

    access_token = create_access_token(
        subject=user_id,
        extra_claims=extra_claims,
    )

    refresh_token = create_refresh_token(
        subject=user_id,
        token_id=token_id,
    )

    return access_token, refresh_token, token_id


def is_token_expired(token: str) -> bool:
    """
    Verifica si un token ha expirado.

    Args:
        token: Token JWT

    Returns:
        True si el token está expirado o es inválido
    """
    payload = decode_token(token)
    if payload is None:
        return True

    exp = payload.get("exp")
    if exp is None:
        return True

    expiry = datetime.fromtimestamp(exp, tz=timezone.utc)
    return expiry < datetime.now(timezone.utc)
