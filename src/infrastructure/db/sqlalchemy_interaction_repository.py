from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.interaction_repository import InteractionRepository
from domain.entities import Interaction
from infrastructure.db.models import InteractionModel


class SqlAlchemyInteractionRepository(InteractionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, interaction: Interaction) -> None:
        self._session.add(
            InteractionModel(
                id=interaction.id,
                session_id=interaction.session_id,
                action_type=interaction.action_type,
                occurred_at=interaction.occurred_at,
                metadata_json=interaction.metadata,
            )
        )
        await self._session.commit()
