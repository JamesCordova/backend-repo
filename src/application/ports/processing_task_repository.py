from typing import Protocol
from uuid import UUID

from domain.entities import ProcessingTask


class ProcessingTaskRepository(Protocol):
    async def get_latest_by_study_id(self, study_id: UUID) -> ProcessingTask | None:
        """El intento mas reciente -- un estudio puede tener varios
        (reprocesamiento), solo el ultimo es relevante para mostrar progreso."""
        ...
