from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from domain.entities import Interaction, Role, Session, Study, StudyStatus, User
from infrastructure.db.sqlalchemy_interaction_repository import SqlAlchemyInteractionRepository
from infrastructure.db.sqlalchemy_session_repository import SqlAlchemySessionRepository
from infrastructure.db.sqlalchemy_study_repository import SqlAlchemyStudyRepository
from infrastructure.db.sqlalchemy_user_repository import SqlAlchemyUserRepository


async def _seed_session(db_session) -> Session:
    owner = User(
        id=uuid4(), name="Ana", email=f"ana-{uuid4()}@example.com", password_hash="hashed:x",
        role=Role.STUDENT, created_at=datetime.now(UTC),
    )
    await SqlAlchemyUserRepository(db_session).save(owner)
    study = Study(
        id=uuid4(), name="Torax", status=StudyStatus.READY, created_by=owner.id,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyStudyRepository(db_session).save(study)
    session = Session(
        id=uuid4(), user_id=owner.id, study_id=study.id, started_at=datetime.now(UTC)
    )
    await SqlAlchemySessionRepository(db_session).save(session)
    return session


async def test_guarda_la_interaccion_con_metadata_jsonb(db_session):
    session = await _seed_session(db_session)
    repo = SqlAlchemyInteractionRepository(db_session)
    interaction = Interaction(
        id=uuid4(),
        session_id=session.id,
        action_type="rotar_volumen",
        occurred_at=datetime.now(UTC),
        metadata={"eje": "z", "grados": 90},
    )

    await repo.save(interaction)

    result = await db_session.execute(
        text("SELECT action_type, metadata FROM interactions WHERE id = :id"),
        {"id": interaction.id},
    )
    action_type, metadata = result.first()
    assert action_type == "rotar_volumen"
    assert metadata == {"eje": "z", "grados": 90}
