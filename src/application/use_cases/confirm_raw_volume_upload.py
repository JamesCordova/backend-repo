from dataclasses import dataclass
from uuid import UUID

from application.errors import (
    MissingUploadedFileError,
    StudyAccessDeniedError,
    StudyNotFoundError,
)
from application.ports.object_storage import ObjectStorage
from application.ports.study_repository import StudyRepository
from application.ports.task_queue import TaskQueue
from application.use_cases.upload_study_file import object_key_for
from domain.entities import Study

# Mismo allowlist que RAW_DTYPES en worker-repo (interfaces/tasks/celery_app.py)
# -- duplicado deliberado (seccion 1.3 del documento de arquitectura: sin
# codigo compartido por import entre repos), pero validar tambien aca deja
# fallar rapido con un 422 real en vez de esperar a que el worker lo rechace
# despues de haber encolado.
_ALLOWED_DTYPES = {"uint8", "int16", "uint16", "int32", "float32", "float64"}


@dataclass(frozen=True, slots=True)
class ConfirmRawVolumeUploadInput:
    study_id: UUID
    filename: str
    dims: tuple[int, int, int]
    dtype: str
    spacing: tuple[float, float, float]
    requesting_user_id: UUID
    # Opcional -- ver TaskQueue.enqueue_raw_processing. None (default) deja
    # que el worker use min-max automatico en vez de una ventana declarada.
    value_range: tuple[float, float] | None = None


class ConfirmRawVolumeUpload:
    """Como ConfirmStudyUpload pero para un volumen .raw (sin cabecera): el
    archivo no trae dims/dtype/spacing, asi que el cliente los declara aca --
    ninguna libreria puede inferir esa informacion si no esta en el archivo
    (a diferencia de un DICOM real, que la trae en sus propios tags)."""

    def __init__(
        self, studies: StudyRepository, storage: ObjectStorage, tasks: TaskQueue
    ) -> None:
        self._studies = studies
        self._storage = storage
        self._tasks = tasks

    async def execute(self, data: ConfirmRawVolumeUploadInput) -> Study:
        study = await self._studies.get_by_id(data.study_id)
        if study is None:
            raise StudyNotFoundError(data.study_id)
        if study.created_by != data.requesting_user_id:
            raise StudyAccessDeniedError(data.study_id)

        if data.dtype not in _ALLOWED_DTYPES:
            raise ValueError(
                f"dtype no soportado: {data.dtype!r} (validos: {sorted(_ALLOWED_DTYPES)})"
            )
        if any(d <= 0 for d in data.dims):
            raise ValueError(f"dims debe ser positivo en las 3 dimensiones, llego {data.dims}")
        if any(s <= 0 for s in data.spacing):
            raise ValueError(
                f"spacing debe ser positivo en las 3 dimensiones, llego {data.spacing}"
            )
        if data.value_range is not None and data.value_range[0] >= data.value_range[1]:
            raise ValueError(
                f"value_range[0] debe ser menor que value_range[1], llego {data.value_range}"
            )

        key = object_key_for(data.study_id, data.filename)
        if not await self._storage.exists(key):
            raise MissingUploadedFileError(key)

        self._tasks.enqueue_raw_processing(
            study.id, key, list(data.dims), data.dtype, list(data.spacing), data.value_range
        )
        return study
