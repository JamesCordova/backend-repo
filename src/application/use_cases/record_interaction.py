from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from application.errors import SessionAccessDeniedError, SessionNotFoundError
from application.ports.id_generator import IdGenerator
from application.ports.interaction_repository import InteractionRepository
from application.ports.session_repository import SessionRepository
from domain.entities import Interaction, Role


@dataclass(frozen=True, slots=True)
class RecordInteractionInput:
    session_id: UUID
    action_type: str
    metadata: dict
    requesting_user_id: UUID
    requesting_user_role: Role


class RecordInteraction:
    """El user_id de la interaccion se deriva de la sesion (y la sesion, del
    JWT verificado al abrirla) -- nunca de un campo que mande el cliente en
    el body, que podria falsificarse (seccion 9 del documento de
    arquitectura)."""

    def __init__(
        self, sessions: SessionRepository, interactions: InteractionRepository, ids: IdGenerator
    ) -> None:
        self._sessions = sessions
        self._interactions = interactions
        self._ids = ids

    async def execute(self, data: RecordInteractionInput) -> Interaction:
        session = await self._sessions.get_by_id(data.session_id)
        if session is None:
            raise SessionNotFoundError(data.session_id)

        is_owner = session.user_id == data.requesting_user_id
        is_staff = data.requesting_user_role in (Role.PROFESSOR, Role.ADMIN)
        if not is_owner and not is_staff:
            raise SessionAccessDeniedError(data.session_id)

        interaction = Interaction(
            id=self._ids.generate(),
            session_id=data.session_id,
            action_type=data.action_type,
            occurred_at=datetime.now(UTC),
            metadata=data.metadata,
        )
        await self._interactions.save(interaction)
        return interaction
