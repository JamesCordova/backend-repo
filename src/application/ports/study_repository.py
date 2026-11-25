from typing import Protocol
from uuid import UUID

from domain.entities import Study


class StudyRepository(Protocol):
    async def get_by_id(self, study_id: UUID) -> Study | None: ...

    async def save(self, study: Study) -> None: ...

    async def list_all(self) -> list[Study]:
        """Todos los estudios, para cualquier usuario autenticado -- Axial es
        una biblioteca compartida de estudios para la clase (datasets
        abiertos/sinteticos, no datos reales de pacientes; ver seccion 9/21
        del documento de arquitectura), no un sistema de documentos
        personales por dueno. `created_by` se sigue guardando para
        atribucion, pero no restringe la lectura. Orden: mas reciente
        primero."""
        ...
