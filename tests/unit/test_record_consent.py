from uuid import UUID

from application.use_cases.record_consent import RecordConsent, RecordConsentInput


async def test_registra_el_consentimiento_la_primera_vez(consent_repository, id_generator):
    use_case = RecordConsent(consent_repository, id_generator)
    user_id = UUID(int=1)

    consent = await use_case.execute(RecordConsentInput(user_id=user_id))

    assert consent.user_id == user_id
    assert consent.accepted_at is not None
    stored = await consent_repository.get_by_user_id(user_id)
    assert stored == consent


async def test_aceptar_de_nuevo_es_idempotente_no_crea_un_segundo_registro(
    consent_repository, id_generator
):
    use_case = RecordConsent(consent_repository, id_generator)
    user_id = UUID(int=1)

    first = await use_case.execute(RecordConsentInput(user_id=user_id))
    second = await use_case.execute(RecordConsentInput(user_id=user_id))

    assert first == second
    assert first.id == second.id
