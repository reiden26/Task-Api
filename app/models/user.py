"""
Modelo SQLAlchemy para usuarios con UUID.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel

if TYPE_CHECKING:
    from app.models.task import Task


class User(BaseModel):
    """
    Modelo de usuario para autenticación y gestión de tareas.

    Usa UUID como identificador.

    Attributes:
        id: UUID único del usuario
        email: Email único del usuario
        hashed_password: Contraseña hasheada con bcrypt
        full_name: Nombre completo opcional
        is_active: Indica si la cuenta está activa
        is_superuser: Privilegios de administrador
        tasks: Relación con las tareas del usuario
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Email único del usuario",
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Contraseña hasheada con bcrypt",
    )

    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Nombre completo del usuario",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Indica si la cuenta está activa",
    )

    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Privilegios de superusuario",
    )

    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Última fecha de inicio de sesión",
    )

    # Relaciones
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Representación legible del usuario."""
        return f"<<User(id={self.id}, email={self.email}, active={self.is_active})>>"

    @property
    def task_count(self) -> int:
        """Retorna el número de tareas del usuario."""
        return len([t for t in self.tasks if not t.is_deleted]) if self.tasks else 0

    def update_last_login(self) -> None:
        """Actualiza la fecha del último login."""
        self.last_login = datetime.now(timezone.utc)

    def deactivate(self) -> None:
        """Desactiva la cuenta de usuario."""
        self.is_active = False

    def activate(self) -> None:
        """Activa la cuenta de usuario."""
        self.is_active = True

    def to_dict(self) -> dict:
        """Convierte el usuario a diccionario serializable."""
        return {
            "id": str(self.id),
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }