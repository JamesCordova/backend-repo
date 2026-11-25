from typing import Protocol

from domain.entities import Interaction


class InteractionRepository(Protocol):
    async def save(self, interaction: Interaction) -> None: ...
