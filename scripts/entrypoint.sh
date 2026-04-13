#!/bin/sh

# Script de entrada para Docker
# Espera a que PostgreSQL esté listo, ejecuta migraciones e inicia la aplicación

set -e

echo "========================================"
echo "Task API - Docker Entrypoint"
echo "========================================"

# Función para esperar a que un host:puerto esté disponible
wait_for_service() {
    host="$1"
    port="$2"
    service="$3"

    echo "⏳ Waiting for $service at $host:$port..."

    timeout=60
    counter=0
    while ! nc -z "$host" "$port" 2>/dev/null; do
        counter=$((counter + 1))
        if [ $counter -gt $timeout ]; then
            echo "❌ Timeout waiting for $service"
            exit 1
        fi
        echo "   Still waiting... ($counter/$timeout)"
        sleep 1
    done

    echo "✅ $service is ready!"
}

# Esperar a PostgreSQL
wait_for_service "$POSTGRES_SERVER" "$POSTGRES_PORT" "PostgreSQL"

# Esperar a Redis (opcional, para asegurar que todo está listo)
if [ -n "$REDIS_HOST" ]; then
    wait_for_service "$REDIS_HOST" "${REDIS_PORT:-6379}" "Redis"
fi

# Ejecutar migraciones de base de datos
echo ""
echo "📦 Running database migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully"
else
    echo "❌ Migration failed"
    exit 1
fi

# Iniciar la aplicación
echo ""
echo "🚀 Starting application..."
echo "========================================"

exec "$@"
