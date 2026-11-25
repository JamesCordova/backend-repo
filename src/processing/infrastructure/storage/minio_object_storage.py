from pathlib import Path

from minio import Minio

from processing.application.ports.object_storage import ObjectStorage


class MinioObjectStorage(ObjectStorage):
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False
    ) -> None:
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket

    def download_to(self, key: str, local_path: Path) -> None:
        self._client.fget_object(self._bucket, key, str(local_path))

    def upload_from(self, local_path: Path, key: str) -> None:
        self._client.fput_object(self._bucket, key, str(local_path))
