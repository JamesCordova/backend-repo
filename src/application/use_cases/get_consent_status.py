from dataclasses import dataclass
from uuid import UUID

from application.ports.consent_repository import ConsentRepository
from domain.entities import ConsentRecord


@dataclass(frozen=True, slots=True)
class GetConsentStatusInput:
    user_id: UUID


class GetConsentStatus:
    """Consulta si el usuario ya acepto el consentimiento -- no bloqueante,
    solo informa (el frontend decide que hacer con la respuesta, ej. mostrar
    el dialogo de aceptacion si todavia no acepto)."""

    def __init__(self, consents: ConsentRepository) -> None:
        self._consents = consents

    async def execute(self, data: GetConsentStatusInput) -> ConsentRecord | None:
        return await self._consents.get_by_user_id(data.user_id)
