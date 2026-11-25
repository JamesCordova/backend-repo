from datetime import UTC, datetime
from uuid import uuid4

from domain.entities import Role, Study, StudyStatus, User
from infrastructure.db.models import ProcessingTaskModel
from infrastructure.db.sqlalchemy_processing_task_repository import (
    SqlAlchemyProcessingTaskRepository,
)
from infrastructure.db.sqlalchemy_study_repository import SqlAlchemyStudyRepository
from infrastructure.db.sqlalchemy_user_repository import SqlAlchemyUserRepository


async def test_devuelve_el_intento_mas_reciente(db_session):
    owner = User(
        id=uuid4(),
        name="Ana",
        email=f"ana-{uuid4()}@example.com",
        password_hash="hashed:x",
        role=Role.STUDENT,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyUserRepository(db_session).save(owner)
    study = Study(
        id=uuid4(),
        name="Torax",
        status=StudyStatus.PROCESSING,
        created_by=owner.id,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyStudyRepository(db_session).save(study)

    db_session.add(
        ProcessingTaskModel(
            id=uuid4(),
            study_id=study.id,
            attempt_number=1,
            status="failed",
            stage="reading_dicom",
            progress_percent=20,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )
    latest_id = uuid4()
    db_session.add(
        ProcessingTaskModel(
            id=latest_id,
            study_id=study.id,
            attempt_number=2,
            status="running",
            stage="resampling",
            progress_percent=70,
            started_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    repo = SqlAlchemyProcessingTaskRepository(db_session)
    latest = await repo.get_latest_by_study_id(study.id)

    assert latest is not None
    assert latest.id == latest_id
    assert latest.attempt_number == 2
    assert latest.stage == "resampling"
    assert latest.progress_percent == 70


async def test_sin_intentos_devuelve_none(db_session):
    repo = SqlAlchemyProcessingTaskRepository(db_session)

    assert await repo.get_latest_by_study_id(uuid4()) is None
