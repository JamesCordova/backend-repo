from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from application.errors import (
    InvalidRangeError,
    StudyNotFoundError,
    VolumeNotReadyError,
)
from application.ports.object_storage import ObjectStorage
from application.ports.study_repository import StudyRepository
from application.ports.volume_repository import VolumeRepository
from domain.entities import StudyStatus, Volume


def parse_byte_range(range_header: str | None, total_size: int) -> tuple[int, int] | None:
    """Parsea un header HTTP Range (RFC 7233) de un solo rango --
    'bytes=a-b', 'bytes=a-' (hasta el final) o 'bytes=-n' (los ultimos n
    bytes) -- contra el tamano total conocido del recurso. Funcion pura,
    sin dependencia de FastAPI/Starlette, para poder probarla aislada.

    Devuelve None si no hay header (se pide el recurso completo) o
    (start, end) inclusive dentro de los limites de total_size. Lanza
    InvalidRangeError si el header esta mal formado, tiene multiples rangos
    (no soportado), o no es satisfacible (start fuera de rango)."""
    if not range_header:
        return None
    if not range_header.startswith("bytes=") or "," in range_header:
        raise InvalidRangeError(range_header, total_size)

    spec = range_header.removeprefix("bytes=")
    start_str, sep, end_str = spec.partition("-")
    if not sep:
        raise InvalidRangeError(range_header, total_size)

    try:
        if start_str == "":
            # rango de sufijo: los ultimos N bytes ("bytes=-500")
            suffix_length = int(end_str)
            if suffix_length <= 0:
                raise InvalidRangeError(range_header, total_size)
            start = max(total_size - suffix_length, 0)
            end = total_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str != "" else total_size - 1
    except ValueError as exc:
        raise InvalidRangeError(range_header, total_size) from exc

    if start < 0 or start > end or start >= total_size:
        raise InvalidRangeError(range_header, total_size)
    return start, min(end, total_size - 1)


@dataclass(frozen=True, slots=True)
class GetStudyVolumeInput:
    study_id: UUID
    detail_level: str = "full"  # LOD: "preview" (rapido) o "full" (resolucion completa)
    range_header: str | None = None  # header HTTP Range crudo, sin parsear


class GetStudyVolume:
    """Devuelve el stream del volumen -- la API es la unica que le habla a
    MinIO (seccion 6.6 del documento de clean architecture, la descarga pasa
    por la API como proxy de streaming, nunca directo a MinIO). Cualquier
    usuario autenticado puede descargar cualquier volumen -- mismo criterio
    que GetStudy, Axial es una biblioteca compartida, no hay dueno que
    restrinja la lectura."""

    def __init__(
        self, studies: StudyRepository, volumes: VolumeRepository, storage: ObjectStorage
    ) -> None:
        self._studies = studies
        self._volumes = volumes
        self._storage = storage

    async def execute(
        self, data: GetStudyVolumeInput
    ) -> tuple[AsyncIterator[bytes], Volume, tuple[int, int] | None]:
        if data.detail_level not in ("preview", "full"):
            raise ValueError(f"detail_level invalido: {data.detail_level!r}")

        study = await self._studies.get_by_id(data.study_id)
        if study is None:
            raise StudyNotFoundError(data.study_id)

        if study.status != StudyStatus.READY:
            raise VolumeNotReadyError(data.study_id)

        volume = await self._volumes.get_latest_by_study_id(data.study_id, data.detail_level)
        if volume is None:
            # Inconsistencia de datos (status=ready sin fila en volumes) --
            # no deberia pasar, pero no se asume, se verifica.
            raise VolumeNotReadyError(data.study_id)

        byte_range = parse_byte_range(data.range_header, volume.size_bytes)
        if byte_range is None:
            stream = self._storage.get_stream(volume.storage_path)
        else:
            start, end = byte_range
            stream = self._storage.get_stream(volume.storage_path, offset=start, length=end - start + 1)
        return stream, volume, byte_range
