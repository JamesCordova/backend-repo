import io
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import (
    InvalidRangeError,
    StudyNotFoundError,
    VolumeNotReadyError,
)
from application.use_cases.get_study_volume import GetStudyVolume, GetStudyVolumeInput
from domain.entities import Study, StudyStatus, Volume


def _study(study_id: UUID, owner_id: UUID, status: StudyStatus) -> Study:
    return Study(
        id=study_id, name="Torax", status=status, created_by=owner_id, created_at=datetime.now(UTC)
    )


def _volume(study_id: UUID, detail_level: str = "full") -> Volume:
    return Volume(
        id=UUID(int=500),
        study_id=study_id,
        processing_task_id=UUID(int=1),
        detail_level=detail_level,
        format="npz",
        storage_path=f"results/{study_id}/{detail_level}.npz",
        size_bytes=1234,
        created_at=datetime.now(UTC),
    )


async def test_devuelve_el_stream_cuando_esta_listo(
    study_repository, volume_repository, object_storage
):
    owner_id = UUID(int=1)
    study_id = UUID(int=7)
    study = _study(study_id, owner_id, StudyStatus.READY)
    await study_repository.save(study)
    volume = _volume(study_id)
    volume_repository.seed(volume)
    await object_storage.put(volume.storage_path, io.BytesIO(b"npz-fake"), 8)
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    stream, returned_volume, byte_range = await use_case.execute(
        GetStudyVolumeInput(study_id=study_id)
    )

    assert returned_volume == volume
    assert byte_range is None
    chunks = [chunk async for chunk in stream]
    assert b"".join(chunks) == b"npz-fake"


async def test_rechaza_si_el_estudio_no_esta_listo(
    study_repository, volume_repository, object_storage
):
    owner_id = UUID(int=1)
    study_id = UUID(int=7)
    await study_repository.save(_study(study_id, owner_id, StudyStatus.PROCESSING))
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    with pytest.raises(VolumeNotReadyError):
        await use_case.execute(GetStudyVolumeInput(study_id=study_id))


async def test_cualquier_usuario_puede_descargar_un_volumen_ajeno(
    study_repository, volume_repository, object_storage
):
    # Axial es una biblioteca compartida -- no hay restriccion por dueno.
    owner_id = UUID(int=1)
    study_id = UUID(int=7)
    study = _study(study_id, owner_id, StudyStatus.READY)
    await study_repository.save(study)
    volume = _volume(study_id)
    volume_repository.seed(volume)
    await object_storage.put(volume.storage_path, io.BytesIO(b"npz-fake"), 8)
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    stream, returned_volume, _ = await use_case.execute(GetStudyVolumeInput(study_id=study_id))

    assert returned_volume == volume
    assert b"".join([c async for c in stream]) == b"npz-fake"


async def test_rechaza_estudio_inexistente(study_repository, volume_repository, object_storage):
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    with pytest.raises(StudyNotFoundError):
        await use_case.execute(GetStudyVolumeInput(study_id=UUID(int=404)))


async def test_preview_y_full_son_independientes(study_repository, volume_repository, object_storage):
    """Cada nivel de detalle (LOD) tiene su propia key en storage y su propia
    fila en volumes -- pedir 'preview' no debe devolver el volumen 'full' ni
    viceversa."""
    owner_id = UUID(int=1)
    study_id = UUID(int=7)
    await study_repository.save(_study(study_id, owner_id, StudyStatus.READY))
    preview = _volume(study_id, detail_level="preview")
    full = _volume(study_id, detail_level="full")
    volume_repository.seed(preview)
    volume_repository.seed(full)
    await object_storage.put(preview.storage_path, io.BytesIO(b"preview-bytes"), 13)
    await object_storage.put(full.storage_path, io.BytesIO(b"full-bytes"), 10)
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    preview_stream, preview_returned, _ = await use_case.execute(
        GetStudyVolumeInput(study_id=study_id, detail_level="preview")
    )
    full_stream, full_returned, _ = await use_case.execute(
        GetStudyVolumeInput(study_id=study_id, detail_level="full")
    )

    assert preview_returned.storage_path != full_returned.storage_path
    assert b"".join([c async for c in preview_stream]) == b"preview-bytes"
    assert b"".join([c async for c in full_stream]) == b"full-bytes"


async def test_con_range_header_devuelve_solo_la_porcion_pedida(
    study_repository, volume_repository, object_storage
):
    owner_id = UUID(int=1)
    study_id = UUID(int=7)
    await study_repository.save(_study(study_id, owner_id, StudyStatus.READY))
    contenido = bytes(range(256)) * 5  # 1280 bytes
    volume = replace(_volume(study_id), size_bytes=len(contenido))
    volume_repository.seed(volume)
    await object_storage.put(volume.storage_path, io.BytesIO(contenido), len(contenido))
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    stream, returned_volume, byte_range = await use_case.execute(
        GetStudyVolumeInput(study_id=study_id, range_header="bytes=10-19")
    )

    assert byte_range == (10, 19)
    assert returned_volume == volume
    chunks = b"".join([c async for c in stream])
    assert chunks == contenido[10:20]


async def test_con_range_header_invalido_lanza_invalid_range_error(
    study_repository, volume_repository, object_storage
):
    owner_id = UUID(int=1)
    study_id = UUID(int=7)
    await study_repository.save(_study(study_id, owner_id, StudyStatus.READY))
    volume = _volume(study_id)
    volume_repository.seed(volume)
    await object_storage.put(volume.storage_path, io.BytesIO(b"x" * volume.size_bytes), volume.size_bytes)
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    with pytest.raises(InvalidRangeError):
        await use_case.execute(
            GetStudyVolumeInput(study_id=study_id, range_header="bytes=99999-100000")
        )


async def test_rechaza_detail_level_invalido(study_repository, volume_repository, object_storage):
    owner_id = UUID(int=1)
    study_id = UUID(int=7)
    await study_repository.save(_study(study_id, owner_id, StudyStatus.READY))
    use_case = GetStudyVolume(study_repository, volume_repository, object_storage)

    with pytest.raises(ValueError):
        await use_case.execute(GetStudyVolumeInput(study_id=study_id, detail_level="4k"))
