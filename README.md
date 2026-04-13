# Task API

API REST para gestion de tareas con autenticacion JWT, construida con FastAPI, PostgreSQL y Redis.

## Caracteristicas

- Autenticacion JWT: Login seguro con access tokens y refresh tokens
- Gestion de Tareas: CRUD completo con soft delete, filtros y busqueda
- Cache con Redis: Almacenamiento en cache de tareas para mejor rendimiento
- Rate Limiting: Proteccion contra abuso de la API
- Base de Datos: PostgreSQL con SQLAlchemy 2.0 async
- Seguridad: Headers de seguridad, CORS configurado, validacion de inputs
- Documentacion: Swagger UI y ReDoc integrados
- Testing: Suite completa de tests con pytest

## Tecnologias

- Python 3.12
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL 16
- Redis 7
- Docker y Docker Compose
- Pytest

## Requisitos

- Docker Desktop o Docker Engine
- Git

## Instalacion

### Opcion 1: Docker Compose (Recomendado)

1. Clonar el repositorio:

   ```bash
   git clone https://github.com/reiden26/Task-Api.git
   cd Task-Api
   ```

2. Iniciar los servicios:

   ```bash
   docker compose up -d
   ```

3. Verificar que los contenedores esten corriendo:

   ```bash
   docker compose ps
   ```

4. Acceder a la documentacion:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Opcion 2: Desarrollo Local

1. Crear entorno virtual:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   .venv\Scripts\activate     # Windows
   ```

2. Instalar dependencias:

   ```bash
   pip install -e ".[dev]"
   ```

3. Configurar variables de entorno:

   ```bash
   cp .env.example .env
   ```

4. Ejecutar migraciones y iniciar:

   ```bash
   uvicorn app.main:app --reload
   ```

## Estructura del Proyecto

```
Task-api/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py       # Endpoints de autenticacion
│   │       │   └── tasks.py      # Endpoints de tareas
│   │       └── router.py
│   ├── core/
│   │   ├── cache.py              # Gestion de cache con Redis
│   │   ├── config.py             # Configuracion de la aplicacion
│   │   ├── rate_limit.py         # Rate limiting
│   │   └── security.py           # Seguridad y JWT
│   ├── db/
│   │   ├── base.py               # Base de modelos SQLAlchemy
│   │   └── session.py            # Gestion de sesiones
│   ├── models/
│   │   ├── task.py               # Modelo de tareas
│   │   └── user.py               # Modelo de usuarios
│   ├── repositories/
│   │   ├── base.py               # Repositorio base
│   │   ├── task.py               # Operaciones de tareas
│   │   └── user.py               # Operaciones de usuarios
│   ├── schemas/
│   │   ├── task.py               # Esquemas Pydantic de tareas
│   │   └── user.py               # Esquemas Pydantic de usuarios
│   ├── services/
│   │   └── auth.py               # Logica de autenticacion
│   └── main.py                   # Punto de entrada
├── tests/
│   ├── conftest.py               # Configuracion de tests
│   ├── test_auth.py              # Tests de autenticacion
│   └── test_tasks.py             # Tests de tareas
├── docker-compose.yml            # Orquestacion de contenedores
├── Dockerfile                    # Imagen de la aplicacion
├── pyproject.toml                # Configuracion del proyecto
└── README.md                     # Este archivo
```

## Endpoints

### Autenticacion

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST   | /api/v1/auth/register | Registro de usuario |
| POST   | /api/v1/auth/login    | Inicio de sesion    |
| POST   | /api/v1/auth/refresh  | Refrescar token     |
| POST   | /api/v1/auth/logout   | Cerrar sesion       |
| GET    | /api/v1/auth/me       | Obtener usuario actual |

### Tareas

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST   | /api/v1/tasks/               | Crear tarea           |
| GET    | /api/v1/tasks/               | Listar tareas         |
| GET    | /api/v1/tasks/{id}           | Obtener tarea         |
| PATCH  | /api/v1/tasks/{id}           | Actualizar tarea      |
| DELETE | /api/v1/tasks/{id}           | Eliminar tarea        |
| PATCH  | /api/v1/tasks/{id}/restore   | Restaurar tarea       |
| GET    | /api/v1/tasks/statistics     | Estadisticas          |
| GET    | /api/v1/tasks/overdue        | Tareas vencidas       |

### Health

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET    | /health | Estado del sistema |
| GET    | /       | Informacion basica |

## Ejemplos de Uso

### Registro de Usuario

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "usuario@example.com",
    "password": "Password123",
    "full_name": "Nombre Completo"
  }'
```

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "usuario@example.com",
    "password": "Password123"
  }'
```

### Crear Tarea

```bash
curl -X POST http://localhost:8000/api/v1/tasks/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "title": "Nueva Tarea",
    "description": "Descripcion de la tarea",
    "priority": "HIGH",
    "status": "TODO"
  }'
```

### Listar Tareas con Filtros

```bash
curl "http://localhost:8000/api/v1/tasks/?status=TODO&priority=HIGH&search=tarea" \
  -H "Authorization: Bearer <token>"
```

## Testing

Ejecutar todos los tests:

```bash
docker compose exec app pytest tests/ -v
```

Ejecutar tests especificos:

```bash
docker compose exec app pytest tests/test_auth.py -v
docker compose exec app pytest tests/test_tasks.py -v
```

Ver cobertura:

```bash
docker compose exec app pytest tests/ --cov=app --cov-report=html
```

## Configuracion

### Variables de Entorno

| Variable                      | Descripcion                               | Default       |
|-------------------------------|-------------------------------------------|---------------|
| ENVIRONMENT                   | Entorno (development/staging/production)  | development   |
| DEBUG                         | Modo debug                                | false         |
| SECRET_KEY                    | Clave secreta para JWT                    | -             |
| ACCESS_TOKEN_EXPIRE_MINUTES   | Expiracion de access token                | 15            |
| REFRESH_TOKEN_EXPIRE_DAYS     | Expiracion de refresh token               | 7             |
| POSTGRES_SERVER               | Host de PostgreSQL                        | localhost     |
| POSTGRES_PORT                 | Puerto de PostgreSQL                      | 5432          |
| POSTGRES_USER                 | Usuario de PostgreSQL                     | taskapi       |
| POSTGRES_PASSWORD             | Contrasena de PostgreSQL                  | taskapi_secret|
| POSTGRES_DB                   | Base de datos PostgreSQL                  | taskdb        |
| REDIS_HOST                    | Host de Redis                             | localhost     |
| REDIS_PORT                    | Puerto de Redis                           | 6379          |
| RATE_LIMIT_ENABLED            | Habilitar rate limiting                   | true          |

### Seguridad

La API implementa las siguientes medidas de seguridad:

- CORS: Configurado para origenes especificos
- CSP: Content Security Policy headers
- HSTS: HTTP Strict Transport Security
- XSS Protection: Proteccion contra XSS
- Rate Limiting: Limites de peticiones por IP/usuario
- Password Hashing: Contrasenas hasheadas con bcrypt
- JWT Tokens: Tokens firmados con expiracion

## Modelo de Datos

### Usuario

- id: UUID
- email: String (unico)
- hashed_password: String
- full_name: String (opcional)
- is_active: Boolean
- is_superuser: Boolean
- last_login: DateTime
- created_at: DateTime
- updated_at: DateTime

### Tarea

- id: UUID
- title: String (200 caracteres)
- description: Text (opcional)
- status: Enum (TODO, IN_PROGRESS, DONE, CANCELLED)
- priority: Enum (LOW, MEDIUM, HIGH, URGENT)
- due_date: DateTime (opcional)
- completed_at: DateTime (opcional)
- deleted_at: DateTime (soft delete)
- owner_id: UUID (relacion con usuario)
- created_at: DateTime
- updated_at: DateTime

## Arquitectura

### Flujo de Autenticacion

1. Usuario se registra con email/contrasena
2. Contrasena se hashea con bcrypt
3. Login retorna access_token y refresh_token
4. Access token usado en header Authorization: Bearer
5. Refresh token usado para obtener nuevos access tokens
6. Logout invalida tokens en Redis blacklist

### Flujo de Tareas

1. Usuario autenticado crea tarea
2. Tarea almacenada en PostgreSQL
3. Consulta individual cacheada en Redis (5 min TTL)
4. Update/Delete invalida cache automaticamente
5. Soft delete marca deleted_at, hard delete elimina registro

### Rate Limiting

- General: 100 peticiones/minuto por IP
- Login: 5 intentos/15 minutos por IP
- Implementado con Redis sorted sets (sliding window)
- Headers informativos en respuestas

## Desarrollo

### Estructura de Commits

- feat: Nueva caracteristica
- fix: Correccion de bug
- docs: Documentacion
- test: Tests
- refactor: Refactorizacion
- chore: Tareas de mantenimiento

### Calidad de Codigo

```bash
# Formato
black app/ tests/

# Linting
ruff check app/ tests/

# Type checking
mypy app/
```

## Troubleshooting

### Problemas de conexion a PostgreSQL

Verificar que el contenedor este saludable:

```bash
docker compose logs postgres
```

### Problemas de conexion a Redis

```bash
docker compose exec redis redis-cli ping
```

### Tests fallan por conexion

Asegurar que la base de datos de test existe:

```bash
docker compose exec postgres psql -U taskapi -d postgres -c "CREATE DATABASE taskdb_test;"
```

## Contribuir

1. Fork el repositorio
2. Crear rama feature: `git checkout -b feature/nueva-caracteristica`
3. Commit cambios: `git commit -m 'feat: agrega nueva caracteristica'`
4. Push a la rama: `git push origin feature/nueva-caracteristica`
5. Abrir Pull Request

## Licencia

MIT License - ver LICENSE para detalles.

## Contacto

Para preguntas o soporte, abrir un issue en el repositorio.
