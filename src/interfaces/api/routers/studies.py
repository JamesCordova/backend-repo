from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from application.errors import (
    InvalidRangeError,
    MissingUploadedFileError,
    StudyAccessDeniedError,
    StudyNotFoundError,
    VolumeNotReadyError,
)
from application.use_cases.confirm_raw_volume_upload import (
    ConfirmRawVolumeUpload,
    ConfirmRawVolumeUploadInput,
)
from application.use_cases.confirm_study_upload import ConfirmStudyUpload, ConfirmStudyUploadInput
from application.use_cases.get_study import GetStudy, GetStudyInput
from application.use_cases.get_study_volume import GetStudyVolume, GetStudyVolumeInput
from application.use_cases.list_studies import ListStudies
from application.use_cases.upload_study import UploadStudy, UploadStudyInput
from application.use_cases.upload_study_file import UploadStudyFile, UploadStudyFileInput
from domain.entities import ProcessingTask, Study, User
from interfaces.api.deps import (
    get_confirm_raw_volume_upload_use_case,
    get_confirm_study_upload_use_case,
    get_current_user,
    get_get_study_use_case,
    get_get_study_volume_use_case,
    get_list_studies_use_case,
    get_upload_study_file_use_case,
    get_upload_study_use_case,
)
from interfaces.api.schemas.study import (
    ConfirmRawUploadRequest,
    ConfirmUploadRequest,
    StudyResponse,
    UploadStudyRequest,
)

router = APIRouter(prefix="/estudios", tags=["studies"])


def _to_response(study: Study, processing_task: ProcessingTask | None = None) -> StudyResponse:
    return StudyResponse(
        id=study.id,
        name=study.name,
        status=study.status,
        created_by=study.created_by,
        created_at=study.created_at,
        stage=processing_task.stage if processing_task else None,
        progress_percent=processing_task.progress_percent if processing_task else None,
        error_message=processing_task.error_message if processing_task else None,
    )


@router.post("", response_model=StudyResponse, status_code=status.HTTP_201_CREATED)
async def crear_estudio(
    body: UploadStudyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[UploadStudy, Depends(get_upload_study_use_case)],
) -> StudyResponse:
    study = await use_case.execute(UploadStudyInput(name=body.name, created_by=current_user.id))
    return _to_response(study)


@router.get("", response_model=list[StudyResponse])
async def listar_estudios(
    # Solo exige estar autenticado (401 si no) -- no se usa la identidad para
    # filtrar, ver ListStudies/StudyRepository.list_all.
    _current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[ListStudies, Depends(get_list_studies_use_case)],
) -> list[StudyResponse]:
    studies = await use_case.execute()
    return [_to_response(study) for study in studies]


@router.put("/{study_id}/archivos/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def subir_archivo(
    study_id: UUID,
    filename: str,
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[UploadStudyFile, Depends(get_upload_study_file_use_case)],
) -> None:
    try:
        await use_case.execute(
            UploadStudyFileInput(
                study_id=study_id, filename=filename, requesting_user_id=current_user.id
            ),
            stream=file.file,
            length=file.size or 0,
        )
    except StudyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado") from exc
    except StudyAccessDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a este estudio") from exc


@router.post("/{study_id}/confirmar-subida", response_model=StudyResponse)
async def confirmar_subida(
    study_id: UUID,
    body: ConfirmUploadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[ConfirmStudyUpload, Depends(get_confirm_study_upload_use_case)],
) -> StudyResponse:
    try:
        study = await use_case.execute(
            ConfirmStudyUploadInput(
                study_id=study_id,
                filenames=body.filenames,
                requesting_user_id=current_user.id,
            )
        )
    except StudyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado") from exc
    except StudyAccessDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a este estudio") from exc
    except MissingUploadedFileError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Falta subir: {exc}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _to_response(study)


@router.post("/{study_id}/confirmar-subida-raw", response_model=StudyResponse)
async def confirmar_subida_raw(
    study_id: UUID,
    body: ConfirmRawUploadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[ConfirmRawVolumeUpload, Depends(get_confirm_raw_volume_upload_use_case)],
) -> StudyResponse:
    """Camino alternativo a /confirmar-subida para un volumen .raw (sin
    cabecera) -- el cliente ya subio el archivo via PUT
    /estudios/{id}/archivos/{filename} (mismo endpoint que un slice DICOM,
    a la API no le importa el contenido), y aca declara dims/dtype/spacing
    porque el archivo no los trae."""
    try:
        study = await use_case.execute(
            ConfirmRawVolumeUploadInput(
                study_id=study_id,
                filename=body.filename,
                dims=body.dims,
                dtype=body.dtype,
                spacing=body.spacing,
                requesting_user_id=current_user.id,
                value_range=body.value_range,
            )
        )
    except StudyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado") from exc
    except StudyAccessDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a este estudio") from exc
    except MissingUploadedFileError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Falta subir: {exc}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _to_response(study)


@router.get("/{study_id}", response_model=StudyResponse)
async def obtener_estudio(
    study_id: UUID,
    # Solo exige estar autenticado -- ver GetStudy, biblioteca compartida.
    _current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[GetStudy, Depends(get_get_study_use_case)],
) -> StudyResponse:
    try:
        study, processing_task = await use_case.execute(GetStudyInput(study_id=study_id))
    except StudyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado") from exc
    return _to_response(study, processing_task)


@router.get("/{study_id}/volumen")
async def descargar_volumen(
    study_id: UUID,
    # Solo exige estar autenticado -- ver GetStudyVolume, biblioteca compartida.
    _current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[GetStudyVolume, Depends(get_get_study_volume_use_case)],
    detail_level: Annotated[str, Query()] = "full",
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    try:
        stream, volume, byte_range = await use_case.execute(
            GetStudyVolumeInput(
                study_id=study_id,
                detail_level=detail_level,
                range_header=range_header,
            )
        )
    except StudyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado") from exc
    except VolumeNotReadyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El volumen todavia no esta listo"
        ) from exc
    except InvalidRangeError as exc:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{exc.total_size}"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    headers = {"Accept-Ranges": "bytes"}
    if byte_range is None:
        response_status = status.HTTP_200_OK
        headers["Content-Length"] = str(volume.size_bytes)
    else:
        start, end = byte_range
        response_status = status.HTTP_206_PARTIAL_CONTENT
        headers["Content-Length"] = str(end - start + 1)
        headers["Content-Range"] = f"bytes {start}-{end}/{volume.size_bytes}"
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers=headers,
        status_code=response_status,
    )
