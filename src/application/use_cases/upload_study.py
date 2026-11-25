from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from application.ports.id_generator import IdGenerator
from application.ports.study_repository import StudyRepository
from domain.entities import Study, StudyStatus


@dataclass(frozen=True, slots=True)
class UploadStudyInput:
    name: str
    created_by: UUID


class UploadStudy:
    """Crea el registro del estudio -- no recibe archivos. Los slices se
    suben despues, uno por uno, via UploadStudyFile; el procesamiento se
    encola recien al confirmar la subida (ConfirmStudyUpload). Ver seccion 6.2
    del documento de clean architecture."""

    def __init__(self, studies: StudyRepository, ids: IdGenerator) -> None:
        self._studies = studies
        self._ids = ids

    async def execute(self, data: UploadStudyInput) -> Study:
        study = Study(
            id=self._ids.generate(),
            name=data.name.strip(),
            status=StudyStatus.PENDING,
            created_by=data.created_by,
            created_at=datetime.now(UTC),
        )
        await self._studies.save(study)
        return study
