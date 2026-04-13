.PHONY: help install install-dev clean test test-cov lint format migrate migrate-create shell run run-dev docker-build docker-up docker-down docker-logs

# Variables
PYTHON := python
PIP := pip
PYTEST := pytest
ALEMBIC := alembic
DOCKER_COMPOSE := docker-compose

# Colores para output
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
NC := \033[0m

help: ## Muestra esta ayuda
	@echo "$(GREEN)Task API - Comandos disponibles:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# Instalación
# =============================================================================
install: ## Instala dependencias de producción
	$(PIP) install -e .

install-dev: ## Instala dependencias de desarrollo
	$(PIP) install -e ".[dev]"
	pre-commit install

# =============================================================================
# Desarrollo
# =============================================================================
run-dev: ## Ejecuta el servidor de desarrollo con hot-reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

run: ## Ejecuta el servidor de producción
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

shell: ## Abre un shell de Python con el contexto de la app cargado
	$(PYTHON) -c "import asyncio; from app.db.session import async_session; from app.models import User, Task; print('Shell listo. Variables disponibles: asyncio, async_session, User, Task')" -i

# =============================================================================
# Testing
# =============================================================================
test: ## Ejecuta todos los tests
	$(PYTEST) -v

test-cov: ## Ejecuta tests con cobertura
	$(PYTEST) --cov=app --cov-report=html --cov-report=term-missing

test-watch: ## Ejecuta tests en modo watch (requiere pytest-watch)
	ptw -- -v

# =============================================================================
# Calidad de Código
# =============================================================================
lint: ## Ejecuta linters (ruff)
	ruff check app tests
	ruff check --select I app tests

format: ## Formatea el código con black y ruff
	black app tests
	ruff format app tests
	ruff check --fix app tests

type-check: ## Ejecuta type checking con mypy
	mypy app

check: lint type-check test ## Ejecuta todas las verificaciones (lint + type-check + test)

# =============================================================================
# Base de Datos
# =============================================================================
migrate: ## Ejecuta migraciones pendientes
	$(ALEMBIC) upgrade head

migrate-create: ## Crea una nueva migración (usar: make migrate-create MSG="descripcion")
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

migrate-down: ## Revierte la última migración
	$(ALEMBIC) downgrade -1

migrate-history: ## Muestra historial de migraciones
	$(ALEMBIC) history --verbose

migrate-check: ## Verifica si hay migraciones pendientes
	$(ALEMBIC) current
	$(ALEMBIC) history --verbose

db-reset: ## Reinicia la base de datos (⚠️ Elimina todos los datos)
	@echo "$(YELLOW)⚠️  Esto eliminará todos los datos. ¿Continuar? [y/N]$(NC)"
	@read confirm && [ $$confirm = y ] && $(ALEMBIC) downgrade base && $(ALEMBIC) upgrade head || echo "Cancelado"

# =============================================================================
# Docker
# =============================================================================
docker-build: ## Construye las imágenes Docker
	$(DOCKER_COMPOSE) build

docker-up: ## Inicia los servicios con Docker
	$(DOCKER_COMPOSE) up -d

docker-down: ## Detiene los servicios Docker
	$(DOCKER_COMPOSE) down

docker-logs: ## Muestra logs de los servicios
	$(DOCKER_COMPOSE) logs -f

docker-logs-app: ## Muestra logs solo de la app
	$(DOCKER_COMPOSE) logs -f app

docker-migrate: ## Ejecuta migraciones en Docker
	$(DOCKER_COMPOSE) run --rm migrate

docker-shell: ## Abre un shell en el contenedor de la app
	$(DOCKER_COMPOSE) exec app /bin/sh

docker-test: ## Ejecuta tests en Docker
	$(DOCKER_COMPOSE) exec app pytest

docker-clean: ## Limpia contenedores, volúmenes e imágenes
	$(DOCKER_COMPOSE) down -v --rmi all --remove-orphans

# =============================================================================
# Utilidades
# =============================================================================
clean: ## Limpia archivos temporales y caché
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".coverage" -delete 2>/dev/null || true
	rm -rf build/ dist/ .eggs/ 2>/dev/null || true
	@echo "$(GREEN)✅ Limpieza completada$(NC)"

requirements: ## Genera requirements.txt desde pyproject.toml
	$(PIP) freeze > requirements.txt

openapi: ## Exporta la especificación OpenAPI a archivo JSON
	$(PYTHON) -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json
	@echo "$(GREEN)✅ OpenAPI spec exportada a openapi.json$(NC)"

seed: ## Ejecuta script de seeding de datos (si existe)
	$(PYTHON) -c "import asyncio; from app.db.session import async_session; from app.models import User, Task; from app.core.security import get_password_hash; asyncio.run(seed_data())"

# =============================================================================
# CI/CD
# =============================================================================
ci-setup: ## Prepara el entorno para CI
	$(PIP) install -e ".[dev]"

ci-test: ## Comando para ejecutar tests en CI
	$(PYTEST) --cov=app --cov-report=xml --cov-report=term-missing

ci-lint: ## Comando para linting en CI
	ruff check app tests
	black --check app tests

.DEFAULT_GOAL := help