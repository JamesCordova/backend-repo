from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.study_repository import StudyRepository
from domain.entities import Study, StudyStatus
from infrastructure.db.models import StudyModel


def _to_entity(row: StudyModel) -> Study:
    return Study(
        id=row.id,
        name=row.name,
        status=StudyStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _to_model(study: Study) -> StudyModel:
    return StudyModel(
        id=study.id,
        name=study.name,
        status=study.status.value,
        created_by=study.created_by,
        created_at=study.created_at,
    )


class SqlAlchemyStudyRepository(StudyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, study_id: UUID) -> Study | None:
        row = await self._session.get(StudyModel, study_id)
        return _to_entity(row) if row else None

    async def save(self, study: Study) -> None:
        self._session.add(_to_model(study))
        await self._session.commit()

    async def list_all(self) -> list[Study]:
        stmt = select(StudyModel).order_by(StudyModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]
