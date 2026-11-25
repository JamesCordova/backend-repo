"""Prueba la orquestacion real de la tarea (_process_study) con fakes -- ni
Postgres, MinIO ni SimpleITK real. La funcion completa sometida al
ProcessPoolExecutor (run_dicom_processing, con los adaptadores reales) se
prueba de punta a punta en tests/processing/integration/test_jobs_real_pipeline.py
(Postgres + MinIO reales via testcontainers, sin fakes)."""

import shutil
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from processing.application.ports.study_status_repository import StudyStatusRepository
from processing.application.ports.volume_repository import VolumeRepository
from processing.domain.entities import Volume
from processing.jobs import _process_study


class FakeVolumeProcessor:
    def load_series(self, dicom_paths: list) -> Volume:
        return Volume(pixel_array=np.array([[[-1000.0, 1000.0]]]), spacing=(2.0, 1.0, 1.0))

    def resample_to_isotropic(self, volume: Volume, target_spacing_mm: float) -> Volume:
        return Volume(pixel_array=volume.pixel_array, spacing=(target_spacing_mm,) * 3)


class FailingVolumeProcessor:
    def load_series(self, dicom_paths: list) -> Volume:
        raise RuntimeError("DICOM corrupto")

    def resample_to_isotropic(self, volume: Volume, target_spacing_mm: float) -> Volume:
        raise AssertionError("no deberia llegar aqui")


class FakeStudyStatusRepository(StudyStatusRepository):
    def __init__(self) -> None:
        self.calls: list[tuple] = []  # solo start/mark_succeeded/mark_failed
        self.progress_calls: list[tuple] = []  # solo update_progress, aparte
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
    """No habla con MinIO -- 'descarga' copiando desde donde ya esta el
    archivo de prueba en disco (la fixture synthetic_dicom_series), y
    'sube' el resultado a un dict en memoria."""

    def __init__(self, key_to_source: dict[str, Path]) -> None:
        self._key_to_source = key_to_source
        self.uploaded: dict[str, int] = {}  # key -> tamano en bytes al momento de subir

    def download_to(self, key: str, local_path: Path) -> None:
        shutil.copy(self._key_to_source[key], local_path)

    def upload_from(self, local_path: Path, key: str) -> None:
        # Leer el tamano ahora -- local_path vive en un TemporaryDirectory que
        # se borra al salir del "with" en _process_study, antes de que el
        # test pueda inspeccionarlo.
        self.uploaded[key] = local_path.stat().st_size


class FakeVolumeSerializer:
    """No escribe NIfTI real -- solo unos bytes deterministicos, para probar
    la orquestacion sin depender de SimpleITK aqui (el adaptador real se
    prueba aparte, ver tests/unit/test_simpleitk_volume_serializer.py)."""

    def save(self, volume: Volume, path: Path) -> None:
        path.write_bytes(b"fake-nifti-bytes")


def _fake_keys_and_storage(dicom_paths: list[Path]) -> tuple[list[str], FakeObjectStorage]:
    keys = [f"studies/fake/{p.name}" for p in dicom_paths]
    return keys, FakeObjectStorage(dict(zip(keys, dicom_paths)))


def test_procesa_exitosamente_sube_el_resultado_y_marca_succeeded(synthetic_dicom_series):
    status_repo = FakeStudyStatusRepository()
    volume_repo = FakeVolumeRepository()
    study_id = UUID(int=42)
    keys, storage = _fake_keys_and_storage(synthetic_dicom_series)

    payload = _process_study(
        status_repo, FakeVolumeProcessor(), storage, volume_repo, FakeVolumeSerializer(),
        str(study_id), keys,
    )

    assert payload["study_id"] == str(study_id)
    assert set(payload["detail_levels"]) == {"preview", "full"}
    assert status_repo.calls == [
        ("start_processing", study_id),
        ("mark_succeeded", study_id, UUID(int=1)),
    ]
    # el resultado de AMBOS niveles se subio ANTES de marcar succeeded
    # (volume_repo.create ya se llamo para cada uno cuando llegamos aca)
    assert len(volume_repo.created) == 2
    created_by_level = {row[2]: row for row in volume_repo.created}
    assert set(created_by_level.keys()) == {"preview", "full"}
    for detail_level, row in created_by_level.items():
        result_key = f"results/{study_id}/{detail_level}.nii.gz"
        assert result_key in storage.uploaded
        assert row == (
            study_id, UUID(int=1), detail_level, "nii.gz", result_key, storage.uploaded[result_key]
        )

    # el progreso avanza monotonamente de 0 (implicito en start_processing)
    # a un maximo de 95 antes de mark_succeeded (que ya pone 100 el solo)
    stages = [stage for _, stage, _ in status_repo.progress_calls]
    percents = [pct for _, _, pct in status_repo.progress_calls]
    assert stages == [
        "downloading_dicom", "processing", "uploading_result", "uploading_result", "uploading_result"
    ]
    assert percents == sorted(percents)
    assert percents[-1] == 95  # 70 + 25*(2/2), 2 niveles (preview+full)


def test_si_el_procesamiento_falla_marca_failed_y_relanza_sin_subir_nada(synthetic_dicom_series):
    status_repo = FakeStudyStatusRepository()
    volume_repo = FakeVolumeRepository()
    study_id = UUID(int=42)
    keys, storage = _fake_keys_and_storage(synthetic_dicom_series)

    with pytest.raises(RuntimeError, match="DICOM corrupto"):
        _process_study(
            status_repo, FailingVolumeProcessor(), storage, volume_repo, FakeVolumeSerializer(),
            str(study_id), keys,
        )

    assert status_repo.calls == [
        ("start_processing", study_id),
        ("mark_failed", study_id, UUID(int=1), "DICOM corrupto"),
    ]
    assert volume_repo.created == []
    assert storage.uploaded == {}
    # el fallo ocurre dentro de ProcessDicomSeries.execute() -- alcanzo a
    # reportar "downloading_dicom" y "processing", nunca "uploading_result"
    stages = [stage for _, stage, _ in status_repo.progress_calls]
    assert stages == ["downloading_dicom", "processing"]
