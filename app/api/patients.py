"""
Patient REST API endpoints.

FLOW MAP:
  HTTP request → FastAPI router → patient_service → DB → response envelope

ENDPOINTS:
  GET    /patients        — List all patients (with optional filters)
  GET    /patients/{id}   — Get a single patient by UUID
  POST   /patients        — Create a new patient record
  PUT    /patients/{id}   — Update patient (partial updates supported)
  DELETE /patients/{id}   — Soft-delete a patient record

KEY DETAILS:
  - All responses use the standardized {"data": ..., "error": ...} envelope
  - Server-side validation via Pydantic schemas (never trust LLM output alone)
  - Query filters: ?last_name=, ?date_of_birth=, ?phone_number=
  - DELETE is a soft-delete (sets deleted_at, does not remove the row)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.schemas.patient import (
    PatientCreate,
    PatientResponse,
    PatientUpdate,
)
from app.services import patient_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("")
async def list_patients(
    last_name: Optional[str] = Query(
        None,
        description="Filter by last name (case-insensitive partial match).",
    ),
    date_of_birth: Optional[str] = Query(
        None,
        description="Filter by date of birth (YYYY-MM-DD format).",
    ),
    phone_number: Optional[str] = Query(
        None,
        description="Filter by phone number (any common US format).",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    List all active (non-deleted) patients.

    Supports optional query filters for last_name, date_of_birth,
    and phone_number. Results are ordered by most recently created.
    """
    patients = await patient_service.list_patients(
        db,
        last_name=last_name,
        date_of_birth=date_of_birth,
        phone_number=phone_number,
    )
    return success_response(
        data=[PatientResponse.model_validate(p).model_dump(mode="json") for p in patients],
    )


@router.get("/{patient_id}")
async def get_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single patient by their UUID.

    Returns 404 if the patient does not exist or has been soft-deleted.
    """
    patient = await patient_service.get_patient_by_id(db, patient_id)
    if patient is None:
        return error_response(
            message=f"Patient with ID '{patient_id}' not found.",
            status_code=404,
            code="NOT_FOUND",
        )
    return success_response(
        data=PatientResponse.model_validate(patient).model_dump(mode="json"),
    )


@router.post("", status_code=201)
async def create_patient(
    payload: PatientCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new patient record.

    All required demographic fields are validated server-side.
    Phone numbers are normalized to E.164 format (+1XXXXXXXXXX).
    Returns the created record with its generated UUID.
    """
    patient = await patient_service.create_patient(db, payload)
    return success_response(
        data=PatientResponse.model_validate(patient).model_dump(mode="json"),
        status_code=201,
        message="Patient registered successfully.",
    )


@router.put("/{patient_id}")
async def update_patient(
    patient_id: str,
    payload: PatientUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing patient's demographics.

    Supports partial updates — only fields included in the request
    body are modified. The same validation rules apply.
    Returns 404 if the patient does not exist or is soft-deleted.
    """
    patient = await patient_service.update_patient(db, patient_id, payload)
    if patient is None:
        return error_response(
            message=f"Patient with ID '{patient_id}' not found.",
            status_code=404,
            code="NOT_FOUND",
        )
    return success_response(
        data=PatientResponse.model_validate(patient).model_dump(mode="json"),
        message="Patient updated successfully.",
    )


@router.delete("/{patient_id}")
async def delete_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete a patient record.

    Sets the deleted_at timestamp; the record is excluded from
    subsequent queries but remains in the database for audit purposes.
    Returns 404 if the patient does not exist or is already deleted.
    """
    patient = await patient_service.soft_delete_patient(db, patient_id)
    if patient is None:
        return error_response(
            message=f"Patient with ID '{patient_id}' not found.",
            status_code=404,
            code="NOT_FOUND",
        )
    return success_response(
        data={"id": patient.id, "deleted_at": patient.deleted_at.isoformat()},
        message="Patient record soft-deleted.",
    )
