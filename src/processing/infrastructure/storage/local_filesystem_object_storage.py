"""Version sincrona del adaptador de filesystem local -- para el lado
processing (corre en un proceso hijo del ProcessPoolExecutor, sin event
loop). Ver infrastructure/storage/local_filesystem_object_storage.py (lado
API) para el porque de este adaptador en vez de MinIO.

Comparte el MISMO directorio base que el lado API (misma `settings.
local_storage_dir`, ver processing/jobs.py:_build_adapters) -- al correr todo
en un solo proceso/maquina ya no hace falta un servicio de red intermedio
(MinIO) para que api y processing "vean" los mismos archivos: alcanza con
que ambos lean/escriban el mismo directorio en disco.
"""

import shutil
from pathlib import Path

from processing.application.ports.object_storage import ObjectStorage


class InvalidObjectKeyError(ValueError):
    """Misma validacion que el adaptador async -- ver su docstring."""


class LocalFilesystemObjectStorage(ObjectStorage):
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir).resolve()

    def _resolve(self, key: str) -> Path:
        path = (self._base_dir / key).resolve()
        if path != self._base_dir and self._base_dir not in path.parents:
            raise InvalidObjectKeyError(key)
        return path

    def download_to(self, key: str, local_path: Path) -> None:
        shutil.copy(self._resolve(key), local_path)

    def upload_from(self, local_path: Path, key: str) -> None:
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(local_path, dest)
