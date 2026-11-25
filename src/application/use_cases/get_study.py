from dataclasses import dataclass
from uuid import UUID

from application.errors import StudyNotFoundError
from application.ports.processing_task_repository import ProcessingTaskRepository
from application.ports.study_repository import StudyRepository
from domain.entities import ProcessingTask, Study


@dataclass(frozen=True, slots=True)
class GetStudyInput:
    study_id: UUID


class GetStudy:
    """Cualquier usuario autenticado puede consultar cualquier estudio --
    Axial es una biblioteca compartida (datasets abiertos/sinteticos, no
    datos reales de pacientes de terceros; seccion 9/21 del documento de
    arquitectura), no hay nada que restringir por dueno. `created_by` se
    sigue guardando en el estudio para atribucion, solo no se usa para
    autorizar la lectura."""

    def __init__(
        self, studies: StudyRepository, processing_tasks: ProcessingTaskRepository
    ) -> None:
        self._studies = studies
        self._processing_tasks = processing_tasks

    async def execute(self, data: GetStudyInput) -> tuple[Study, ProcessingTask | None]:
        study = await self._studies.get_by_id(data.study_id)
        if study is None:
            raise StudyNotFoundError(data.study_id)

        # None si el estudio nunca fue encolado todavia (recien creado, sin
        # confirmar subida) -- no es un error, es un estado valido (pending).
        processing_task = await self._processing_tasks.get_latest_by_study_id(data.study_id)
        return study, processing_task
