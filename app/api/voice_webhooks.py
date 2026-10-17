"""
Vapi voice AI webhook and tool-call handler.

FLOW MAP:
  Vapi assistant → HTTP POST webhooks → this router → patient_service → DB
  Vapi function call → /api/voice/tools → dispatch → structured result → Vapi

KEY DETAILS:
  - Handles Vapi server events: assistant-request, function-call, end-of-call-report
  - Tool dispatch maps function names to service layer operations
  - lookup_patient: finds returning callers by phone (duplicate detection)
  - register_patient: validates + creates a new patient record
  - update_patient: updates an existing patient (returning caller flow)
  - All tool responses include structured result or error for the LLM to relay
  - Call session tracking with transcript persistence on end-of-call
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.patient import CallSession, CallSessionStatus
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate
from app.services import patient_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["Voice AI"])


# ---------------------------------------------------------------------------
# Vapi assistant configuration (returned on assistant-request event)
# ---------------------------------------------------------------------------

def _build_assistant_config() -> dict[str, Any]:
    """
    Build the Vapi assistant configuration with system prompt and tool definitions.

    This is returned when Vapi sends an 'assistant-request' event, allowing
    dynamic assistant configuration per call.
    """
    return {
        "name": "Patient Registration Agent",
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": _get_system_prompt(),
                }
            ],
            "tools": _get_tool_definitions(),
            "temperature": 0.3,
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "sarah",
            "stability": 0.6,
            "similarityBoost": 0.8,
        },
        "firstMessage": (
            "Hello! Thank you for calling Metro Health Clinic. "
            "My name is Sarah, and I'll be helping you with your "
            "patient registration today. May I start by getting "
            "your first and last name?"
        ),
        "endCallMessage": (
            "Thank you for registering with Metro Health Clinic. "
            "We look forward to seeing you! Have a wonderful day."
        ),
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "en",
            "smartFormat": True,
        },
        "endCallFunctionEnabled": True,
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 600,
    }


def _get_system_prompt() -> str:
    """
    Return the full system prompt for the patient intake coordinator.

    Prompt engineering principles applied:
    - Clear role definition and clinic identity
    - Step-by-step collection order (required fields first, then optional)
    - Explicit confirmation loop with read-back protocol
    - Spelling correction handling ("D-A-V-I-S")
    - Validation error re-prompting instructions
    - Conversational pacing guidelines (calm, measured, one thought per turn)
    - Empathetic and professional tone throughout
    """
    return """You are Sarah, a warm and professional Patient Intake Coordinator at Metro Health Clinic. Your role is to collect patient demographic information over a phone call in a natural, conversational manner.

## Your Personality
- Warm, empathetic, and patient — never rush the caller
- Professional but approachable — use natural conversational language
- Speak at a calm, measured cadence; pause briefly between sentences
- After the caller finishes speaking, take a breath before responding
- One thought per turn, then let the caller respond
- If the caller seems confused or frustrated, acknowledge their feelings before continuing

## Registration Flow

### Step 1: Lookup Returning Caller
- When the call begins, IMMEDIATELY use the `lookup_patient` tool with the caller's phone number (if available from caller ID)
- If a record is found, greet them by name: "Welcome back, [Name]! I see we already have your information on file. Would you like to update anything?"
- If they want to update, ask which fields to change and use `update_patient`
- If no record is found, proceed with new registration

### Step 2: Collect Required Information (in this order)
1. **Full Name** — First and last name. If unusual spelling, ask them to spell it out letter by letter.
2. **Date of Birth** — Ask for month, day, and year. Confirm you heard correctly.
3. **Sex** — Ask sensitively: "For our medical records, how would you like us to record your sex? The options are Male, Female, Other, or you may decline to answer."
4. **Phone Number** — Confirm the number on file or ask for their preferred contact number.
5. **Mailing Address** — Street address, city, state, and ZIP code. Ask for each component clearly.

### Step 3: Offer Optional Information
After collecting all required fields, ask:
"I have all the essential information. Would you also like to provide any of the following? It's completely optional:
- Email address
- Insurance information (provider name and member ID)
- Emergency contact (name and phone number)
- Preferred language for communication"

Only collect what the caller volunteers. Don't push if they decline.

### Step 4: Read Back and Confirm
Read back ALL collected information clearly and ask for confirmation:
"Let me read back what I have to make sure everything is correct..."

- If the caller corrects a field (e.g., "Actually, my last name is spelled D-A-V-I-S"), acknowledge and update
- After all corrections, read back the corrected information again
- Only proceed to save when the caller explicitly confirms ("Yes, that's correct" or similar)

### Step 5: Save the Record
- Use the `register_patient` tool with all collected data
- If successful, confirm: "Wonderful! You're all registered, [First Name]. Your patient ID is [ID]."
- If there's a validation error, explain the issue in plain language and ask for the correct information

## Important Rules
- NEVER fabricate or assume data — always ask the caller
- If you can't understand something, ask them to repeat or spell it out
- For dates, always confirm: "Just to make sure, that's [Month] [Day], [Year], correct?"
- For phone numbers, read back digit by digit
- Always get explicit verbal confirmation before saving
- If the caller wants to stop midway, be understanding and let them know they can call back anytime
- Handle one field at a time — don't overwhelm with multiple questions"""


def _get_tool_definitions() -> list[dict[str, Any]]:
    """
    Return Vapi-compatible tool/function definitions for the assistant.

    These map directly to the handlers in _dispatch_tool_call().
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_patient",
                "description": (
                    "Look up an existing patient record by phone number. "
                    "Use this at the start of the call to check if the caller "
                    "is a returning patient."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "The caller's phone number in any US format.",
                        },
                    },
                    "required": ["phone_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "register_patient",
                "description": (
                    "Register a new patient with their demographic information. "
                    "Only call this AFTER the caller has confirmed all their details. "
                    "All required fields must be provided."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {
                            "type": "string",
                            "description": "Patient's first name.",
                        },
                        "last_name": {
                            "type": "string",
                            "description": "Patient's last name.",
                        },
                        "date_of_birth": {
                            "type": "string",
                            "description": "Date of birth in YYYY-MM-DD format.",
                        },
                        "sex": {
                            "type": "string",
                            "enum": ["Male", "Female", "Other", "Decline to Answer"],
                            "description": "Patient's sex for medical records.",
                        },
                        "phone_number": {
                            "type": "string",
                            "description": "Patient's contact phone number.",
                        },
                        "address_line_1": {
                            "type": "string",
                            "description": "Street address.",
                        },
                        "city": {
                            "type": "string",
                            "description": "City name.",
                        },
                        "state": {
                            "type": "string",
                            "description": "2-letter US state code (e.g., TX, CA).",
                        },
                        "zip_code": {
                            "type": "string",
                            "description": "5-digit or ZIP+4 US ZIP code.",
                        },
                        "email": {
                            "type": "string",
                            "description": "Email address (optional).",
                        },
                        "address_line_2": {
                            "type": "string",
                            "description": "Apartment, suite, unit (optional).",
                        },
                        "insurance_provider": {
                            "type": "string",
                            "description": "Insurance company name (optional).",
                        },
                        "insurance_member_id": {
                            "type": "string",
                            "description": "Insurance member/subscriber ID (optional).",
                        },
                        "preferred_language": {
                            "type": "string",
                            "description": "Preferred language (optional, default English).",
                        },
                        "emergency_contact_name": {
                            "type": "string",
                            "description": "Emergency contact full name (optional).",
                        },
                        "emergency_contact_phone": {
                            "type": "string",
                            "description": "Emergency contact phone number (optional).",
                        },
                    },
                    "required": [
                        "first_name", "last_name", "date_of_birth", "sex",
                        "phone_number", "address_line_1", "city", "state", "zip_code",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_patient",
                "description": (
                    "Update an existing patient's information. Use this for returning "
                    "callers who want to correct or update their demographics. "
                    "Only include fields that need to be changed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {
                            "type": "string",
                            "description": "The UUID of the patient to update.",
                        },
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "date_of_birth": {"type": "string", "description": "YYYY-MM-DD format."},
                        "sex": {
                            "type": "string",
                            "enum": ["Male", "Female", "Other", "Decline to Answer"],
                        },
                        "phone_number": {"type": "string"},
                        "address_line_1": {"type": "string"},
                        "city": {"type": "string"},
                        "state": {"type": "string"},
                        "zip_code": {"type": "string"},
                        "email": {"type": "string"},
                        "address_line_2": {"type": "string"},
                        "insurance_provider": {"type": "string"},
                        "insurance_member_id": {"type": "string"},
                        "preferred_language": {"type": "string"},
                        "emergency_contact_name": {"type": "string"},
                        "emergency_contact_phone": {"type": "string"},
                    },
                    "required": ["patient_id"],
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Main Vapi webhook endpoint.

    Handles all server-side events from Vapi:
    - assistant-request: returns dynamic assistant configuration
    - function-call: dispatches tool calls to service layer
    - end-of-call-report: persists transcript and finalizes session
    - status-update: tracks call lifecycle state changes

    Vapi expects specific response shapes for each event type.
    """
    body = await request.json()
    message = body.get("message", {})
    event_type = message.get("type", "")

    logger.info("Vapi webhook event: %s", event_type)

    if event_type == "assistant-request":
        return {"assistant": _build_assistant_config()}

    elif event_type == "function-call":
        return await _handle_function_call(message, db)

    elif event_type == "end-of-call-report":
        await _handle_end_of_call(message, db)
        return {"status": "ok"}

    elif event_type == "status-update":
        await _handle_status_update(message, db)
        return {"status": "ok"}

    else:
        logger.debug("Unhandled Vapi event type: %s", event_type)
        return {"status": "ok"}


@router.post("/tools")
async def vapi_tool_call(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Dedicated tool/function-call endpoint for Vapi server URL configuration.

    Some Vapi setups send function calls to a separate URL rather than
    the main webhook. This endpoint handles the same dispatch logic.
    """
    body = await request.json()
    message = body.get("message", body)
    return await _handle_function_call(message, db)


# ---------------------------------------------------------------------------
# Internal handlers
# ---------------------------------------------------------------------------

async def _handle_function_call(
    message: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Dispatch a Vapi function call to the appropriate service handler.

    Returns a structured result that Vapi forwards to the LLM.
    """
    function_call = message.get("functionCall", {})
    fn_name = function_call.get("name", "")
    fn_args = function_call.get("parameters", {})

    logger.info("Tool call: %s args=%s", fn_name, json.dumps(fn_args, default=str))

    try:
        result = await _dispatch_tool_call(fn_name, fn_args, db)
    except Exception as exc:
        logger.exception("Tool call '%s' failed", fn_name)
        result = {
            "success": False,
            "error": f"An internal error occurred: {type(exc).__name__}: {exc}",
        }

    return {"results": [{"result": json.dumps(result, default=str)}]}


async def _dispatch_tool_call(
    name: str,
    args: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Map function name to service handler and execute.

    Each handler returns a dict that is serialized to JSON and sent
    back to Vapi as the function call result.
    """
    if name == "lookup_patient":
        return await _tool_lookup_patient(args, db)
    elif name == "register_patient":
        return await _tool_register_patient(args, db)
    elif name == "update_patient":
        return await _tool_update_patient(args, db)
    else:
        return {"success": False, "error": f"Unknown function: {name}"}


async def _tool_lookup_patient(
    args: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """Look up a patient by phone number for returning-caller detection."""
    phone = args.get("phone_number", "")
    if not phone:
        return {"success": False, "error": "Phone number is required."}

    patient = await patient_service.lookup_patient_by_phone(db, phone)
    if patient is None:
        return {
            "success": True,
            "found": False,
            "message": "No existing patient record found for this phone number.",
        }

    return {
        "success": True,
        "found": True,
        "patient": PatientResponse.model_validate(patient).model_dump(mode="json"),
        "message": (
            f"Found existing patient: {patient.first_name} {patient.last_name}. "
            "Ask if they would like to update their information."
        ),
    }


async def _tool_register_patient(
    args: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """Validate and create a new patient record from voice-collected data."""
    try:
        data = PatientCreate(**args)
    except Exception as exc:
        # Extract clear validation error messages for the LLM to relay.
        error_messages = _extract_validation_errors(exc)
        return {
            "success": False,
            "error": "Validation failed. Please correct the following:",
            "validation_errors": error_messages,
        }

    patient = await patient_service.create_patient(db, data)
    return {
        "success": True,
        "patient_id": patient.id,
        "message": (
            f"Patient {patient.first_name} {patient.last_name} has been "
            f"successfully registered with ID {patient.id}."
        ),
    }


async def _tool_update_patient(
    args: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """Update an existing patient record (returning caller flow)."""
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return {"success": False, "error": "Patient ID is required for updates."}

    if not args:
        return {"success": False, "error": "No fields provided to update."}

    try:
        data = PatientUpdate(**args)
    except Exception as exc:
        error_messages = _extract_validation_errors(exc)
        return {
            "success": False,
            "error": "Validation failed for update:",
            "validation_errors": error_messages,
        }

    patient = await patient_service.update_patient(db, patient_id, data)
    if patient is None:
        return {"success": False, "error": f"Patient {patient_id} not found."}

    return {
        "success": True,
        "message": f"Patient {patient.first_name} {patient.last_name}'s record has been updated.",
        "updated_fields": list(args.keys()),
    }


async def _handle_end_of_call(
    message: dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Persist call transcript and finalize the call session on call end.

    Vapi sends the full conversation transcript in the end-of-call-report.
    """
    call_data = message.get("call", {})
    call_id = call_data.get("id")
    transcript = message.get("transcript", "")
    caller_phone = (
        call_data.get("customer", {}).get("number", "")
        if call_data.get("customer")
        else ""
    )

    # Create or update the call session record.
    session = CallSession(
        caller_phone=caller_phone or None,
        status=CallSessionStatus.COMPLETED,
        transcript=transcript if isinstance(transcript, str) else json.dumps(transcript),
        vapi_call_id=call_id,
        ended_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()

    logger.info(
        "Call session %s completed (vapi_call_id=%s, caller=%s)",
        session.id, call_id, caller_phone,
    )


async def _handle_status_update(
    message: dict[str, Any],
    db: AsyncSession,
) -> None:
    """Handle Vapi call status change events for session tracking."""
    status = message.get("status", "")
    call_data = message.get("call", {})
    call_id = call_data.get("id", "")

    logger.info("Call %s status: %s", call_id, status)

    if status == "in-progress":
        caller_phone = (
            call_data.get("customer", {}).get("number", "")
            if call_data.get("customer")
            else ""
        )
        session = CallSession(
            caller_phone=caller_phone or None,
            status=CallSessionStatus.IN_PROGRESS,
            vapi_call_id=call_id,
        )
        db.add(session)
        await db.flush()
        logger.info("Call session started: %s", session.id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_validation_errors(exc: Exception) -> list[str]:
    """
    Extract human-readable validation error messages from a Pydantic exception.

    Returns a list of clear error strings that the LLM can relay to the caller.
    """
    messages: list[str] = []
    if hasattr(exc, "errors"):
        for err in exc.errors():
            loc = " → ".join(str(l) for l in err.get("loc", []))
            msg = err.get("msg", str(exc))
            messages.append(f"{loc}: {msg}" if loc else msg)
    else:
        messages.append(str(exc))
    return messages
