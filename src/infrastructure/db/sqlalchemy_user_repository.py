from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.user_repository import UserRepository
from domain.entities import Role, User
from infrastructure.db.models import UserModel


def _to_entity(row: UserModel) -> User:
    return User(
        id=row.id,
        name=row.name,
        email=row.email,
        password_hash=row.password_hash,
        role=Role(row.role),
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


def _to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id,
        name=user.name,
        email=user.email,
        password_hash=user.password_hash,
        role=user.role.value,
        created_at=user.created_at,
        deleted_at=user.deleted_at,
    )


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None

    async def get_by_id(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return _to_entity(row) if row else None

    async def save(self, user: User) -> None:
        self._session.add(_to_model(user))
        await self._session.commit()
