from dataclasses import dataclass
from uuid import UUID

from application.errors import SusQuestionnaireAccessDeniedError, SusQuestionnaireNotFoundError
from application.ports.sus_repository import SusRepository
from domain.entities import Role, SusQuestionnaire


@dataclass(frozen=True, slots=True)
class GetSusQuestionnaireInput:
    questionnaire_id: UUID
    requesting_user_id: UUID
    requesting_user_role: Role


class GetSusQuestionnaire:
    def __init__(self, sus: SusRepository) -> None:
        self._sus = sus

    async def execute(self, data: GetSusQuestionnaireInput) -> SusQuestionnaire:
        questionnaire = await self._sus.get_by_id(data.questionnaire_id)
        if questionnaire is None:
            raise SusQuestionnaireNotFoundError(data.questionnaire_id)

        is_owner = questionnaire.user_id == data.requesting_user_id
        is_staff = data.requesting_user_role in (Role.PROFESSOR, Role.ADMIN)
        if not is_owner and not is_staff:
            raise SusQuestionnaireAccessDeniedError(data.questionnaire_id)

        return questionnaire
