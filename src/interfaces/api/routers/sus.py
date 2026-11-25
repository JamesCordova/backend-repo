from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from application.errors import SusQuestionnaireAccessDeniedError, SusQuestionnaireNotFoundError
from application.use_cases.get_sus_questionnaire import (
    GetSusQuestionnaire,
    GetSusQuestionnaireInput,
)
from application.use_cases.submit_sus_questionnaire import (
    SubmitSusQuestionnaire,
    SubmitSusQuestionnaireInput,
)
from domain.entities import SusQuestionnaire, User
from domain.entities import SusResponseInput as DomainSusResponseInput
from interfaces.api.deps import get_current_user, get_get_sus_use_case, get_submit_sus_use_case
from interfaces.api.schemas.sus import (
    SubmitSusQuestionnaireRequest,
    SusQuestionnaireResponse,
    SusResponseResponse,
)

router = APIRouter(prefix="/cuestionarios-sus", tags=["sus"])


def _to_response(questionnaire: SusQuestionnaire) -> SusQuestionnaireResponse:
    return SusQuestionnaireResponse(
        id=questionnaire.id,
        user_id=questionnaire.user_id,
        session_id=questionnaire.session_id,
        completed_at=questionnaire.completed_at,
        score=questionnaire.score,
        responses=[
            SusResponseResponse(question_number=r.question_number, score=r.score)
            for r in questionnaire.responses
        ],
    )


@router.post("", response_model=SusQuestionnaireResponse, status_code=status.HTTP_201_CREATED)
async def enviar_cuestionario_sus(
    body: SubmitSusQuestionnaireRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[SubmitSusQuestionnaire, Depends(get_submit_sus_use_case)],
) -> SusQuestionnaireResponse:
    try:
        questionnaire = await use_case.execute(
            SubmitSusQuestionnaireInput(
                responses=[
                    DomainSusResponseInput(question_number=r.question_number, score=r.score)
                    for r in body.responses
                ],
                requesting_user_id=current_user.id,
                session_id=body.session_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _to_response(questionnaire)


@router.get("/{questionnaire_id}", response_model=SusQuestionnaireResponse)
async def obtener_cuestionario_sus(
    questionnaire_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[GetSusQuestionnaire, Depends(get_get_sus_use_case)],
) -> SusQuestionnaireResponse:
    try:
        questionnaire = await use_case.execute(
            GetSusQuestionnaireInput(
                questionnaire_id=questionnaire_id,
                requesting_user_id=current_user.id,
                requesting_user_role=current_user.role,
            )
        )
    except SusQuestionnaireNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuestionario no encontrado") from exc
    except SusQuestionnaireAccessDeniedError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "No tienes acceso a este cuestionario"
        ) from exc
    return _to_response(questionnaire)
