"""
Pydantic schemas for patient data validation, serialization, and API contracts.

FLOW MAP:
  Incoming JSON body → PatientCreate / PatientUpdate (validation) → service layer
  DB row → PatientResponse (serialization) → JSON response envelope

KEY DETAILS:
  - Strict server-side validation for ALL demographic fields
  - Custom validators for US phone numbers, state codes, ZIP codes, and DOB
  - Name fields allow alphabetic chars plus hyphens, apostrophes, spaces
  - Phone numbers normalized to +1XXXXXXXXXX using the phonenumbers library
  - Date of birth must be a valid past date
  - PatientUpdate makes all fields optional for partial updates (PATCH semantics)
"""

import re
from datetime import date, datetime
from typing import Optional

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Valid 2-letter US state abbreviations (USPS standard).
US_STATE_CODES: set[str] = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    # Territories
    "DC", "PR", "VI", "GU", "AS", "MP",
}

#: Regex for valid person names: letters, hyphens, apostrophes, spaces.
NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z' -]{0,49}$")

#: Regex for US ZIP codes: 5 digits or ZIP+4 (e.g. 12345 or 12345-6789).
ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")

#: Allowed sex/gender values per the challenge specification.
ALLOWED_SEX_VALUES: set[str] = {"Male", "Female", "Other", "Decline to Answer"}


# ---------------------------------------------------------------------------
# Shared field validators
# ---------------------------------------------------------------------------

def _validate_us_phone(value: str) -> str:
    """
    Parse and normalize a US phone number to E.164 format (+1XXXXXXXXXX).

    Raises ValueError with a clear message if the number is invalid.
    """
    if not value:
        raise ValueError("Phone number is required.")

    try:
        parsed = phonenumbers.parse(value, "US")
    except phonenumbers.NumberParseException as exc:
        raise ValueError(
            f"Invalid phone number format: {exc}. "
            "Please provide a valid 10-digit US phone number."
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(
            f"'{value}' is not a valid US phone number. "
            "Please provide a 10-digit number (e.g. 512-555-0199)."
        )

    # Normalize to E.164: +12125550199
    return phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.E164
    )


def _validate_name(value: str, field_name: str) -> str:
    """Validate and title-case a person name field."""
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} is required.")
    if len(value) > 50:
        raise ValueError(f"{field_name} must be 50 characters or fewer.")
    if not NAME_PATTERN.match(value):
        raise ValueError(
            f"{field_name} may only contain letters, hyphens, "
            "apostrophes, and spaces."
        )
    return value.title()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class PatientCreate(BaseModel):
    """
    Schema for creating a new patient record.

    All required fields must pass strict validation. Optional fields
    are validated only when provided.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # Required fields
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str

    # Optional fields
    email: Optional[EmailStr] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    # --- Field Validators ---

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        return _validate_name(v, "First name")

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, v: str) -> str:
        return _validate_name(v, "Last name")

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: date) -> date:
        if v > date.today():
            raise ValueError(
                "Date of birth cannot be in the future. "
                f"Received: {v.isoformat()}"
            )
        # Sanity check: reject dates more than 150 years ago.
        min_year = date.today().year - 150
        if v.year < min_year:
            raise ValueError(
                f"Date of birth year ({v.year}) is unreasonably far in the past."
            )
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: str) -> str:
        # Normalize casing for matching.
        normalized = v.strip().title()
        # Special case for "Decline to Answer" (title-case would produce
        # "Decline To Answer" but we want to match both).
        for allowed in ALLOWED_SEX_VALUES:
            if normalized.lower() == allowed.lower():
                return allowed
        raise ValueError(
            f"Sex must be one of: {', '.join(sorted(ALLOWED_SEX_VALUES))}. "
            f"Received: '{v}'"
        )

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_us_phone(v)

    @field_validator("address_line_1")
    @classmethod
    def validate_address(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Address line 1 is required.")
        if len(v) > 255:
            raise ValueError("Address line 1 must be 255 characters or fewer.")
        return v

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("City is required.")
        if len(v) > 100:
            raise ValueError("City must be 100 characters or fewer.")
        return v.title()

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in US_STATE_CODES:
            raise ValueError(
                f"'{v}' is not a valid US state abbreviation. "
                "Use 2-letter codes (e.g. TX, CA, NY)."
            )
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: str) -> str:
        v = v.strip()
        if not ZIP_PATTERN.match(v):
            raise ValueError(
                f"'{v}' is not a valid US ZIP code. "
                "Use 5-digit (12345) or ZIP+4 (12345-6789) format."
            )
        return v

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        return _validate_us_phone(v)

    @field_validator("emergency_contact_name")
    @classmethod
    def validate_emergency_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        return _validate_name(v, "Emergency contact name")

    @field_validator("insurance_provider")
    @classmethod
    def validate_insurance_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if len(v) > 100:
            raise ValueError("Insurance provider must be 100 characters or fewer.")
        return v

    @field_validator("insurance_member_id")
    @classmethod
    def validate_insurance_member_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if len(v) > 100:
            raise ValueError("Insurance member ID must be 100 characters or fewer.")
        return v


class PatientUpdate(BaseModel):
    """
    Schema for partial patient updates (PUT/PATCH).

    All fields are optional — only provided fields are updated.
    The same validation rules apply to any field that is supplied.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    # Reuse the same validators — they already handle None gracefully
    # for optional fields. For required-in-create fields that are optional
    # here, we only validate when a value is actually provided.

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: Optional[str]) -> Optional[str]:
        return _validate_name(v, "First name") if v else v

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, v: Optional[str]) -> Optional[str]:
        return _validate_name(v, "Last name") if v else v

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return v
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        min_year = date.today().year - 150
        if v.year < min_year:
            raise ValueError(f"Date of birth year ({v.year}) is unreasonably old.")
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        for allowed in ALLOWED_SEX_VALUES:
            if v.strip().lower() == allowed.lower():
                return allowed
        raise ValueError(
            f"Sex must be one of: {', '.join(sorted(ALLOWED_SEX_VALUES))}."
        )

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return _validate_us_phone(v) if v else v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if v not in US_STATE_CODES:
            raise ValueError(f"'{v}' is not a valid US state abbreviation.")
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not ZIP_PATTERN.match(v):
            raise ValueError(f"'{v}' is not a valid US ZIP code.")
        return v

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        return _validate_us_phone(v)

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> "PatientUpdate":
        """Ensure the update payload is not completely empty."""
        values = self.model_dump(exclude_unset=True)
        if not values:
            raise ValueError("At least one field must be provided for update.")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PatientResponse(BaseModel):
    """
    Schema for patient data returned in API responses.

    Maps directly from the ORM model with all fields serialized.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str
    email: Optional[str] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("sex", mode="before")
    @classmethod
    def serialize_sex_enum(cls, v):
        """Convert SexEnum to its string value for JSON serialization."""
        if hasattr(v, "value"):
            return v.value
        return v


class CallSessionResponse(BaseModel):
    """Schema for call session data returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    caller_phone: Optional[str] = None
    patient_id: Optional[str] = None
    status: str
    transcript: Optional[str] = None
    vapi_call_id: Optional[str] = None
    created_at: datetime
    ended_at: Optional[datetime] = None

    @field_validator("status", mode="before")
    @classmethod
    def serialize_status_enum(cls, v):
        """Convert CallSessionStatus to its string value for JSON serialization."""
        if hasattr(v, "value"):
            return v.value
        return v
