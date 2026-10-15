import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SessionStatus(str, enum.Enum):
    # pending/processing are pre-created offline queue slots; the pipeline fills
    # them in Phases 3 (audio processing) and 6 (offline sync).
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SYNCED = "synced"


class AudioSource(str, enum.Enum):
    WIRED_MIC = "wired_mic"
    ONBOARD_MIC = "onboard_mic"
    UNKNOWN = "unknown"


class AudioKind(str, enum.Enum):
    RAW = "raw"
    ENHANCED = "enhanced"


class Session(Base):
    """One captured conversation.

    `client_session_id` exists for Phase 6 offline sync: the phone mints its own
    id while offline and the server deduplicates on (owner, client id), so a
    retried upload can never create a duplicate session."""

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("owner_id", "client_session_id", name="uq_sessions_owner_client"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'synced')",
            name="ck_sessions_status",
        ),
        CheckConstraint(
            "audio_source IN ('wired_mic', 'onboard_mic', 'unknown')",
            name="ck_sessions_audio_source",
        ),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_sessions_duration"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(
            SessionStatus,
            values_callable=lambda e: [m.value for m in e],
            native_enum=False,
            length=16,
        ),
        nullable=False,
        server_default=SessionStatus.PENDING.value,
    )
    language: Mapped[str | None] = mapped_column(String(12), nullable=True)
    audio_source: Mapped[AudioSource] = mapped_column(
        SAEnum(
            AudioSource,
            values_callable=lambda e: [m.value for m in e],
            native_enum=False,
            length=16,
        ),
        nullable=False,
        server_default=AudioSource.UNKNOWN.value,
    )
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    noise_suppression_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SessionAudio(Base):
    """Audio objects for a session; `object_key` is a pointer into whatever blob
    storage Phase 3 adopts — the database never holds audio bytes."""

    __tablename__ = "session_audio"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[AudioKind] = mapped_column(
        SAEnum(
            AudioKind, values_callable=lambda e: [m.value for m in e], native_enum=False, length=16
        ),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(Text(), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("kind IN ('raw', 'enhanced')", name="ck_session_audio_kind"),
        CheckConstraint("byte_size IS NULL OR byte_size >= 0", name="ck_session_audio_size"),
        UniqueConstraint("session_id", "kind", name="uq_session_audio_kind"),
    )


class SessionTranscript(Base):
    """Transcript text. `revision` increments on user edits (Phase 9 async review
    flow); earlier revisions are never overwritten so corrections are auditable."""

    __tablename__ = "session_transcripts"
    __table_args__ = (
        UniqueConstraint("session_id", "revision", name="uq_transcript_revision"),
        CheckConstraint("revision >= 1", name="ck_transcript_revision_positive"),
        CheckConstraint("source IN ('auto', 'user_edit')", name="ck_transcript_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("1"))
    text: Mapped[str] = mapped_column(Text(), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float(), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="auto")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
