"""
Módulo de esquemas Pydantic para validación y serialización.

Define los DTOs (Data Transfer Objects) de la API.
"""

from app.schemas.task import (
    TaskCreate,
    TaskFilter,
    TaskList,
    TaskPartialUpdate,
    TaskRead,
    TaskStatusEnum,
    TaskPriorityEnum,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.schemas.user import (
    Token,
    TokenPayload,
    TokenRefresh,
    UserCreate,
    UserLogin,
    UserRead,
    UserUpdate,
)

__all__ = [
    # User schemas
    "UserCreate",
    "UserRead",
    "UserUpdate",
    "UserLogin",
    "Token",
    "TokenRefresh",
    "TokenPayload",
    # Task schemas
    "TaskCreate",
    "TaskRead",
    "TaskUpdate",
    "TaskPartialUpdate",
    "TaskStatusUpdate",
    "TaskStatusEnum",
    "TaskPriorityEnum",
    "TaskList",
    "TaskFilter",
]