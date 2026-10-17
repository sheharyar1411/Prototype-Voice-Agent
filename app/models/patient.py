"""
SQLAlchemy ORM models for patient registration and call session tracking.

FLOW MAP:
  init_db / Alembic → Base.metadata.create_all → Patient, CallSession tables

KEY DETAILS:
  - Patient stores all demographic fields from the challenge specification
  - CallSession tracks each voice call's lifecycle and transcript for auditing
  - Soft-delete via deleted_at column on Patient (filtered in queries by default)
  - UUIDs as primary keys for external exposure (no auto-increment leakage)
  - Sex is an enum constrained to the 4 allowed values
"""

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


class SexEnum(str, enum.Enum):
    """Allowed values for patient biological sex / gender identity."""
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE = "Decline to Answer"


class CallSessionStatus(str, enum.Enum):
    """Lifecycle status of a voice call session."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Patient(Base):
    """
    Core patient demographics table.

    Stores all required and optional fields collected during the
    voice-based intake process. Supports soft-delete via deleted_at.
    """

    __tablename__ = "patients"

    # --- Primary Key ---
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="UUID v4 primary key, safe for external exposure.",
    )

    # --- Required Demographics ---
    first_name = Column(
        String(50),
        nullable=False,
        doc="Patient first name (1–50 chars, alphabetic + hyphens/apostrophes).",
    )
    last_name = Column(
        String(50),
        nullable=False,
        doc="Patient last name (1–50 chars, alphabetic + hyphens/apostrophes).",
    )
    date_of_birth = Column(
        Date,
        nullable=False,
        doc="Date of birth (must not be in the future).",
    )
    sex = Column(
        Enum(SexEnum, values_callable=lambda x: [e.value for e in x], name="sex_enum", create_constraint=True),
        nullable=False,
        doc="Biological sex / gender identity.",
    )
    phone_number = Column(
        String(15),
        nullable=False,
        doc="US phone number normalized to +1XXXXXXXXXX format.",
    )
    address_line_1 = Column(
        String(255),
        nullable=False,
        doc="Street address line 1.",
    )
    city = Column(
        String(100),
        nullable=False,
        doc="City name.",
    )
    state = Column(
        String(2),
        nullable=False,
        doc="2-letter US state abbreviation (e.g. TX, CA, NY).",
    )
    zip_code = Column(
        String(10),
        nullable=False,
        doc="US ZIP code (5-digit or ZIP+4 format).",
    )

    # --- Optional Demographics ---
    email = Column(
        String(255),
        nullable=True,
        doc="Email address (validated format if provided).",
    )
    address_line_2 = Column(
        String(255),
        nullable=True,
        doc="Apartment, suite, unit number.",
    )
    insurance_provider = Column(
        String(100),
        nullable=True,
        doc="Name of insurance company.",
    )
    insurance_member_id = Column(
        String(100),
        nullable=True,
        doc="Insurance member / subscriber ID.",
    )
    preferred_language = Column(
        String(50),
        nullable=True,
        default="English",
        doc="Preferred communication language.",
    )
    emergency_contact_name = Column(
        String(100),
        nullable=True,
        doc="Emergency contact full name.",
    )
    emergency_contact_phone = Column(
        String(15),
        nullable=True,
        doc="Emergency contact US phone number.",
    )

    # --- Timestamps ---
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="Record creation timestamp (UTC).",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        doc="Last update timestamp (UTC).",
    )
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        doc="Soft-delete timestamp. Non-null means record is archived.",
    )

    # --- Relationships ---
    call_sessions = relationship(
        "CallSession",
        back_populates="patient",
        lazy="selectin",
    )

    # --- Indexes for common query patterns ---
    __table_args__ = (
        Index("ix_patients_phone_number", "phone_number"),
        Index("ix_patients_last_name", "last_name"),
        Index("ix_patients_dob", "date_of_birth"),
        Index("ix_patients_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Patient(id={self.id!r}, name={self.first_name!r} {self.last_name!r}, "
            f"phone={self.phone_number!r})>"
        )


class CallSession(Base):
    """
    Voice call session audit log.

    Each inbound call creates a session record that tracks the caller,
    linked patient (if registration completes), transcript, and status.
    """

    __tablename__ = "call_sessions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="UUID v4 session identifier.",
    )
    caller_phone = Column(
        String(15),
        nullable=True,
        doc="Caller's phone number from Vapi webhook.",
    )
    patient_id = Column(
        String(36),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
        doc="FK to the patient record created or updated in this session.",
    )
    status = Column(
        Enum(CallSessionStatus, values_callable=lambda x: [e.value for e in x], name="call_session_status_enum", create_constraint=True),
        nullable=False,
        default=CallSessionStatus.IN_PROGRESS,
        doc="Current lifecycle status of the call.",
    )
    transcript = Column(
        Text,
        nullable=True,
        doc="Full conversation transcript (JSON or plain text).",
    )
    vapi_call_id = Column(
        String(100),
        nullable=True,
        doc="Vapi's external call identifier for cross-referencing.",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    ended_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when the call ended.",
    )

    # --- Relationships ---
    patient = relationship(
        "Patient",
        back_populates="call_sessions",
    )

    __table_args__ = (
        Index("ix_call_sessions_caller_phone", "caller_phone"),
        Index("ix_call_sessions_vapi_call_id", "vapi_call_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<CallSession(id={self.id!r}, caller={self.caller_phone!r}, "
            f"status={self.status!r})>"
        )
