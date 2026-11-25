from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from application.ports.sus_repository import SusRepository
from domain.entities import SusQuestionnaire, SusResponse
from infrastructure.db.models import SusQuestionnaireModel, SusResponseModel


def _to_entity(row: SusQuestionnaireModel) -> SusQuestionnaire:
    return SusQuestionnaire(
        id=row.id,
        user_id=row.user_id,
        session_id=row.session_id,
        completed_at=row.completed_at,
        responses=tuple(
            SusResponse(
                id=r.id,
                questionnaire_id=r.questionnaire_id,
                question_number=r.question_number,
                score=r.score,
            )
            for r in row.responses
        ),
    )


class SqlAlchemySusRepository(SusRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_with_responses(self, questionnaire: SusQuestionnaire) -> None:
        self._session.add(
            SusQuestionnaireModel(
                id=questionnaire.id,
                user_id=questionnaire.user_id,
                session_id=questionnaire.session_id,
                completed_at=questionnaire.completed_at,
            )
        )
        for response in questionnaire.responses:
            self._session.add(
                SusResponseModel(
                    id=response.id,
                    questionnaire_id=questionnaire.id,
                    question_number=response.question_number,
                    score=response.score,
                )
            )
        await self._session.commit()

    async def get_by_id(self, questionnaire_id: UUID) -> SusQuestionnaire | None:
        result = await self._session.execute(
            select(SusQuestionnaireModel)
            .options(selectinload(SusQuestionnaireModel.responses))
            .where(SusQuestionnaireModel.id == questionnaire_id)
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None
