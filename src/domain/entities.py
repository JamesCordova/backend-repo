"""Entidades de dominio. Sin imports de FastAPI, SQLAlchemy, Pydantic ni ningun framework.

Ver intern-talk/arquitectura-backend-clean-architecture.md seccion 1.3: este modulo es
el unico candidato razonable a compartirse (por copia o submodule) entre api-repo y
worker-repo, precisamente porque no arrastra dependencias de ninguno de los dos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class Role(str, Enum):
    STUDENT = "student"
    PROFESSOR = "professor"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    name: str
    email: str
    password_hash: str
    role: Role
    created_at: datetime
    deleted_at: datetime | None = field(default=None)

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None


class StudyStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Study:
    id: UUID
    name: str
    status: StudyStatus
    created_by: UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProcessingTask:
    """Escrita por worker-repo -- refleja el progreso granular de un intento
    de procesamiento (seccion 6.5 del documento de clean architecture).
    `stage` es libre (no un Enum) porque lo define el pipeline del worker, que
    esta pensado para poder cambiar de pasos sin tocar esta API."""

    id: UUID
    study_id: UUID
    attempt_number: int
    status: str
    stage: str | None
    progress_percent: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class Session:
    """Una sesion de visualizacion -- vincula un usuario a un estudio durante
    un lapso, para poder atribuirle las interacciones (seccion 9/21 del
    documento de arquitectura: atribucion de actividad, no control de acceso
    a datos sensibles de terceros)."""

    id: UUID
    user_id: UUID
    study_id: UUID
    started_at: datetime
    ended_at: datetime | None = field(default=None)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


@dataclass(frozen=True, slots=True)
class Interaction:
    """Un evento dentro de una sesion (ej. 'rotar_volumen', 'cambiar_ventana_hu') --
    action_type es libre, lo define el frontend, esta API no lo valida contra
    un catalogo cerrado."""

    id: UUID
    session_id: UUID
    action_type: str
    occurred_at: datetime
    metadata: dict


@dataclass(frozen=True, slots=True)
class SusResponseInput:
    """Una respuesta individual, tal como llega del cliente -- sin id ni
    questionnaire_id todavia (los asigna SubmitSusQuestionnaire)."""

    question_number: int
    score: int

    def __post_init__(self) -> None:
        if not (1 <= self.question_number <= 10):
            raise ValueError(f"question_number debe estar entre 1 y 10, llego {self.question_number}")
        if not (1 <= self.score <= 5):
            raise ValueError(f"score debe estar entre 1 y 5, llego {self.score}")


@dataclass(frozen=True, slots=True)
class SusResponse:
    id: UUID
    questionnaire_id: UUID
    question_number: int
    score: int


@dataclass(frozen=True, slots=True)
class SusQuestionnaire:
    """session_id es nullable a proposito -- la seccion 20 del documento de
    arquitectura deja pendiente si el SUS se responde una vez por sesion o
    una vez por participante sobre el sistema completo; el esquema soporta
    ambos sin necesitar esa decision para existir."""

    id: UUID
    user_id: UUID
    session_id: UUID | None
    completed_at: datetime
    responses: tuple[SusResponse, ...] = field(default_factory=tuple)

    @property
    def score(self) -> float:
        """Formula estandar SUS (Brooke, 1996): items impares (1,3,5,7,9)
        contribuyen (puntaje-1); items pares (2,4,6,8,10) contribuyen
        (5-puntaje); la suma se multiplica por 2.5 -- rango final 0-100.
        Requiere las 10 respuestas completas."""
        if len(self.responses) != 10:
            raise ValueError(
                f"el puntaje SUS requiere las 10 respuestas, hay {len(self.responses)}"
            )
        total = 0
        for r in self.responses:
            total += (r.score - 1) if r.question_number % 2 == 1 else (5 - r.score)
        return total * 2.5


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    """El consentimiento informado de un participante para las pruebas de
    usabilidad de la tesis (seccion 20/21 del documento de arquitectura) --
    una sola vez por participante, no bloqueante (se registra, no impide usar
    la plataforma) y sin versionar el texto (solo el hecho de haber aceptado
    y cuando)."""

    id: UUID
    user_id: UUID
    accepted_at: datetime


@dataclass(frozen=True, slots=True)
class Volume:
    """Registro del resultado escrito por worker-repo -- ver seccion 21 del
    documento de arquitectura. `storage_path` es una key de MinIO, no una ruta
    de disco; esta API nunca la expone directo al cliente (seccion 6.6)."""

    id: UUID
    study_id: UUID
    processing_task_id: UUID
    detail_level: str
    format: str
    storage_path: str
    size_bytes: int
    created_at: datetime
