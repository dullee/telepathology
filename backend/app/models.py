from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import JSON, Column, Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Case(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_ref: str = Field(index=True)
    clinic: str = ""
    specimen: str = ""
    filename: str
    # queued -> analyzing -> ready -> reviewed  (or failed)
    status: str = Field(default="queued", index=True)
    urgency: Optional[float] = Field(default=None, index=True)
    tier: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    analyzed_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    diagnosis: str = ""
    notes: str = ""
    error: str = ""
    result: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


class CaseReview(SQLModel):
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
