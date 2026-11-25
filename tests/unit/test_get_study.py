from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import StudyNotFoundError
from application.use_cases.get_study import GetStudy, GetStudyInput
from domain.entities import ProcessingTask, Study, StudyStatus


def _study(created_by: UUID) -> Study:
    return Study(
        id=UUID(int=99),
        name="Torax",
        status=StudyStatus.PENDING,
        created_by=created_by,
        created_at=datetime.now(UTC),
    )


async def test_el_dueno_puede_consultar_su_estudio(study_repository, processing_task_repository):
    owner_id = UUID(int=1)
    study = _study(created_by=owner_id)
    await study_repository.save(study)
    use_case = GetStudy(study_repository, processing_task_repository)

    result_study, result_task = await use_case.execute(GetStudyInput(study_id=study.id))

    assert result_study == study
    assert result_task is None  # nunca se encolo -- sin processing_task todavia


async def test_devuelve_el_progreso_cuando_existe(study_repository, processing_task_repository):
    owner_id = UUID(int=1)
    study = _study(created_by=owner_id)
    await study_repository.save(study)
    task = ProcessingTask(
        id=UUID(int=500),
        study_id=study.id,
        attempt_number=1,
        status="running",
        stage="normalizing",
        progress_percent=50,
        error_message=None,
        started_at=datetime.now(UTC),
        finished_at=None,
    )
    processing_task_repository.seed(task)
    use_case = GetStudy(study_repository, processing_task_repository)

    _, result_task = await use_case.execute(GetStudyInput(study_id=study.id))

    assert result_task == task


async def test_cualquier_usuario_puede_consultar_un_estudio_ajeno(
    study_repository, processing_task_repository
):
    # Axial es una biblioteca compartida (datasets abiertos/sinteticos) --
    # no hay restriccion por dueno para consultar un estudio.
    owner_id = UUID(int=1)
    study = _study(created_by=owner_id)
    await study_repository.save(study)
    use_case = GetStudy(study_repository, processing_task_repository)

    result_study, _ = await use_case.execute(GetStudyInput(study_id=study.id))

    assert result_study == study


async def test_estudio_inexistente_lanza_not_found(study_repository, processing_task_repository):
    use_case = GetStudy(study_repository, processing_task_repository)

    with pytest.raises(StudyNotFoundError):
        await use_case.execute(GetStudyInput(study_id=UUID(int=404)))
