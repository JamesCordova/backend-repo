"""Punto de entrada del procesamiento pesado (CPU-bound). Deliberadamente
delgado: solo traduce entre los argumentos que le pasa la API (via
`infrastructure/queue/in_process_task_queue.py`) y el caso de uso real
(`processing/application/use_cases/process_dicom_series.py`) -- ninguna
logica de negocio vive aqui.

Origen: esto era `worker-repo/src/interfaces/tasks/celery_app.py`, un proceso
Celery separado que consumia mensajes de Redis. Fusionado en un solo backend
(ver README, seccion "De 5 servicios a 3") se volvio innecesario: no hace
falta un broker (Redis) ni un segundo proceso de aplicacion (worker) para
lograr que el procesamiento sea asincrono -- basta con NO correrlo en el
event loop de la API. Las funciones `run_dicom_processing`/
`run_raw_volume_processing` de mas abajo son las que
`InProcessTaskQueue` (infrastructure/queue/in_process_task_queue.py) somete a
un `ProcessPoolExecutor`: cada llamada corre en un proceso Python aparte (no
un hilo -- SimpleITK/numpy liberan el GIL en parte pero siguen siendo
CPU-bound; un proceso aparte tambien aisla un crash del worker de matar la
API), asi que procesar un estudio nunca bloquea el loop de asyncio que sirve
el resto de los requests, y varios estudios se procesan en paralelo hasta el
limite del pool (ver `settings.processing_workers`).

Todo lo demas (que el DICOM se descarga a un tmpdir que se autolimpia, que
cada nivel de detalle se sube y se registra por separado, que el progreso se
refleja en Postgres entre cada paso) es identico a como funcionaba en
worker-repo -- ese diseno no dependia de Celery, solo de que la funcion
corriera fuera del proceso que sirve HTTP.
"""

import logging
import tempfile
from pathlib import Path
from uuid import UUID

import numpy as np

from infrastructure.config import settings
from processing.application.ports.object_storage import ObjectStorage
from processing.application.ports.study_status_repository import StudyStatusRepository
from processing.application.ports.volume_processor import VolumeProcessor
from processing.application.ports.volume_repository import VolumeRepository
from processing.application.ports.volume_serializer import VolumeSerializer
from processing.application.use_cases.process_dicom_series import (
    DEFAULT_DETAIL_LEVELS,
    ProcessDicomSeries,
    ProcessDicomSeriesInput,
)
from processing.domain.entities import Volume
from processing.domain.minmax import normalize_minmax, normalize_range
from processing.infrastructure.db.postgres_study_status_repository import (
    PostgresStudyStatusRepository,
)
from processing.infrastructure.db.postgres_volume_repository import PostgresVolumeRepository
from processing.infrastructure.dicom.simpleitk_volume_processor import SimpleItkVolumeProcessor
from processing.infrastructure.dicom.simpleitk_volume_serializer import SimpleItkVolumeSerializer
from processing.infrastructure.storage.local_filesystem_object_storage import (
    LocalFilesystemObjectStorage,
)
from processing.infrastructure.storage.minio_object_storage import MinioObjectStorage

logger = logging.getLogger(__name__)

# dtypes de numpy validos para un volumen .raw -- allowlist explicita en vez
# de confiar en np.dtype(string) directo con lo que mande el cliente, para
# dar un error claro (ValueError) en vez de uno crudo de numpy si mandan
# algo raro (ej. "object", que no tiene sentido para un volumen escalar).
RAW_DTYPES: dict[str, type] = {
    "uint8": np.uint8,
    "int16": np.int16,
    "uint16": np.uint16,
    "int32": np.int32,
    "float32": np.float32,
    "float64": np.float64,
}

# NIfTI (.nii.gz): decision de formato ya cerrada (ver README de worker-repo
# original) -- volume-renderer-ts (el frontend) ya sabe leer NIfTI via
# nifti-reader-js, asi que se serializa directo a ese formato.
_RESULT_FORMAT = "nii.gz"


def _result_object_key(study_id: UUID, detail_level: str) -> str:
    """Mismo prefijo que usa el lado API para servir el resultado -- ver
    GET /estudios/{id}/volumen en interfaces/api/routers/studies.py."""
    return f"results/{study_id}/{detail_level}.{_RESULT_FORMAT}"


def _finish_processing(
    status_repo: StudyStatusRepository,
    storage: ObjectStorage,
    volumes: VolumeRepository,
    serializer: VolumeSerializer,
    processing_task_id: UUID,
    study_id: UUID,
    volumes_by_level: dict[str, Volume],
    tmp_dir: str,
) -> dict:
    """Comun a los dos caminos de entrada (DICOM y RAW, ver mas abajo) --
    sube cada nivel de detalle ya calculado, registra las filas en `volumes`,
    marca succeeded. Separado para no duplicar esta parte, identica en
    ambos casos."""
    status_repo.update_progress(processing_task_id, "uploading_result", 70)
    uploaded = []  # (detail_level, result_key, size_bytes) -- para registrar despues
    num_levels = len(volumes_by_level)
    for i, (detail_level, volume) in enumerate(volumes_by_level.items()):
        result_key = _result_object_key(study_id, detail_level)
        result_path = Path(tmp_dir) / f"{detail_level}.{_RESULT_FORMAT}"
        serializer.save(volume, result_path)
        storage.upload_from(result_path, result_key)
        uploaded.append((detail_level, result_key, result_path.stat().st_size))
        # 70 -> 95% repartido entre los niveles subidos, no todos de una --
        # si hay 1 solo nivel salta directo a 95.
        progress = 70 + round(25 * (i + 1) / num_levels)
        status_repo.update_progress(processing_task_id, "uploading_result", progress)

    # Registrar recien despues de que TODAS las subidas salieron bien -- si
    # una fallara a mitad, el caller ya la habria atajado antes de llegar
    # aca, asi que no queda una fila de "volumes" sin su archivo real.
    for detail_level, result_key, size_bytes in uploaded:
        volumes.create(
            study_id=study_id,
            processing_task_id=processing_task_id,
            detail_level=detail_level,
            format=_RESULT_FORMAT,
            storage_path=result_key,
            size_bytes=size_bytes,
        )
    status_repo.mark_succeeded(study_id, processing_task_id)

    full_volume = volumes_by_level["full"]
    return {
        "study_id": str(study_id),
        "detail_levels": list(volumes_by_level.keys()),
        "shape": list(full_volume.pixel_array.shape),
        "spacing": list(full_volume.spacing),
    }


def _process_study(
    status_repo: StudyStatusRepository,
    processor: VolumeProcessor,
    storage: ObjectStorage,
    volumes: VolumeRepository,
    serializer: VolumeSerializer,
    study_id_str: str,
    dicom_object_keys: list[str],
) -> dict:
    """Orquestacion real, separada de `run_dicom_processing` para poder
    probarla con fakes (ver tests/processing/unit/test_jobs.py) sin depender
    de Postgres ni MinIO reales."""
    study_id = UUID(study_id_str)
    logger.info("procesando estudio %s (%d archivos)", study_id_str, len(dicom_object_keys))

    processing_task_id = status_repo.start_processing(study_id)
    try:
        # TemporaryDirectory limpia el disco solo al salir del bloque, incluso
        # si algo revienta adentro.
        with tempfile.TemporaryDirectory(prefix="axial-dicom-") as tmp_dir:
            status_repo.update_progress(processing_task_id, "downloading_dicom", 10)
            local_paths = []
            for key in dicom_object_keys:
                local_path = Path(tmp_dir) / Path(key).name
                storage.download_to(key, local_path)
                local_paths.append(local_path)

            status_repo.update_progress(processing_task_id, "processing", 40)
            use_case = ProcessDicomSeries(processor)
            volumes_by_level = use_case.execute(ProcessDicomSeriesInput(dicom_paths=local_paths))

            return _finish_processing(
                status_repo, storage, volumes, serializer,
                processing_task_id, study_id, volumes_by_level, tmp_dir,
            )
    except Exception as exc:
        logger.exception("fallo procesando estudio %s", study_id_str)
        status_repo.mark_failed(study_id, processing_task_id, str(exc))
        raise


def _process_raw_volume(
    status_repo: StudyStatusRepository,
    storage: ObjectStorage,
    volumes: VolumeRepository,
    serializer: VolumeSerializer,
    study_id_str: str,
    raw_object_key: str,
    dims: list[int],
    dtype: str,
    spacing: list[float],
    value_range: tuple[float, float] | None = None,
) -> dict:
    """Camino de entrada alternativo a _process_study: un volumen .raw (sin
    cabecera, sin metadata) en vez de una serie DICOM -- el cliente ya
    declaro dims/dtype/spacing de antemano (ConfirmRawVolumeUpload en el
    lado API los valida) porque el archivo no los trae. Sin normalizacion de
    Hounsfield (esos valores no son HU real por defecto, ver
    domain/minmax.py) -- salvo que el cliente declare `value_range`, en cuyo
    caso se usa esa ventana en vez de min-max automatico."""
    study_id = UUID(study_id_str)
    logger.info("procesando volumen raw %s (dims=%s, dtype=%s)", study_id_str, dims, dtype)

    processing_task_id = status_repo.start_processing(study_id)
    try:
        with tempfile.TemporaryDirectory(prefix="axial-raw-") as tmp_dir:
            status_repo.update_progress(processing_task_id, "downloading_dicom", 10)
            local_path = Path(tmp_dir) / Path(raw_object_key).name
            storage.download_to(raw_object_key, local_path)

            status_repo.update_progress(processing_task_id, "processing", 40)
            # Re-validado aca (no solo del lado API, que ya lo valido antes de
            # someterlo al pool) -- el procesamiento no confia ciegamente en
            # el mensaje recibido, sigue el mismo criterio de "verificar, no
            # asumir" que el resto del sistema.
            if dtype not in RAW_DTYPES:
                raise ValueError(f"dtype no soportado: {dtype!r} (validos: {sorted(RAW_DTYPES)})")
            numpy_dtype = RAW_DTYPES[dtype]
            array: np.ndarray = np.fromfile(local_path, dtype=numpy_dtype)
            expected_voxels = dims[0] * dims[1] * dims[2]
            if array.size != expected_voxels:
                raise ValueError(
                    f"el archivo tiene {array.size} valores de tipo {dtype}, "
                    f"pero dims={dims} espera {expected_voxels}"
                )
            raw_volume = Volume(
                pixel_array=array.reshape(dims).astype(np.float32),
                spacing=(float(spacing[0]), float(spacing[1]), float(spacing[2])),
            )
            normalized = (
                normalize_range(raw_volume, value_range[0], value_range[1])
                if value_range is not None
                else normalize_minmax(raw_volume)
            )

            processor = SimpleItkVolumeProcessor()
            volumes_by_level = {
                level: processor.resample_to_isotropic(normalized, spacing_mm)
                for level, spacing_mm in DEFAULT_DETAIL_LEVELS.items()
            }

            return _finish_processing(
                status_repo, storage, volumes, serializer,
                processing_task_id, study_id, volumes_by_level, tmp_dir,
            )
    except Exception as exc:
        logger.exception("fallo procesando volumen raw %s", study_id_str)
        status_repo.mark_failed(study_id, processing_task_id, str(exc))
        raise


def _build_adapters() -> tuple[
    PostgresStudyStatusRepository, PostgresVolumeRepository, ObjectStorage
]:
    """Cada llamada corre en un proceso hijo del `ProcessPoolExecutor` (ver
    infrastructure/queue/in_process_task_queue.py) -- no hereda conexiones
    del proceso padre (psycopg/minio no son fork-safe de forma confiable, y
    en Windows/spawn ni siquiera aplicaria), asi que arma sus propios
    adaptadores por llamada, igual que hacia cada tarea de Celery antes.

    `settings.storage_backend` elige el mismo adaptador que
    interfaces/api/deps.py:_build_object_storage() -- ambos lados tienen que
    coincidir (si la API sube con "local" pero processing intenta leer con
    "minio", no va a encontrar nada), lo garantiza compartir la misma
    `settings`."""
    status_repo = PostgresStudyStatusRepository(settings.database_url_sync)
    volume_repo = PostgresVolumeRepository(settings.database_url_sync)
    storage: ObjectStorage
    if settings.storage_backend == "minio":
        storage = MinioObjectStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
    else:
        storage = LocalFilesystemObjectStorage(settings.local_storage_dir)
    return status_repo, volume_repo, storage


def run_dicom_processing(study_id: str, dicom_object_keys: list[str]) -> dict:
    """Funcion de entrada sometida al `ProcessPoolExecutor` para el camino
    DICOM -- debe ser top-level (picklable) y recibir solo argumentos
    picklables (str/list), nunca un objeto vivo (sesion de DB, conexion) del
    proceso padre."""
    status_repo, volume_repo, storage = _build_adapters()
    processor = SimpleItkVolumeProcessor()
    serializer = SimpleItkVolumeSerializer()
    return _process_study(
        status_repo, processor, storage, volume_repo, serializer, study_id, dicom_object_keys
    )


def run_raw_volume_processing(
    study_id: str,
    raw_object_key: str,
    dims: list[int],
    dtype: str,
    spacing: list[float],
    value_range: list[float] | None = None,
) -> dict:
    """Idem `run_dicom_processing` para el camino .raw."""
    status_repo, volume_repo, storage = _build_adapters()
    serializer = SimpleItkVolumeSerializer()
    return _process_raw_volume(
        status_repo, storage, volume_repo, serializer, study_id, raw_object_key, dims, dtype,
        spacing, value_range=(value_range[0], value_range[1]) if value_range is not None else None,
    )
