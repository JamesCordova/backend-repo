"""Contra MinIO real (testcontainers) -- upload_from/download_to de punta a
punta, el mismo camino que recorre el worker real al bajar los slices subidos
por api-repo y subir el resultado."""

from pathlib import Path
from uuid import uuid4

from processing.infrastructure.storage.minio_object_storage import MinioObjectStorage


def _storage(minio_container, minio_bucket_name) -> MinioObjectStorage:
    config = minio_container.get_config()
    return MinioObjectStorage(
        endpoint=config["endpoint"],
        access_key=config["access_key"],
        secret_key=config["secret_key"],
        bucket=minio_bucket_name,
    )


def test_upload_from_y_download_to_redondo_completo(
    minio_container, minio_bucket_name, tmp_path: Path
):
    storage = _storage(minio_container, minio_bucket_name)
    key = f"tests/{uuid4()}/full.npz"
    original = tmp_path / "original.npz"
    original.write_bytes(b"contenido-de-volumen-falso")

    storage.upload_from(original, key)

    downloaded = tmp_path / "downloaded.npz"
    storage.download_to(key, downloaded)

    assert downloaded.read_bytes() == b"contenido-de-volumen-falso"
