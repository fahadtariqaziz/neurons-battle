"""The app's own tables (docs/requirements.md §9, adapted to health).

LangGraph's checkpoint tables hold the graph's working state; these tables hold what we want to
QUERY: sessions and their status, kept evidence, final reports, (Phase 8) user feedback, and the patient
chat's messages (chat_messages, written by api/chat.py).
We don't copy every state field: the full state stays in the checkpoint, keyed by thread_id.

Schema changes go through Alembic migrations (backend/migrations), never by hand.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DecisionSession(Base):
    """One row per graph session (thread_id)."""

    __tablename__ = "decision_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)   # links to the checkpoints
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(10), server_default="full", index=True)   # full (admin) / quick (patient chat)
    condition_name: Mapped[str | None] = mapped_column(String(200))
    condition_category: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(40), index=True)                   # a WorkflowStatus value
    red_flags: Mapped[list] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)                    # rounds, retries, seconds...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # cascade: deleting a session deletes its evidence, report and feedback too (in Python and in the DB).
    evidence: Mapped[list["EvidenceRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    report: Mapped["DecisionReport | None"] = relationship(back_populates="session", cascade="all, delete-orphan")
    feedback: Mapped[list["UserFeedback"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class EvidenceRecord(Base):
    """One row per kept source of a session (ev_001, ev_002, ...)."""

    __tablename__ = "evidence_records"
    __table_args__ = (
        UniqueConstraint("session_id", "evidence_id", name="uq_evidence_session_evidence_id"),
        Index("ix_evidence_verification_status", "verification_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision_sessions.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[str] = mapped_column(String(20))
    perspective: Mapped[str] = mapped_column(String(20))           # research / doctor / patient
    source_url: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(40))
    excerpt: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(30))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)     # strength, claims, limitations, patient context...

    session: Mapped[DecisionSession] = relationship(back_populates="evidence")


class DecisionReport(Base):
    """The final report. UNIQUE per session, so saving twice updates instead of duplicating."""

    __tablename__ = "decision_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision_sessions.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(40))                # completed / completed_with_uncertainty
    is_conditional: Mapped[bool]
    report_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[DecisionSession] = relationship(back_populates="report")


class UserFeedback(Base):
    """Ratings / comments from the user. No writer yet: the feedback API endpoint comes in Phase 8."""

    __tablename__ = "user_feedback"
    __table_args__ = (CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_feedback_rating_1_5"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision_sessions.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str | None] = mapped_column(String(40))
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[DecisionSession] = relationship(back_populates="feedback")


class ChatMessage(Base):
    """One message of the patient chat that follows onboarding (quick sessions). The onboarding itself
    (first message, questions and answers, summary) lives in the checkpoint; only the free chat is here.
    Linked by thread_id (not a foreign key): the chat works even when PERSIST_RESULTS=false skips the session row."""

    __tablename__ = "chat_messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
