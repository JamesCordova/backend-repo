from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from application.ports.id_generator import IdGenerator
from application.ports.sus_repository import SusRepository
from domain.entities import SusQuestionnaire, SusResponse, SusResponseInput


@dataclass(frozen=True, slots=True)
class SubmitSusQuestionnaireInput:
    responses: list[SusResponseInput]
    requesting_user_id: UUID
    session_id: UUID | None = None


class SubmitSusQuestionnaire:
    """No valida que session_id pertenezca al usuario -- session_id aqui es
    solo un vinculo opcional de contexto (seccion 20: granularidad del SUS
    sin decidir), no un recurso protegido como Session en start_session.py.
    """

    def __init__(self, sus: SusRepository, ids: IdGenerator) -> None:
        self._sus = sus
        self._ids = ids

    async def execute(self, data: SubmitSusQuestionnaireInput) -> SusQuestionnaire:
        if len(data.responses) != 10:
            raise ValueError(f"se requieren exactamente 10 respuestas, llegaron {len(data.responses)}")
        question_numbers = {r.question_number for r in data.responses}
        if question_numbers != set(range(1, 11)):
            raise ValueError("las respuestas deben cubrir las preguntas 1 a 10 sin repetir")

        questionnaire_id = self._ids.generate()
        responses = tuple(
            SusResponse(
                id=self._ids.generate(),
                questionnaire_id=questionnaire_id,
                question_number=r.question_number,
                score=r.score,
            )
            for r in data.responses
        )
        questionnaire = SusQuestionnaire(
            id=questionnaire_id,
            user_id=data.requesting_user_id,
            session_id=data.session_id,
            completed_at=datetime.now(UTC),
            responses=responses,
        )
        await self._sus.save_with_responses(questionnaire)
        return questionnaire
