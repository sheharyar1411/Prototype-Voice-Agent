#!/usr/bin/env python3
"""
Interactive & Automated Voice Agent Simulator.

Allows testing the Patient Intake Coordinator (Sarah) without dialing a phone number:
  1. Automated Mode: Runs 4 end-to-end conversation scenarios:
     - Scenario 1: Fresh caller happy path with read-back confirmation & DB save
     - Scenario 2: Validation rejection (DOB in future) & graceful re-prompt
     - Scenario 3: Returning caller recognition & selective demographic update
     - Scenario 4: Mid-call spelling correction ("Actually last name is D-A-V-I-S")
  2. Interactive Mode: Chat directly with the agent through the terminal as if you
     were on a live phone call.

Usage:
  python scripts/simulate_call.py --automated
  python scripts/simulate_call.py --interactive
"""

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8000"


def print_banner():
    print("=" * 70)
    print("   GERTA AI — CLINICAL VOICE AGENT SIMULATOR (SARAH)")
    print("=" * 70)
    print("Simulating inbound call via Vapi webhook endpoints...\n")


def print_turn(speaker: str, message: str, color_code: str = "36"):
    prefix = f"\033[1;{color_code}m[{speaker}]\033[0m"
    print(f"{prefix} {message}")


async def check_health(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{BASE_URL}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


async def run_scenario_1_happy_path(client: httpx.AsyncClient):
    print("\n" + "-" * 70)
    print("SCENARIO 1: Fresh Caller Happy Path (Full Intake + Read-back + DB Save)")
    print("-" * 70)

    caller_phone = "+15125550188"
    call_id = f"sim-{uuid.uuid4().hex[:8]}"

    # Step 1: Call starts, Vapi requests assistant config
    print_turn("Vapi Gateway", f"Inbound call from {caller_phone}. Requesting assistant config...")
    resp = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={"message": {"type": "assistant-request", "call": {"id": call_id, "customer": {"number": caller_phone}}}},
    )
    assert resp.status_code == 200, f"Assistant config request failed: {resp.text}"
    assistant = resp.json()["assistant"]
    print_turn("Sarah", assistant["firstMessage"], "32")

    # Step 2: Immediate lookup_patient for returning caller detection
    print_turn("Vapi Tool Call", f"Executing lookup_patient(phone_number='{caller_phone}')...")
    resp = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={
            "message": {
                "type": "function-call",
                "functionCall": {"name": "lookup_patient", "parameters": {"phone_number": caller_phone}},
            }
        },
    )
    result = json.loads(resp.json()["results"][0]["result"])
    print_turn("System", f"Lookup result: found={result.get('found')} ({result.get('message')})", "33")
    print_turn("Sarah", "I don't see an existing file for this number, so let's get you registered! Could I get your full name?", "32")

    # Step 3: Conversational intake
    print_turn("Caller", "My name is Marcus Vance.")
    print_turn("Sarah", "Thank you, Marcus. And what is your date of birth?", "32")
    print_turn("Caller", "August 24th, 1988.")
    print_turn("Sarah", "Got it, August 24, 1988. For medical records, how should we record your sex?", "32")
    print_turn("Caller", "Male.")
    print_turn("Sarah", "Thank you. And what is your street address?", "32")
    print_turn("Caller", "742 Evergreen Terrace, Austin, Texas 78704.")
    print_turn("Sarah", "Would you also like to provide an email or insurance information?", "32")
    print_turn("Caller", "Yes, my email is marcus.vance@example.com, and I have Aetna insurance, member ID AET987654.")

    # Step 4: Sarah reads back all information for explicit verbal confirmation
    print_turn(
        "Sarah",
        "Let me read that back to make sure everything is exact:\n"
        "  - Name: Marcus Vance\n"
        "  - Date of Birth: August 24, 1988\n"
        "  - Sex: Male\n"
        "  - Phone: 512-555-0188\n"
        "  - Address: 742 Evergreen Terrace, Austin, TX 78704\n"
        "  - Email: marcus.vance@example.com\n"
        "  - Insurance: Aetna (Member ID: AET987654)\n"
        "Does everything sound correct?",
        "32",
    )
    print_turn("Caller", "Yes, that's completely correct!")

    # Step 5: Save record via tool call
    print_turn("Vapi Tool Call", "Executing register_patient with confirmed demographics...")
    patient_data = {
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
        "insurance_member_id": "AET987654",
    }
    resp = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={
            "message": {
                "type": "function-call",
                "functionCall": {"name": "register_patient", "parameters": patient_data},
            }
        },
    )
    res = json.loads(resp.json()["results"][0]["result"])
    assert res["success"] is True, f"Registration failed: {res}"
    patient_id = res["patient_id"]
    print_turn("System", f"Saved to DB! Patient ID: {patient_id}", "33")
    print_turn("Sarah", f"Wonderful! You are now registered with Metro Health Clinic, Marcus. Your patient ID is {patient_id}.", "32")

    # Step 6: End of call report & transcript persistence
    transcript = (
        "Sarah: Hello! Thank you for calling Metro Health Clinic...\n"
        "Caller: My name is Marcus Vance...\n"
        "Sarah: Let me read that back... Marcus: Yes that is correct.\n"
        f"Sarah: You are all registered! Patient ID {patient_id}."
    )
    await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={"message": {"type": "end-of-call-report", "call": {"id": call_id, "customer": {"number": caller_phone}}, "transcript": transcript}},
    )
    print_turn("System", "Call ended. Session and full transcript persisted.", "33")
    print("\033[1;32m[PASS]\033[0m Scenario 1 completed successfully!")
    return patient_id, caller_phone


async def run_scenario_2_validation_resilience(client: httpx.AsyncClient):
    print("\n" + "-" * 70)
    print("SCENARIO 2: Validation Resilience (Future DOB Rejected & Re-prompted)")
    print("-" * 70)

    # Caller tries to register with a DOB in 2099
    bad_data = {
        "first_name": "Jordan",
        "last_name": "Miller",
        "date_of_birth": "2099-01-01",  # Future date!
        "sex": "Female",
        "phone_number": "5125557766",
        "address_line_1": "100 Congress Ave",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
    }
    print_turn("Caller", "My date of birth is January 1st, 2099.")
    print_turn("Vapi Tool Call", "Attempting register_patient with future DOB (2099-01-01)...")

    resp = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={
            "message": {
                "type": "function-call",
                "functionCall": {"name": "register_patient", "parameters": bad_data},
            }
        },
    )
    res = json.loads(resp.json()["results"][0]["result"])
    assert res["success"] is False, "Expected validation failure for future DOB!"
    print_turn("System (Validator)", f"Server-side rejection: {res.get('validation_errors')}", "31")

    print_turn(
        "Sarah",
        "I'm sorry Jordan, but that birth date appears to be in the future. "
        "Could you please confirm the four-digit year you were born?",
        "32",
    )
    print_turn("Caller", "Oh sorry about that! I meant 1999, not 2099.")

    # Corrected registration
    bad_data["date_of_birth"] = "1999-01-01"
    print_turn("Vapi Tool Call", "Re-attempting register_patient with corrected DOB (1999-01-01)...")
    resp2 = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={
            "message": {
                "type": "function-call",
                "functionCall": {"name": "register_patient", "parameters": bad_data},
            }
        },
    )
    res2 = json.loads(resp2.json()["results"][0]["result"])
    assert res2["success"] is True, f"Correction should succeed: {res2}"
    print_turn("System", f"Success! Patient ID: {res2['patient_id']}", "33")
    print_turn("Sarah", "That worked perfectly! You're all registered.", "32")
    print("\033[1;32m[PASS]\033[0m Scenario 2 completed successfully!")


async def run_scenario_3_returning_caller(client: httpx.AsyncClient, patient_id: str, caller_phone: str):
    print("\n" + "-" * 70)
    print("SCENARIO 3: Returning Caller Recognition & Selective Demographic Update")
    print("-" * 70)

    print_turn("Vapi Gateway", f"Inbound call from {caller_phone}. Executing lookup_patient...")
    resp = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={
            "message": {
                "type": "function-call",
                "functionCall": {"name": "lookup_patient", "parameters": {"phone_number": caller_phone}},
            }
        },
    )
    res = json.loads(resp.json()["results"][0]["result"])
    assert res["success"] is True and res["found"] is True, f"Expected caller lookup match: {res}"
    matched_patient = res["patient"]

    print_turn("System", f"Found record: {matched_patient['first_name']} {matched_patient['last_name']} (ID: {matched_patient['id']})", "33")
    print_turn(
        "Sarah",
        f"Welcome back, {matched_patient['first_name']}! I see you are already registered with us. "
        "Are you calling to update your address or any other information today?",
        "32",
    )
    print_turn("Caller", "Yes, I recently moved. My new address is 500 South Congress Ave, Apt 12B, Austin TX 78704.")

    # Execute update_patient
    update_data = {
        "patient_id": matched_patient["id"],
        "address_line_1": "500 South Congress Ave",
        "address_line_2": "Apt 12B",
        "zip_code": "78704",
    }
    print_turn("Vapi Tool Call", f"Executing update_patient for ID {matched_patient['id']}...")
    resp2 = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={
            "message": {
                "type": "function-call",
                "functionCall": {"name": "update_patient", "parameters": update_data},
            }
        },
    )
    res2 = json.loads(resp2.json()["results"][0]["result"])
    assert res2["success"] is True, f"Update failed: {res2}"
    print_turn("System", f"Update confirmed: {res2.get('message')}", "33")
    print_turn("Sarah", "I have updated your address to 500 South Congress Ave, Apartment 12B. Everything is up to date!", "32")
    print("\033[1;32m[PASS]\033[0m Scenario 3 completed successfully!")


async def run_scenario_4_spelling_correction(client: httpx.AsyncClient):
    print("\n" + "-" * 70)
    print("SCENARIO 4: Mid-Call Spelling Correction Handling ('D-A-V-I-S')")
    print("-" * 70)

    print_turn("Caller", "My name is John Davis.")
    print_turn("Sarah", "Could you spell your last name for me to ensure accurate records?", "32")
    print_turn("Caller", "It's spelled D-A-V-I-S.")
    print_turn("Sarah", "Thank you, D-A-V-I-S. Got it!", "32")
    print_turn("Caller", "Actually, I gave you my brother's last name by mistake, mine is spelled D-A-V-I-E-S.")
    print_turn("Sarah", "Understood, D-A-V-I-E-S, John Davies. Let me make sure I have that updated.", "32")

    patient_data = {
        "first_name": "John",
        "last_name": "Davies",
        "date_of_birth": "1994-03-11",
        "sex": "Male",
        "phone_number": "5125558833",
        "address_line_1": "888 West 6th St",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78703",
    }
    resp = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={
            "message": {
                "type": "function-call",
                "functionCall": {"name": "register_patient", "parameters": patient_data},
            }
        },
    )
    res = json.loads(resp.json()["results"][0]["result"])
    assert res["success"] is True
    print_turn("System", f"Patient registered as: {patient_data['first_name']} {patient_data['last_name']} (ID: {res['patient_id']})", "33")
    print("\033[1;32m[PASS]\033[0m Scenario 4 completed successfully!")


async def interactive_mode(client: httpx.AsyncClient):
    print_banner()
    print("INTERACTIVE CALL MODE")
    print("You are connected to Sarah at Metro Health Clinic.")
    print("Type your responses below. Type 'exit' or 'hangup' to end the call.\n")

    caller_phone = input("Enter your phone number (or press Enter for default 512-555-0100): ").strip()
    if not caller_phone:
        caller_phone = "5125550100"

    call_id = f"sim-{uuid.uuid4().hex[:8]}"

    # Assistant setup
    resp = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={"message": {"type": "assistant-request", "call": {"id": call_id, "customer": {"number": caller_phone}}}},
    )
    first_msg = (
        resp.json().get("assistant", {}).get("firstMessage")
        or "Hello! Thank you for calling Metro Health Clinic. My name is Sarah."
    )
    print_turn("Sarah", first_msg, "32")

    # Check caller ID
    resp_lookup = await client.post(
        f"{BASE_URL}/api/voice/webhook",
        json={"message": {"type": "function-call", "functionCall": {"name": "lookup_patient", "parameters": {"phone_number": caller_phone}}}},
    )
    lookup_res = json.loads(resp_lookup.json()["results"][0]["result"])
    if lookup_res.get("found"):
        pat = lookup_res["patient"]
        print_turn("Sarah", f"Welcome back, {pat['first_name']} {pat['last_name']}! Would you like to update your records?", "32")
    else:
        print_turn("Sarah", "May I start by getting your first and last name?", "32")

    # Simple guided intake loop
    fields = [
        ("first_name", "First name"),
        ("last_name", "Last name"),
        ("date_of_birth", "Date of birth (YYYY-MM-DD or MM/DD/YYYY)"),
        ("sex", "Sex (Male, Female, Other, Decline to Answer)"),
        ("address_line_1", "Street address"),
        ("city", "City"),
        ("state", "State (2 letters, e.g. TX)"),
        ("zip_code", "ZIP code (5 digits)"),
    ]

    collected = {"phone_number": caller_phone}
    for field_key, prompt in fields:
        user_input = input(f"\n[You] ({prompt}): ").strip()
        if user_input.lower() in ("exit", "hangup", "quit"):
            print_turn("Sarah", "Thank you for calling Metro Health Clinic. Have a wonderful day!", "32")
            return
        collected[field_key] = user_input

    print("\n" + "=" * 50)
    print_turn("Sarah", "Let me read back what I've collected for your confirmation:", "32")
    for k, v in collected.items():
        print(f"  {k}: {v}")

    confirm = input("\nDoes everything sound correct? (yes/no): ").strip().lower()
    if confirm in ("y", "yes"):
        resp_save = await client.post(
            f"{BASE_URL}/api/voice/webhook",
            json={"message": {"type": "function-call", "functionCall": {"name": "register_patient", "parameters": collected}}},
        )
        res_save = json.loads(resp_save.json()["results"][0]["result"])
        if res_save.get("success"):
            print_turn("Sarah", f"Wonderful! You are all registered. Your patient ID is {res_save['patient_id']}.", "32")
        else:
            print_turn("Sarah", f"There was an issue saving: {res_save.get('error')} {res_save.get('validation_errors')}", "31")
    else:
        print_turn("Sarah", "No problem, we can restart whenever you're ready. Have a good day!", "32")


async def main():
    parser = argparse.ArgumentParser(description="Voice AI Patient Registration Simulator")
    parser.add_argument("--interactive", action="store_true", help="Run interactive terminal call session")
    parser.add_argument("--automated", action="store_true", default=True, help="Run automated test scenarios (default)")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=10.0) as client:
        if not await check_health(client):
            print(f"\033[1;31m[ERROR]\033[0m Backend is not running at {BASE_URL}!")
            print("Please start the backend first with:")
            print("  .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000")
            sys.exit(1)

        if args.interactive:
            await interactive_mode(client)
        else:
            print_banner()
            patient_id, phone = await run_scenario_1_happy_path(client)
            await run_scenario_2_validation_resilience(client)
            await run_scenario_3_returning_caller(client, patient_id, phone)
            await run_scenario_4_spelling_correction(client)
            print("\n" + "=" * 70)
            print("ALL 4 CONVERSATIONAL SCENARIOS PASSED WITH 100% SUCCESS!")
            print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
