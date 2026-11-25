# Imagen unica (antes eran dos: api-repo y worker-repo) -- se construye
# directamente en la VM/maquina destino a partir del codigo fuente, sin
# registro de contenedores (mismo criterio que los repos originales).

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/
WORKDIR /app

# Capa de dependencias separada del codigo: cambiar src/ no invalida esta
# capa, solo cambiar pyproject.toml/uv.lock lo hace -- rebuilds mas rapidos.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY alembic.ini ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim

# libgomp1: SimpleITK/ITK usa OpenMP para paralelizar el procesamiento de
# imagenes -- sin esta libreria del sistema, falla al importar SimpleITK
# (antes vivia solo en el Dockerfile de worker-repo; ahora ambos lados
# comparten esta unica imagen).
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app app
WORKDIR /app
COPY --from=builder /app /app
# storage_backend="local" (default, ver infrastructure/config.py) escribe
# aca -- crearlo y darle dueno "app" ahora, mientras todavia somos root,
# para que el proceso (ya como "app" mas abajo) pueda escribir. En
# docker-compose.yml se monta un volumen encima (objects_data) para que
# sobreviva un `docker compose down`/rebuild.
RUN mkdir -p /app/data/objects && chown -R app:app /app/data
ENV PATH="/app/.venv/bin:$PATH"
USER app

EXPOSE 8000

# El esquema lo aplica Alembic al arrancar el contenedor -- unica fuente de
# verdad, la misma en dev y produccion. Si la migracion falla, el contenedor
# no llega a levantar el servidor (falla visible en `docker compose logs`,
# no un servidor sirviendo con esquema desactualizado). Un solo proceso: la
# API y el procesamiento (ProcessPoolExecutor) viven en el mismo `uvicorn`
# -- no hay un segundo comando de `celery worker` que levantar aparte.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn interfaces.api.main:app --host 0.0.0.0 --port 8000 --app-dir src"]
