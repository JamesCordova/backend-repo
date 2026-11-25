from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SusResponseItem(BaseModel):
    question_number: int = Field(ge=1, le=10)
    score: int = Field(ge=1, le=5)


class SubmitSusQuestionnaireRequest(BaseModel):
    session_id: UUID | None = None
    responses: list[SusResponseItem] = Field(min_length=10, max_length=10)


class SusResponseResponse(BaseModel):
    question_number: int
    score: int


class SusQuestionnaireResponse(BaseModel):
    id: UUID
    user_id: UUID
    session_id: UUID | None
    completed_at: datetime
    score: float
    responses: list[SusResponseResponse]
