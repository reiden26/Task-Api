"""
Esquemas Pydantic para tareas con UUID y soft delete.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import TaskPriority, TaskStatus


# =============================================================================
# Enums
# =============================================================================
class TaskStatusEnum(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskPriorityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


# =============================================================================
# Base
# =============================================================================
class TaskBase(BaseModel):
    """Campos base de tarea."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Título de la tarea (max 200 caracteres)",
    )
    description: Optional[str] = Field(None, description="Descripción detallada")


# =============================================================================
# Creación
# =============================================================================
class TaskCreate(TaskBase):
    """
    Schema para crear una nueva tarea.

    Los campos priority, status y due_date son opcionales.
    """

    priority: TaskPriorityEnum = Field(
        default=TaskPriorityEnum.MEDIUM,
        description="Prioridad de la tarea",
    )
    status: TaskStatusEnum = Field(
        default=TaskStatusEnum.TODO,
        description="Estado inicial de la tarea",
    )
    due_date: Optional[datetime] = Field(None, description="Fecha límite (ISO 8601)")


# =============================================================================
# Actualización
# =============================================================================
class TaskUpdate(BaseModel):
    """
    Schema para actualizar completamente una tarea.
    """

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[TaskPriorityEnum] = None
    status: Optional[TaskStatusEnum] = None
    due_date: Optional[datetime] = None


class TaskPartialUpdate(BaseModel):
    """
    Schema para actualizar parcialmente una tarea (PATCH).
    Todos los campos son opcionales.
    """

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[TaskPriorityEnum] = None
    status: Optional[TaskStatusEnum] = None
    due_date: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    """Schema para actualizar solo el estado de una tarea."""

    status: TaskStatusEnum = Field(
        ...,
        description="Nuevo estado de la tarea",
    )


# =============================================================================
# Respuesta
# =============================================================================
class TaskRead(TaskBase):
    """Schema para respuestas con datos completos de una tarea."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="UUID único de la tarea")
    status: TaskStatusEnum = Field(..., description="Estado actual")
    priority: TaskPriorityEnum = Field(..., description="Nivel de prioridad")
    due_date: Optional[datetime] = Field(None, description="Fecha límite")
    completed_at: Optional[datetime] = Field(None, description="Fecha de completado")
    created_at: datetime = Field(..., description="Fecha de creación")
    updated_at: datetime = Field(..., description="Fecha de última actualización")
    deleted_at: Optional[datetime] = Field(None, description="Fecha de eliminación lógica")
    is_deleted: bool = Field(False, description="Indica si está eliminada")
    owner_id: UUID = Field(..., description="UUID del propietario")
    is_overdue: bool = Field(..., description="Indica si está vencida")


class TaskList(BaseModel):
    """Schema para listado paginado de tareas."""

    items: list[TaskRead] = Field(default_factory=list, description="Lista de tareas")
    total: int = Field(..., description="Total de tareas")
    page: int = Field(..., description="Página actual")
    page_size: int = Field(..., description="Tamaño de página")
    pages: int = Field(..., description="Total de páginas")
    has_next: bool = Field(..., description="Hay página siguiente")
    has_prev: bool = Field(..., description="Hay página anterior")


# =============================================================================
# Filtros
# =============================================================================
class TaskFilter(BaseModel):
    """
    Schema para filtrar tareas en listados.
    """

    model_config = ConfigDict(extra="forbid")

    status: Optional[TaskStatusEnum] = None
    priority: Optional[TaskPriorityEnum] = None
    search: Optional[str] = Field(None, description="Búsqueda en título y descripción")
    include_deleted: bool = Field(False, description="Incluir tareas eliminadas")
    order_by: Literal["created_at", "updated_at", "due_date", "priority"] = Field(
        default="created_at",
        description="Campo para ordenar",
    )
    order: Literal["asc", "desc"] = Field(default="desc", description="Dirección del orden")

    # Paginación
    page: int = Field(default=1, ge=1, description="Número de página")
    page_size: int = Field(default=20, ge=1, le=100, description="Tamaño de página")