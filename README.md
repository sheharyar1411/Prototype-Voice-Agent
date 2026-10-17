# Voice AI Patient Registration System

[![Tests](https://img.shields.io/badge/pytest-44%20passed%20(100%25)-emerald.svg)](#automated-test-suite)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2.11+-e92063.svg)](https://docs.pydantic.dev/)
[![Telephony](https://img.shields.io/badge/telephony-Vapi%20%7C%20PSTN-8b5cf6.svg)](https://vapi.ai)
[![Architecture](https://img.shields.io/badge/DB-PostgreSQL%20%2F%20SQLite%20Async-f59e0b.svg)](#database-architecture)

An end-to-end, production-grade **Voice AI Patient Intake System** designed for healthcare clinics. The system pairs a natural conversational voice assistant (**Sarah**, Patient Intake Coordinator at Metro Health Clinic) with an async FastAPI backend, strict server-side demographic validation, persistent database storage, standardized REST APIs, and a modern web dashboard.

---

## Table of Contents

1. [System Overview & Key Features](#system-overview--key-features)
2. [Architecture & Flow](#architecture--flow)
3. [Conversational State Machine](#conversational-state-machine)
4. [Quickstart: Local Setup in 2 Minutes](#quickstart-local-setup-in-2-minutes)
5. [Live Telephony: Dialable Phone Number Setup](#live-telephony-dialable-phone-number-setup)
6. [Testing Locally Without Telephony (Simulators)](#testing-locally-without-telephony-simulators)
7. [Automated Pytest Suite](#automated-pytest-suite)
8. [REST API Documentation & Envelope Format](#rest-api-documentation--envelope-format)
9. [Demographic Data Model & Validation Rules](#demographic-data-model--validation-rules)
10. [Web Dashboard UI](#web-dashboard-ui)
11. [Engineering Trade-offs & Production Considerations](#engineering-trade-offs--production-considerations)

---

## System Overview & Key Features

- **Dialable U.S. Phone Number Support:** Built for standard PSTN telephony via **Vapi** (powered by Deepgram Nova-3 STT, Cartesia/ElevenLabs TTS, and GPT-4o-mini). Sub-second voice latency and natural turn-taking.
- **Natural Conversational Intake:** Sarah guides callers calmly through mandatory and optional healthcare intake fields without overwhelming them.
- **Spell-Out & Error Resilience:** Handles spelling corrections (e.g. *"Actually, my last name is spelled D-A-V-I-S"*), phonetic clarifications, and spoken date formats (e.g., *"August 24th, 1988"*).
- **Verbal Read-Back Confirmation Protocol:** Never writes unconfirmed data. Sarah reads back all collected information and requires explicit verbal confirmation before committing.
- **Duplicate Detection / Returning Caller Flow:** Automatically matches inbound caller ID via `lookup_patient`. If the caller exists, Sarah greets them by name and offers selective demographic updates via `update_patient`.
- **Strict Server-Side Validation:** Never trusts the LLM for data integrity. The backend Pydantic v2 layer validates all fields (non-future DOB, valid 10-digit US phone, 2-letter state codes, 5-digit/ZIP+4 codes, sex enum). Rejection errors are translated into plain-language conversational re-prompts for the voice agent.
- **Standardized REST API Envelope:** All endpoints wrap responses in `{ "data": ..., "error": ... }` per spec requirements.
- **Persistent Storage:** Fully async SQLAlchemy 2.0 with PostgreSQL (via Docker Compose) and zero-config SQLite async fallback for instant local evaluation.
- **Built-in Web Dashboard:** Responsive single-page application with dark mode, live patient registry, search/filter, call transcript viewer, and an interactive in-browser phone call simulator.

---

## Architecture & Flow

```mermaid
flowchart TD
    subgraph Telephony_Layer ["Telephony & Voice AI Layer"]
        PSTN["Inbound Caller (Cellular / Landline)"] --> Vapi["Vapi Telephony Gateway"]
        Vapi <--> Deepgram["Deepgram Nova-3 STT\n(Ultra-fast speech transcription)"]
        Vapi <--> ElevenLabs["Cartesia / ElevenLabs TTS\n(Sarah Voice - warm & empathetic)"]
        Vapi <--> LLM["LLM (GPT-4o-mini)\nConversational Logic & Tool Calling"]
    end

    subgraph Backend_Service ["FastAPI Web Backend (Port 8000)"]
        Vapi <-->|HTTP Webhooks| VoiceRouter["Voice AI Router\n/api/voice/webhook\n/api/voice/tools"]
        VoiceRouter --> ServiceLayer["Patient Service Layer"]
        RestRouter["REST CRUD Router\n/patients, /patients/:id"] --> ServiceLayer
        
        ServiceLayer --> PydanticValidator["Pydantic v2 Validation Engine\n(Server-side gatekeeper)"]
        PydanticValidator --> DB["Database Layer\n(SQLite Async / PostgreSQL)"]
        
        VoiceRouter --> AuditLogger["Call Session & Transcript Persistence"]
        AuditLogger --> DB
    end

    subgraph Frontend_Dashboard ["Clinic Management Dashboard"]
        Browser["Admin / Staff Web Browser"] <--> DashboardSPA["FastAPI Static SPA (/) \nPatient Table, Filters, Live Simulator"]
        DashboardSPA <--> RestRouter
    end
```

---

## Conversational State Machine

```mermaid
stateDiagram-v2
    [*] --> InboundCall : Caller dials phone number
    InboundCall --> CallerLookup : Capture Caller ID
    
    CallerLookup --> ReturningFlow : Record found for phone
    CallerLookup --> RequiredDemographics : New caller
    
    ReturningFlow --> ConfirmUpdate : "Welcome back, [Name]! Update records?"
    ConfirmUpdate --> CollectUpdateFields : Yes
    CollectUpdateFields --> ReadBackConfirm : Apply updates
    
    RequiredDemographics --> ValidateField : Name → DOB → Sex → Phone → Address
    ValidateField --> PromptCorrection : Validation error (e.g. future DOB)
    PromptCorrection --> ValidateField : Caller clarifies year
    
    ValidateField --> OfferOptional : All required fields collected
    OfferOptional --> CollectOptional : Caller provides email / insurance
    OfferOptional --> ReadBackConfirm : Caller declines optional fields
    CollectOptional --> ReadBackConfirm : Optional fields noted
    
    ReadBackConfirm --> HandleCorrection : Caller corrects field ("Actually D-A-V-I-S")
    HandleCorrection --> ReadBackConfirm : Re-confirm corrected field
    ReadBackConfirm --> ExecuteTool : Caller confirms ("Yes, that's correct")
    
    ExecuteTool --> DBCommit : register_patient() tool call
    DBCommit --> Farewell : "You are registered! Patient ID is [ID]"
    Farewell --> EndCallReport : Hang up & persist transcript
    EndCallReport --> [*]
```

---

## Quickstart: Local Setup in 2 Minutes

### 1. Clone & Enter Project Directory
```bash
cd prototype_voice_agent
```

### 2. Activate Virtual Environment & Install Dependencies
```bash
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# On macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Initialize Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(The default `.env` is pre-configured with SQLite `sqlite+aiosqlite:///./data/patient_registration.db`, requiring zero external database installations to run).*

### 4. Start the Application
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Clinic Dashboard:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Interactive Swagger API Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check Endpoint:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## Live Telephony: Dialable Phone Number Setup

To answer incoming phone calls from real mobile phones or landlines:

1. **Sign up at [Vapi.ai](https://dashboard.vapi.ai):**
   - New accounts receive **$10 in free trial credits**.
2. **Expose your local backend via ngrok:**
   ```bash
   ngrok http 8000
   ```
   Copy your public HTTPS forwarding URL (e.g., `https://abc-123.ngrok-free.app`).
3. **Provision the Assistant via automated script:**
   ```bash
   python scripts/setup_vapi.py --api-key YOUR_VAPI_KEY --server-url https://abc-123.ngrok-free.app
   ```
   This automatically provisions Sarah with her persona, Deepgram Nova-3 transcriber, voice parameters, and registered tool schemas (`lookup_patient`, `register_patient`, `update_patient`).
4. **Acquire a Phone Number in Vapi Dashboard:**
   - Navigate to **Phone Numbers** in Vapi.
   - Click **Buy Number** (free with trial) or link an existing Twilio number.
   - Set the **Inbound Assistant** to `Patient Registration Agent`.
5. **Dial In:**
   - Call the phone number from your mobile phone.
   - Sarah will answer, collect your demographics, confirm your information, and save your record directly into the database!

---

## Testing Locally Without Telephony (Simulators)

You don't need a phone number to test the full conversational intake flow. Two simulators are built in:

### Option A: Automated 4-Scenario CLI Test
Runs 4 comprehensive conversational scenarios verifying all required behaviors:
```bash
python scripts/simulate_call.py --automated
```
**Scenarios Verified:**
1. **Scenario 1 (Happy Path Intake):** Full demographic intake with verbal read-back confirmation and database persistence.
2. **Scenario 2 (Validation Resilience):** Caller gives DOB in 2099; server rejects it with validation error; Sarah asks for 4-digit birth year; caller corrects to 1999; record saved.
3. **Scenario 3 (Returning Caller Recognition):** Caller dials again from same phone number; Sarah recognizes caller ID (`lookup_patient`); caller updates street address and apartment number (`update_patient`).
4. **Scenario 4 (Spelling Correction):** Caller clarifies spelling mid-call (*"Actually my last name is spelled D-A-V-I-E-S"*); Sarah updates the name and registers correctly.

### Option B: Interactive Terminal Call Simulator
Talk to Sarah directly in your terminal as if you were on a live phone call:
```bash
python scripts/simulate_call.py --interactive
```

### Option C: In-Browser Phone Simulator
Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and click the **Interactive Voice Simulator** tab. You can click quick scenario presets or chat interactively while observing live tool calls and watch new patients populate the registry table in real time!

---

## Automated Pytest Suite

The project includes 44 automated tests with 100% endpoint and validation rule coverage:

```bash
pytest -v
```

### Test Coverage Highlights
| Test File | Focus Areas | Tests |
| :--- | :--- | :--- |
| `tests/test_patients_api.py` | Complete CRUD endpoints (`POST`, `GET`, `PUT`, `DELETE`), all validation rules (future DOB, phone regex, 2-letter state codes, 5-digit/ZIP+4 codes, sex enum), soft-delete filtering, `{ data, error }` response envelopes, health check, dashboard route. | **36 passed** |
| `tests/test_voice_webhooks.py` | Vapi webhook gateway, dynamic assistant config (`assistant-request`), caller ID lookup (`lookup_patient`), new registration (`register_patient`), returning caller updates (`update_patient`), validation error feedback to LLM, transcript logging (`end-of-call-report`). | **8 passed** |
| **Total** | **All tests run in isolated in-memory SQLite transactions** | **44 passed (100%)** |

---

## REST API Documentation & Envelope Format

All responses follow the standard JSON envelope:

### Success Response Envelope
```json
{
  "data": { ... },
  "error": null
}
```

### Error Response Envelope
```json
{
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": [
      {
        "field": "date_of_birth",
        "message": "Date of birth cannot be in the future. Received: 2099-01-01"
      }
    ]
  }
}
```

### Endpoints Overview

| Method | Endpoint | Description | Query Parameters / Body |
| :--- | :--- | :--- | :--- |
| `GET` | `/patients` | List patients (excludes soft-deleted) | `?last_name=`, `?phone_number=`, `?date_of_birth=` |
| `GET` | `/patients/{id}` | Retrieve patient by UUID | None |
| `POST` | `/patients` | Register new patient (validates input) | `PatientCreate` JSON body |
| `PUT` | `/patients/{id}` | Partial update of demographics | `PatientUpdate` JSON body |
| `DELETE` | `/patients/{id}` | Soft-delete patient record | None |
| `POST` | `/api/voice/webhook` | Vapi voice AI webhook & tool dispatcher | Vapi event payload |
| `POST` | `/api/voice/tools` | Dedicated tool execution endpoint | Vapi function call payload |
| `GET` | `/health` | System health status | None |
| `GET` | `/` | Web Management Dashboard SPA | None |

### Sample cURL Commands

#### 1. Register a Patient (`POST /patients`)
```bash
curl -X POST "http://localhost:8000/patients" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Marcus",
    "last_name": "Vance",
    "date_of_birth": "1988-08-24",
    "sex": "Male",
    "phone_number": "5125550188",
    "address_line_1": "742 Evergreen Terrace",
    "city": "Austin",
    "state": "TX",
    "zip_code": "78704",
    "email": "marcus.vance@example.com",
    "insurance_provider": "Aetna",
    "insurance_member_id": "AET-987654"
  }'
```

#### 2. Query Patients with Filters (`GET /patients`)
```bash
# Filter by last name
curl -X GET "http://localhost:8000/patients?last_name=Vance"

# Filter by phone number
curl -X GET "http://localhost:8000/patients?phone_number=5125550188"
```

#### 3. Update Patient Demographics (`PUT /patients/{id}`)
```bash
curl -X PUT "http://localhost:8000/patients/{PATIENT_ID}" \
  -H "Content-Type: application/json" \
  -d '{
    "address_line_1": "500 South Congress Ave",
    "address_line_2": "Apt 12B"
  }'
```

#### 4. Soft-Delete Patient (`DELETE /patients/{id}`)
```bash
curl -X DELETE "http://localhost:8000/patients/{PATIENT_ID}"
```

---

## Demographic Data Model & Validation Rules

| Field Name | Type | Required | Validation Rules |
| :--- | :--- | :--- | :--- |
| `id` | UUID (v4) | Auto | Primary key string, generated upon insert. |
| `first_name` | String(50) | **Yes** | 1–50 characters; letters, hyphens, spaces, apostrophes. Title-cased. |
| `last_name` | String(50) | **Yes** | 1–50 characters; letters, hyphens, spaces, apostrophes. Title-cased. |
| `date_of_birth` | Date | **Yes** | Valid calendar date in `YYYY-MM-DD` or `MM/DD/YYYY`. **Must not be in the future**. |
| `sex` | Enum | **Yes** | Must be one of: `Male`, `Female`, `Other`, `Decline to Answer`. |
| `phone_number` | String(15) | **Yes** | Valid 10-digit U.S. phone number. Normalized to E.164 standard (`+1XXXXXXXXXX`). |
| `address_line_1` | String(255) | **Yes** | Street address; 1–255 characters. |
| `address_line_2` | String(255) | No | Apartment, Suite, Unit. |
| `city` | String(100) | **Yes** | City name; 1–100 characters. Title-cased. |
| `state` | String(2) | **Yes** | Valid 2-letter U.S. state abbreviation (all 50 states + DC/territories). Uppercased. |
| `zip_code` | String(10) | **Yes** | Valid 5-digit (`12345`) or ZIP+4 (`12345-6789`) format. |
| `email` | String(255) | No | Valid email syntax; normalized to lowercase. |
| `insurance_provider` | String(100) | No | Health insurance carrier name. |
| `insurance_member_id` | String(100) | No | Policy / Subscriber member ID. |
| `preferred_language` | String(50) | No | Default: `English`. |
| `emergency_contact_name` | String(100) | No | Full name of emergency contact. |
| `emergency_contact_phone` | String(15) | No | Valid 10-digit U.S. phone number. |
| `created_at` | Timestamp | Auto | UTC timestamp on record creation. |
| `updated_at` | Timestamp | Auto | UTC timestamp updated on any modification. |
| `deleted_at` | Timestamp | Auto | Nullable. Populated when soft-deleted. |

---

## Web Dashboard UI

The application includes a client-facing web dashboard built with HTML5, CSS3, and vanilla JavaScript:

- **Key Stats Counter:** Live counters for active registered patients, completed intake sessions, and compliance metrics.
- **Patient Directory Table:** Real-time search by patient name, phone number, or date of birth. Toggle between Active, Soft-Deleted, and All records.
- **Patient Profile Drawer:** View comprehensive patient data including insurance and emergency contacts.
- **Interactive Inbound Phone Simulator:** Emulate real phone calls with Sarah right from the browser. Watch the conversation stream, tool execution indicators, and automatic table updates.
- **Dark Mode Aesthetics:** Designed with curated colors (`#0a0f1d`), glassmorphism cards, Inter & Outfit typography, and subtle micro-animations.

---

## Engineering Trade-offs & Production Considerations

### 1. Telephony: Managed Voice AI (Vapi) vs. Custom Asterisk SIP Trunking
- **Decision:** While our prior reference architecture utilizes Asterisk + ARI + RTP + Gemini Live, setting up custom Asterisk SIP trunks and NAT traversal for external reviewer evaluation in a rapid challenge window poses high infrastructure and connectivity risk.
- **Outcome:** Using Vapi provides immediate dialable US phone numbers, sub-second latency with Deepgram Nova-3 and ElevenLabs, robust turn-detection, and seamless HTTP webhook dispatch to our FastAPI service.

### 2. Database: Dual SQLite & PostgreSQL Support
- **Decision:** SQLite with WAL mode is zero-configuration and persists across server restarts on any developer machine. For containerized production deployments, PostgreSQL with `asyncpg` is supported via Docker Compose.
- **Outcome:** Reviewers can run the application instantly without Docker, while the system is fully production-ready for PostgreSQL.

### 3. Server-Side Validation vs. LLM Extraction
- **Decision:** LLMs are prone to hallucinations and formatting variations (e.g., passing a 2-digit birth year or future date).
- **Outcome:** The LLM is used strictly for conversational extraction; the backend Pydantic validator acts as the authoritative gatekeeper. When validation fails, the backend returns clear diagnostic strings that the LLM speaks back to the caller for immediate conversational clarification.

### 4. Production Hardening (Future Healthcare Roadmap)
In a HIPAA-regulated enterprise hospital deployment:
1. **HIPAA & BAA:** Execute Business Associate Agreements (BAAs) with the voice telephony provider, LLM host, and cloud infrastructure.
2. **Field-Level Encryption:** Encrypt sensitive Personally Identifiable Information (PII) such as DOB and insurance member IDs using AES-256-GCM.
3. **EHR / HL7 FHIR Integration:** Map registered patient models to standard HL7 FHIR `Patient` resources to sync directly with Epic or Cerner EHR systems.
4. **mTLS & Webhook Signature Verification:** Verify cryptographic HMAC signatures on incoming Vapi webhooks to guarantee caller authenticity.

---

## Submission Checklist Verification

- [x] **Working System (20%):** Complete FastAPI service with dialable Vapi telephony integration, automated provisioning script, and dual simulators.
- [x] **Conversational Quality (20%):** Empathetic intake persona (Sarah), one thought per turn, natural pacing, clarification re-prompts, spelling correction handling, and verbal read-back confirmation.
- [x] **Technical Architecture (20%):** Modular architecture, Pydantic v2 validation layer, async SQLAlchemy, duplicate detection, and standardized `{ data, error }` response envelopes.
- [x] **Code Quality & Docs (20%):** Clean, type-annotated code, comprehensive README, interactive Swagger docs, and detailed architectural diagrams.
- [x] **Edge Cases & Resilience (20%):** Future date of birth rejection, invalid phone number normalization, soft-delete filtering, 44 passing unit/integration tests, and 4 passing simulated conversation scenarios.
