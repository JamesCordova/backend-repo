from typing import Protocol
from uuid import UUID


class StudyStatusRepository(Protocol):
    """Refleja el progreso del procesamiento en Postgres (studies.status +
    processing_tasks) -- api-repo posee el esquema/migraciones (seccion 15),
    el worker solo escribe filas cuya forma ya existe.

    Regla documentada en la seccion 21 del documento de arquitectura:
    studies.status se actualiza siempre como ultimo paso de un intento en
    processing_tasks, nunca de forma independiente -- por eso estos 3 metodos
    siempre tocan ambas tablas juntas, en una sola operacion atomica.
    """

    def start_processing(self, study_id: UUID) -> UUID:
        """Marca studies.status='processing', crea una fila en
        processing_tasks (status='running', attempt_number = intentos previos + 1)
        y devuelve su id -- para poder cerrarla despues con mark_succeeded/mark_failed."""
        ...

    def update_progress(self, processing_task_id: UUID, stage: str, progress_percent: int) -> None:
        """Progreso granular (seccion 6.5 del documento de clean architecture)
        -- NO toca studies.status, solo processing_tasks. Se llama entre pasos
        del pipeline, no al empezar/terminar (eso ya lo cubren
        start_processing/mark_succeeded/mark_failed)."""
        ...

    def mark_succeeded(self, study_id: UUID, processing_task_id: UUID) -> None:
        """studies.status='ready' + processing_tasks.status='succeeded'."""
        ...

    def mark_failed(self, study_id: UUID, processing_task_id: UUID, error_message: str) -> None:
        """studies.status='failed' + processing_tasks.status='failed' con el mensaje."""
        ...
