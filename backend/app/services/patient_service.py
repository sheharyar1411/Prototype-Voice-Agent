"""
Patient service — business logic for CRUD operations and duplicate detection.

FLOW MAP:
  API router → patient_service functions → SQLAlchemy queries → DB
  Vapi tool calls → patient_service functions → validated persistence

KEY DETAILS:
  - All queries filter out soft-deleted records (deleted_at IS NULL) by default
  - Duplicate detection by phone number for returning caller flow
  - Partial updates via exclude_unset to only touch provided fields
  - Returns ORM model instances; serialization happens in the router layer
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, SexEnum
from app.schemas.patient import PatientCreate, PatientUpdate

logger = logging.getLogger(__name__)


async def create_patient(
    db: AsyncSession,
    data: PatientCreate,
) -> Patient:
    """
    Create a new patient record from validated input.

    Args:
        db: Active database session (injected via FastAPI dependency).
        data: Validated patient demographics from PatientCreate schema.

    Returns:
        The newly created Patient ORM instance with generated UUID.
    """
    # Map the Pydantic sex string to the SQLAlchemy enum value.
    sex_enum = SexEnum(data.sex)

    patient = Patient(
        first_name=data.first_name,
        last_name=data.last_name,
        date_of_birth=data.date_of_birth,
        sex=sex_enum,
        phone_number=data.phone_number,
        address_line_1=data.address_line_1,
        city=data.city,
        state=data.state,
        zip_code=data.zip_code,
        email=data.email,
        address_line_2=data.address_line_2,
        insurance_provider=data.insurance_provider,
        insurance_member_id=data.insurance_member_id,
        preferred_language=data.preferred_language,
        emergency_contact_name=data.emergency_contact_name,
        emergency_contact_phone=data.emergency_contact_phone,
    )
    db.add(patient)
    await db.flush()
    await db.refresh(patient)

    logger.info(
        "Created patient %s: %s %s (phone=%s)",
        patient.id, patient.first_name, patient.last_name, patient.phone_number,
    )
    return patient


async def get_patient_by_id(
    db: AsyncSession,
    patient_id: str,
) -> Optional[Patient]:
    """
    Retrieve a single patient by UUID, excluding soft-deleted records.

    Args:
        db: Active database session.
        patient_id: The UUID string of the patient to look up.

    Returns:
        Patient instance if found and not deleted, otherwise None.
    """
    stmt = select(Patient).where(
        Patient.id == patient_id,
        Patient.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_patients(
    db: AsyncSession,
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> list[Patient]:
    """
    List all active patients, optionally filtered by query parameters.

    Filters are case-insensitive partial matches for last_name,
    exact match for date_of_birth, and normalized match for phone_number.

    Args:
        db: Active database session.
        last_name: Optional last name filter (case-insensitive contains).
        date_of_birth: Optional DOB filter (YYYY-MM-DD string).
        phone_number: Optional phone number filter (exact E.164 match).

    Returns:
        List of matching Patient instances, ordered by created_at descending.
    """
    stmt = select(Patient).where(Patient.deleted_at.is_(None))

    if last_name:
        stmt = stmt.where(Patient.last_name.ilike(f"%{last_name}%"))

    if date_of_birth:
        stmt = stmt.where(Patient.date_of_birth == date_of_birth)

    if phone_number:
        # Normalize the search phone number for consistent matching.
        from app.schemas.patient import _validate_us_phone
        try:
            normalized = _validate_us_phone(phone_number)
            stmt = stmt.where(Patient.phone_number == normalized)
        except ValueError:
            # If the search phone is invalid, return empty results.
            return []

    stmt = stmt.order_by(Patient.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_patient(
    db: AsyncSession,
    patient_id: str,
    data: PatientUpdate,
) -> Optional[Patient]:
    """
    Update an existing patient with partial data.

    Only fields explicitly provided in the request body are updated.
    Soft-deleted records cannot be updated.

    Args:
        db: Active database session.
        patient_id: UUID of the patient to update.
        data: Validated partial update data.

    Returns:
        Updated Patient instance, or None if not found.
    """
    patient = await get_patient_by_id(db, patient_id)
    if patient is None:
        return None

    # Only update fields that were explicitly set in the request.
    update_data = data.model_dump(exclude_unset=True)

    for field_name, value in update_data.items():
        if field_name == "sex" and value is not None:
            value = SexEnum(value)
        setattr(patient, field_name, value)

    patient.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(patient)

    logger.info("Updated patient %s: fields=%s", patient_id, list(update_data.keys()))
    return patient


async def soft_delete_patient(
    db: AsyncSession,
    patient_id: str,
) -> Optional[Patient]:
    """
    Soft-delete a patient by setting deleted_at timestamp.

    The record remains in the database but is excluded from all
    standard queries. This is reversible by clearing deleted_at.

    Args:
        db: Active database session.
        patient_id: UUID of the patient to soft-delete.

    Returns:
        The soft-deleted Patient instance, or None if not found.
    """
    patient = await get_patient_by_id(db, patient_id)
    if patient is None:
        return None

    patient.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(patient)

    logger.info("Soft-deleted patient %s", patient_id)
    return patient


async def lookup_patient_by_phone(
    db: AsyncSession,
    phone_number: str,
) -> Optional[Patient]:
    """
    Find an existing patient by phone number (duplicate detection).

    Used by the voice agent on call connect to detect returning callers
    and offer to update their information instead of creating a duplicate.

    Args:
        db: Active database session.
        phone_number: Phone number to search (will be normalized to E.164).

    Returns:
        The most recently created matching Patient, or None.
    """
    from app.schemas.patient import _validate_us_phone

    try:
        normalized = _validate_us_phone(phone_number)
    except ValueError:
        return None

    stmt = (
        select(Patient)
        .where(
            Patient.phone_number == normalized,
            Patient.deleted_at.is_(None),
        )
        .order_by(Patient.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
