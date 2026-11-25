"""Punto unico de entrada a la configuracion. Ver
intern-talk/arquitectura-backend-clean-architecture.md seccion 2.

domain/ y application/ nunca importan este modulo -- solo infrastructure/ e
interfaces/ (via deps.py) saben que existen variables de entorno. Lo mismo
aplica a processing/: sus funciones reciben `database_url_sync`/credenciales
de MinIO como argumentos (ver processing/jobs.py:_build_adapters), nunca
importan `pydantic_settings` directo -- pero como ahora processing/ vive en
el mismo proceso/paquete que la API (ver README), comparte esta UNICA
instancia de Settings en vez de tener su propio config.py duplicado como
tenia worker-repo.

Sin `redis_url`: no hay broker -- el procesamiento corre en el mismo proceso
via un ProcessPoolExecutor (ver infrastructure/queue/in_process_task_queue.py),
no en un segundo servicio de aplicacion que consuma una cola.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "dev"
    # Driver async (asyncpg) -- lo usa el engine de SQLAlchemy del lado API
    # (infrastructure/db/session.py). El procesamiento pesado corre en un
    # proceso aparte (ver database_url_sync mas abajo) porque psycopg (sync)
    # es quien hablaba con Postgres desde worker-repo, y cambiarlo a asyncpg
    # ahi no tendria sentido: esos procesos hijos no corren un event loop.
    database_url: str = "postgresql+asyncpg://app:devpassword@localhost:5432/axial"
    jwt_secret: str = "changeme-in-.env"
    jwt_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:5173"
    # "local" (default): LocalFilesystemObjectStorage, sin servicios externos
    # -- ver README, seccion "Correr sin Docker" (los binarios community de
    # MinIO dejaron de publicarse para descarga directa a fines de 2025).
    # "minio": MinioObjectStorage, para cuando SI hay un MinIO/S3 real
    # disponible (ej. produccion contra un bucket real). Ambos implementan el
    # mismo Protocol (application/ports/object_storage.py y su equivalente
    # sincrono en processing/), asi que ningun caso de uso sabe cual esta
    # activo -- se elige en interfaces/api/deps.py y processing/jobs.py.
    storage_backend: str = "local"
    # Directorio base para storage_backend="local". Relativo al directorio
    # desde donde se arranca el proceso (WORKDIR /app dentro del Dockerfile).
    local_storage_dir: str = "./data/objects"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "axial-studies"
    minio_secure: bool = False
    # Tamano del ProcessPoolExecutor que corre processing/jobs.py -- cuantos
    # estudios se procesan en simultaneo como maximo. None (default) deja que
    # ProcessPoolExecutor use os.process_cpu_count() (min(32, cpu_count+4) en
    # versiones viejas de Python) -- explicito aca para poder bajarlo en una
    # maquina con pocos recursos sin tocar codigo.
    processing_workers: int | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url_sync(self) -> str:
        """Misma base de datos que `database_url`, driver sincrono (psycopg)
        -- lo necesitan los adaptadores de processing/ (PostgresStudyStatusRepository,
        PostgresVolumeRepository), que corren en un proceso hijo sin event
        loop. Antes esto era una variable de entorno *separada* en
        worker-repo (con su propio config.py) porque era un repo/deploy
        distinto; ahora que es el mismo proceso/config, se deriva de
        `database_url` en vez de arriesgarse a que las dos queden
        desincronizadas (mismo host/usuario/clave/base, solo cambia el
        scheme de la URL)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


settings = Settings()
