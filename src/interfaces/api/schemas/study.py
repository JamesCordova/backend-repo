from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from domain.entities import StudyStatus


class UploadStudyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ConfirmUploadRequest(BaseModel):
    filenames: list[str] = Field(min_length=1)


class ConfirmRawUploadRequest(BaseModel):
    """Un .raw no trae dims/dtype/spacing en el archivo (a diferencia de un
    DICOM real) -- el cliente los declara aca. La validacion de negocio
    (dtype soportado, valores positivos) vive en ConfirmRawVolumeUpload, no
    aca (mismo criterio que el resto de los schemas de este archivo)."""

    filename: str = Field(min_length=1)
    dims: tuple[int, int, int]
    dtype: str
    spacing: tuple[float, float, float]
    # Opcional -- si el cliente sabe que sus valores son HU real (u otra
    # escala fisica conocida) declara la ventana a mostrar; si no la manda,
    # el worker usa min-max automatico sobre los propios datos (ver
    # domain/minmax.py en worker-repo).
    value_range: tuple[float, float] | None = None


class StudyResponse(BaseModel):
    id: UUID
    name: str
    status: StudyStatus
    created_by: UUID
    created_at: datetime
    # None si el estudio todavia no fue encolado (pending sin confirmar
    # subida) -- no es un error, closes el loop de polling de la seccion 16
    # del documento original con progreso real, no binario.
    stage: str | None = None
    progress_percent: int | None = None
    # Solo tiene sentido cuando status=failed -- el worker lo guarda en
    # processing_tasks.error_message pero antes nunca llegaba hasta aca, asi
    # que un cliente no tenia forma de saber POR QUE fallo, solo que fallo.
    error_message: str | None = None
