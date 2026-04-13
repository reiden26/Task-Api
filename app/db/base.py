"""
Base declarativa SQLAlchemy para todos los modelos.

Define la clase base que todos los modelos deben extender.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import sqlalchemy as sa


class BaseModel(DeclarativeBase):
    """
    Clase base para todos los modelos de la aplicación.

    Características:
    - UUID como clave primaria
    - Timestamps automáticos (created_at, updated_at)
    - Soft delete support (deleted_at)
    - Representación string útil para debugging
    """

    __abstract__ = True

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Identificador único UUID del registro",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Fecha de creación del registro",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Fecha de última actualización del registro",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha de eliminación lógica (soft delete)",
    )

    def __repr__(self) -> str:
        """Representación legible del modelo."""
        return f"<<{self.__class__.__name__}(id={self.id})>>"

    def soft_delete(self) -> None:
        """Marca el registro como eliminado (soft delete)."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restaura un registro eliminado."""
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        """Verifica si el registro está eliminado."""
        return self.deleted_at is not None

    def to_dict(self) -> dict[str, Any]:
        """Convierte el modelo a un diccionario."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            # Convertir UUID a string
            if isinstance(value, uuid.UUID):
                value = str(value)
            # Convertir datetime a ISO format
            elif isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


# Alias para compatibilidad con Alembic
Base = BaseModel