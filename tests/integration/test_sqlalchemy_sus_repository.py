from datetime import UTC, datetime
from uuid import uuid4

from domain.entities import Role, Session, Study, StudyStatus, SusQuestionnaire, SusResponse, User
from infrastructure.db.sqlalchemy_session_repository import SqlAlchemySessionRepository
from infrastructure.db.sqlalchemy_study_repository import SqlAlchemyStudyRepository
from infrastructure.db.sqlalchemy_sus_repository import SqlAlchemySusRepository
from infrastructure.db.sqlalchemy_user_repository import SqlAlchemyUserRepository


async def _seed_user(db_session) -> User:
    user = User(
        id=uuid4(),
        name="Ana",
        email=f"ana-{uuid4()}@example.com",
        password_hash="hashed:x",
        role=Role.STUDENT,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyUserRepository(db_session).save(user)
    return user


def _questionnaire(user_id, session_id=None) -> SusQuestionnaire:
    questionnaire_id = uuid4()
    responses = tuple(
        SusResponse(id=uuid4(), questionnaire_id=questionnaire_id, question_number=i, score=3)
        for i in range(1, 11)
    )
    return SusQuestionnaire(
        id=questionnaire_id,
        user_id=user_id,
        session_id=session_id,
        completed_at=datetime.now(UTC),
        responses=responses,
    )


async def test_guarda_y_recupera_un_cuestionario_con_sus_10_respuestas(db_session):
    user = await _seed_user(db_session)
    repo = SqlAlchemySusRepository(db_session)
    questionnaire = _questionnaire(user.id)

    await repo.save_with_responses(questionnaire)
    found = await repo.get_by_id(questionnaire.id)

    assert found == questionnaire
    assert found.score == 50.0


async def test_acepta_session_id_opcional(db_session):
    user = await _seed_user(db_session)
    study = Study(
        id=uuid4(), name="Torax", status=StudyStatus.READY, created_by=user.id,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyStudyRepository(db_session).save(study)
    session = Session(
        id=uuid4(), user_id=user.id, study_id=study.id, started_at=datetime.now(UTC)
    )
    await SqlAlchemySessionRepository(db_session).save(session)
    repo = SqlAlchemySusRepository(db_session)
    questionnaire = _questionnaire(user.id, session_id=session.id)

    await repo.save_with_responses(questionnaire)
    found = await repo.get_by_id(questionnaire.id)

    assert found.session_id == session.id


async def test_id_inexistente_devuelve_none(db_session):
    repo = SqlAlchemySusRepository(db_session)

    assert await repo.get_by_id(uuid4()) is None
