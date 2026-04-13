"""
Repositorio base genérico con operaciones CRUD y soft delete.

Proporciona métodos comunes para todos los repositorios.
"""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import asc, desc

from app.db.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    """
    Repositorio base con operaciones CRUD async y soft delete.

    Args:
        model: Clase del modelo SQLAlchemy
    """

    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get_by_id(
        self,
        db: AsyncSession,
        id: UUID,
        include_deleted: bool = False,
    ) -> ModelType | None:
        """
        Obtiene un registro por su UUID.

        Args:
            db: Sesión de base de datos
            id: UUID del registro
            include_deleted: Incluir registros eliminados lógicamente

        Returns:
            Instancia del modelo o None si no existe
        """
        query = select(self.model).where(self.model.id == id)
        if not include_deleted:
            query = query.where(self.model.deleted_at.is_(None))

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "created_at",
        order: str = "desc",
        include_deleted: bool = False,
    ) -> list[ModelType]:
        """
        Obtiene múltiples registros con paginación.

        Args:
            db: Sesión de base de datos
            skip: Número de registros a omitir
            limit: Número máximo de registros a retornar
            order_by: Campo para ordenar
            order: Dirección del orden (asc/desc)
            include_deleted: Incluir registros eliminados

        Returns:
            Lista de instancias del modelo
        """
        query = select(self.model)

        if not include_deleted:
            query = query.where(self.model.deleted_at.is_(None))

        # Ordenamiento
        order_column = getattr(self.model, order_by, self.model.created_at)
        if order == "desc":
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(asc(order_column))

        # Paginación
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: dict[str, Any],
    ) -> ModelType:
        """
        Crea un nuevo registro.

        Args:
            db: Sesión de base de datos
            obj_in: Diccionario con los datos del nuevo registro

        Returns:
            Instancia creada
        """
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        await db.flush()  # Genera el UUID sin hacer commit
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: dict[str, Any],
    ) -> ModelType:
        """
        Actualiza un registro existente.

        Args:
            db: Sesión de base de datos
            db_obj: Instancia a actualizar
            obj_in: Diccionario con los campos a actualizar

        Returns:
            Instancia actualizada
        """
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def delete(
        self,
        db: AsyncSession,
        *,
        id: UUID,
        hard: bool = False,
    ) -> ModelType | None:
        """
        Elimina un registro por su UUID.

        Args:
            db: Sesión de base de datos
            id: UUID del registro a eliminar
            hard: Si True, elimina físicamente; si False, soft delete

        Returns:
            Instancia eliminada o None si no existía
        """
        obj = await self.get_by_id(db, id, include_deleted=True)
        if obj:
            if hard:
                await db.delete(obj)
            else:
                obj.soft_delete()
                db.add(obj)
            await db.flush()
        return obj

    async def restore(
        self,
        db: AsyncSession,
        *,
        id: UUID,
    ) -> ModelType | None:
        """
        Restaura un registro eliminado.

        Args:
            db: Sesión de base de datos
            id: UUID del registro a restaurar

        Returns:
            Instancia restaurada o None si no existía
        """
        obj = await self.get_by_id(db, id, include_deleted=True)
        if obj and obj.is_deleted:
            obj.restore()
            db.add(obj)
            await db.flush()
            await db.refresh(obj)
        return obj

    async def count(
        self,
        db: AsyncSession,
        include_deleted: bool = False,
    ) -> int:
        """
        Cuenta el total de registros.

        Args:
            db: Sesión de base de datos
            include_deleted: Incluir registros eliminados

        Returns:
            Número total de registros
        """
        query = select(func.count(self.model.id))
        if not include_deleted:
            query = query.where(self.model.deleted_at.is_(None))

        result = await db.execute(query)
        return result.scalar() or 0

    async def exists(
        self,
        db: AsyncSession,
        id: UUID,
        include_deleted: bool = False,
    ) -> bool:
        """
        Verifica si existe un registro con el ID dado.

        Args:
            db: Sesión de base de datos
            id: UUID a verificar
            include_deleted: Incluir registros eliminados

        Returns:
            True si existe, False en caso contrario
        """
        query = select(func.count(self.model.id)).where(self.model.id == id)
        if not include_deleted:
            query = query.where(self.model.deleted_at.is_(None))

        result = await db.execute(query)
        return (result.scalar() or 0) > 0