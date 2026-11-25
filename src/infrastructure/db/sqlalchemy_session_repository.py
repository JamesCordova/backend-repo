from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession as DbSession

from application.ports.session_repository import SessionRepository
from domain.entities import Session
from infrastructure.db.models import SessionModel


def _to_entity(row: SessionModel) -> Session:
    return Session(
        id=row.id,
        user_id=row.user_id,
        study_id=row.study_id,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def _to_model(session: Session) -> SessionModel:
    return SessionModel(
        id=session.id,
        user_id=session.user_id,
        study_id=session.study_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


class SqlAlchemySessionRepository(SessionRepository):
    def __init__(self, db_session: DbSession) -> None:
        self._db_session = db_session

    async def get_by_id(self, session_id: UUID) -> Session | None:
        row = await self._db_session.get(SessionModel, session_id)
        return _to_entity(row) if row else None

    async def save(self, session: Session) -> None:
        existing = await self._db_session.get(SessionModel, session.id)
        if existing is None:
            self._db_session.add(_to_model(session))
        else:
            existing.ended_at = session.ended_at
        await self._db_session.commit()
