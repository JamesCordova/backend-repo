from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.volume_repository import VolumeRepository
from domain.entities import Volume
from infrastructure.db.models import VolumeModel


def _to_entity(row: VolumeModel) -> Volume:
    return Volume(
        id=row.id,
        study_id=row.study_id,
        processing_task_id=row.processing_task_id,
        detail_level=row.detail_level,
        format=row.format,
        storage_path=row.storage_path,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


class SqlAlchemyVolumeRepository(VolumeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_by_study_id(self, study_id: UUID, detail_level: str) -> Volume | None:
        result = await self._session.execute(
            select(VolumeModel)
            .where(VolumeModel.study_id == study_id, VolumeModel.detail_level == detail_level)
            .order_by(VolumeModel.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None
