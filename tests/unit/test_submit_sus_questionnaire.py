from uuid import UUID

import pytest

from application.use_cases.submit_sus_questionnaire import (
    SubmitSusQuestionnaire,
    SubmitSusQuestionnaireInput,
)
from domain.entities import SusResponseInput


def _ten_neutral_responses() -> list[SusResponseInput]:
    return [SusResponseInput(question_number=i, score=3) for i in range(1, 11)]


async def test_crea_el_cuestionario_con_las_10_respuestas(sus_repository, id_generator):
    use_case = SubmitSusQuestionnaire(sus_repository, id_generator)
    user_id = UUID(int=1)

    questionnaire = await use_case.execute(
        SubmitSusQuestionnaireInput(
            responses=_ten_neutral_responses(), requesting_user_id=user_id
        )
    )

    assert questionnaire.user_id == user_id
    assert questionnaire.session_id is None
    assert len(questionnaire.responses) == 10
    assert questionnaire.score == 50.0
    stored = await sus_repository.get_by_id(questionnaire.id)
    assert stored == questionnaire


async def test_acepta_session_id_opcional(sus_repository, id_generator):
    use_case = SubmitSusQuestionnaire(sus_repository, id_generator)
    session_id = UUID(int=99)

    questionnaire = await use_case.execute(
        SubmitSusQuestionnaireInput(
            responses=_ten_neutral_responses(),
            requesting_user_id=UUID(int=1),
            session_id=session_id,
        )
    )

    assert questionnaire.session_id == session_id


async def test_rechaza_menos_de_10_respuestas(sus_repository, id_generator):
    use_case = SubmitSusQuestionnaire(sus_repository, id_generator)

    with pytest.raises(ValueError, match="10 respuestas"):
        await use_case.execute(
            SubmitSusQuestionnaireInput(
                responses=_ten_neutral_responses()[:9], requesting_user_id=UUID(int=1)
            )
        )


async def test_rechaza_preguntas_repetidas(sus_repository, id_generator):
    use_case = SubmitSusQuestionnaire(sus_repository, id_generator)
    responses = _ten_neutral_responses()[:9] + [SusResponseInput(question_number=1, score=3)]

    with pytest.raises(ValueError, match="cubrir las preguntas"):
        await use_case.execute(
            SubmitSusQuestionnaireInput(responses=responses, requesting_user_id=UUID(int=1))
        )
