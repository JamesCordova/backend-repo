from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.consent_repository import ConsentRepository
from domain.entities import ConsentRecord
from infrastructure.db.models import ConsentRecordModel


def _to_entity(row: ConsentRecordModel) -> ConsentRecord:
    return ConsentRecord(id=row.id, user_id=row.user_id, accepted_at=row.accepted_at)


class SqlAlchemyConsentRepository(ConsentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> ConsentRecord | None:
        result = await self._session.execute(
            select(ConsentRecordModel).where(ConsentRecordModel.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None

    async def save(self, consent: ConsentRecord) -> None:
        self._session.add(
            ConsentRecordModel(
                id=consent.id, user_id=consent.user_id, accepted_at=consent.accepted_at
            )
        )
        await self._session.commit()
