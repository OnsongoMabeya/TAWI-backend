import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _enum_values(e: type) -> list[str]:
    """Persist enum *values* (e.g. "listener"), not member names."""
    return [member.value for member in e]


class UserRole(str, enum.Enum):
    """The three account types from the PRD. Adult and child listeners share the
    `listener` role; `date_of_birth` distinguishes them, which is what COPPA rules
    and "therapists link only to adult users" key off."""

    LISTENER = "listener"
    CAREGIVER = "caregiver"
    THERAPIST = "therapist"


class LinkKind(str, enum.Enum):
    CAREGIVER = "caregiver"
    THERAPIST = "therapist"


class ConsentGivenBy(str, enum.Enum):
    SELF = "self"
    GUARDIAN = "guardian"


class RetentionPreference(str, enum.Enum):
    STANDARD = "standard"
    MINIMAL = "minimal"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=_enum_values, native_enum=False, length=16),
        nullable=False,
    )
    date_of_birth: Mapped[date] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # COPPA/GDPR-style consent fields (Phase 2 item 2.3). Enforcement of the minor
    # consent flow lands in Phase 7; these record what was captured at signup.
    consent_given_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consent_given_by: Mapped[ConsentGivenBy | None] = mapped_column(
        SAEnum(ConsentGivenBy, values_callable=_enum_values, native_enum=False, length=16),
        nullable=True,
    )
    data_retention_preference: Mapped[RetentionPreference] = mapped_column(
        SAEnum(RetentionPreference, values_callable=_enum_values, native_enum=False, length=16),
        nullable=False,
        server_default=RetentionPreference.STANDARD.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("role IN ('listener', 'caregiver', 'therapist')", name="ck_users_role"),
        CheckConstraint(
            "consent_given_by IS NULL OR consent_given_by IN ('self', 'guardian')",
            name="ck_users_consent_given_by",
        ),
        CheckConstraint(
            "data_retention_preference IN ('standard', 'minimal')",
            name="ck_users_retention_preference",
        ),
    )


class UserLink(Base):
    """A caregiver or therapist's authorisation to see a listener's data."""

    __tablename__ = "user_links"
    __table_args__ = (
        UniqueConstraint("listener_id", "authorised_user_id", "kind", name="uq_user_links"),
        CheckConstraint("kind IN ('caregiver', 'therapist')", name="ck_user_links_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listener_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    authorised_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[LinkKind] = mapped_column(
        SAEnum(LinkKind, values_callable=_enum_values, native_enum=False, length=16), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LinkCode(Base):
    """One-time, short-lived pairing code a listener generates so a caregiver or
    therapist can authorise a link without anyone being able to enumerate accounts."""

    __tablename__ = "link_codes"
    __table_args__ = (
        CheckConstraint(
            "grants_kind IN ('caregiver', 'therapist')", name="ck_link_codes_grants_kind"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    grants_kind: Mapped[LinkKind] = mapped_column(
        SAEnum(LinkKind, values_callable=_enum_values, native_enum=False, length=16), nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RefreshToken(Base):
    """Only the SHA-256 of the opaque token is ever stored, so a database leak
    grants nothing. `family_id` enables rotation-reuse detection: if a rotated
    token is presented again, the whole family is revoked."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
