from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Category(str, Enum):
    SECURITY = "security"
    HARASSMENT = "harassment"
    CORRUPTION = "corruption"
    TECHNICAL = "technical"
    OTHER = "other"


class Status(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


ALLOWED_TRANSITIONS = {
    Status.SUBMITTED: {Status.UNDER_REVIEW},
    Status.UNDER_REVIEW: {Status.RESOLVED, Status.DISMISSED},
    Status.RESOLVED: set(),
    Status.DISMISSED: set(),
}
FINAL_STATUSES = {Status.RESOLVED, Status.DISMISSED}


class Strict(BaseModel):
    # reject unknown fields, so things like "email" or "name" can't be sent in
    model_config = ConfigDict(extra="forbid")


class ReportCreate(Strict):
    category: Category
    description: str = Field(max_length=5000, examples=[
        "The shared admin password for the billing server is written on a sticky note in room 204."])
    evidence_url: Optional[str] = Field(default=None, max_length=2048,
                                        examples=["https://example.com/screenshot.png"])

    @field_validator("description")
    @classmethod
    def description_long_enough(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 20:
            raise ValueError("description must be at least 20 characters")
        return value

    @field_validator("evidence_url")
    @classmethod
    def evidence_url_is_web_link(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("evidence_url must be a full http:// or https:// link")
        return value


class ReportCreated(BaseModel):
    case_code: str
    status: Status
    submitted_on: str
    message: str


class PublicUpdate(BaseModel):
    status: Optional[Status]
    note: str
    created_at: str


class ReportTracking(BaseModel):
    category: Category
    status: Status
    is_closed: bool
    submitted_on: str
    updates: List[PublicUpdate]


class LoginRequest(Strict):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str


class StatusChange(Strict):
    status: Status
    note: str = Field(min_length=1, max_length=500,
                      examples=["We have started looking into this."])
    visible_to_reporter: bool = True

    @field_validator("note")
    @classmethod
    def note_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("note cannot be blank")
        return value


class NoteCreate(Strict):
    note: str = Field(min_length=1, max_length=500)
    visible_to_reporter: bool = True

    @field_validator("note")
    @classmethod
    def note_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("note cannot be blank")
        return value


class ModeratorUpdate(BaseModel):
    from_status: Optional[Status]
    to_status: Optional[Status]
    note: str
    visible_to_reporter: bool
    moderator: str
    created_at: str


class ReportSummary(BaseModel):
    id: str
    category: Category
    status: Status
    is_closed: bool
    submitted_on: str
    description_preview: str


class ReportList(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[ReportSummary]


class ReportDetail(BaseModel):
    id: str
    category: Category
    status: Status
    is_closed: bool
    submitted_on: str
    description: str
    evidence_url: Optional[str]
    updates: List[ModeratorUpdate]
