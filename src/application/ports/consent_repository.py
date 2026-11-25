from typing import Protocol
from uuid import UUID

from domain.entities import ConsentRecord


class ConsentRepository(Protocol):
    async def get_by_user_id(self, user_id: UUID) -> ConsentRecord | None: ...

    async def save(self, consent: ConsentRecord) -> None: ...
