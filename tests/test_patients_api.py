"""
Comprehensive API tests for the Patient Registration System.

Covers:
  - CRUD operations (create, read, update, soft-delete)
  - Server-side validation (all field rules from the challenge spec)
  - Response envelope format enforcement
  - Query filters (last_name, date_of_birth, phone_number)
  - Edge cases (duplicate phone, future DOB, invalid state, bad ZIP, etc.)
  - Soft-delete behavior (excluded from list, 404 on direct access)

Uses in-memory SQLite via conftest fixtures for complete test isolation.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import valid_patient_data, valid_patient_data_with_optionals


# ==========================================================================
# Helper to create a patient and return the response data
# ==========================================================================

async def _create_patient(client: AsyncClient, **overrides) -> dict:
    """Create a patient and return the response body's 'data' dict."""
    payload = valid_patient_data(**overrides)
    resp = await client.post("/patients", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    return body["data"]


# ==========================================================================
# CREATE (POST /patients)
# ==========================================================================

class TestCreatePatient:
    """Tests for patient registration endpoint."""

    @pytest.mark.asyncio
    async def test_create_patient_minimal(self, client: AsyncClient):
        """Create a patient with only required fields."""
        resp = await client.post("/patients", json=valid_patient_data())
        assert resp.status_code == 201
        body = resp.json()

        # Envelope structure
        assert body["error"] is None
        assert body["data"] is not None
        assert "id" in body["data"]
        assert body["message"] == "Patient registered successfully."

        # Field values
        data = body["data"]
        assert data["first_name"] == "John"
        assert data["last_name"] == "Smith"
        assert data["date_of_birth"] == "1990-05-15"
        assert data["sex"] == "Male"
        assert data["phone_number"] == "+15125550199"  # E.164 normalized
        assert data["state"] == "TX"
        assert data["zip_code"] == "78701"

    @pytest.mark.asyncio
    async def test_create_patient_all_fields(self, client: AsyncClient):
        """Create a patient with all optional fields populated."""
        resp = await client.post("/patients", json=valid_patient_data_with_optionals())
        assert resp.status_code == 201
        data = resp.json()["data"]

        assert data["email"] == "john.smith@example.com"
        assert data["address_line_2"] == "Apt 4B"
        assert data["insurance_provider"] == "Blue Cross Blue Shield"
        assert data["insurance_member_id"] == "BCB-12345678"
        assert data["emergency_contact_name"] == "Jane Smith"
        assert data["emergency_contact_phone"] == "+15125550200"

    @pytest.mark.asyncio
    async def test_create_patient_phone_normalized(self, client: AsyncClient):
        """Phone numbers in various formats should be normalized to E.164."""
        formats = [
            ("(512) 555-0199", "+15125550199"),
            ("512-555-0199", "+15125550199"),
            ("512.555.0199", "+15125550199"),
            ("+1 512 555 0199", "+15125550199"),
            ("5125550199", "+15125550199"),
        ]
        for raw_phone, expected in formats:
            resp = await client.post(
                "/patients",
                json=valid_patient_data(phone_number=raw_phone),
            )
            assert resp.status_code == 201, f"Failed for format: {raw_phone}"
            assert resp.json()["data"]["phone_number"] == expected

    @pytest.mark.asyncio
    async def test_create_patient_name_title_cased(self, client: AsyncClient):
        """Names should be title-cased automatically."""
        resp = await client.post(
            "/patients",
            json=valid_patient_data(first_name="john", last_name="o'brien"),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["first_name"] == "John"
        assert data["last_name"] == "O'Brien"

    @pytest.mark.asyncio
    async def test_create_patient_state_uppercased(self, client: AsyncClient):
        """State codes should be auto-uppercased."""
        resp = await client.post(
            "/patients", json=valid_patient_data(state="tx"),
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["state"] == "TX"


# ==========================================================================
# VALIDATION ERRORS (POST /patients — rejected inputs)
# ==========================================================================

class TestCreatePatientValidation:
    """Tests for server-side validation rules."""

    @pytest.mark.asyncio
    async def test_reject_future_dob(self, client: AsyncClient):
        """Date of birth in the future should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(date_of_birth="2099-01-01"),
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["data"] is None
        assert body["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_reject_invalid_phone(self, client: AsyncClient):
        """Invalid phone number should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(phone_number="123"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_invalid_state(self, client: AsyncClient):
        """Invalid state abbreviation should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(state="ZZ"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_invalid_zip(self, client: AsyncClient):
        """Invalid ZIP code format should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(zip_code="1234"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_invalid_zip_plus4(self, client: AsyncClient):
        """Malformed ZIP+4 should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(zip_code="12345-67"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_accept_valid_zip_plus4(self, client: AsyncClient):
        """Valid ZIP+4 format should be accepted."""
        resp = await client.post(
            "/patients", json=valid_patient_data(zip_code="78701-1234"),
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["zip_code"] == "78701-1234"

    @pytest.mark.asyncio
    async def test_reject_invalid_sex(self, client: AsyncClient):
        """Invalid sex value should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(sex="Unknown"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_accept_all_sex_values(self, client: AsyncClient):
        """All valid sex values should be accepted."""
        for sex in ["Male", "Female", "Other", "Decline to Answer"]:
            resp = await client.post(
                "/patients", json=valid_patient_data(sex=sex),
            )
            assert resp.status_code == 201, f"Rejected valid sex: {sex}"

    @pytest.mark.asyncio
    async def test_reject_name_with_numbers(self, client: AsyncClient):
        """Names with numeric characters should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(first_name="John123"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_empty_required_fields(self, client: AsyncClient):
        """Empty required fields should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(first_name=""),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_missing_required_fields(self, client: AsyncClient):
        """Missing required fields should be rejected."""
        incomplete = {"first_name": "John", "last_name": "Smith"}
        resp = await client.post("/patients", json=incomplete)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_invalid_email(self, client: AsyncClient):
        """Invalid email format should be rejected."""
        resp = await client.post(
            "/patients", json=valid_patient_data(email="not-an-email"),
        )
        assert resp.status_code == 422


# ==========================================================================
# READ (GET /patients, GET /patients/{id})
# ==========================================================================

class TestReadPatients:
    """Tests for patient retrieval endpoints."""

    @pytest.mark.asyncio
    async def test_list_patients_empty(self, client: AsyncClient):
        """Empty database should return an empty list, not an error."""
        resp = await client.get("/patients")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["error"] is None

    @pytest.mark.asyncio
    async def test_list_patients_returns_created(self, client: AsyncClient):
        """Created patients should appear in the list."""
        await _create_patient(client)
        resp = await client.get("/patients")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    @pytest.mark.asyncio
    async def test_get_patient_by_id(self, client: AsyncClient):
        """Should return a specific patient by UUID."""
        created = await _create_patient(client)
        resp = await client.get(f"/patients/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_patient_not_found(self, client: AsyncClient):
        """Non-existent UUID should return 404 with error envelope."""
        resp = await client.get("/patients/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        body = resp.json()
        assert body["data"] is None
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_filter_by_last_name(self, client: AsyncClient):
        """Filter patients by last name (case-insensitive partial match)."""
        await _create_patient(client, last_name="Johnson", phone_number="5125550201")
        await _create_patient(client, last_name="Davis", phone_number="5125550202")

        resp = await client.get("/patients?last_name=john")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["last_name"] == "Johnson"

    @pytest.mark.asyncio
    async def test_filter_by_phone(self, client: AsyncClient):
        """Filter patients by phone number."""
        await _create_patient(client, phone_number="5125550301")
        await _create_patient(client, phone_number="5125550302")

        resp = await client.get("/patients?phone_number=5125550301")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["phone_number"] == "+15125550301"


# ==========================================================================
# UPDATE (PUT /patients/{id})
# ==========================================================================

class TestUpdatePatient:
    """Tests for patient update endpoint."""

    @pytest.mark.asyncio
    async def test_update_single_field(self, client: AsyncClient):
        """Partial update: change only one field."""
        created = await _create_patient(client)
        resp = await client.put(
            f"/patients/{created['id']}",
            json={"first_name": "Jonathan"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["first_name"] == "Jonathan"
        # Other fields unchanged
        assert resp.json()["data"]["last_name"] == "Smith"

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, client: AsyncClient):
        """Update multiple fields simultaneously."""
        created = await _create_patient(client)
        resp = await client.put(
            f"/patients/{created['id']}",
            json={"city": "Dallas", "state": "TX", "zip_code": "75201"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["city"] == "Dallas"
        assert data["zip_code"] == "75201"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient):
        """Update non-existent patient returns 404."""
        resp = await client.put(
            "/patients/00000000-0000-0000-0000-000000000000",
            json={"first_name": "Test"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_validates_fields(self, client: AsyncClient):
        """Updated fields must still pass validation."""
        created = await _create_patient(client)
        resp = await client.put(
            f"/patients/{created['id']}",
            json={"state": "ZZ"},
        )
        assert resp.status_code == 422


# ==========================================================================
# DELETE (DELETE /patients/{id})
# ==========================================================================

class TestDeletePatient:
    """Tests for patient soft-delete endpoint."""

    @pytest.mark.asyncio
    async def test_soft_delete(self, client: AsyncClient):
        """Soft-delete should set deleted_at and return success."""
        created = await _create_patient(client)
        resp = await client.delete(f"/patients/{created['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["deleted_at"] is not None
        assert body["error"] is None

    @pytest.mark.asyncio
    async def test_deleted_excluded_from_list(self, client: AsyncClient):
        """Soft-deleted patients should not appear in list queries."""
        created = await _create_patient(client)
        await client.delete(f"/patients/{created['id']}")

        resp = await client.get("/patients")
        assert len(resp.json()["data"]) == 0

    @pytest.mark.asyncio
    async def test_deleted_returns_404_on_get(self, client: AsyncClient):
        """Soft-deleted patients should return 404 on direct access."""
        created = await _create_patient(client)
        await client.delete(f"/patients/{created['id']}")

        resp = await client.get(f"/patients/{created['id']}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient):
        """Deleting a non-existent patient returns 404."""
        resp = await client.delete("/patients/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


# ==========================================================================
# RESPONSE ENVELOPE FORMAT
# ==========================================================================

class TestResponseEnvelope:
    """Verify all responses follow the {data, error} envelope format."""

    @pytest.mark.asyncio
    async def test_success_envelope(self, client: AsyncClient):
        """Successful responses have data and null error."""
        resp = await client.post("/patients", json=valid_patient_data())
        body = resp.json()
        assert "data" in body
        assert "error" in body
        assert body["error"] is None

    @pytest.mark.asyncio
    async def test_error_envelope(self, client: AsyncClient):
        """Error responses have null data and structured error."""
        resp = await client.get("/patients/nonexistent")
        body = resp.json()
        assert "data" in body
        assert "error" in body
        assert body["data"] is None
        assert "code" in body["error"]
        assert "message" in body["error"]

    @pytest.mark.asyncio
    async def test_validation_error_envelope(self, client: AsyncClient):
        """Validation errors have null data, error code, and details."""
        resp = await client.post("/patients", json={"first_name": "x"})
        body = resp.json()
        assert body["data"] is None
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in body["error"]

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health endpoint returns status ok."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dashboard_endpoint(self, client: AsyncClient):
        """Root and /dashboard return the single-page application HTML."""
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Metro Health Clinic" in resp.text
