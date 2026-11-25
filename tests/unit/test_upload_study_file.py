import io
from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import StudyAccessDeniedError, StudyNotFoundError
from application.use_cases.upload_study_file import (
    UploadStudyFile,
    UploadStudyFileInput,
    object_key_for,
)
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


async def test_sube_el_archivo_con_la_key_esperada(study_repository, object_storage):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    use_case = UploadStudyFile(study_repository, object_storage)

    await use_case.execute(
        UploadStudyFileInput(
            study_id=study.id, filename="slice_000.dcm", requesting_user_id=owner_id
        ),
        stream=io.BytesIO(b"contenido-dicom"),
        length=len(b"contenido-dicom"),
    )

    key = object_key_for(study.id, "slice_000.dcm")
    assert await object_storage.exists(key)


async def test_rechaza_si_el_estudio_no_existe(study_repository, object_storage):
    use_case = UploadStudyFile(study_repository, object_storage)

    with pytest.raises(StudyNotFoundError):
        await use_case.execute(
            UploadStudyFileInput(
                study_id=UUID(int=999), filename="a.dcm", requesting_user_id=UUID(int=1)
            ),
            stream=io.BytesIO(b"x"),
            length=1,
        )


async def test_rechaza_si_no_es_el_dueno(study_repository, object_storage):
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    study = await _seed_study(study_repository, owner_id)
    use_case = UploadStudyFile(study_repository, object_storage)

    with pytest.raises(StudyAccessDeniedError):
        await use_case.execute(
            UploadStudyFileInput(
                study_id=study.id, filename="a.dcm", requesting_user_id=other_id
            ),
            stream=io.BytesIO(b"x"),
            length=1,
        )
