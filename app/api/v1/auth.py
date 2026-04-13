"""
Endpoints de autenticación.

Gestiona registro, login, refresh de tokens y logout.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.schemas.user import (
    Token,
    TokenRefresh,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services.auth import auth_service

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo usuario",
    description="Crea una nueva cuenta de usuario con email y contraseña.",
    responses={
        201: {"description": "Usuario creado exitosamente"},
        409: {"description": "Email ya registrado"},
        422: {"description": "Datos de entrada inválidos"},
    },
)
async def register(
    user_in: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    """
    Registra un nuevo usuario.

    - **email**: Email válido y único
    - **password**: Mínimo 8 caracteres, debe incluir mayúsculas, minúsculas y números
    - **full_name**: Nombre completo opcional
    """
    return await auth_service.register(db, user_in)


@router.post(
    "/login",
    response_model=Token,
    summary="Iniciar sesión",
    description="Autentica un usuario y retorna tokens JWT.",
    responses={
        200: {"description": "Login exitoso"},
        401: {"description": "Credenciales inválidas"},
        403: {"description": "Usuario inactivo"},
    },
)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """
    Autentica un usuario.

    - **email**: Email registrado
    - **password**: Contraseña del usuario

    Retorna access token y refresh token.
    """
    return await auth_service.login(db, credentials)


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refrescar token",
    description="Genera nuevos tokens usando un refresh token válid.",
    responses={
        200: {"description": "Tokens refrescados"},
        401: {"description": "Refresh token inválido o revocado"},
    },
)
async def refresh_token(
    refresh_data: TokenRefresh,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """
    Refresca los tokens de acceso.

    - **refresh_token**: Token de refresco obtenido del login

    El refresh token anterior se invalida y se generan nuevos tokens.
    """
    return await auth_service.refresh_access_token(
        db,
        refresh_data.refresh_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Cerrar sesión",
    description="Invalida el token de acceso actual.",
    responses={
        200: {"description": "Logout exitoso"},
        401: {"description": "Token inválido"},
    },
)
async def logout(
    authorization: Annotated[str, Header(..., alias="Authorization")],
) -> dict:
    """
    Cierra la sesión del usuario.

    Invalida el access token actual. El refresh token también
    debería ser descartado por el cliente.
    """
    # Extraer token del header "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    await auth_service.logout(token)

    return {"message": "Successfully logged out"}


@router.get(
    "/me",
    response_model=UserRead,
    summary="Obtener usuario actual",
    description="Retorna información del usuario autenticado.",
    responses={
        200: {"description": "Datos del usuario"},
        401: {"description": "No autenticado"},
    },
)
async def get_me(
    current_user: CurrentUser,
) -> UserRead:
    """
    Obtiene el perfil del usuario autenticado.
    """
    return UserRead.model_validate(current_user)