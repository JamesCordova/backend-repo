from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.processing_task_repository import ProcessingTaskRepository
from domain.entities import ProcessingTask
from infrastructure.db.models import ProcessingTaskModel


def _to_entity(row: ProcessingTaskModel) -> ProcessingTask:
    return ProcessingTask(
        id=row.id,
        study_id=row.study_id,
        attempt_number=row.attempt_number,
        status=row.status,
        stage=row.stage,
        progress_percent=row.progress_percent,
        error_message=row.error_message,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


class SqlAlchemyProcessingTaskRepository(ProcessingTaskRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_by_study_id(self, study_id: UUID) -> ProcessingTask | None:
        result = await self._session.execute(
            select(ProcessingTaskModel)
            .where(ProcessingTaskModel.study_id == study_id)
            .order_by(ProcessingTaskModel.attempt_number.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None
