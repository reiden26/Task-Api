"""
Configuración centralizada de la aplicación usando pydantic-settings.
Soporta variables de entorno y archivo .env
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración de la aplicación Task API.

    Las variables se cargan en orden de prioridad:
    1. Variables de entorno del sistema
    2. Archivo .env (en desarrollo)
    3. Valores por defecto definidos aquí
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # =========================================================================
    # Información de la Aplicación
    # =========================================================================
    APP_NAME: str = Field(default="Task API", description="Nombre de la aplicación")
    APP_VERSION: str = Field(default="1.0.0", description="Versión de la API")
    APP_DESCRIPTION: str = Field(
        default="API REST para gestión de tareas con autenticación JWT",
        description="Descripción de la aplicación",
    )

    # =========================================================================
    # Entorno
    # =========================================================================
    ENVIRONMENT: str = Field(default="development", description="Entorno: development, staging, production")
    DEBUG: bool = Field(default=False, description="Modo debug")
    LOG_LEVEL: str = Field(default="INFO", description="Nivel de logging")

    @validator("ENVIRONMENT")
    def validate_environment(cls, v: str) -> str:
        """Valida que el entorno sea válido."""
        allowed = {"development", "staging", "production", "testing"}
        if v.lower() not in allowed:
            raise ValueError(f"ENVIRONMENT debe ser uno de: {allowed}")
        return v.lower()

    # =========================================================================
    # Seguridad
    # =========================================================================
    SECRET_KEY: str = Field(
        default="supersecretkeychangemeinproduction",
        description="Clave secreta para JWT y hashing",
        min_length=32,
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        description="Tiempo de expiración del access token en minutos",
        ge=1,
        le=1440,
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        description="Tiempo de expiración del refresh token en días",
        ge=1,
        le=365,
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="Algoritmo de JWT")

    # =========================================================================
    # Base de Datos PostgreSQL
    # =========================================================================
    POSTGRES_SERVER: str = Field(default="localhost", description="Host de PostgreSQL")
    POSTGRES_PORT: int = Field(default=5432, description="Puerto de PostgreSQL", ge=1, le=65535)
    POSTGRES_USER: str = Field(default="taskapi", description="Usuario de PostgreSQL")
    POSTGRES_PASSWORD: str = Field(default="taskapi_secret", description="Contraseña de PostgreSQL")
    POSTGRES_DB: str = Field(default="taskdb", description="Nombre de la base de datos")
    DATABASE_URL: Optional[str] = Field(default=None, description="URL completa de la base de datos (opcional)")

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Construye la URL de conexión async a PostgreSQL."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # =========================================================================
    # Redis
    # =========================================================================
    REDIS_HOST: str = Field(default="localhost", description="Host de Redis")
    REDIS_PORT: int = Field(default=6379, description="Puerto de Redis", ge=1, le=65535)
    REDIS_DB: int = Field(default=0, description="Número de base de datos Redis", ge=0, le=15)
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Contraseña de Redis")
    REDIS_URL: Optional[str] = Field(default=None, description="URL completa de Redis (opcional)")

    @property
    def REDIS_CONNECTION_URL(self) -> str:
        """Construye la URL de conexión a Redis."""
        if self.REDIS_URL:
            return self.REDIS_URL
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # =========================================================================
    # Rate Limiting
    # =========================================================================
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Habilita rate limiting")
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Peticiones permitidas por ventana")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Ventana de tiempo en segundos")

    # =========================================================================
    # CORS
    # =========================================================================
    BACKEND_CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="Orígenes permitidos para CORS (separados por coma)",
    )

    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        """Convierte la string de orígenes a lista."""
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",")]

    # =========================================================================
    # Configuración de la API
    # =========================================================================
    API_V1_STR: str = Field(default="/api/v1", description="Prefijo de la API v1")
    APP_PORT: int = Field(default=8000, description="Puerto de la aplicación", ge=1, le=65535)

    # =========================================================================
    # Propiedades calculadas
    # =========================================================================
    @property
    def is_development(self) -> bool:
        """Verifica si está en modo desarrollo."""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Verifica si está en modo producción."""
        return self.ENVIRONMENT == "production"

    @property
    def is_testing(self) -> bool:
        """Verifica si está en modo testing."""
        return self.ENVIRONMENT == "testing"


@lru_cache()
def get_settings() -> Settings:
    """
    Retorna una instancia cacheada de Settings.

    El cacheo mejora el rendimiento al evitar re-parsear
    las variables de entorno en cada llamada.
    """
    return Settings()


# Instancia global de configuración
settings = get_settings()