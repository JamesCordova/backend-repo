"""Contra Postgres real (testcontainers). Studies tiene FK a users -- primero
hay que crear el usuario dueno, igual que en produccion."""

from datetime import UTC, datetime
from uuid import uuid4

from domain.entities import Role, Study, StudyStatus, User
from infrastructure.db.sqlalchemy_study_repository import SqlAlchemyStudyRepository
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


async def test_guarda_y_recupera_un_estudio(db_session):
    owner = await _seed_user(db_session)
    repo = SqlAlchemyStudyRepository(db_session)
    study = Study(
        id=uuid4(),
        name="Torax de prueba",
        status=StudyStatus.PENDING,
        created_by=owner.id,
        created_at=datetime.now(UTC),
    )

    await repo.save(study)
    found = await repo.get_by_id(study.id)

    assert found == study


async def test_id_inexistente_devuelve_none(db_session):
    repo = SqlAlchemyStudyRepository(db_session)

    assert await repo.get_by_id(uuid4()) is None


async def test_list_all_devuelve_estudios_de_cualquier_dueno(db_session):
    # Axial es una biblioteca compartida -- list_all no filtra por dueno.
    owner = await _seed_user(db_session)
    other = await _seed_user(db_session)
    repo = SqlAlchemyStudyRepository(db_session)
    own_study = Study(
        id=uuid4(), name="Propio", status=StudyStatus.PENDING, created_by=owner.id,
        created_at=datetime.now(UTC),
    )
    other_study = Study(
        id=uuid4(), name="Ajeno", status=StudyStatus.PENDING, created_by=other.id,
        created_at=datetime.now(UTC),
    )
    await repo.save(own_study)
    await repo.save(other_study)

    result = await repo.list_all()

    assert own_study in result
    assert other_study in result
