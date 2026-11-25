"""Adaptador de ObjectStorage sobre el filesystem local -- alternativa a
MinioObjectStorage para correr sin ningun servicio externo (ni Docker, ni un
binario de MinIO aparte: los binarios community de MinIO dejaron de
publicarse para descarga directa a fines de 2025 -- `dl.min.io` devuelve
`410 Gone`; el proyecto community esta archivado. Ver README, seccion
"Correr sin Docker"). Mismo Protocol (application/ports/object_storage.py),
asi que ningun caso de uso (ConfirmStudyUpload, GetStudyVolume, ...) sabe ni
le importa cual de los dos adaptadores esta activo -- se elige en
interfaces/api/deps.py segun `settings.storage_backend`.

Las operaciones de disco son bloqueantes -- igual que MinioObjectStorage,
cada una corre en threadpool (run_in_threadpool/iterate_in_threadpool) para
no bloquear el event loop de uvicorn.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import IO

from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from application.ports.object_storage import ObjectStorage

_CHUNK_SIZE = 64 * 1024


class InvalidObjectKeyError(ValueError):
    """La key resuelve fuera del directorio base (ej. contiene "..") -- no
    deberia pasar nunca con keys armadas internamente (ver
    application/use_cases/upload_study_file.py:object_key_for), pero se
    valida explicito en vez de confiar en que ningun input de usuario llega
    hasta aca sin pasar por ahi (el unico dato de usuario en una key es
    `filename`, tomado directo de la URL en
    PUT /estudios/{id}/archivos/{filename})."""


class LocalFilesystemObjectStorage(ObjectStorage):
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir).resolve()

    def _resolve(self, key: str) -> Path:
        path = (self._base_dir / key).resolve()
        if path != self._base_dir and self._base_dir not in path.parents:
            raise InvalidObjectKeyError(key)
        return path

    def ensure_bucket(self) -> None:
        """Mismo nombre que MinioObjectStorage.ensure_bucket() (llamado por
        interfaces/api/main.py:lifespan) -- acá solo crea el directorio base
        si no existe, no hay ningun "bucket" real que declarar."""
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, stream: IO[bytes], length: int) -> None:
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Streaming acotado a `length` -- nunca carga el archivo completo
            # en RAM, mismo criterio que MinioObjectStorage.put.
            remaining = length
            with open(path, "wb") as f:
                while remaining > 0:
                    chunk = stream.read(min(_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)

        await run_in_threadpool(_write)

    async def exists(self, key: str) -> bool:
        def _exists() -> bool:
            try:
                return self._resolve(key).is_file()
            except InvalidObjectKeyError:
                return False

        return await run_in_threadpool(_exists)

    async def get_stream(self, key: str, offset: int = 0, length: int = 0) -> AsyncIterator[bytes]:
        path = self._resolve(key)

        def _sync_chunks() -> Iterator[bytes]:
            with open(path, "rb") as f:
                if offset:
                    f.seek(offset)
                remaining = length if length else None  # None == "hasta EOF"
                while remaining is None or remaining > 0:
                    to_read = _CHUNK_SIZE if remaining is None else min(_CHUNK_SIZE, remaining)
                    chunk = f.read(to_read)
                    if not chunk:
                        break
                    if remaining is not None:
                        remaining -= len(chunk)
                    yield chunk

        async for chunk in iterate_in_threadpool(_sync_chunks()):
            yield chunk
