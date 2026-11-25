"""Cierra el mismo gap que antes cerraba test_celery_task_real_queue.py en
worker-repo, adaptado a que ya no hay broker: antes se encolaba
`procesar_dicom_task` a traves de un Redis REAL (testcontainers) y un worker
de Celery real (`start_worker`) la consumia. Ahora no hace falta ese salto --
`run_dicom_processing`/`run_raw_volume_processing` (processing/jobs.py) SON
la funcion que el `ProcessPoolExecutor` ejecuta (ver
infrastructure/queue/in_process_task_queue.py); probarlas llamandolas
directo, con Postgres y MinIO reales (mismos containers de sesion que el
resto de tests/processing/integration/), es tan de punta a punta como antes
-- lo unico que YA NO hace falta demostrar es que un mensaje viaja por Redis,
porque ya no hay Redis. La cobertura de que `InProcessTaskQueue` de verdad
somete estas funciones a un `ProcessPoolExecutor` (el reemplazo puntual del
transporte que antes daba Celery) vive en
tests/unit/test_in_process_task_queue.py, con un target fake y sin
contenedores (mas rapido, no repite esta parte)."""

import tempfile
from pathlib import Path
from uuid import UUID

import numpy as np
import psycopg
import SimpleITK as sitk

from infrastructure.config import settings
from processing.infrastructure.storage.minio_object_storage import MinioObjectStorage
from processing.jobs import run_dicom_processing, run_raw_volume_processing


def _point_settings_at_test_containers(monkeypatch, database_url: str, minio_container, minio_bucket_name: str) -> None:
    """run_dicom_processing()/run_raw_volume_processing() arman sus propios
    adaptadores leyendo `settings` (ver processing/jobs.py:_build_adapters)
    -- se redirige a los containers de este modulo de tests, igual que hacia
    `celery_worker_env` en el test original de worker-repo. `database_url`
    (el fixture, forma sync "postgresql://...") se asigna directo a
    settings.database_url: `database_url_sync` es una property derivada
    (ver infrastructure/config.py) que solo reemplaza el prefijo
    "postgresql+asyncpg://" si existe -- al no existir aca, la devuelve tal
    cual, exactamente el valor sync que necesitan estos adaptadores."""
    monkeypatch.setattr(settings, "database_url", database_url)
    config = minio_container.get_config()
    monkeypatch.setattr(settings, "minio_endpoint", config["endpoint"])
    monkeypatch.setattr(settings, "minio_access_key", config["access_key"])
    monkeypatch.setattr(settings, "minio_secret_key", config["secret_key"])
    monkeypatch.setattr(settings, "minio_bucket", minio_bucket_name)


def _fetch_study_status(database_url: str, study_id: UUID) -> str:
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM studies WHERE id = %s", (study_id,))
        return cur.fetchone()[0]


def _storage(minio_container, minio_bucket_name) -> MinioObjectStorage:
    config = minio_container.get_config()
    return MinioObjectStorage(
        endpoint=config["endpoint"],
        access_key=config["access_key"],
        secret_key=config["secret_key"],
        bucket=minio_bucket_name,
    )


def _assert_both_levels_are_readable_nifti(storage: MinioObjectStorage, study_id: UUID) -> None:
    for detail_level in ("preview", "full"):
        result_key = f"results/{study_id}/{detail_level}.nii.gz"
        with tempfile.TemporaryDirectory() as tmp:
            downloaded_path = Path(tmp) / "result.nii.gz"
            storage.download_to(result_key, downloaded_path)
            assert downloaded_path.stat().st_size > 0
            image = sitk.ReadImage(str(downloaded_path))
            assert sitk.GetArrayFromImage(image).ndim == 3


def test_run_dicom_processing_de_punta_a_punta_contra_postgres_y_minio_reales(
    monkeypatch,
    seeded_study_id: UUID,
    minio_container,
    minio_bucket_name: str,
    synthetic_dicom_series,
    database_url: str,
):
    _point_settings_at_test_containers(monkeypatch, database_url, minio_container, minio_bucket_name)

    storage = _storage(minio_container, minio_bucket_name)
    object_keys = []
    for path in synthetic_dicom_series:
        key = f"studies/{seeded_study_id}/{path.name}"
        storage.upload_from(path, key)
        object_keys.append(key)

    payload = run_dicom_processing(str(seeded_study_id), object_keys)

    assert payload["study_id"] == str(seeded_study_id)
    assert set(payload["detail_levels"]) == {"preview", "full"}
    assert _fetch_study_status(database_url, seeded_study_id) == "ready"
    _assert_both_levels_are_readable_nifti(storage, seeded_study_id)


def test_run_raw_volume_processing_de_punta_a_punta_contra_postgres_y_minio_reales(
    monkeypatch,
    seeded_study_id: UUID,
    minio_container,
    minio_bucket_name: str,
    database_url: str,
):
    """Mismo criterio que el test de arriba, para el camino alternativo de
    entrada (.raw sin cabecera, dims/dtype/spacing declarados por el
    cliente en vez de leidos de tags DICOM)."""
    _point_settings_at_test_containers(monkeypatch, database_url, minio_container, minio_bucket_name)

    storage = _storage(minio_container, minio_bucket_name)
    dims = (4, 8, 8)
    array = np.arange(dims[0] * dims[1] * dims[2], dtype=np.uint8).reshape(dims)
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / "volumen.raw"
        array.tofile(raw_path)
        raw_key = f"raws/{seeded_study_id}/volumen.raw"
        storage.upload_from(raw_path, raw_key)

    # value_range viaja como argumento normal de Python (no serializado a
    # JSON por un broker) -- confirma que sobrevive intacto de punta a
    # punta igual que antes, ahora sin necesitar un mensaje de cola.
    payload = run_raw_volume_processing(
        str(seeded_study_id), raw_key, list(dims), "uint8", [1.0, 1.0, 1.0],
        value_range=[0.0, 255.0],
    )

    assert payload["study_id"] == str(seeded_study_id)
    assert set(payload["detail_levels"]) == {"preview", "full"}
    assert _fetch_study_status(database_url, seeded_study_id) == "ready"
    _assert_both_levels_are_readable_nifti(storage, seeded_study_id)
