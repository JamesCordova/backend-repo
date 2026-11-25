from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt

from application.ports.token_service import InvalidTokenError, TokenService
from domain.entities import Role

_ALGORITHM = "HS256"


class JoseTokenService(TokenService):
    def __init__(self, secret: str, expire_minutes: int) -> None:
        self._secret = secret
        self._expire_minutes = expire_minutes

    def issue(self, user_id: UUID, role: Role) -> str:
        payload = {
            "sub": str(user_id),
            "role": role.value,
            "exp": datetime.now(UTC) + timedelta(minutes=self._expire_minutes),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> UUID:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
            return UUID(payload["sub"])
        except (JWTError, KeyError, ValueError) as exc:
            raise InvalidTokenError() from exc
