from typing import Protocol
from uuid import UUID

from domain.entities import Role


class TokenService(Protocol):
    def issue(self, user_id: UUID, role: Role) -> str: ...

    def verify(self, token: str) -> UUID:
        """Devuelve el user_id si el token es valido. Lanza InvalidTokenError si no."""
        ...


class InvalidTokenError(Exception):
    pass
