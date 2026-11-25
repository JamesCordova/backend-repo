from dataclasses import dataclass

from application.errors import InvalidCredentialsError
from application.ports.password_hasher import PasswordHasher
from application.ports.token_service import TokenService
from application.ports.user_repository import UserRepository


@dataclass(frozen=True, slots=True)
class LoginUserInput:
    email: str
    plain_password: str


@dataclass(frozen=True, slots=True)
class LoginUserOutput:
    access_token: str


class LoginUser:
    def __init__(
        self, users: UserRepository, hasher: PasswordHasher, tokens: TokenService
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens

    async def execute(self, data: LoginUserInput) -> LoginUserOutput:
        user = await self._users.get_by_email(data.email.strip().lower())
        # Mismo error para "no existe" y "password incorrecto": no revelar
        # si un email esta registrado a traves del mensaje de error.
        if user is None or not user.is_active:
            raise InvalidCredentialsError()
        if not self._hasher.verify(data.plain_password, user.password_hash):
            raise InvalidCredentialsError()

        token = self._tokens.issue(user.id, user.role)
        return LoginUserOutput(access_token=token)
