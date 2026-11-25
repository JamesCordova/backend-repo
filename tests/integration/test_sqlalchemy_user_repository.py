"""Contra Postgres real (testcontainers) -- verifica que el adaptador cumple
de verdad el contrato del puerto UserRepository, no solo que compila."""

from datetime import UTC, datetime
from uuid import uuid4

from domain.entities import Role, User
from infrastructure.db.sqlalchemy_user_repository import SqlAlchemyUserRepository


def _user(email: str) -> User:
    return User(
        id=uuid4(),
        name="Ana",
        email=email,
        password_hash="hashed:secret123",
        role=Role.STUDENT,
        created_at=datetime.now(UTC),
    )


async def test_guarda_y_recupera_por_email(db_session):
    repo = SqlAlchemyUserRepository(db_session)
    user = _user(f"ana-{uuid4()}@example.com")

    await repo.save(user)
    found = await repo.get_by_email(user.email)

    assert found == user


async def test_recupera_por_id(db_session):
    repo = SqlAlchemyUserRepository(db_session)
    user = _user(f"beto-{uuid4()}@example.com")
    await repo.save(user)

    found = await repo.get_by_id(user.id)

    assert found == user


async def test_email_inexistente_devuelve_none(db_session):
    repo = SqlAlchemyUserRepository(db_session)

    assert await repo.get_by_email(f"nadie-{uuid4()}@example.com") is None


async def test_id_inexistente_devuelve_none(db_session):
    repo = SqlAlchemyUserRepository(db_session)

    assert await repo.get_by_id(uuid4()) is None
