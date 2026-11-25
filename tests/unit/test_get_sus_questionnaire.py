from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import SusQuestionnaireAccessDeniedError, SusQuestionnaireNotFoundError
from application.use_cases.get_sus_questionnaire import (
    GetSusQuestionnaire,
    GetSusQuestionnaireInput,
)
from domain.entities import Role, SusQuestionnaire, SusResponse


def _questionnaire(user_id: UUID) -> SusQuestionnaire:
    responses = tuple(
        SusResponse(id=UUID(int=i), questionnaire_id=UUID(int=1), question_number=i, score=3)
        for i in range(1, 11)
    )
    return SusQuestionnaire(
        id=UUID(int=1), user_id=user_id, session_id=None,
        completed_at=datetime.now(UTC), responses=responses,
    )


async def test_el_dueno_puede_consultar_su_cuestionario(sus_repository):
    owner_id = UUID(int=1)
    questionnaire = _questionnaire(owner_id)
    await sus_repository.save_with_responses(questionnaire)
    use_case = GetSusQuestionnaire(sus_repository)

    result = await use_case.execute(
        GetSusQuestionnaireInput(
            questionnaire_id=questionnaire.id,
            requesting_user_id=owner_id,
            requesting_user_role=Role.STUDENT,
        )
    )

    assert result == questionnaire


async def test_un_profesor_puede_consultar_cualquier_cuestionario(sus_repository):
    owner_id = UUID(int=1)
    professor_id = UUID(int=2)
    questionnaire = _questionnaire(owner_id)
    await sus_repository.save_with_responses(questionnaire)
    use_case = GetSusQuestionnaire(sus_repository)

    result = await use_case.execute(
        GetSusQuestionnaireInput(
            questionnaire_id=questionnaire.id,
            requesting_user_id=professor_id,
            requesting_user_role=Role.PROFESSOR,
        )
    )

    assert result == questionnaire


async def test_otro_estudiante_no_puede_consultar_cuestionario_ajeno(sus_repository):
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    questionnaire = _questionnaire(owner_id)
    await sus_repository.save_with_responses(questionnaire)
    use_case = GetSusQuestionnaire(sus_repository)

    with pytest.raises(SusQuestionnaireAccessDeniedError):
        await use_case.execute(
            GetSusQuestionnaireInput(
                questionnaire_id=questionnaire.id,
                requesting_user_id=other_id,
                requesting_user_role=Role.STUDENT,
            )
        )


async def test_cuestionario_inexistente_lanza_not_found(sus_repository):
    use_case = GetSusQuestionnaire(sus_repository)

    with pytest.raises(SusQuestionnaireNotFoundError):
        await use_case.execute(
            GetSusQuestionnaireInput(
                questionnaire_id=UUID(int=404),
                requesting_user_id=UUID(int=1),
                requesting_user_role=Role.STUDENT,
            )
        )
