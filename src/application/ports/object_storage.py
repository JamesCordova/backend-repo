from collections.abc import AsyncIterator
from typing import IO, Protocol


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None:
        """Preparar el storage para el primer uso -- crear el bucket de
        MinIO si no existe, o el directorio base si es filesystem local (ver
        infrastructure/storage/). Llamado una sola vez al arrancar la app
        (interfaces/api/main.py:lifespan), antes de servir requests reales
        -- por eso es sincrono, no hay ningun event loop compitiendo
        todavia."""
        ...

    async def put(self, key: str, stream: IO[bytes], length: int) -> None:
        """Sube en streaming -- nunca carga el archivo completo en RAM del
        proceso de la API (ver seccion 6.2 del documento de clean architecture)."""
        ...

    async def exists(self, key: str) -> bool: ...

    async def get_stream(self, key: str, offset: int = 0, length: int = 0) -> AsyncIterator[bytes]:
        """Descarga en streaming -- la API hace de proxy transparente hacia
        MinIO (nunca expuesto directo, seccion 6.6), sin materializar el
        archivo completo en RAM. offset/length en bytes permiten pedir solo
        una porcion del objeto (soporte de HTTP Range, seccion 6.6); 0/0
        (default) trae el objeto completo."""
        ...
