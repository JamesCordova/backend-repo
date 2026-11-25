from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from application.errors import SessionAccessDeniedError, SessionNotFoundError
from application.ports.session_repository import SessionRepository
from domain.entities import Role


@dataclass(frozen=True, slots=True)
class EndSessionInput:
    session_id: UUID
    requesting_user_id: UUID
    requesting_user_role: Role


class EndSession:
    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, data: EndSessionInput) -> None:
        session = await self._sessions.get_by_id(data.session_id)
        if session is None:
            raise SessionNotFoundError(data.session_id)

        is_owner = session.user_id == data.requesting_user_id
        is_staff = data.requesting_user_role in (Role.PROFESSOR, Role.ADMIN)
        if not is_owner and not is_staff:
            raise SessionAccessDeniedError(data.session_id)

        if session.is_active:
            await self._sessions.save(replace(session, ended_at=datetime.now(UTC)))
