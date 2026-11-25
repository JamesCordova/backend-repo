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


@dataclass(frozen=True, slots=True)
class ConfirmStudyUploadInput:
    study_id: UUID
    filenames: list[str]
    requesting_user_id: UUID


class ConfirmStudyUpload:
    """Verifica contra el storage real que los archivos declarados existen
    -- nunca confia en 'ya subi todo' del cliente (seccion 6.2) -- y recien
    ahi encola el procesamiento."""

    def __init__(
        self, studies: StudyRepository, storage: ObjectStorage, tasks: TaskQueue
    ) -> None:
        self._studies = studies
        self._storage = storage
        self._tasks = tasks

    async def execute(self, data: ConfirmStudyUploadInput) -> Study:
        study = await self._studies.get_by_id(data.study_id)
        if study is None:
            raise StudyNotFoundError(data.study_id)
        if study.created_by != data.requesting_user_id:
            raise StudyAccessDeniedError(data.study_id)
        if not data.filenames:
            raise ValueError("filenames no puede estar vacio")

        keys = [object_key_for(data.study_id, name) for name in data.filenames]
        for key in keys:
            if not await self._storage.exists(key):
                raise MissingUploadedFileError(key)

        self._tasks.enqueue_processing(study.id, keys)
        return study
