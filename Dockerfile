# syntax=docker/dockerfile:1

# ===========================================
# Stage 1: Builder
# ===========================================
FROM python:3.12-slim as builder

# Configuración de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Instalar dependencias del sistema para compilar
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /build

# Instalar dependencias Python
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --user --no-cache-dir -e .

# ===========================================
# Stage 2: Production
# ===========================================
FROM python:3.12-slim as production

# Labels
LABEL maintainer="developer@example.com"
LABEL version="1.0.0"
LABEL description="Task Manager API - FastAPI Production Image"

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    APP_HOME=/app \
    PYTHONPATH=/app

# Instalar dependencias runtime y utilidades
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Crear usuario no-root para seguridad
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Copiar dependencias instaladas desde builder
COPY --from=builder /root/.local /home/appuser/.local
RUN chown -R appuser:appgroup /home/appuser/.local

# Crear directorio de la aplicación
WORKDIR $APP_HOME

# Copiar código de la aplicación
COPY --chown=appuser:appgroup ./app ./app
COPY --chown=appuser:appgroup ./alembic ./alembic
COPY --chown=appuser:appgroup ./alembic.ini ./
COPY --chown=appuser:appgroup ./scripts ./scripts
COPY --chown=appuser:appgroup ./README.md ./

# Hacer ejecutable el script de entrada
RUN chmod +x ./scripts/entrypoint.sh

# Crear directorio de logs
RUN mkdir -p /app/logs && chown -R appuser:appgroup /app

# Puerto expuesto
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Cambiar a usuario no-root
USER appuser

# Agregar path de binarios locales
ENV PATH=/home/appuser/.local/bin:$PATH

# Comando de inicio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers"]

# ===========================================
# Stage 3: Development
# ===========================================
FROM production as development

USER root

# Instalar dependencias de desarrollo
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov httpx black ruff mypy

# Copiar utilidades de desarrollo
COPY --chown=appuser:appgroup ./tests ./tests
COPY --chown=appuser:appgroup ./README.md ./

# Volver a usuario no-root
USER appuser

# Comando para desarrollo con reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "debug"]