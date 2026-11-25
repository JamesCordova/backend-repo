"""Fixtures de integracion del lado processing: Postgres y MinIO REALES, en
contenedores efimeros via testcontainers -- mismo criterio que
tests/integration/conftest.py (lado API), pero con un Postgres via psycopg
(sync, no asyncpg) porque los adaptadores de processing/ son sincronos (ver
processing/jobs.py:_build_adapters). Directorio separado de
tests/integration/ a proposito: `postgres_container` acA es un fixture
DISTINTO (driver psycopg, esquema minimo propio) del `postgres_container` de
tests/integration/conftest.py (driver asyncpg, esquema completo via
Base.metadata) -- pytest los resuelve sin choque porque cada uno vive en su
propio subarbol de directorios.

processing/ no posee las migraciones de Alembic (esas son del lado API) asi
que aca se crea un esquema minimo propio, solo con las columnas que estos
adaptadores realmente usan -- no es una copia del esquema completo de
produccion, es lo necesario para probar que las consultas SQL son correctas.
"""

from uuid import UUID, uuid4

import psycopg
import pytest
from testcontainers.community.minio import MinioContainer
from testcontainers.community.postgres import PostgresContainer

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS studies (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS processing_tasks (
    id UUID PRIMARY KEY,
    study_id UUID NOT NULL REFERENCES studies(id),
    attempt_number INT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    progress_percent INT NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS volumes (
    id UUID PRIMARY KEY,
    study_id UUID NOT NULL REFERENCES studies(id),
    processing_task_id UUID NOT NULL REFERENCES processing_tasks(id),
    detail_level TEXT NOT NULL,
    format TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16", driver="psycopg") as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    # psycopg (v3, sin SQLAlchemy de por medio) no entiende el sufijo
    # "+psycopg" -- eso es una convencion de dialecto de SQLAlchemy.
    url = postgres_container.get_connection_url()
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="session", autouse=True)
def _create_schema(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
        conn.commit()


@pytest.fixture
def seeded_study_id(database_url: str) -> UUID:
    study_id = uuid4()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO studies (id, status) VALUES (%s, 'pending')", (study_id,))
        conn.commit()
    return study_id


@pytest.fixture(scope="session")
def minio_container():
    with MinioContainer("minio/minio") as minio:
        yield minio


@pytest.fixture(scope="session")
def minio_bucket_name() -> str:
    return "axial-processing-test"


@pytest.fixture(scope="session", autouse=True)
def _ensure_minio_bucket(minio_container: MinioContainer, minio_bucket_name: str) -> None:
    client = minio_container.get_client()
    if not client.bucket_exists(minio_bucket_name):
        client.make_bucket(minio_bucket_name)
