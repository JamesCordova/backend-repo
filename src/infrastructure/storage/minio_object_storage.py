from collections.abc import AsyncIterator, Iterator
from typing import IO

from minio import Minio
from minio.error import S3Error
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from application.ports.object_storage import ObjectStorage


class MinioObjectStorage(ObjectStorage):
    """El cliente oficial de MinIO es sincrono -- cada llamada se corre en un
    threadpool (run_in_threadpool, lo mismo que usa FastAPI internamente para
    dependencias sync) para no bloquear el event loop de uvicorn.
    """

    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False
    ) -> None:
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket

    def ensure_bucket(self) -> None:
        """Llamado una vez al arrancar la app (sync, ver interfaces/api/main.py) --
        no tiene sentido hacerlo async porque corre antes de que uvicorn sirva
        requests."""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    async def put(self, key: str, stream: IO[bytes], length: int) -> None:
        await run_in_threadpool(
            self._client.put_object, self._bucket, key, stream, length
        )

    async def exists(self, key: str) -> bool:
        def _stat() -> bool:
            try:
                self._client.stat_object(self._bucket, key)
                return True
            except S3Error:
                return False

        return await run_in_threadpool(_stat)

    async def get_stream(self, key: str, offset: int = 0, length: int = 0) -> AsyncIterator[bytes]:
        # get_object() en si (abrir la conexion) tambien es bloqueante --
        # correrlo en threadpool antes de empezar a iterar. offset/length en
        # 0/0 (default) hace que el cliente de MinIO no mande header Range y
        # traiga el objeto completo -- mismo comportamiento que antes.
        response = await run_in_threadpool(
            self._client.get_object, self._bucket, key, offset=offset, length=length
        )

        def _sync_chunks() -> Iterator[bytes]:
            try:
                yield from response.stream(32 * 1024)
            finally:
                response.close()
                response.release_conn()

        # iterate_in_threadpool: cada .read() bloqueante del iterador sync
        # corre en threadpool, sin bloquear el event loop mientras se
        # transmiten los chunks al cliente (misma idea que run_in_threadpool,
        # pero para iteracion en vez de una sola llamada).
        async for chunk in iterate_in_threadpool(_sync_chunks()):
            yield chunk
