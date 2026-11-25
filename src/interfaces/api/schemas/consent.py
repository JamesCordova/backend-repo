from datetime import datetime

from pydantic import BaseModel


class ConsentStatusResponse(BaseModel):
    accepted: bool
    accepted_at: datetime | None
