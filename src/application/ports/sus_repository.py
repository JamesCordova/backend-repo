from typing import Protocol
from uuid import UUID

from domain.entities import SusQuestionnaire


class SusRepository(Protocol):
    async def save_with_responses(self, questionnaire: SusQuestionnaire) -> None:
        """Guarda el cuestionario y sus 10 respuestas en una sola operacion
        atomica -- nunca debe quedar un cuestionario sin sus respuestas o
        viceversa."""
        ...

    async def get_by_id(self, questionnaire_id: UUID) -> SusQuestionnaire | None: ...
