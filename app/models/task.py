"""
Modelo SQLAlchemy para tareas con UUID y soft delete.
"""

import uuid
from datetime import date, datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class TaskStatus(str, PyEnum):
    """Estados posibles de una tarea."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskPriority(str, PyEnum):
    """Niveles de prioridad de una tarea."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class Task(BaseModel):
    """
    Modelo de tarea para gestión de actividades.

    Usa UUID como identificador y soft delete.

    Attributes:
        id: UUID único de la tarea
        title: Título de la tarea (max 200 chars)
        description: Descripción detallada opcional
        status: Estado actual (enum)
        priority: Nivel de prioridad (enum)
        due_date: Fecha límite opcional
        completed_at: Fecha de completado
        deleted_at: Fecha de eliminación lógica
        owner_id: UUID del usuario propietario
        owner: Relación con el usuario propietario
    """

    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="Título de la tarea (max 200 caracteres)",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Descripción detallada de la tarea",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=TaskStatus.TODO.value,
        nullable=False,
        index=True,
        comment="Estado de la tarea",
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        default=TaskPriority.MEDIUM.value,
        nullable=False,
        index=True,
        comment="Prioridad de la tarea",
    )

    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Fecha límite de la tarea",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha de completado de la tarea",
    )

    # Clave foránea al usuario propietario (UUID)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="UUID del usuario propietario",
    )

    # Relaciones
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="tasks",
        lazy="joined",
    )

    def __repr__(self) -> str:
        """Representación legible de la tarea."""
        return f"<<Task(id={self.id}, title={self.title[:30]}..., status={self.status})>>"

    def complete(self) -> None:
        """Marca la tarea como completada."""
        self.status = TaskStatus.DONE.value
        self.completed_at = datetime.now(timezone.utc)

    def reopen(self) -> None:
        """Reabre una tarea completada."""
        self.status = TaskStatus.TODO.value
        self.completed_at = None

    def start(self) -> None:
        """Marca la tarea como en progreso."""
        if self.status == TaskStatus.TODO.value:
            self.status = TaskStatus.IN_PROGRESS.value

    def cancel(self) -> None:
        """Cancela la tarea."""
        self.status = TaskStatus.CANCELLED.value

    @property
    def is_overdue(self) -> bool:
        """Verifica si la tarea está vencida."""
        if not self.due_date or self.status in [
            TaskStatus.DONE.value,
            TaskStatus.CANCELLED.value,
        ]:
            return False
        return self.due_date < datetime.now(timezone.utc)

    @property
    def is_completed(self) -> bool:
        """Verifica si la tarea está completada."""
        return self.status == TaskStatus.DONE.value

    def to_dict(self) -> dict:
        """Convierte la tarea a diccionario serializable."""
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "owner_id": str(self.owner_id),
            "is_deleted": self.is_deleted,
        }