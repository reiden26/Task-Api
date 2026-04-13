"""
Router principal de la API v1.

Agrupa todos los routers de la versión 1.
"""

from fastapi import APIRouter

from app.api.v1 import auth, tasks

api_router = APIRouter()

# Routers de autenticación
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

# Routers de tareas
api_router.include_router(
    tasks.router,
    prefix="/tasks",
    tags=["Tasks"],
)