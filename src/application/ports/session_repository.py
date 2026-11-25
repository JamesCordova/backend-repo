from typing import Protocol
from uuid import UUID

from domain.entities import Session


class SessionRepository(Protocol):
    async def get_by_id(self, session_id: UUID) -> Session | None: ...

    async def save(self, session: Session) -> None: ...
