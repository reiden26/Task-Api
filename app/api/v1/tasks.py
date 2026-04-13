"""
Endpoints de gestión de tareas.

CRUD completo con filtros, paginación, soft delete y caché.
"""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.models.task import TaskPriority, TaskStatus
from app.schemas.task import (
    TaskCreate,
    TaskFilter,
    TaskList,
    TaskPartialUpdate,
    TaskRead,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.task import task_service

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=TaskList,
    summary="Listar tareas",
    description="Obtiene el listado paginado de tareas del usuario con filtros.",
)
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    status: Annotated[
        str | None,
        Query(description="Filtrar por estado: TODO, IN_PROGRESS, DONE, CANCELLED"),
    ] = None,
    priority: Annotated[
        str | None,
        Query(description="Filtrar por prioridad: LOW, MEDIUM, HIGH, URGENT"),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Buscar en título y descripción"),
    ] = None,
    include_deleted: Annotated[
        bool,
        Query(description="Incluir tareas eliminadas"),
    ] = False,
    order_by: Annotated[
        str,
        Query(description="Campo de ordenamiento"),
    ] = "created_at",
    order: Annotated[
        str,
        Query(description="Dirección: asc o desc"),
    ] = "desc",
    page: Annotated[
        int,
        Query(ge=1, description="Número de página"),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Tamaño de página"),
    ] = 20,
) -> TaskList:
    """
    Lista las tareas del usuario autenticado.
    """
    # Convertir strings a enums si se proporcionan
    status_enum = None
    if status:
        try:
            status_enum = TaskStatus(status.upper())
        except ValueError:
            pass

    priority_enum = None
    if priority:
        try:
            priority_enum = TaskPriority(priority.upper())
        except ValueError:
            pass

    filters = TaskFilter(
        status=status_enum,
        priority=priority_enum,
        search=search,
        include_deleted=include_deleted,
        order_by=order_by,  # type: ignore
        order=order,  # type: ignore
        page=page,
        page_size=page_size,
    )

    return await task_service.list_tasks(db, current_user.id, filters)


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear tarea",
    description="Crea una nueva tarea para el usuario autenticado.",
)
async def create_task(
    task_in: TaskCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> TaskRead:
    """
    Crea una nueva tarea.
    """
    return await task_service.create_task(db, task_in, current_user.id)


@router.get(
    "/statistics",
    summary="Estadísticas de tareas",
    description="Obtiene estadísticas de las tareas del usuario.",
)
async def get_statistics(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> dict:
    """
    Retorna estadísticas de tareas.
    """
    return await task_service.get_statistics(db, current_user.id)


@router.get(
    "/overdue",
    response_model=list[TaskRead],
    summary="Tareas vencidas",
    description="Obtiene las tareas que han pasado su fecha límite.",
)
async def get_overdue_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> list[TaskRead]:
    """
    Lista las tareas vencidas del usuario.
    """
    return await task_service.get_overdue_tasks(db, current_user.id)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Obtener tarea",
    description="Obtiene los detalles de una tarea específica (cacheada 5 min).",
    responses={
        404: {"description": "Tarea no encontrada"},
        403: {"description": "No autorizado"},
    },
)
async def get_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> TaskRead:
    """
    Obtiene una tarea por su ID.

    El resultado se cachea por 5 minutos.
    """
    return await task_service.get_task_cached(db, task_id, current_user.id)


@router.put(
    "/{task_id}",
    response_model=TaskRead,
    summary="Actualizar tarea",
    description="Actualiza completamente una tarea existente. Invalida caché.",
)
async def update_task(
    task_id: UUID,
    task_in: TaskUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> TaskRead:
    """
    Actualiza una tarea.
    """
    return await task_service.update_task(
        db,
        task_id,
        current_user.id,
        task_in,
    )


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Actualizar parcialmente",
    description="Actualiza campos específicos de una tarea (PATCH). Invalida caché.",
)
async def patch_task(
    task_id: UUID,
    task_in: TaskPartialUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> TaskRead:
    """
    Actualiza parcialmente una tarea.

    Solo los campos proporcionados se actualizan.
    """
    return await task_service.partial_update_task(
        db,
        task_id,
        current_user.id,
        task_in,
    )


@router.patch(
    "/{task_id}/status",
    response_model=TaskRead,
    summary="Actualizar estado",
    description="Cambia el estado de una tarea.",
)
async def update_task_status(
    task_id: UUID,
    status_update: TaskStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> TaskRead:
    """
    Actualiza solo el estado de una tarea.
    """
    return await task_service.update_task_status(
        db,
        task_id,
        current_user.id,
        status_update.status,
    )


@router.post(
    "/{task_id}/restore",
    response_model=TaskRead,
    summary="Restaurar tarea",
    description="Restaura una tarea previamente eliminada (soft delete).",
)
async def restore_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> TaskRead:
    """
    Restaura una tarea eliminada.
    """
    return await task_service.restore_task(db, task_id, current_user.id)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar tarea",
    description="Elimina una tarea (soft delete por defecto). Invalida caché.",
)
async def delete_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    hard: bool = Query(False, description="Eliminar físicamente"),
) -> None:
    """
    Elimina una tarea por su ID.

    Por defecto realiza soft delete (marcar como eliminada).
    Use hard=true para eliminación física (irreversible).
    """
    await task_service.delete_task(db, task_id, current_user.id, hard=hard)