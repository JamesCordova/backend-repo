from datetime import UTC, datetime
from uuid import UUID

from application.use_cases.get_consent_status import GetConsentStatus, GetConsentStatusInput
from domain.entities import ConsentRecord


async def test_devuelve_none_si_no_acepto_todavia(consent_repository):
    use_case = GetConsentStatus(consent_repository)

    result = await use_case.execute(GetConsentStatusInput(user_id=UUID(int=1)))

    assert result is None


async def test_devuelve_el_registro_si_ya_acepto(consent_repository):
    user_id = UUID(int=1)
    consent = ConsentRecord(id=UUID(int=100), user_id=user_id, accepted_at=datetime.now(UTC))
    await consent_repository.save(consent)
    use_case = GetConsentStatus(consent_repository)

    result = await use_case.execute(GetConsentStatusInput(user_id=user_id))

    assert result == consent
