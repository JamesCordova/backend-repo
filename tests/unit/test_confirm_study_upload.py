import io
from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import (
    MissingUploadedFileError,
    StudyAccessDeniedError,
    StudyNotFoundError,
)
from application.use_cases.confirm_study_upload import (
    ConfirmStudyUpload,
    ConfirmStudyUploadInput,
)
from application.use_cases.upload_study_file import object_key_for
from domain.entities import Study, StudyStatus


async def _seed_study(study_repository, owner_id: UUID) -> Study:
    study = Study(
        id=UUID(int=7),
        name="Torax",
        status=StudyStatus.PENDING,
        created_by=owner_id,
        created_at=datetime.now(UTC),
    )
    await study_repository.save(study)
    return study


async def test_confirma_y_encola_cuando_todos_los_archivos_existen(
    study_repository, object_storage, task_queue
):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "a.dcm"), io.BytesIO(b"x"), 1)
    await object_storage.put(object_key_for(study.id, "b.dcm"), io.BytesIO(b"x"), 1)
    use_case = ConfirmStudyUpload(study_repository, object_storage, task_queue)

    await use_case.execute(
        ConfirmStudyUploadInput(
            study_id=study.id, filenames=["a.dcm", "b.dcm"], requesting_user_id=owner_id
        )
    )

    assert task_queue.enqueued == [
        (
            study.id,
            [object_key_for(study.id, "a.dcm"), object_key_for(study.id, "b.dcm")],
        )
    ]


async def test_rechaza_si_falta_un_archivo_y_no_encola(
    study_repository, object_storage, task_queue
):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "a.dcm"), io.BytesIO(b"x"), 1)
    # "b.dcm" nunca se subio
    use_case = ConfirmStudyUpload(study_repository, object_storage, task_queue)

    with pytest.raises(MissingUploadedFileError):
        await use_case.execute(
            ConfirmStudyUploadInput(
                study_id=study.id, filenames=["a.dcm", "b.dcm"], requesting_user_id=owner_id
            )
        )

    assert task_queue.enqueued == []


async def test_rechaza_si_no_es_el_dueno(study_repository, object_storage, task_queue):
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    study = await _seed_study(study_repository, owner_id)
    use_case = ConfirmStudyUpload(study_repository, object_storage, task_queue)

    with pytest.raises(StudyAccessDeniedError):
        await use_case.execute(
            ConfirmStudyUploadInput(
                study_id=study.id, filenames=["a.dcm"], requesting_user_id=other_id
            )
        )


async def test_rechaza_estudio_inexistente(study_repository, object_storage, task_queue):
    use_case = ConfirmStudyUpload(study_repository, object_storage, task_queue)

    with pytest.raises(StudyNotFoundError):
        await use_case.execute(
            ConfirmStudyUploadInput(
                study_id=UUID(int=404), filenames=["a.dcm"], requesting_user_id=UUID(int=1)
            )
        )
