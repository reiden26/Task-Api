"""
Servicio de gestión de tareas con caché Redis.

Maneja el CRUD de tareas, filtros, y lógica de negocio.
"""

from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_manager
from app.models.task import Task, TaskPriority, TaskStatus
from app.repositories.task import task_repository
from app.schemas.task import (
    TaskCreate,
    TaskFilter,
    TaskList,
    TaskPartialUpdate,
    TaskRead,
    TaskUpdate,
)

logger = structlog.get_logger(__name__)

# Constantes de caché
CACHE_PREFIX_TASK = "task"
CACHE_EXPIRE_TASK = 300  # 5 minutos


class TaskService:
    """
    Servicio de gestión de tareas con caché Redis.

    Proporciona métodos de alto nivel para:
    - CRUD de tareas con validaciones
    - Filtrado y búsqueda avanzada
    - Gestión de estados y transiciones
    - Caché de consultas individuales
    - Soft delete
    """

    async def create_task(
        self,
        db: AsyncSession,
        task_in: TaskCreate,
        user_id: UUID,
    ) -> TaskRead:
        """
        Crea una nueva tarea para un usuario.

        Args:
            db: Sesión de base de datos
            task_in: Datos de la tarea
            user_id: UUID del propietario

        Returns:
            Tarea creada
        """
        task_data = task_in.model_dump()
        task_data["owner_id"] = user_id

        task = await task_repository.create(db, obj_in=task_data)
        await db.commit()

        logger.info("task_created", task_id=str(task.id), user_id=str(user_id))
        return TaskRead.model_validate(task)

    async def get_task(
        self,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
    ) -> Task:
        """
        Obtiene una tarea por ID verificando propiedad.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            user_id: UUID del usuario solicitante

        Returns:
            Tarea encontrada

        Raises:
            HTTPException: Si no existe o no pertenece al usuario
        """
        task = await task_repository.get_by_id(db, task_id)

        if not task or task.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if task.owner_id != user_id:
            logger.warning(
                "unauthorized_task_access_attempt",
                task_id=str(task_id),
                user_id=str(user_id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this task",
            )

        return task

    async def get_task_cached(
        self,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
    ) -> TaskRead:
        """
        Obtiene una tarea con caché Redis.

        El resultado se cachea por 5 minutos.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            user_id: UUID del usuario

        Returns:
            Tarea con datos del propietario
        """
        cache_key = f"{CACHE_PREFIX_TASK}:{task_id}:{user_id}"

        # Intentar obtener de caché
        cached = await cache_manager.get(cache_key)
        if cached:
            logger.debug("task_cache_hit", task_id=str(task_id))
            return TaskRead.model_validate(cached)

        # Obtener de base de datos
        task = await self.get_task(db, task_id, user_id)
        task_read = TaskRead.model_validate(task)

        # Guardar en caché
        await cache_manager.set(cache_key, task_read.model_dump(), CACHE_EXPIRE_TASK)
        logger.debug("task_cache_set", task_id=str(task_id))

        return task_read

    async def invalidate_task_cache(self, task_id: UUID, user_id: UUID) -> None:
        """
        Invalida la caché de una tarea.

        Args:
            task_id: UUID de la tarea
            user_id: UUID del usuario
        """
        cache_key = f"{CACHE_PREFIX_TASK}:{task_id}:{user_id}"
        await cache_manager.delete(cache_key)

        # También invalidar patrones relacionados
        pattern = f"{CACHE_PREFIX_TASK}:{task_id}:*"
        await cache_manager.delete_pattern(pattern)
        logger.debug("task_cache_invalidated", task_id=str(task_id))

    async def list_tasks(
        self,
        db: AsyncSession,
        user_id: UUID,
        filters: TaskFilter,
    ) -> TaskList:
        """
        Lista tareas del usuario con filtros y paginación.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario
            filters: Filtros y paginación

        Returns:
            Listado paginado de tareas
        """
        tasks, total = await task_repository.get_filtered(db, user_id, filters)

        pages = (total + filters.page_size - 1) // filters.page_size if total > 0 else 1

        return TaskList(
            items=[TaskRead.model_validate(t) for t in tasks],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            pages=pages,
            has_next=filters.page < pages,
            has_prev=filters.page > 1,
        )

    async def update_task(
        self,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
        task_in: TaskUpdate,
    ) -> TaskRead:
        """
        Actualiza completamente una tarea.

        Invalida la caché de la tarea.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            user_id: UUID del propietario
            task_in: Datos a actualizar

        Returns:
            Tarea actualizada
        """
        task = await self.get_task(db, task_id, user_id)

        update_data = task_in.model_dump(exclude_unset=True)

        # Si se está completando la tarea, establecer completed_at
        if update_data.get("status") == TaskStatus.DONE.value and not task.completed_at:
            from datetime import datetime, timezone
            update_data["completed_at"] = datetime.now(timezone.utc)
        # Si se está reabriendo, limpiar completed_at
        elif update_data.get("status") != TaskStatus.DONE.value:
            update_data["completed_at"] = None

        updated_task = await task_repository.update(
            db,
            db_obj=task,
            obj_in=update_data,
        )
        await db.commit()

        # Invalidar caché
        await self.invalidate_task_cache(task_id, user_id)

        logger.info("task_updated", task_id=str(task_id), user_id=str(user_id))
        return TaskRead.model_validate(updated_task)

    async def partial_update_task(
        self,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
        task_in: TaskPartialUpdate,
    ) -> TaskRead:
        """
        Actualiza parcialmente una tarea (PATCH).

        Invalida la caché de la tarea.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            user_id: UUID del propietario
            task_in: Datos parciales a actualizar

        Returns:
            Tarea actualizada
        """
        return await self.update_task(db, task_id, user_id, TaskUpdate(**task_in.model_dump(exclude_unset=True)))

    async def update_task_status(
        self,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
        new_status: TaskStatus,
    ) -> TaskRead:
        """
        Actualiza solo el estado de una tarea.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            user_id: UUID del propietario
            new_status: Nuevo estado

        Returns:
            Tarea actualizada
        """
        return await self.update_task(
            db,
            task_id,
            user_id,
            TaskUpdate(status=new_status),
        )

    async def delete_task(
        self,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
        hard: bool = False,
    ) -> None:
        """
        Elimina una tarea (soft delete por defecto).

        Invalida la caché de la tarea.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            user_id: UUID del propietario
            hard: Si True, elimina físicamente
        """
        task = await self.get_task(db, task_id, user_id)
        await task_repository.delete(db, id=task_id, hard=hard)
        await db.commit()

        # Invalidar caché
        await self.invalidate_task_cache(task_id, user_id)

        logger.info(
            "task_deleted",
            task_id=str(task_id),
            user_id=str(user_id),
            hard=hard,
        )

    async def restore_task(
        self,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
    ) -> TaskRead:
        """
        Restaura una tarea eliminada.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            user_id: UUID del propietario

        Returns:
            Tarea restaurada
        """
        task = await task_repository.get_by_id(db, task_id, include_deleted=True)

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if task.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to restore this task",
            )

        if not task.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task is not deleted",
            )

        restored = await task_repository.restore(db, id=task_id)
        await db.commit()

        # Invalidar caché
        await self.invalidate_task_cache(task_id, user_id)

        logger.info("task_restored", task_id=str(task_id), user_id=str(user_id))
        return TaskRead.model_validate(restored)

    async def get_statistics(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> dict:
        """
        Obtiene estadísticas de tareas del usuario.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario

        Returns:
            Diccionario con estadísticas
        """
        return await task_repository.get_statistics(db, user_id)

    async def get_overdue_tasks(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> list[TaskRead]:
        """
        Obtiene tareas vencidas del usuario.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario

        Returns:
            Lista de tareas vencidas
        """
        tasks = await task_repository.get_overdue_tasks(db, user_id)
        return [TaskRead.model_validate(t) for t in tasks]


# Instancia global del servicio
task_service = TaskService()