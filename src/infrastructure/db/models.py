"""Modelos SQLAlchemy. Viven solo en infrastructure/ -- las entidades de
domain.entities son las que usa el resto del sistema; estos modelos solo saben
mapearlas a filas.

El esquema real lo gestiona exclusivamente Alembic (seccion 15 del documento
de arquitectura) -- ver src/infrastructure/db/migrations/.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class StudyModel(Base):
    __tablename__ = "studies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessingTaskModel(Base):
    """Escrita por el worker (axial-worker), no por esta API -- ver
    infrastructure/db/postgres_study_status_repository.py en worker-repo. El
    modelo vive aqui porque Alembic (la unica fuente de verdad del esquema,
    seccion 15) vive solo en api-repo; worker-repo se conecta a la misma
    Postgres pero no posee migraciones propias.
    """

    __tablename__ = "processing_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    # Progreso granular (seccion 6.5 del documento de clean architecture) --
    # actualizado por el worker entre pasos del pipeline, para que el polling
    # de GET /estudios/{id} deje de ser un binario pending/ready.
    stage: Mapped[str | None] = mapped_column(String(30), default=None)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class VolumeModel(Base):
    """Escrita por el worker (axial-worker), mismo caso que ProcessingTaskModel
    -- ver infrastructure/db/postgres_volume_repository.py en worker-repo."""

    __tablename__ = "volumes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id"))
    processing_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_tasks.id"))
    detail_level: Mapped[str] = mapped_column(String(20))
    format: Mapped[str] = mapped_column(String(20))
    storage_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class InteractionModel(Base):
    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    action_type: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # El atributo Python no puede llamarse "metadata" -- ese nombre esta
    # reservado por DeclarativeBase (es el MetaData de la clase). La columna
    # real en Postgres si se llama "metadata", como en la seccion 21.
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class ConsentRecordModel(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # unique=True: una sola vez por participante (seccion 20/21 del documento
    # de arquitectura) -- aceptar de nuevo no crea una segunda fila, ver
    # RecordConsent (idempotente a nivel de caso de uso, reforzado aqui a
    # nivel de esquema).
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SusQuestionnaireModel(Base):
    __tablename__ = "sus_questionnaires"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Nullable a proposito -- seccion 20 del documento de arquitectura deja
    # pendiente si el SUS es por sesion o por participante; el esquema
    # soporta ambos.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id"), default=None
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    responses: Mapped[list["SusResponseModel"]] = relationship(lazy="raise")


class SusResponseModel(Base):
    __tablename__ = "sus_responses"
    __table_args__ = (
        CheckConstraint("question_number BETWEEN 1 AND 10", name="ck_sus_question_number"),
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_sus_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sus_questionnaires.id"))
    question_number: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
