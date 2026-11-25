from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from application.errors import (
    SessionAccessDeniedError,
    SessionNotFoundError,
    StudyNotFoundError,
)
from application.use_cases.end_session import EndSession, EndSessionInput
from application.use_cases.record_interaction import RecordInteraction, RecordInteractionInput
from application.use_cases.start_session import StartSession, StartSessionInput
from domain.entities import Interaction, Session, User
from interfaces.api.deps import (
    get_current_user,
    get_end_session_use_case,
    get_record_interaction_use_case,
    get_start_session_use_case,
)
from interfaces.api.schemas.session import (
    InteractionResponse,
    RecordInteractionRequest,
    SessionResponse,
)

# Sin prefix propio: "iniciar sesion" cuelga de /estudios/{id} (seccion 21 --
# una sesion siempre nace ligada a un estudio); "terminar"/"interacciones"
# cuelgan de /sesiones/{id} porque ya no necesitan el estudio en la URL.
study_sessions_router = APIRouter(prefix="/estudios", tags=["sessions"])
sessions_router = APIRouter(prefix="/sesiones", tags=["sessions"])


def _session_to_response(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        study_id=session.study_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


@study_sessions_router.post(
    "/{study_id}/sesiones", response_model=SessionResponse, status_code=status.HTTP_201_CREATED
)
async def iniciar_sesion(
    study_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[StartSession, Depends(get_start_session_use_case)],
) -> SessionResponse:
    try:
        session = await use_case.execute(
            StartSessionInput(study_id=study_id, requesting_user_id=current_user.id)
        )
    except StudyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado") from exc
    return _session_to_response(session)


@sessions_router.post("/{session_id}/fin", status_code=status.HTTP_204_NO_CONTENT)
async def terminar_sesion(
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[EndSession, Depends(get_end_session_use_case)],
) -> None:
    try:
        await use_case.execute(
            EndSessionInput(
                session_id=session_id,
                requesting_user_id=current_user.id,
                requesting_user_role=current_user.role,
            )
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesion no encontrada") from exc
    except SessionAccessDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a esta sesion") from exc


@sessions_router.post(
    "/{session_id}/interacciones",
    response_model=InteractionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_interaccion(
    session_id: UUID,
    body: RecordInteractionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[RecordInteraction, Depends(get_record_interaction_use_case)],
) -> InteractionResponse:
    try:
        interaction: Interaction = await use_case.execute(
            RecordInteractionInput(
                session_id=session_id,
                action_type=body.action_type,
                metadata=body.metadata,
                requesting_user_id=current_user.id,
                requesting_user_role=current_user.role,
            )
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesion no encontrada") from exc
    except SessionAccessDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a esta sesion") from exc
    return InteractionResponse(
        id=interaction.id,
        session_id=interaction.session_id,
        action_type=interaction.action_type,
        occurred_at=interaction.occurred_at,
        metadata=interaction.metadata,
    )
