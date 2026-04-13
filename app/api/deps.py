"""
Dependencias reutilizables para FastAPI.

Proporciona inyección de dependencias para DB, autenticación, etc.
"""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import TokenPayload
from app.services.auth import auth_service

logger = structlog.get_logger(__name__)

# Seguridad Bearer para tokens JWT
reusable_oauth2 = HTTPBearer(auto_error=False)


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[HTTPAuthorizationCredentials | None, Depends(reusable_oauth2)],
) -> User:
    """
    Dependency para obtener el usuario autenticado.

    Args:
        db: Sesión de base de datos
        token: Credenciales del header Authorization

    Returns:
        Usuario autenticado

    Raises:
        HTTPException: Si el token es inválido o falta
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await auth_service.get_current_user(db, token.credentials)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Dependency para verificar que el usuario está activo.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


# Type aliases para uso en endpoints
CurrentUser = Annotated[User, Depends(get_current_active_user)]