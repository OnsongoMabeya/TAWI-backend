import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.account import ConsentGivenBy, LinkKind, RetentionPreference, UserRole
from app.permissions import is_adult
from app.security.passwords import validate_password_strength

PAIRING_CODE_PATTERN = re.compile(r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1)]
    role: UserRole
    date_of_birth: date
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    consent_accepted: bool = False
    consent_given_by: Literal["self", "guardian"] | None = None
    data_retention_preference: RetentionPreference = RetentionPreference.STANDARD

    @field_validator("password")
    @classmethod
    def strong_enough(cls, value: str) -> str:
        violations = validate_password_strength(value)
        if violations:
            raise ValueError("password " + "; ".join(violations))
        return value

    @field_validator("date_of_birth")
    @classmethod
    def not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def consent_consistent(self) -> "RegisterRequest":
        if self.role != UserRole.LISTENER and not is_adult(self.date_of_birth):
            raise ValueError("caregiver and therapist accounts must be adults")
        # Recorded, not yet enforced: the full minor-consent flow (COPPA/GDPR)
        # is Phase 7 (7.5 UI, 7.6 endpoints, 7.10 enforcement tests).
        if self.consent_accepted and self.consent_given_by is None:
            self.consent_given_by = (
                ConsentGivenBy.SELF.value
                if is_adult(self.date_of_birth)
                else ConsentGivenBy.GUARDIAN.value
            )
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1)]


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_in: int


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    display_name: str
    date_of_birth: date
    consent_given_at: datetime | None
    consent_given_by: ConsentGivenBy | None
    data_retention_preference: RetentionPreference
    created_at: datetime


class AuthResponse(BaseModel):
    tokens: TokenPair
    user: UserProfile


class LinkCodeRequest(BaseModel):
    """Kind of access the generated code will grant when redeemed."""

    grants: LinkKind


class LinkCodeResponse(BaseModel):
    """Returned once, on creation. The raw code is never stored or returned again."""

    code: str
    grants: LinkKind
    expires_at: datetime


class RedeemLinkCodeRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def shape(cls, value: str) -> str:
        value = value.upper().strip()
        if not PAIRING_CODE_PATTERN.match(value):
            raise ValueError("codes look like XXXX-XXXX (letters and digits, no 0/1/O/I)")
        return value


class LinkRedeemedResponse(BaseModel):
    listener_id: uuid.UUID
    kind: LinkKind
    created_at: datetime


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    language: str | None
    audio_source: str
    recorded_at: datetime | None
    duration_ms: int | None
    created_at: datetime


class SessionListResponse(BaseModel):
    listener_id: uuid.UUID
    sessions: list[SessionSummary]
