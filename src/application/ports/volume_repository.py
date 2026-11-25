from typing import Protocol
from uuid import UUID

from domain.entities import Volume


class VolumeRepository(Protocol):
    async def get_latest_by_study_id(self, study_id: UUID, detail_level: str) -> Volume | None:
        """El mas reciente de ese nivel de detalle (LOD -- "preview" o "full",
        seccion 2 del documento de arquitectura) -- un estudio puede tener
        varios intentos de procesamiento (processing_tasks.attempt_number),
        solo el ultimo exitoso de cada nivel importa para servir el resultado
        actual."""
        ...
