from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    study_id: UUID
    started_at: datetime
    ended_at: datetime | None = None


class RecordInteractionRequest(BaseModel):
    action_type: str = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionResponse(BaseModel):
    id: UUID
    session_id: UUID
    action_type: str
    occurred_at: datetime
    metadata: dict[str, Any]
