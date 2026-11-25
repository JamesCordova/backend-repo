import io
from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import (
    MissingUploadedFileError,
    StudyAccessDeniedError,
    StudyNotFoundError,
)
from application.use_cases.confirm_raw_volume_upload import (
    ConfirmRawVolumeUpload,
    ConfirmRawVolumeUploadInput,
)
from application.use_cases.upload_study_file import object_key_for
from domain.entities import Study, StudyStatus


async def _seed_study(study_repository, owner_id: UUID) -> Study:
    study = Study(
        id=UUID(int=7), name="Volumen raw", status=StudyStatus.PENDING, created_by=owner_id,
        created_at=datetime.now(UTC),
    )
    await study_repository.save(study)
    return study


def _valid_input(study_id: UUID, owner_id: UUID) -> ConfirmRawVolumeUploadInput:
    return ConfirmRawVolumeUploadInput(
        study_id=study_id,
        filename="volumen.raw",
        dims=(256, 256, 256),
        dtype="uint8",
        spacing=(1.0, 1.0, 1.0),
        requesting_user_id=owner_id,
    )


async def test_confirma_y_encola_cuando_el_archivo_existe(
    study_repository, object_storage, task_queue
):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "volumen.raw"), io.BytesIO(b"x"), 1)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)

    await use_case.execute(_valid_input(study.id, owner_id))

    assert task_queue.enqueued_raw == [
        (
            study.id, object_key_for(study.id, "volumen.raw"), [256, 256, 256], "uint8",
            [1.0, 1.0, 1.0], None,
        )
    ]


async def test_rechaza_si_el_archivo_no_se_subio(study_repository, object_storage, task_queue):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)

    with pytest.raises(MissingUploadedFileError):
        await use_case.execute(_valid_input(study.id, owner_id))

    assert task_queue.enqueued_raw == []


async def test_rechaza_si_no_es_el_dueno(study_repository, object_storage, task_queue):
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    study = await _seed_study(study_repository, owner_id)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)

    with pytest.raises(StudyAccessDeniedError):
        await use_case.execute(_valid_input(study.id, other_id))


async def test_rechaza_estudio_inexistente(study_repository, object_storage, task_queue):
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)

    with pytest.raises(StudyNotFoundError):
        await use_case.execute(_valid_input(UUID(int=404), UUID(int=1)))


async def test_rechaza_dtype_no_soportado(study_repository, object_storage, task_queue):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "volumen.raw"), io.BytesIO(b"x"), 1)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)
    bad_input = ConfirmRawVolumeUploadInput(
        study_id=study.id, filename="volumen.raw", dims=(2, 2, 2), dtype="complex128",
        spacing=(1.0, 1.0, 1.0), requesting_user_id=owner_id,
    )

    with pytest.raises(ValueError, match="dtype no soportado"):
        await use_case.execute(bad_input)

    assert task_queue.enqueued_raw == []


async def test_rechaza_dims_no_positivos(study_repository, object_storage, task_queue):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "volumen.raw"), io.BytesIO(b"x"), 1)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)
    bad_input = ConfirmRawVolumeUploadInput(
        study_id=study.id, filename="volumen.raw", dims=(0, 2, 2), dtype="uint8",
        spacing=(1.0, 1.0, 1.0), requesting_user_id=owner_id,
    )

    with pytest.raises(ValueError, match="dims"):
        await use_case.execute(bad_input)


async def test_rechaza_spacing_no_positivo(study_repository, object_storage, task_queue):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "volumen.raw"), io.BytesIO(b"x"), 1)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)
    bad_input = ConfirmRawVolumeUploadInput(
        study_id=study.id, filename="volumen.raw", dims=(2, 2, 2), dtype="uint8",
        spacing=(1.0, -1.0, 1.0), requesting_user_id=owner_id,
    )

    with pytest.raises(ValueError, match="spacing"):
        await use_case.execute(bad_input)


async def test_confirma_y_encola_con_value_range_declarado(
    study_repository, object_storage, task_queue
):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "volumen.raw"), io.BytesIO(b"x"), 1)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)
    input_with_range = ConfirmRawVolumeUploadInput(
        study_id=study.id, filename="volumen.raw", dims=(2, 2, 2), dtype="uint8",
        spacing=(1.0, 1.0, 1.0), requesting_user_id=owner_id, value_range=(-1000.0, 1000.0),
    )

    await use_case.execute(input_with_range)

    assert task_queue.enqueued_raw == [
        (
            study.id, object_key_for(study.id, "volumen.raw"), [2, 2, 2], "uint8",
            [1.0, 1.0, 1.0], (-1000.0, 1000.0),
        )
    ]


async def test_rechaza_value_range_invertido(study_repository, object_storage, task_queue):
    owner_id = UUID(int=1)
    study = await _seed_study(study_repository, owner_id)
    await object_storage.put(object_key_for(study.id, "volumen.raw"), io.BytesIO(b"x"), 1)
    use_case = ConfirmRawVolumeUpload(study_repository, object_storage, task_queue)
    bad_input = ConfirmRawVolumeUploadInput(
        study_id=study.id, filename="volumen.raw", dims=(2, 2, 2), dtype="uint8",
        spacing=(1.0, 1.0, 1.0), requesting_user_id=owner_id, value_range=(1000.0, -1000.0),
    )

    with pytest.raises(ValueError, match="value_range"):
        await use_case.execute(bad_input)

    assert task_queue.enqueued_raw == []
