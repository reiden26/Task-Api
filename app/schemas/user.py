"""
Esquemas Pydantic para usuarios y autenticación.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# =============================================================================
# Base
# =============================================================================
class UserBase(BaseModel):
    """Campos base de usuario."""

    email: EmailStr = Field(..., description="Email único del usuario")
    full_name: Optional[str] = Field(None, max_length=255, description="Nombre completo")


# =============================================================================
# Creación
# =============================================================================
class UserCreate(UserBase):
    """
    Schema para crear un nuevo usuario.

    La contraseña debe tener al menos 8 caracteres con mayúsculas,
    minúsculas y números.
    """

    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Contraseña (mínimo 8 caracteres)",
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Valida que la contraseña sea fuerte."""
        if not any(c.isupper() for c in v):
            raise ValueError("La contraseña debe contener al menos una mayúscula")
        if not any(c.islower() for c in v):
            raise ValueError("La contraseña debe contener al menos una minúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("La contraseña debe contener al menos un número")
        return v


# =============================================================================
# Login
# =============================================================================
class UserLogin(BaseModel):
    """Schema para login de usuario."""

    email: EmailStr = Field(..., description="Email del usuario")
    password: str = Field(..., min_length=1, description="Contraseña")


# =============================================================================
# Actualización
# =============================================================================
class UserUpdate(BaseModel):
    """Schema para actualizar datos de usuario."""

    full_name: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=100)

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Respuesta
# =============================================================================
class UserRead(UserBase):
    """
    Schema para respuestas con datos de usuario.
    No incluye la contraseña por seguridad.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="UUID único del usuario")
    is_active: bool = Field(..., description="Estado de la cuenta")
    is_superuser: bool = Field(..., description="Privilegios de administrador")
    created_at: datetime = Field(..., description="Fecha de creación")
    updated_at: datetime = Field(..., description="Fecha de última actualización")
    last_login: Optional[datetime] = Field(None, description="Último inicio de sesión")


# =============================================================================
# Tokens
# =============================================================================
class Token(BaseModel):
    """Schema para respuesta de autenticación exitosa."""

    access_token: str = Field(..., description="Token de acceso JWT")
    refresh_token: str = Field(..., description="Token de refresco JWT")
    token_type: str = Field(default="bearer", description="Tipo de token")
    expires_in: int = Field(..., description="Segundos hasta expiración del access token")


class TokenRefresh(BaseModel):
    """Schema para solicitar refresh de token."""

    refresh_token: str = Field(..., description="Token de refresco válido")


class TokenPayload(BaseModel):
    """
    Schema para el payload decodificado de un JWT.
    """

    sub: Optional[str] = Field(None, description="Subject - ID del usuario")
    exp: Optional[datetime] = Field(None, description="Fecha de expiración")
    iat: Optional[datetime] = Field(None, description="Fecha de emisión")
    type: Optional[str] = Field(None, description="Tipo de token (access/refresh)")
    email: Optional[str] = Field(None, description="Email del usuario")


class TokenBlacklisted(BaseModel):
    """Schema para respuesta de logout exitoso."""

    message: str = Field(default="Token revocado exitosamente")
    token_type: str = Field(..., description="Tipo de token revocado")