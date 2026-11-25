from dataclasses import dataclass
from datetime import UTC, datetime

from application.errors import EmailAlreadyRegisteredError
from application.ports.id_generator import IdGenerator
from application.ports.password_hasher import PasswordHasher
from application.ports.user_repository import UserRepository
from domain.entities import Role, User


@dataclass(frozen=True, slots=True)
class RegisterUserInput:
    name: str
    email: str
    plain_password: str
    role: Role = Role.STUDENT


class RegisterUser:
    def __init__(
        self, users: UserRepository, hasher: PasswordHasher, ids: IdGenerator
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._ids = ids

    async def execute(self, data: RegisterUserInput) -> User:
        email = data.email.strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)

        user = User(
            id=self._ids.generate(),
            name=data.name.strip(),
            email=email,
            password_hash=self._hasher.hash(data.plain_password),
            role=data.role,
            created_at=datetime.now(UTC),
        )
        await self._users.save(user)
        return user
