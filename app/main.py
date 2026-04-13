"""
Punto de entrada de la aplicación Task API.

Configura FastAPI con middlewares de seguridad, rate limiting, logging estructurado.
"""

import time
import traceback
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.rate_limit import rate_limit_middleware
from app.db.session import db_manager

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación.
    """
    # Startup
    logger.info(
        "application_starting",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )

    # Verificar conexión a base de datos
    db_ok = await db_manager.check_connection()
    if not db_ok:
        logger.error("database_connection_failed_on_startup")
    else:
        logger.info("database_connection_verified")

    yield

    # Shutdown
    logger.info("application_shutting_down")
    await db_manager.close()
    logger.info("application_shutdown_complete")


def create_application() -> FastAPI:
    """
    Factory de aplicación FastAPI con seguridad y logging.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ==========================================================================
    # Middlewares de Seguridad
    # ==========================================================================

    # CORS - Configuración segura desde variables de entorno
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS_LIST,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Request-ID",
        ],
    )

    # Compresión GZIP para respuestas > 1000 bytes
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # ==========================================================================
    # Middleware de Logging y Request ID
    # ==========================================================================

    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        """
        Middleware de logging estructurado con request ID.

        Loguea: request method + path + status_code + duration
        """
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()

        logger.info(
            "request_started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(process_time * 1000, 2),
            )

            # Agregar headers de seguridad
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

            # CSP más permisivo para Swagger UI y ReDoc
            if request.url.path in ("/docs", "/redoc", "/openapi.json"):
                # Permitir CDNs necesarios para documentación
                csp = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                    "img-src 'self' data: https://fastapi.tiangolo.com; "
                    "connect-src 'self'"
                )
            else:
                csp = "default-src 'self'"
            response.headers["Content-Security-Policy"] = csp

            return response

        except Exception as exc:
            process_time = time.time() - start_time
            logger.error(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                error=str(exc),
                error_type=type(exc).__name__,
                traceback=traceback.format_exc() if settings.DEBUG else None,
                duration_ms=round(process_time * 1000, 2),
            )
            raise

    # ==========================================================================
    # Rate Limiting Middleware
    # ==========================================================================

    if settings.RATE_LIMIT_ENABLED:
        app.middleware("http")(rate_limit_middleware)

    # ==========================================================================
    # Routers
    # ==========================================================================

    # API v1
    app.include_router(
        api_router,
        prefix=settings.API_V1_STR,
    )

    # ==========================================================================
    # Health Checks
    # ==========================================================================

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """
        Endpoint de health check para monitoreo.
        """
        db_ok = await db_manager.check_connection()
        status_code = "healthy" if db_ok else "degraded"

        return {
            "status": status_code,
            "database": "connected" if db_ok else "disconnected",
            "version": settings.APP_VERSION,
        }

    @app.get("/", tags=["Root"])
    async def root() -> dict:
        """Endpoint raíz con información básica."""
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "documentation": "/docs",
            "health": "/health",
            "environment": settings.ENVIRONMENT,
        }

    # ==========================================================================
    # Manejo Global de Errores
    # ==========================================================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        Manejador global de excepciones.

        No expone información sensible en producción.
        """
        request_id = getattr(request.state, "request_id", "unknown")

        logger.error(
            "unhandled_exception",
            request_id=request_id,
            error=str(exc),
            type=type(exc).__name__,
            path=request.url.path,
            traceback=traceback.format_exc() if settings.DEBUG else None,
        )

        # En producción, no mostrar detalles del error
        if settings.is_production:
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "type": "internal_error",
                    "request_id": request_id,
                },
            )

        # En desarrollo, mostrar más información
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "request_id": request_id,
            },
        )

    return app


# Instancia de la aplicación
app = create_application()


# Punto de entrada para desarrollo local
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=settings.is_development,
        log_level=settings.LOG_LEVEL.lower(),
    )