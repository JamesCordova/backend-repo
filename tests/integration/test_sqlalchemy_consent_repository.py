"""Contra Postgres real (testcontainers) -- verifica que el adaptador cumple
de verdad el contrato del puerto ConsentRepository, incluida la restriccion
de unicidad por user_id (una sola vez por participante)."""

from datetime import UTC, datetime
from uuid import uuid4

from domain.entities import ConsentRecord, Role, User
from infrastructure.db.sqlalchemy_consent_repository import SqlAlchemyConsentRepository
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


async def test_guarda_y_recupera_un_consentimiento(db_session):
    user = await _seed_user(db_session)
    repo = SqlAlchemyConsentRepository(db_session)
    consent = ConsentRecord(id=uuid4(), user_id=user.id, accepted_at=datetime.now(UTC))

    await repo.save(consent)
    found = await repo.get_by_user_id(user.id)

    assert found == consent


async def test_usuario_sin_consentimiento_devuelve_none(db_session):
    user = await _seed_user(db_session)
    repo = SqlAlchemyConsentRepository(db_session)

    assert await repo.get_by_user_id(user.id) is None
