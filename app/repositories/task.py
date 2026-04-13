"""
Repositorio de tareas con filtros, paginación avanzada y soft delete.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.repositories.base import BaseRepository
from app.schemas.task import TaskFilter, TaskStatusEnum


class TaskRepository(BaseRepository[Task]):
    """
    Repositorio de tareas.

    Extiende el repositorio base con métodos específicos
    para la gestión de tareas, incluyendo filtros y búsqueda.
    """

    def __init__(self):
        super().__init__(Task)

    async def get_by_id_with_owner(
        self,
        db: AsyncSession,
        task_id: UUID,
        include_deleted: bool = False,
    ) -> Task | None:
        """
        Obtiene una tarea incluyendo su propietario.

        Args:
            db: Sesión de base de datos
            task_id: UUID de la tarea
            include_deleted: Incluir tareas eliminadas

        Returns:
            Tarea con propietario cargado o None
        """
        from sqlalchemy.orm import joinedload

        query = select(Task).options(joinedload(Task.owner))
        query = query.where(Task.id == task_id)

        if not include_deleted:
            query = query.where(Task.deleted_at.is_(None))

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        db: AsyncSession,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[Task]:
        """
        Obtiene tareas de un usuario específico.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario
            skip: Número de registros a omitir
            limit: Número máximo de registros
            include_deleted: Incluir tareas eliminadas

        Returns:
            Lista de tareas del usuario
        """
        query = select(Task).where(Task.owner_id == user_id)

        if not include_deleted:
            query = query.where(Task.deleted_at.is_(None))

        query = query.order_by(desc(Task.created_at)).offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        db: AsyncSession,
        user_id: UUID,
        include_deleted: bool = False,
    ) -> int:
        """
        Cuenta las tareas de un usuario.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario
            include_deleted: Incluir tareas eliminadas

        Returns:
            Número de tareas del usuario
        """
        query = select(func.count(Task.id)).where(Task.owner_id == user_id)
        if not include_deleted:
            query = query.where(Task.deleted_at.is_(None))

        result = await db.execute(query)
        return result.scalar() or 0

    async def get_filtered(
        self,
        db: AsyncSession,
        user_id: UUID,
        filters: TaskFilter,
    ) -> tuple[list[Task], int]:
        """
        Obtiene tareas filtradas con paginación.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario propietario
            filters: Filtros y paginación

        Returns:
            Tupla de (lista de tareas, total de registros)
        """
        # Query base
        query = select(Task).where(Task.owner_id == user_id)

        # Excluir eliminadas por defecto
        if not filters.include_deleted:
            query = query.where(Task.deleted_at.is_(None))

        # Filtro por estado
        if filters.status:
            query = query.where(Task.status == filters.status.value)

        # Filtro por prioridad
        if filters.priority:
            query = query.where(Task.priority == filters.priority.value)

        # Filtro de búsqueda en título/descripción
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Task.title.ilike(search_term),
                    Task.description.ilike(search_term),
                )
            )

        # Contar total antes de paginar
        count_result = await db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        # Ordenamiento
        order_column = getattr(Task, filters.order_by, Task.created_at)
        if filters.order == "desc":
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(asc(order_column))

        # Paginación
        offset = (filters.page - 1) * filters.page_size
        query = query.offset(offset).limit(filters.page_size)

        # Ejecutar query
        result = await db.execute(query)
        tasks = list(result.scalars().all())

        return tasks, total

    async def get_overdue_tasks(
        self,
        db: AsyncSession,
        user_id: UUID | None = None,
        include_deleted: bool = False,
    ) -> list[Task]:
        """
        Obtiene tareas vencidas.

        Args:
            db: Sesión de base de datos
            user_id: Filtrar por usuario específico (opcional)
            include_deleted: Incluir tareas eliminadas

        Returns:
            Lista de tareas vencidas
        """
        now = datetime.now(timezone.utc)
        query = select(Task).where(
            Task.due_date.is_not(None),
            Task.due_date < now,
            Task.status.notin_([
                TaskStatus.DONE.value,
                TaskStatus.CANCELLED.value,
            ]),
        )

        if user_id:
            query = query.where(Task.owner_id == user_id)

        if not include_deleted:
            query = query.where(Task.deleted_at.is_(None))

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_statistics(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> dict:
        """
        Obtiene estadísticas de tareas de un usuario.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario

        Returns:
            Diccionario con estadísticas
        """
        # Total por estado (solo no eliminadas)
        status_query = await db.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.owner_id == user_id, Task.deleted_at.is_(None))
            .group_by(Task.status)
        )
        by_status = dict(status_query.all())

        # Total por prioridad
        priority_query = await db.execute(
            select(Task.priority, func.count(Task.id))
            .where(Task.owner_id == user_id, Task.deleted_at.is_(None))
            .group_by(Task.priority)
        )
        by_priority = dict(priority_query.all())

        # Vencidas
        now = datetime.now(timezone.utc)
        overdue_query = await db.execute(
            select(func.count(Task.id)).where(
                Task.owner_id == user_id,
                Task.due_date.is_not(None),
                Task.due_date < now,
                Task.status.notin_([
                    TaskStatus.DONE.value,
                    TaskStatus.CANCELLED.value,
                ]),
                Task.deleted_at.is_(None),
            )
        )
        overdue_count = overdue_query.scalar() or 0

        # Eliminadas
        deleted_query = await db.execute(
            select(func.count(Task.id)).where(
                Task.owner_id == user_id,
                Task.deleted_at.is_not(None),
            )
        )
        deleted_count = deleted_query.scalar() or 0

        return {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "by_priority": by_priority,
            "overdue": overdue_count,
            "deleted": deleted_count,
        }


# Instancia global del repositorio
task_repository = TaskRepository()