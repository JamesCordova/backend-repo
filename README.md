# axial-backend

Backend monolítico de **Axial** (API + procesamiento DICOM asíncrono en un
solo proceso). Nace de fusionar `api-repo` (FastAPI) y `worker-repo` (Celery)
en un único repo/servicio desplegable, para poder correr todo el stack
localmente con pocos contenedores en una máquina con espacio en disco
limitado. Ver `intern-talk/arquitectura-backend-ct-volumetrico.md` y
`intern-talk/arquitectura-backend-clean-architecture.md` (repo principal) para
el diseño original de dominio — sigue vigente, lo que cambia acá es solo
**cómo se despliega**, no las reglas de negocio.

## Por qué existe este repo

`api-repo` + `worker-repo` + `infra-repo` funcionan y están bien probados
(ver sus READMEs), pero levantar el stack completo en local exige **5
contenedores**: Postgres, Redis, MinIO, `api` y `worker` — dos imágenes de
aplicación propias (cada una con su propio `python:3.12-slim` base) más tres
servicios de infraestructura. En una máquina con poco disco, eso es peso
real: dos bases de imagen completas, dependencias duplicadas entre ambas
(`pydantic-settings`, `minio`, `celery[redis]`), y dos contenedores enteros
(Redis, MinIO) que existen solo para transportar un mensaje y guardar
archivos respectivamente — nada que una sola máquina, un solo proceso, no
pueda hacer directo.

Este repo colapsa eso a **2 contenedores**: `postgres` y `app` (una sola
imagen que hace de API y de "worker" a la vez, y guarda los archivos en un
volumen propio en vez de en un servicio S3 aparte). Ver
[`docker-compose.yml`](docker-compose.yml) — y más abajo, cómo correrlo
**sin ningún contenedor**.

## Cómo se logra sin perder "asíncrono ni bloqueante"

La pregunta que motivó esto: si la API y el procesamiento pesado (SimpleITK +
numpy sobre una serie DICOM completa) viven en el **mismo proceso**, ¿no se
bloquea la API mientras procesa un estudio? ¿Y si llegan dos estudios a la
vez?

No, por la misma razón por la que ya no hacía falta Celery+Redis para
lograrlo: lo único que importa es que el trabajo pesado **no corra en el
event loop de `uvicorn`**. Antes eso se lograba con un proceso `worker`
aparte, conectado por una cola (Redis). Ahora se logra con
[`concurrent.futures.ProcessPoolExecutor`](https://docs.python.org/3/library/concurrent.futures.html#processpoolexecutor)
(librería estándar, sin dependencias nuevas):

- Al arrancar la app se crea **un solo pool de procesos** (ver
  `src/interfaces/api/deps.py:process_pool`) — no revienta el arranque:
  `ProcessPoolExecutor` no lanza procesos hijo hasta el primer trabajo real.
- `POST /estudios/{id}/confirmar-subida[-raw]` (los mismos endpoints de
  siempre) llaman a `InProcessTaskQueue.enqueue_processing(...)` en vez de
  `CeleryTaskQueue.enqueue_processing(...)` — mismo `Protocol` (`TaskQueue`,
  `src/application/ports/task_queue.py`), sin tocar ningún caso de uso. En
  vez de mandar un mensaje a Redis, somete el trabajo real
  (`processing.jobs.run_dicom_processing`/`run_raw_volume_processing`) al
  pool con `loop.run_in_executor(...)` y **retorna de inmediato** — mismo
  contrato *fire-and-forget* que tenía Celery.
- Ese trabajo corre en un **proceso del sistema operativo aparte** (no un
  hilo): la API sigue respondiendo otros requests sin competir por el GIL
  mientras SimpleITK procesa un volumen de cientos de MB, y un crash del
  procesamiento no puede tumbar el proceso que sirve HTTP.
- Varios estudios se procesan **en paralelo de verdad**, hasta el límite del
  pool (`PROCESSING_WORKERS` en `.env` — default: un worker por núcleo de
  CPU) — ni un estudio bloquea a otro, ni el procesamiento bloquea la API.
- El progreso granular (`processing_tasks.stage`/`progress_percent`,
  `GET /estudios/{id}` para hacer polling) sigue funcionando exactamente
  igual: el proceso hijo escribe a Postgres directo (`psycopg`, síncrono, sin
  event loop) en cada paso — es *literalmente* el mismo código que tenía
  `worker-repo`, solo que ahora vive en `src/processing/jobs.py` en vez de un
  repo/proceso aparte.

## Arquitectura del repo

Dos "bounded contexts" en el mismo código, deliberadamente separados por
namespace de Python (no por repo/red) para no perder la regla de dependencia
de Clean Architecture:

```
src/
├── domain/, application/, infrastructure/, interfaces/api/   # lado API
│                                                               (ex api-repo, intacto)
├── processing/                                                # lado procesamiento
│   ├── domain/            (ex worker-repo: domain/)           (ex worker-repo, intacto,
│   ├── application/       (ex worker-repo: application/)       solo re-namespaced bajo
│   ├── infrastructure/    (ex worker-repo: infrastructure/)    "processing." para no
│   └── jobs.py            (ex worker-repo: interfaces/tasks/   chocar con el lado API
│                            celery_app.py, sin el wrapper       -- Volume, por ejemplo,
│                            de Celery)                          significa algo distinto
│                                                                 en cada lado)
└── infrastructure/queue/
    └── in_process_task_queue.py   # el adaptador nuevo: TaskQueue -> ProcessPoolExecutor
                                     # (reemplaza a infrastructure/queue/celery_task_queue.py)
```

Por qué `processing.Volume` (array de píxeles + spacing) y el `Volume` del
lado API (fila de la tabla `volumes`, ya escrita) siguen siendo dos clases
distintas con el mismo nombre, en vez de unificarse: son conceptos distintos
que conviven en dos módulos distintos (`domain/entities.py` vs
`processing/domain/entities.py`) — exactamente la misma decisión que ya
documentaban los repos originales (`intern-talk/...` sección 1.3), solo que
antes la fronter la marcaba el proceso/red y ahora la marca el namespace de
Python.

`src/application/ports/task_queue.py` (el `Protocol` `TaskQueue`) no cambió
ni una línea — es la costura que hizo posible este cambio sin tocar ningún
caso de uso (`ConfirmStudyUpload`, `ConfirmRawVolumeUpload`).

## De 5 servicios a 2

| Antes (`infra-repo`)                    | Ahora (este repo)          |
|------------------------------------------|-----------------------------|
| `postgres`                                | `postgres` (igual)          |
| `redis` (solo transportaba 1 mensaje)     | **eliminado**                |
| `minio`                                   | **eliminado** (filesystem local, ver abajo) |
| `api` (imagen propia)                     | `app` (API + procesamiento) |
| `worker` (imagen propia, Celery)          | *(fusionado en `app`)*      |

`minio` se reemplazó por [`LocalFilesystemObjectStorage`](src/infrastructure/storage/local_filesystem_object_storage.py)
(y su equivalente síncrono en `src/processing/`) detrás del mismo `Protocol`
`ObjectStorage` que ya usaba `MinioObjectStorage` — ningún caso de uso sabe
cuál de los dos adaptadores está activo (`storage_backend` en `.env`, default
`"local"`). `MinioObjectStorage` sigue en el repo, funcional y con sus tests,
para cuando sí haga falta un S3 real (ver "Qué se pierde" más abajo) — solo
dejó de ser la opción por defecto. Motivo concreto, no solo preferencia: los
binarios de la edición community de MinIO **dejaron de publicarse para
descarga directa** a fines de 2025 (`dl.min.io` devuelve `410 Gone`, el
proyecto community quedó archivado) — instalarlo hoy sin Docker requeriría
compilarlo con Go, así que ya no es el camino simple que era antes.

Beneficio adicional: este repo trae su **propio** `docker-compose.yml` con
`build: context: .` — ya no hace falta clonar 3 repos como hermanos
(`api-repo` + `worker-repo` + `infra-repo`), alcanza con este.

## Cómo correr en local (con Docker)

```bash
uv sync --extra dev             # crea .venv/ con TODAS las dependencias
                                 # (API + procesamiento) en un solo entorno
cp .env.example .env            # generar DB_PASSWORD/JWT_SECRET reales
docker compose up -d --build    # postgres + app (2 contenedores)
curl http://localhost:8000/health
```

Para desarrollo sin reconstruir la imagen en cada cambio (Postgres en
Docker, la app corriendo directo con `uv`):

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn interfaces.api.main:app --reload --app-dir src
```

## Correr sin Docker (Postgres nativo, sin más servicios)

Nada acá depende de Docker en sí — Postgres es solo "un servidor Postgres"
en `localhost`, al que la app se conecta por red; el storage de archivos ya
no necesita ningún servicio aparte (`storage_backend="local"`, default —
ver arriba). Si ya tenés Postgres instalado nativo en la máquina (Windows:
el instalador de EnterpriseDB, corre como servicio) y no querés ni el peso
de Docker Desktop, esta es la otra opción — y la única de las dos que no
necesita **ningún** contenedor.

### 1. Postgres (asumiendo que ya está instalado y el servicio corriendo)

```powershell
# Verificar que esta escuchando en el puerto por defecto:
& "C:\Program Files\PostgreSQL\15\bin\pg_isready.exe"

# Crear el rol y la base (una sola vez; pide la contraseña del superusuario
# "postgres" que pusiste al instalar) -- devpassword/axial son los mismos
# valores que ya trae por default infrastructure/config.py, para no
# necesitar un .env:
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -c "CREATE ROLE app WITH LOGIN PASSWORD 'devpassword';"
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -c "CREATE DATABASE axial OWNER app;"
```

(Ajustá la ruta/versión si tu instalación no es la 15. Si no tenés Postgres
instalado todavía, el instalador oficial es
https://www.postgresql.org/download/windows/ -- durante la instalación te
pide fijar la contraseña del superusuario `postgres`, la que usan los dos
comandos de arriba.)

### 2. La app

```powershell
cd C:\Users\Space\project-tesis\backend-repo
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn interfaces.api.main:app --reload --app-dir src
```

No hace falta crear un `.env` para este camino -- los defaults de
`infrastructure/config.py` ya apuntan a `localhost` con las mismas
credenciales que se crearon arriba, y `storage_backend="local"` escribe los
archivos subidos/procesados en `./data/objects` (relativo a donde corras
`uvicorn` — se crea solo, no hace falta crearlo a mano). Ver
[`.env.local.example`](.env.local.example) si preferís declarar los valores
explícitos igual, o si vas a cambiar `JWT_SECRET`/`CORS_ORIGINS` para algo
más serio que una prueba rápida: `cp .env.local.example .env`.

Confirmar que quedó arriba:

```powershell
curl http://localhost:8000/health
```

Eso es todo — ni un `docker`, ni un `minio.exe`, ni un `redis-server` de
por medio. Postgres corre como servicio de Windows (sobrevive un reinicio
de la máquina sin que hagas nada); la próxima vez que quieras levantar la
app alcanza con repetir el paso 2.

## Verificado (en esta sesión, sin Docker disponible en la máquina)

- `uv sync --extra dev` resuelve e instala **todas** las dependencias de
  ambos lados (FastAPI, SQLAlchemy, Alembic, `python-jose`, `minio`, numpy,
  `pydicom`, `SimpleITK`, `psycopg`) en un solo `uv.lock`, sin conflictos de
  versiones.
- `uv run pytest tests/unit tests/processing/unit tests/api` — **179 tests
  pasan**: toda la lógica de dominio/casos de uso de ambos lados (incluidos
  los que ya traían api-repo/worker-repo, migrados sin tocarles una línea de
  lógica) más los tests nuevos de:
  - `InProcessTaskQueue` (`tests/unit/test_in_process_task_queue.py`): uno
    somete una función real a un `ProcessPoolExecutor` real y confirma que
    cruza a otro proceso del sistema operativo sin bloquear al llamador (con
    un archivo marcador, no un mock — un mock no sobrevive el *pickling*
    hacia el proceso hijo), y otros tres confirman que
    `enqueue_processing`/`enqueue_raw_processing` traducen los argumentos
    correctamente (`UUID`→`str`, tupla→lista para `value_range`) usando un
    `ThreadPoolExecutor` (mismo intérprete, así que `monkeypatch` sí aplica)
    para no pagar el costo de un proceso real en cada test.
  - `LocalFilesystemObjectStorage`, los dos lados
    (`tests/unit/test_local_filesystem_object_storage.py` y
    `tests/processing/unit/test_local_filesystem_object_storage_sync.py`):
    `put`/`exists`/`get_stream` de punta a punta (incluido offset/length
    para Range HTTP), rechazo de keys que intentan salir del directorio base
    (`../...`), y un test que confirma el punto central de este cambio —
    lo que sube el adaptador async (lado API) lo lee directo el adaptador
    sync (lado processing) desde el mismo directorio, sin red de por medio.
- `uv run ruff check .` / `uv run mypy` sobre los archivos nuevos/tocados —
  limpio (el único error de `mypy` que salió, en `processing/jobs.py`, ya
  existía en el `celery_app.py` original de `worker-repo` — se corrigió de
  paso).

**No verificado acá** (esta máquina no tiene Docker corriendo — coherente
con el motivo de este repo): el `docker compose up -d --build` completo
(construir la imagen con `libgomp1`/SimpleITK, healthchecks, migración
automática al arrancar), y `tests/integration`/`tests/processing/integration`
(testcontainers — Postgres/MinIO reales; siguen usando `MinioObjectStorage`
a propósito, para no perder la cobertura de ese adaptador aunque ya no sea
el default). La lógica que esos tests cubren es la misma que ya corrían en
`api-repo`/`worker-repo` (código migrado sin cambios), así que el riesgo es
bajo, pero **correlo vos antes de confiar en este repo para algo real** (sí
verifiqué en esta sesión, sin Docker, el camino que SÍ importa para "sin
Docker": `uv run pytest tests/unit tests/processing/unit` cubre
`LocalFilesystemObjectStorage` de punta a punta, ver arriba):

```bash
docker compose up -d --build && curl http://localhost:8000/health
uv run pytest tests/integration tests/processing/integration -v
```

## Qué se pierde vs. Celery+Redis (léelo antes de decidir)

- **Sin reintentos automáticos.** Celery puede reintentar una tarea fallida
  con backoff; acá, si `run_dicom_processing` lanza una excepción, se marca
  `failed` en Postgres (igual que antes) pero no se reintenta solo. No era
  un comportamiento que los repos originales tuvieran configurado tampoco
  (no se documenta ningún `retry` en `celery_app.py`), así que no es una
  regresión real, pero si pensabas agregarlo, acá se agrega distinto (lógica
  propia, no un decorador de Celery).
- **Sin recuperación automática tras un crash del proceso completo.** Si el
  proceso `app` entero muere a mitad de un procesamiento (no el proceso hijo
  del pool, sino todo el contenedor — ej. `docker compose down` a mano, o el
  host se reinicia), la fila en `processing_tasks` queda en `running` para
  siempre, sin nadie que la marque `failed` ni la reencole. Esto tampoco
  estaba resuelto antes (un `worker` de Celery matado a mitad tampoco
  reencolaba solo sin configuración extra de Celery que no estaba
  presente), pero es más visible acá porque no hay un `docker-compose`
  separado por servicio que puedas reiniciar solo. Si esto te importa para
  la tesis, una rutina simple al arrancar (`SELECT ... WHERE status =
  'running'` → `mark_failed`) cierra el gap; no se agregó para no inventar
  comportamiento no pedido.
- **No escala a múltiples máquinas.** Celery+Redis permite sumar workers en
  otra VM sin tocar código. `ProcessPoolExecutor` está acotado a los núcleos
  de esta máquina. Para una tesis con datasets sintéticos/abiertos corriendo
  en una sola VM (Oracle free tier, ver `infra-repo`), no es una limitación
  real hoy — es el tipo de cosa a reconsiderar solo si el volumen de uso
  cambia mucho.

Ninguno de estos tres puntos motivó una decisión distinta acá: el problema
que se pidió resolver era espacio en disco/cantidad de servicios en local,
no throughput ni alta disponibilidad — si esas prioridades cambian, volver a
Celery+Redis (o pasar a algo como `arq`/`dramatiq` con Redis) es la
conversación a tener, no una sorpresa escondida en este README.

## Cómo se relaciona con `api-repo` / `worker-repo` / `infra-repo`

Este repo se generó copiando el código fuente real de esos tres (no
reescrito desde cero) — cada decisión ya tomada y documentada ahí (Clean
Architecture, NIfTI como formato, LOD, progreso granular, `.raw`/`value_range`,
consentimiento informado, SUS, biblioteca compartida) sigue intacta, ver sus
propios READMEs para el detalle de *qué hace* cada endpoint/caso de uso —
este README solo documenta *cómo cambió el despliegue*.

`api-repo`/`worker-repo`/`infra-repo` siguen existiendo y funcionando tal
cual — no se tocó nada ahí. Quedan como referencia de la arquitectura
multi-servicio (útil si en algún momento sí hace falta escalar a varias
máquinas) y como lo que corre en la VM de producción (Oracle) hasta que se
decida migrar el deploy real a este repo. Antes de reemplazar `infra-repo`
en producción con este repo, faltaría portar lo que `infra-repo` todavía
tiene pendiente (HTTPS/Caddy, backup) — no es específico de este repo, ver
su README.

## Siguientes pasos posibles (no hechos, a propósito)

- **Si en algún momento sí hace falta un S3 real** (ej. producción, o un
  MinIO ya andando en otro lado): `STORAGE_BACKEND=minio` +
  `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`/`MINIO_BUCKET` en
  `.env` — `MinioObjectStorage` (los dos lados) sigue en el repo, con tests,
  nunca se borró. Para levantar un MinIO real vos mismo hoy (ya no hay
  binario suelto descargable, ver arriba): la imagen Docker
  `minio/minio` en Docker Hub podría seguir disponible aunque los binarios
  sueltos no — no lo verifiqué en esta sesión (no hay Docker acá); si seguís
  usando Docker igual de todos modos esa sería la opción mas directa.
- **Git**: este directorio no es todavía un repo git propio (para no decidir
  por vos si reemplaza a `api-repo`/`worker-repo` o convive con ellos, y si
  correspondería un remoto nuevo en GitHub). `git init` + primer commit
  cuando decidas cómo lo querés versionar.
