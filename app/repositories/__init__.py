"""
Módulo de repositorios para acceso a datos.

Implementa el patrón Repository para abstraer el acceso a la BD.
"""

from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository

__all__ = ["UserRepository", "TaskRepository"]