"""
Repositorio de usuarios con operaciones específicas.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repositorio de usuarios.

    Extiende el repositorio base con métodos específicos
    para la gestión de usuarios.
    """

    def __init__(self):
        super().__init__(User)

    async def get_by_email(
        self,
        db: AsyncSession,
        email: str,
        include_deleted: bool = False,
    ) -> User | None:
        """
        Obtiene un usuario por su email.

        Args:
            db: Sesión de base de datos
            email: Email a buscar
            include_deleted: Incluir usuarios eliminados

        Returns:
            Usuario encontrado o None
        """
        query = select(User).where(func.lower(User.email) == func.lower(email))
        if not include_deleted:
            query = query.where(User.deleted_at.is_(None))

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_active_user(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> User | None:
        """
        Obtiene un usuario activo por su UUID.

        Args:
            db: Sesión de base de datos
            user_id: UUID del usuario

        Returns:
            Usuario activo o None si no existe o está inactivo/eliminado
        """
        result = await db.execute(
            select(User).where(
                User.id == user_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def email_exists(
        self,
        db: AsyncSession,
        email: str,
        include_deleted: bool = False,
    ) -> bool:
        """
        Verifica si un email ya está registrado.

        Args:
            db: Sesión de base de datos
            email: Email a verificar
            include_deleted: Incluir usuarios eliminados

        Returns:
            True si el email existe, False en caso contrario
        """
        query = select(func.count(User.id)).where(
            func.lower(User.email) == func.lower(email)
        )
        if not include_deleted:
            query = query.where(User.deleted_at.is_(None))

        result = await db.execute(query)
        return (result.scalar() or 0) > 0

    async def get_active_users(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        """
        Obtiene usuarios activos con paginación.

        Args:
            db: Sesión de base de datos
            skip: Número de registros a omitir
            limit: Número máximo de registros

        Returns:
            Lista de usuarios activos
        """
        result = await db.execute(
            select(User)
            .where(User.is_active.is_(True), User.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_last_login(
        self,
        db: AsyncSession,
        user: User,
    ) -> None:
        """
        Actualiza la fecha de último login del usuario.

        Args:
            db: Sesión de base de datos
            user: Usuario a actualizar
        """
        from datetime import datetime, timezone

        user.last_login = datetime.now(timezone.utc)
        await db.flush()


# Instancia global del repositorio
user_repository = UserRepository()