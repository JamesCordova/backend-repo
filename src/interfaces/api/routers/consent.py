from typing import Annotated

from fastapi import APIRouter, Depends, status

from application.use_cases.get_consent_status import GetConsentStatus, GetConsentStatusInput
from application.use_cases.record_consent import RecordConsent, RecordConsentInput
from domain.entities import User
from interfaces.api.deps import (
    get_current_user,
    get_get_consent_status_use_case,
    get_record_consent_use_case,
)
from interfaces.api.schemas.consent import ConsentStatusResponse

router = APIRouter(prefix="/consentimiento", tags=["consent"])


@router.post("", response_model=ConsentStatusResponse, status_code=status.HTTP_201_CREATED)
async def aceptar_consentimiento(
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[RecordConsent, Depends(get_record_consent_use_case)],
) -> ConsentStatusResponse:
    consent = await use_case.execute(RecordConsentInput(user_id=current_user.id))
    return ConsentStatusResponse(accepted=True, accepted_at=consent.accepted_at)


@router.get("", response_model=ConsentStatusResponse)
async def consultar_consentimiento(
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[GetConsentStatus, Depends(get_get_consent_status_use_case)],
) -> ConsentStatusResponse:
    consent = await use_case.execute(GetConsentStatusInput(user_id=current_user.id))
    return ConsentStatusResponse(
        accepted=consent is not None,
        accepted_at=consent.accepted_at if consent else None,
    )
