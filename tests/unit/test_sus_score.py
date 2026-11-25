from datetime import UTC, datetime
from uuid import UUID

import pytest

from domain.entities import SusQuestionnaire, SusResponse, SusResponseInput


def _questionnaire(scores: list[int]) -> SusQuestionnaire:
    responses = tuple(
        SusResponse(id=UUID(int=i), questionnaire_id=UUID(int=1), question_number=i + 1, score=s)
        for i, s in enumerate(scores)
    )
    return SusQuestionnaire(
        id=UUID(int=1), user_id=UUID(int=1), session_id=None,
        completed_at=datetime.now(UTC), responses=responses,
    )


def test_todas_las_respuestas_neutras_dan_50():
    # Hecho conocido de la formula SUS: responder "3" (neutral) a las 10
    # preguntas siempre da exactamente 50, sin importar el signo del item.
    questionnaire = _questionnaire([3] * 10)

    assert questionnaire.score == 50.0


def test_mejor_respuesta_posible_da_100():
    # Items impares (positivos): 5 = "totalmente de acuerdo" es la mejor.
    # Items pares (negativos): 1 = "totalmente en desacuerdo" es la mejor.
    scores = [5 if (i + 1) % 2 == 1 else 1 for i in range(10)]
    questionnaire = _questionnaire(scores)

    assert questionnaire.score == 100.0


def test_peor_respuesta_posible_da_0():
    scores = [1 if (i + 1) % 2 == 1 else 5 for i in range(10)]
    questionnaire = _questionnaire(scores)

    assert questionnaire.score == 0.0


def test_ejemplo_mixto_conocido():
    # 1,2,3,4,5,1,2,3,4,5 -- calculado a mano:
    # impares (1,3,5,7,9)=posiciones score 1,3,5,2,4 -> (1-1)+(3-1)+(5-1)+(2-1)+(4-1)=0+2+4+1+3=10
    # pares (2,4,6,8,10)=posiciones score 2,4,1,3,5 -> (5-2)+(5-4)+(5-1)+(5-3)+(5-5)=3+1+4+2+0=10
    # total=20 * 2.5 = 50
    questionnaire = _questionnaire([1, 2, 3, 4, 5, 1, 2, 3, 4, 5])

    assert questionnaire.score == 50.0


def test_requiere_las_10_respuestas():
    questionnaire = _questionnaire([3] * 9)  # solo 9

    with pytest.raises(ValueError):
        _ = questionnaire.score


def test_sus_response_input_rechaza_question_number_fuera_de_rango():
    with pytest.raises(ValueError):
        SusResponseInput(question_number=11, score=3)


def test_sus_response_input_rechaza_score_fuera_de_rango():
    with pytest.raises(ValueError):
        SusResponseInput(question_number=1, score=6)
