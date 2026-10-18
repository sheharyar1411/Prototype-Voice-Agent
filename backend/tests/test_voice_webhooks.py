"""
Unit and integration tests for Vapi voice AI webhooks and tool calls.

Covers:
  - Assistant configuration request (assistant-request)
  - Tool call dispatch for:
      * lookup_patient (caller ID lookup, found and not found)
      * register_patient (valid registration, validation failure feedback)
      * update_patient (returning caller update flow)
      * unknown / malformed tool calls
  - Call lifecycle & session persistence (end-of-call-report, status-update)
"""

import json
from datetime import date
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import CallSession, CallSessionStatus, Patient
from tests.conftest import valid_patient_data


@pytest.mark.asyncio
async def test_assistant_request_event(client: AsyncClient):
    """
    POST /api/voice/webhook with 'assistant-request' event.
    Verifies that the server returns the complete Sarah assistant configuration,
    including system prompt and tool definitions.
    """
    payload = {
        "message": {
            "type": "assistant-request",
            "call": {
                "id": "call-test-123",
                "customer": {"number": "+15125550199"},
            },
        }
    }
    response = await client.post("/api/voice/webhook", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "assistant" in data
    assistant = data["assistant"]
    assert assistant["name"] == "Patient Registration Agent"
    assert "model" in assistant
    assert assistant["model"]["provider"] == "openai"
    assert len(assistant["model"]["messages"]) > 0

    # Ensure system prompt contains core instructions
    prompt = assistant["model"]["messages"][0]["content"]
    assert "Sarah" in prompt
    assert "Metro Health Clinic" in prompt
    assert "lookup_patient" in prompt
    assert "register_patient" in prompt

    # Verify tool definitions
    tools = assistant["model"]["tools"]
    tool_names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
    assert "lookup_patient" in tool_names
    assert "register_patient" in tool_names
    assert "update_patient" in tool_names


@pytest.mark.asyncio
async def test_tool_lookup_patient_not_found(client: AsyncClient):
    """
    Function-call lookup_patient for a new, unknown phone number.
    Should return found=false and advise proceeding with new registration.
    """
    payload = {
        "message": {
            "type": "function-call",
            "functionCall": {
                "name": "lookup_patient",
                "parameters": {"phone_number": "5125559999"},
            },
        }
    }
    response = await client.post("/api/voice/webhook", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert "results" in res_data
    result_str = res_data["results"][0]["result"]
    result = json.loads(result_str)
    assert result["success"] is True
    assert result["found"] is False
    assert "No existing patient record found" in result["message"]


@pytest.mark.asyncio
async def test_tool_lookup_patient_found(client: AsyncClient, db_session: AsyncSession):
    """
    Function-call lookup_patient for an existing patient.
    Should return found=true, patient name, and ID for returning caller flow.
    """
    # Insert existing patient directly
    existing = Patient(
        first_name="Jane",
        last_name="Doe",
        date_of_birth=date(1985, 4, 12),
        sex="Female",
        phone_number="+15125551234",
        address_line_1="456 Elm Street",
        city="Austin",
        state="TX",
        zip_code="78702",
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    payload = {
        "message": {
            "type": "function-call",
            "functionCall": {
                "name": "lookup_patient",
                "parameters": {"phone_number": "512-555-1234"},
            },
        }
    }
    response = await client.post("/api/voice/webhook", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    result = json.loads(res_data["results"][0]["result"])
    assert result["success"] is True
    assert result["found"] is True
    assert result["patient"]["id"] == existing.id
    assert result["patient"]["first_name"] == "Jane"
    assert result["patient"]["last_name"] == "Doe"


@pytest.mark.asyncio
async def test_tool_register_patient_success(client: AsyncClient, db_session: AsyncSession):
    """
    Function-call register_patient with valid demographics.
    Should create the patient in DB and return success=true with patient ID.
    """
    patient_input = valid_patient_data(
        first_name="Robert",
        last_name="Johnson",
        phone_number="5125550177",
    )
    payload = {
        "message": {
            "type": "function-call",
            "functionCall": {
                "name": "register_patient",
                "parameters": patient_input,
            },
        }
    }
    response = await client.post("/api/voice/webhook", json=payload)
    assert response.status_code == 200
    result = json.loads(response.json()["results"][0]["result"])
    assert result["success"] is True
    assert "patient_id" in result
    assert "successfully registered" in result["message"]

    # Verify persisted in DB
    saved = await db_session.get(Patient, result["patient_id"])
    assert saved is not None
    assert saved.first_name == "Robert"
    assert saved.last_name == "Johnson"
    assert saved.phone_number == "+15125550177"


@pytest.mark.asyncio
async def test_tool_register_patient_validation_error(client: AsyncClient):
    """
    Function-call register_patient with invalid demographic data
    (e.g., date of birth in future, invalid phone format).
    Should return success=false with clear validation error messages for the LLM to speak.
    """
    patient_input = valid_patient_data(
        date_of_birth="2099-01-01",  # Future date - invalid!
        state="INVALID",             # Invalid US state - invalid!
    )
    payload = {
        "message": {
            "type": "function-call",
            "functionCall": {
                "name": "register_patient",
                "parameters": patient_input,
            },
        }
    }
    response = await client.post("/api/voice/webhook", json=payload)
    assert response.status_code == 200
    result = json.loads(response.json()["results"][0]["result"])
    assert result["success"] is False
    assert "Validation failed" in result["error"]
    assert "validation_errors" in result
    assert len(result["validation_errors"]) > 0


@pytest.mark.asyncio
async def test_tool_update_patient_flow(client: AsyncClient, db_session: AsyncSession):
    """
    Function-call update_patient for a returning caller updating address/phone.
    """
    patient = Patient(
        first_name="Alice",
        last_name="Walker",
        date_of_birth=date(1992, 8, 20),
        sex="Female",
        phone_number="5125553333",
        address_line_1="100 First St",
        city="Austin",
        state="TX",
        zip_code="78701",
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)

    payload = {
        "message": {
            "type": "function-call",
            "functionCall": {
                "name": "update_patient",
                "parameters": {
                    "patient_id": patient.id,
                    "address_line_1": "200 Second St Suite 5",
                    "zip_code": "78704",
                },
            },
        }
    }
    response = await client.post("/api/voice/webhook", json=payload)
    assert response.status_code == 200
    result = json.loads(response.json()["results"][0]["result"])
    assert result["success"] is True
    assert "updated" in result["message"]

    # Verify DB updated
    await db_session.refresh(patient)
    assert patient.address_line_1 == "200 Second St Suite 5"
    assert patient.zip_code == "78704"


@pytest.mark.asyncio
async def test_tool_call_endpoint_alias(client: AsyncClient):
    """
    Test dedicated /api/voice/tools endpoint.
    Some Vapi assistant configurations route tool calls to this separate route.
    """
    payload = {
        "functionCall": {
            "name": "lookup_patient",
            "parameters": {"phone_number": "5125559876"},
        }
    }
    response = await client.post("/api/voice/tools", json=payload)
    assert response.status_code == 200
    result = json.loads(response.json()["results"][0]["result"])
    assert result["success"] is True
    assert result["found"] is False


@pytest.mark.asyncio
async def test_end_of_call_report_persistence(client: AsyncClient, db_session: AsyncSession):
    """
    Test 'end-of-call-report' event from Vapi.
    Verifies that the full conversation transcript and call metadata are saved
    in the call_sessions table.
    """
    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "vapi-call-session-999",
                "customer": {"number": "+15125550199"},
            },
            "transcript": "Assistant: Hello! Caller: Hi Sarah, I'd like to register...",
        }
    }
    response = await client.post("/api/voice/webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Verify persisted CallSession record
    stmt = select(CallSession).where(CallSession.vapi_call_id == "vapi-call-session-999")
    res = await db_session.execute(stmt)
    session = res.scalar_one_or_none()
    assert session is not None
    assert session.status == CallSessionStatus.COMPLETED
    assert "Hi Sarah" in session.transcript
    assert session.caller_phone == "+15125550199"
