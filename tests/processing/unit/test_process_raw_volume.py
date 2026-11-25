"""Prueba _process_raw_volume (el camino alternativo a _process_study para
volumenes .raw sin cabecera) con fakes -- ni Postgres, MinIO ni SimpleITK
real para los fakes de estado/storage; SimpleItkVolumeProcessor.resample_to_isotropic
SI es real aca (no hay forma de fakear el resampling sin perder cobertura de
que el LOD realmente funciona con datos raw)."""

import shutil
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from processing.application.ports.study_status_repository import StudyStatusRepository
from processing.application.ports.volume_repository import VolumeRepository
from processing.domain.entities import Volume
from processing.jobs import _process_raw_volume


class FakeStudyStatusRepository(StudyStatusRepository):
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.progress_calls: list[tuple] = []
        self._next_task_id = UUID(int=1)

    def start_processing(self, study_id: UUID) -> UUID:
        self.calls.append(("start_processing", study_id))
        return self._next_task_id

    def update_progress(self, processing_task_id: UUID, stage: str, progress_percent: int) -> None:
        self.progress_calls.append((processing_task_id, stage, progress_percent))

    def mark_succeeded(self, study_id: UUID, processing_task_id: UUID) -> None:
        self.calls.append(("mark_succeeded", study_id, processing_task_id))

    def mark_failed(self, study_id: UUID, processing_task_id: UUID, error_message: str) -> None:
        self.calls.append(("mark_failed", study_id, processing_task_id, error_message))


class FakeVolumeRepository(VolumeRepository):
    def __init__(self) -> None:
        self.created: list[tuple] = []

    def create(
        self, study_id, processing_task_id, detail_level, format, storage_path, size_bytes
    ) -> None:
        self.created.append(
            (study_id, processing_task_id, detail_level, format, storage_path, size_bytes)
        )


class FakeObjectStorage:
    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path
        self.uploaded: dict[str, int] = {}

    def download_to(self, key: str, local_path: Path) -> None:
        shutil.copy(self._source_path, local_path)

    def upload_from(self, local_path: Path, key: str) -> None:
        self.uploaded[key] = local_path.stat().st_size


class FakeVolumeSerializer:
    def save(self, volume: Volume, path: Path) -> None:
        path.write_bytes(b"fake-nifti-bytes")


class CapturingVolumeSerializer:
    """Ademas de fakear la escritura, guarda el ultimo Volume que le pidieron
    guardar por nivel de detalle -- para poder afirmar que la normalizacion
    aplicada (value_range vs. min-max automatico) produjo los valores
    esperados, no solo que el pipeline no exploto."""

    def __init__(self) -> None:
        self.saved: dict[str, Volume] = {}

    def save(self, volume: Volume, path: Path) -> None:
        detail_level = path.name.split(".")[0]  # "preview.nii.gz" -> "preview"
        self.saved[detail_level] = volume
        path.write_bytes(b"fake-nifti-bytes")


def _write_raw_file(tmp_path: Path, dims: tuple[int, int, int]) -> Path:
    array = np.arange(dims[0] * dims[1] * dims[2], dtype=np.uint8).reshape(dims)
    path = tmp_path / "volumen.raw"
    array.tofile(path)
    return path


def test_procesa_un_raw_exitosamente_sube_el_resultado_y_marca_succeeded(tmp_path: Path):
    dims = (4, 8, 8)
    raw_path = _write_raw_file(tmp_path, dims)
    status_repo = FakeStudyStatusRepository()
    volume_repo = FakeVolumeRepository()
    storage = FakeObjectStorage(raw_path)
    study_id = UUID(int=7)

    payload = _process_raw_volume(
        status_repo, storage, volume_repo, FakeVolumeSerializer(),
        str(study_id), "raws/fake/volumen.raw", list(dims), "uint8", [1.0, 1.0, 1.0],
    )

    assert payload["study_id"] == str(study_id)
    assert set(payload["detail_levels"]) == {"preview", "full"}
    assert status_repo.calls == [
        ("start_processing", study_id),
        ("mark_succeeded", study_id, UUID(int=1)),
    ]
    assert len(volume_repo.created) == 2
    created_by_level = {row[2]: row for row in volume_repo.created}
    assert set(created_by_level.keys()) == {"preview", "full"}
    for detail_level, row in created_by_level.items():
        result_key = f"results/{study_id}/{detail_level}.nii.gz"
        assert result_key in storage.uploaded
        assert row == (
            study_id, UUID(int=1), detail_level, "nii.gz", result_key, storage.uploaded[result_key]
        )


def test_dtype_no_soportado_falla_con_mensaje_claro(tmp_path: Path):
    dims = (2, 2, 2)
    raw_path = _write_raw_file(tmp_path, dims)
    status_repo = FakeStudyStatusRepository()
    volume_repo = FakeVolumeRepository()
    storage = FakeObjectStorage(raw_path)
    study_id = UUID(int=7)

    with pytest.raises(ValueError, match="dtype no soportado"):
        _process_raw_volume(
            status_repo, storage, volume_repo, FakeVolumeSerializer(),
            str(study_id), "raws/fake/volumen.raw", list(dims), "complex128", [1.0, 1.0, 1.0],
        )

    assert status_repo.calls[-1][0] == "mark_failed"


def test_dims_que_no_coinciden_con_el_tamano_real_falla(tmp_path: Path):
    # el archivo real tiene 2x2x2=8 valores, pero se declaran dims de 10x10x10
    raw_path = _write_raw_file(tmp_path, (2, 2, 2))
    status_repo = FakeStudyStatusRepository()
    volume_repo = FakeVolumeRepository()
    storage = FakeObjectStorage(raw_path)
    study_id = UUID(int=7)

    with pytest.raises(ValueError, match="espera"):
        _process_raw_volume(
            status_repo, storage, volume_repo, FakeVolumeSerializer(),
            str(study_id), "raws/fake/volumen.raw", [10, 10, 10], "uint8", [1.0, 1.0, 1.0],
        )

    assert status_repo.calls[-1][0] == "mark_failed"
    assert volume_repo.created == []
    assert storage.uploaded == {}


def test_con_value_range_declarado_usa_esa_ventana_en_vez_de_min_max(tmp_path: Path):
    # valores conocidos: aire=-1000, tejido=0, hueso=1000 -- si tratamos esto
    # como HU real con ventana [-1000, 1000], deberian mapear a 0.0/0.5/1.0
    dims = (1, 1, 3)
    array = np.array([-1000.0, 0.0, 1000.0], dtype=np.float32)
    raw_path = tmp_path / "volumen.raw"
    array.tofile(raw_path)
    status_repo = FakeStudyStatusRepository()
    volume_repo = FakeVolumeRepository()
    storage = FakeObjectStorage(raw_path)
    serializer = CapturingVolumeSerializer()
    study_id = UUID(int=7)

    _process_raw_volume(
        status_repo, storage, volume_repo, serializer,
        str(study_id), "raws/fake/volumen.raw", list(dims), "float32", [1.0, 1.0, 1.0],
        value_range=(-1000.0, 1000.0),
    )

    # el nivel "full" no resamplea el shape (ya es isotropico declarado) --
    # sus valores deben quedar en [0, 0.5, 1] exacto, no aplastados por un
    # min-max automatico que hubiera dado lo mismo aca (coincide porque el
    # rango declarado es igual al observado) -- ver el siguiente test para
    # el caso donde SI difieren.
    full_volume = serializer.saved["full"]
    np.testing.assert_allclose(sorted(full_volume.pixel_array.flatten()), [0.0, 0.5, 1.0])


def test_value_range_declarado_difiere_de_min_max_automatico(tmp_path: Path):
    # el archivo tiene valores 0-255 (todo el rango real observado), pero si
    # el cliente declara que en realidad es HU con ventana [-1000, 1000],
    # el resultado NO debe ser igual al min-max automatico (que daria 0..1
    # sobre 0-255) -- debe reflejar la ventana declarada, aplastando estos
    # valores chicos cerca de 0.5 (justo el efecto indeseado si NO se declara
    # la ventana y se usa min-max en datos que si eran HU real).
    dims = (1, 1, 2)
    array = np.array([0.0, 255.0], dtype=np.float32)
    raw_path = tmp_path / "volumen.raw"
    array.tofile(raw_path)
    status_repo = FakeStudyStatusRepository()
    volume_repo = FakeVolumeRepository()
    storage = FakeObjectStorage(raw_path)
    serializer = CapturingVolumeSerializer()
    study_id = UUID(int=7)

    _process_raw_volume(
        status_repo, storage, volume_repo, serializer,
        str(study_id), "raws/fake/volumen.raw", list(dims), "float32", [1.0, 1.0, 1.0],
        value_range=(-1000.0, 1000.0),
    )

    full_volume = serializer.saved["full"]
    # (0 - (-1000))/2000 = 0.5 ; (255 - (-1000))/2000 = 0.6275
    np.testing.assert_allclose(sorted(full_volume.pixel_array.flatten()), [0.5, 0.6275], atol=1e-4)
