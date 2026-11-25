from typing import Protocol
from uuid import UUID


class VolumeRepository(Protocol):
    def create(
        self,
        study_id: UUID,
        processing_task_id: UUID,
        detail_level: str,
        format: str,
        storage_path: str,
        size_bytes: int,
    ) -> None:
        """Registra en Postgres (tabla volumes, seccion 21 del documento de
        arquitectura) que este intento de procesamiento produjo un archivo
        real en storage -- rastrea de que processing_task salio cada volumen,
        cerrando el punto ciego de trazabilidad ante reprocesamientos."""
        ...
