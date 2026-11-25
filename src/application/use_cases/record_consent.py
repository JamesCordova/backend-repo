from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from application.ports.consent_repository import ConsentRepository
from application.ports.id_generator import IdGenerator
from domain.entities import ConsentRecord


@dataclass(frozen=True, slots=True)
class RecordConsentInput:
    user_id: UUID


class RecordConsent:
    """Registra que el usuario acepto el consentimiento informado -- una sola
    vez por participante (seccion 20/21 del documento de arquitectura).
    Idempotente: aceptar de nuevo no crea un segundo registro, devuelve el
    existente tal cual quedo la primera vez."""

    def __init__(self, consents: ConsentRepository, ids: IdGenerator) -> None:
        self._consents = consents
        self._ids = ids

    async def execute(self, data: RecordConsentInput) -> ConsentRecord:
        existing = await self._consents.get_by_user_id(data.user_id)
        if existing is not None:
            return existing

        consent = ConsentRecord(
            id=self._ids.generate(), user_id=data.user_id, accepted_at=datetime.now(UTC)
        )
        await self._consents.save(consent)
        return consent
