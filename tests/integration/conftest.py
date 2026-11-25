"""Fixtures de integracion: Postgres y MinIO REALES, en contenedores efimeros
via testcontainers -- se levantan y destruyen solos en cada corrida, sin
depender de que alguien levante `docker compose up` a mano (a diferencia de
las verificaciones manuales documentadas en los READMEs). Ver seccion 3 del
documento de arquitectura.

Scope "session": un solo contenedor de cada tipo para toda la corrida de
`tests/integration/` (levantarlos es lo mas lento) -- cada test usa datos con
UUIDs/emails unicos para no pisarse entre si sobre el mismo Postgres/MinIO.
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.minio import MinioContainer
from testcontainers.community.postgres import PostgresContainer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from infrastructure.db.models import Base
from infrastructure.storage.minio_object_storage import MinioObjectStorage


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        yield pg


@pytest_asyncio.fixture(scope="session")
async def db_engine(postgres_container: PostgresContainer):
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.begin() as conn:
        # create_all, no Alembic: aqui se prueban los adaptadores contra un
        # esquema real, no el proceso de migracion en si -- eso ya lo cubre
        # el job "migrations" de CI (alembic upgrade head + alembic check).
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture(scope="session")
def minio_container():
    with MinioContainer("minio/minio") as minio:
        yield minio


@pytest.fixture(scope="session")
def minio_bucket_name() -> str:
    return "axial-studies-test"


@pytest.fixture(scope="session")
def minio_storage(minio_container: MinioContainer, minio_bucket_name: str) -> MinioObjectStorage:
    config = minio_container.get_config()
    storage = MinioObjectStorage(
        endpoint=config["endpoint"],
        access_key=config["access_key"],
        secret_key=config["secret_key"],
        bucket=minio_bucket_name,
        secure=False,
    )
    storage.ensure_bucket()
    return storage
