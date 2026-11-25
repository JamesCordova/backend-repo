from datetime import UTC, datetime
from uuid import uuid4

from domain.entities import Role, Session, Study, StudyStatus, User
from infrastructure.db.sqlalchemy_session_repository import SqlAlchemySessionRepository
from infrastructure.db.sqlalchemy_study_repository import SqlAlchemyStudyRepository
from infrastructure.db.sqlalchemy_user_repository import SqlAlchemyUserRepository


async def _seed_study(db_session) -> Study:
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
        id=uuid4(), name="Torax", status=StudyStatus.READY, created_by=owner.id,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyStudyRepository(db_session).save(study)
    return study


async def test_guarda_y_recupera_una_sesion(db_session):
    study = await _seed_study(db_session)
    repo = SqlAlchemySessionRepository(db_session)
    session = Session(
        id=uuid4(), user_id=study.created_by, study_id=study.id, started_at=datetime.now(UTC)
    )

    await repo.save(session)
    found = await repo.get_by_id(session.id)

    assert found == session
    assert found.is_active


async def test_guardar_de_nuevo_actualiza_ended_at(db_session):
    study = await _seed_study(db_session)
    repo = SqlAlchemySessionRepository(db_session)
    session = Session(
        id=uuid4(), user_id=study.created_by, study_id=study.id, started_at=datetime.now(UTC)
    )
    await repo.save(session)

    ended_session = Session(
        id=session.id,
        user_id=session.user_id,
        study_id=session.study_id,
        started_at=session.started_at,
        ended_at=datetime.now(UTC),
    )
    await repo.save(ended_session)

    found = await repo.get_by_id(session.id)
    assert not found.is_active
    assert found.ended_at is not None


async def test_id_inexistente_devuelve_none(db_session):
    repo = SqlAlchemySessionRepository(db_session)

    assert await repo.get_by_id(uuid4()) is None
