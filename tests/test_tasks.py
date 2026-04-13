"""
Tests de gestión de tareas.

Prueba CRUD, soft delete, filtros, paginación, caché y autorización con UUID.
Cobertura: crear, listar, filtrar, obtener, actualizar, eliminar, restaurar, paginación.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.models.task import Task, TaskPriority, TaskStatus
from app.repositories.task import task_repository

pytestmark = pytest.mark.asyncio


class TestCreateTask:
    """Tests de creación de tareas."""

    async def test_create_task_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        task_create_data: dict,
    ):
        """Crear tarea exitosamente."""
        response = await client.post(
            "/api/v1/tasks",
            headers=auth_headers,
            json=task_create_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == task_create_data["title"]
        assert data["description"] == task_create_data["description"]
        assert data["status"] == "TODO"
        assert data["priority"] == "MEDIUM"
        assert "id" in data
        # Verificar UUID
        assert UUID(data["id"])
        assert data["is_deleted"] is False
        assert data["completed_at"] is None
        assert "owner_id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_task_no_auth(
        self,
        client: AsyncClient,
        task_create_data: dict,
    ):
        """Error 401 al crear sin autenticación."""
        response = await client.post(
            "/api/v1/tasks",
            json=task_create_data,
        )

        assert response.status_code == 401

    async def test_create_task_minimal_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Crear tarea con solo título (campos opcionales por defecto)."""
        response = await client.post(
            "/api/v1/tasks",
            headers=auth_headers,
            json={"title": "Minimal Task"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Task"
        assert data["priority"] == "MEDIUM"  # Default
        assert data["status"] == "TODO"  # Default
        assert data["description"] is None

    async def test_create_task_with_priority(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Crear tarea con prioridad específica."""
        response = await client.post(
            "/api/v1/tasks",
            headers=auth_headers,
            json={
                "title": "High Priority Task",
                "priority": "HIGH",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["priority"] == "HIGH"

    async def test_create_task_invalid_priority(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Error 422 con prioridad inválida."""
        response = await client.post(
            "/api/v1/tasks",
            headers=auth_headers,
            json={
                "title": "Invalid Priority Task",
                "priority": "INVALID_PRIORITY",
            },
        )

        assert response.status_code == 422

    async def test_create_task_title_too_long(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Error 422 con título demasiado largo (>200 chars)."""
        response = await client.post(
            "/api/v1/tasks",
            headers=auth_headers,
            json={
                "title": "A" * 201,
            },
        )

        assert response.status_code == 422

    async def test_create_task_empty_title(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Error 422 con título vacío."""
        response = await client.post(
            "/api/v1/tasks",
            headers=auth_headers,
            json={
                "title": "",
            },
        )

        assert response.status_code == 422


class TestListTasks:
    """Tests de listado de tareas."""

    async def test_list_tasks_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Listar tareas del usuario autenticado."""
        response = await client.get(
            "/api/v1/tasks",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 9
        assert len(data["items"]) == 9
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["pages"] == 1
        assert data["has_next"] is False
        assert data["has_prev"] is False

    async def test_list_tasks_pagination(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Paginación de tareas."""
        response = await client.get(
            "/api/v1/tasks?page=1&page_size=5",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["items"]) == 5
        assert data["pages"] == 2
        assert data["has_next"] is True
        assert data["has_prev"] is False

        # Segunda página
        response2 = await client.get(
            "/api/v1/tasks?page=2&page_size=5",
            headers=auth_headers,
        )
        data2 = response2.json()
        assert data2["page"] == 2
        assert data2["has_prev"] is True
        assert data2["has_next"] is False

    async def test_list_tasks_filter_by_status(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Filtrar tareas por estado."""
        response = await client.get(
            "/api/v1/tasks?status=TODO",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Debería tener 3 tareas con status TODO
        assert all(t["status"] == "TODO" for t in data["items"])
        assert data["total"] == 3

    async def test_list_tasks_filter_by_priority(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Filtrar tareas por prioridad."""
        response = await client.get(
            "/api/v1/tasks?priority=HIGH",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["priority"] == "HIGH" for t in data["items"])

    async def test_list_tasks_search(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Buscar tareas por texto en título o descripción."""
        response = await client.get(
            "/api/v1/tasks?search=Task 0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Debería encontrar "Task 0"
        assert len(data["items"]) >= 1
        assert any("Task 0" in t["title"] for t in data["items"])

    async def test_list_tasks_search_in_description(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Buscar tareas por texto en descripción."""
        response = await client.get(
            "/api/v1/tasks?search=Description for task",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) > 0

    async def test_list_tasks_other_user_invisible(
        self,
        client: AsyncClient,
        auth_headers: dict,
        other_user_task: Task,
    ):
        """No ver tareas de otros usuarios en el listado."""
        response = await client.get(
            "/api/v1/tasks",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # No debería ver la tarea del otro usuario
        task_ids = [t["id"] for t in data["items"]]
        assert str(other_user_task.id) not in task_ids

    async def test_list_tasks_include_deleted(
        self,
        client: AsyncClient,
        auth_headers: dict,
        deleted_task: Task,
    ):
        """Filtrar para incluir tareas eliminadas."""
        # Sin include_deleted, no debería ver la tarea eliminada
        response = await client.get(
            "/api/v1/tasks",
            headers=auth_headers,
        )
        data = response.json()
        task_ids = [t["id"] for t in data["items"]]
        assert str(deleted_task.id) not in task_ids

    async def test_list_tasks_order_by_created_at_desc(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Ordenar por fecha de creación descendente."""
        response = await client.get(
            "/api/v1/tasks?order_by=created_at&order=desc",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Verificar orden descendente
        if len(data["items"]) > 1:
            dates = [t["created_at"] for t in data["items"]]
            assert dates == sorted(dates, reverse=True)


class TestGetTask:
    """Tests de obtención de tarea específica."""

    async def test_get_task_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Obtener tarea existente."""
        response = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Sample Task"
        assert UUID(data["id"]) == sample_task.id
        assert data["owner_id"] == str(sample_task.owner_id)

    async def test_get_task_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        invalid_uuid: str,
    ):
        """Error 404 al obtener tarea inexistente."""
        response = await client.get(
            f"/api/v1/tasks/{invalid_uuid}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_task_other_user_forbidden(
        self,
        client: AsyncClient,
        auth_headers_user_2: dict,
        sample_task: Task,
    ):
        """Error 403 al intentar ver tarea de otro usuario."""
        response = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers_user_2,
        )

        assert response.status_code == 403

    async def test_get_task_deleted_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        deleted_task: Task,
    ):
        """Error 404 al obtener tarea eliminada (soft delete)."""
        response = await client.get(
            f"/api/v1/tasks/{deleted_task.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_task_invalid_uuid_format(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Error 422 con UUID inválido."""
        response = await client.get(
            "/api/v1/tasks/not-a-uuid",
            headers=auth_headers,
        )

        assert response.status_code == 422


class TestUpdateTask:
    """Tests de actualización de tareas."""

    async def test_update_task_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
        task_update_data: dict,
    ):
        """Actualizar tarea existente (PUT)."""
        response = await client.put(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
            json=task_update_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == task_update_data["title"]
        assert data["description"] == task_update_data["description"]
        assert data["priority"] == task_update_data["priority"]
        assert data["status"] == task_update_data["status"]

    async def test_patch_task_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
        task_partial_update_data: dict,
    ):
        """Actualizar parcialmente una tarea (PATCH)."""
        # Solo actualizar descripción
        response = await client.patch(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
            json=task_partial_update_data,
        )

        assert response.status_code == 200
        data = response.json()
        # El título no debería cambiar
        assert data["title"] == sample_task.title
        assert data["description"] == task_partial_update_data["description"]

    async def test_update_task_status_to_done(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Actualizar estado a DONE y verificar completed_at."""
        response = await client.patch(
            f"/api/v1/tasks/{sample_task.id}/status",
            headers=auth_headers,
            json={"status": "DONE"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "DONE"
        assert data["completed_at"] is not None

    async def test_update_task_reopen(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Reabrir una tarea completada."""
        # Primero completarla
        await client.patch(
            f"/api/v1/tasks/{sample_task.id}/status",
            headers=auth_headers,
            json={"status": "DONE"},
        )

        # Reabrir
        response = await client.patch(
            f"/api/v1/tasks/{sample_task.id}/status",
            headers=auth_headers,
            json={"status": "TODO"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "TODO"
        assert data["completed_at"] is None

    async def test_update_task_forbidden(
        self,
        client: AsyncClient,
        auth_headers_user_2: dict,
        sample_task: Task,
    ):
        """Error 403 al actualizar tarea de otro usuario."""
        response = await client.put(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers_user_2,
            json={"title": "Hacked Title"},
        )

        assert response.status_code == 403

    async def test_update_task_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        invalid_uuid: str,
    ):
        """Error 404 al actualizar tarea inexistente."""
        response = await client.put(
            f"/api/v1/tasks/{invalid_uuid}",
            headers=auth_headers,
            json={"title": "New Title"},
        )

        assert response.status_code == 404


class TestSoftDeleteTask:
    """Tests de soft delete de tareas."""

    async def test_soft_delete_task(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Eliminar tarea (soft delete)."""
        response = await client.delete(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verificar que ya no aparece en listados
        get_response = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    async def test_restore_soft_deleted_task(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Restaurar tarea eliminada."""
        # Eliminar primero
        await client.delete(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )

        # Restaurar
        response = await client.post(
            f"/api/v1/tasks/{sample_task.id}/restore",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == sample_task.title
        assert data["is_deleted"] is False
        assert data["deleted_at"] is None

    async def test_hard_delete_task(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Eliminar tarea físicamente (hard delete)."""
        response = await client.delete(
            f"/api/v1/tasks/{sample_task.id}?hard=true",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verificar que no existe ni siquiera como soft deleted
        restore_response = await client.post(
            f"/api/v1/tasks/{sample_task.id}/restore",
            headers=auth_headers,
        )
        assert restore_response.status_code == 404

    async def test_delete_task_forbidden(
        self,
        client: AsyncClient,
        auth_headers_user_2: dict,
        sample_task: Task,
    ):
        """Error 403 al eliminar tarea de otro usuario."""
        response = await client.delete(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers_user_2,
        )

        assert response.status_code == 403

    async def test_delete_task_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        invalid_uuid: str,
    ):
        """Error 404 al eliminar tarea inexistente."""
        response = await client.delete(
            f"/api/v1/tasks/{invalid_uuid}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_restore_not_deleted_task(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Error 400 al intentar restaurar tarea no eliminada."""
        response = await client.post(
            f"/api/v1/tasks/{sample_task.id}/restore",
            headers=auth_headers,
        )

        assert response.status_code == 400


class TestTaskStatistics:
    """Tests de estadísticas de tareas."""

    async def test_get_statistics(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_tasks: list,
    ):
        """Obtener estadísticas de tareas."""
        response = await client.get(
            "/api/v1/tasks/statistics",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_priority" in data
        assert "overdue" in data
        assert "deleted" in data
        assert data["total"] == 9

    async def test_get_overdue_tasks(
        self,
        client: AsyncClient,
        auth_headers: dict,
        overdue_task: Task,
    ):
        """Obtener tareas vencidas."""
        response = await client.get(
            "/api/v1/tasks/overdue",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(t["title"] == "Overdue Task" for t in data)


class TestTaskCache:
    """Tests de caché de tareas."""

    async def test_task_caching(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Verificar que las tareas se cachean."""
        # Primera petición
        response1 = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )
        assert response1.status_code == 200

        # Segunda petición (debería venir de caché)
        response2 = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )
        assert response2.status_code == 200

    async def test_cache_invalidation_on_update(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Verificar que PUT invalida la caché."""
        # Obtener tarea
        await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )

        # Actualizar tarea
        await client.put(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
            json={"title": "Updated Title"},
        )

        # Verificar que se actualizó
        response = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )
        data = response.json()
        assert data["title"] == "Updated Title"

    async def test_cache_invalidation_on_patch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Verificar que PATCH invalida la caché."""
        await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )

        await client.patch(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
            json={"description": "New description"},
        )

        response = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )
        data = response.json()
        assert data["description"] == "New description"

    async def test_cache_invalidation_on_delete(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        """Verificar que DELETE invalida la caché."""
        await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )

        await client.delete(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )

        # La tarea ya no debería existir
        response = await client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404