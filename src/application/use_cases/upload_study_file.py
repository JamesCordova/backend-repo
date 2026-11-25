from dataclasses import dataclass
from typing import IO
from uuid import UUID

from application.errors import StudyAccessDeniedError, StudyNotFoundError
from application.ports.object_storage import ObjectStorage
from application.ports.study_repository import StudyRepository


def object_key_for(study_id: UUID, filename: str) -> str:
    """Unica funcion que arma la ruta dentro del bucket -- todo lo demas
    (UploadStudyFile, ConfirmStudyUpload) la usa, para no duplicar el formato."""
    return f"studies/{study_id}/{filename}"


@dataclass(frozen=True, slots=True)
class UploadStudyFileInput:
    study_id: UUID
    filename: str
    requesting_user_id: UUID


class UploadStudyFile:
    """Un slice DICOM = un archivo = una llamada a este caso de uso (seccion
    6.2). No hace chunking de un archivo grande -- el formato ya viene
    fragmentado en slices, eso es el chunking."""

    def __init__(self, studies: StudyRepository, storage: ObjectStorage) -> None:
        self._studies = studies
        self._storage = storage

    async def execute(self, data: UploadStudyFileInput, stream: IO[bytes], length: int) -> None:
        study = await self._studies.get_by_id(data.study_id)
        if study is None:
            raise StudyNotFoundError(data.study_id)
        if study.created_by != data.requesting_user_id:
            raise StudyAccessDeniedError(data.study_id)

        key = object_key_for(data.study_id, data.filename)
        await self._storage.put(key, stream, length)
