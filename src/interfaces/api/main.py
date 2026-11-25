from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import settings
from interfaces.api.deps import object_storage, process_pool
from interfaces.api.routers import auth, consent, health, sessions, studies, sus


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment != "test":
        # Llamada sincrona (bloqueante) unica vez al arrancar, antes de que
        # uvicorn sirva ningun request -- no hay nada mas compitiendo por el
        # event loop todavia, a diferencia de un put()/exists() en medio de
        # requests reales (esos si van por run_in_threadpool, ver
        # infrastructure/storage/minio_object_storage.py).
        object_storage.ensure_bucket()
    yield
    # Apaga el ProcessPoolExecutor (ver interfaces/api/deps.py) al parar la
    # app -- wait=True deja terminar los procesamientos en curso en vez de
    # matarlos a mitad (mismo espiritu que un `docker stop` con grace period
    # sobre el `worker` de Celery de antes, no un comportamiento nuevo).
    process_pool.shutdown(wait=True)


def create_app() -> FastAPI:
    # El esquema de la base de datos lo gestiona exclusivamente Alembic
    # (`alembic upgrade head`), en dev y en produccion por igual -- ver seccion
    # 15 del documento de arquitectura. La app nunca crea/modifica tablas por
    # su cuenta, ni siquiera como atajo de desarrollo.
    app = FastAPI(title="Axial API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(studies.router)
    app.include_router(sessions.study_sessions_router)
    app.include_router(sessions.sessions_router)
    app.include_router(sus.router)
    app.include_router(consent.router)
    return app


app = create_app()
