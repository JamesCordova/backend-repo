from uuid import UUID

from application.use_cases.upload_study import UploadStudy, UploadStudyInput
from domain.entities import StudyStatus


async def test_crea_el_estudio_en_estado_pending(study_repository, id_generator):
    use_case = UploadStudy(study_repository, id_generator)
    creator_id = UUID(int=42)

    study = await use_case.execute(
        UploadStudyInput(name="Torax de prueba", created_by=creator_id)
    )

    assert study.status == StudyStatus.PENDING
    assert study.created_by == creator_id
    stored = await study_repository.get_by_id(study.id)
    assert stored == study
