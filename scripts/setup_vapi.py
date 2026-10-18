#!/usr/bin/env python3
"""
Vapi Voice AI Automated Provisioning Script.

Automatically configures or updates the Sarah Patient Intake Voice Assistant
on Vapi with all system prompts, tool schemas, and webhook callback URLs.

Usage:
  python scripts/setup_vapi.py --api-key YOUR_VAPI_KEY --server-url https://your-ngrok-url.app
Or with values in .env:
  python scripts/setup_vapi.py
"""

import argparse
import os
import sys
import httpx
from dotenv import load_dotenv

# Add parent directory and backend to path so we can import app modules directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.api.voice_webhooks import _build_assistant_config

VAPI_BASE_URL = "https://api.vapi.ai"


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Provision Vapi Voice AI Assistant")
    parser.add_argument("--api-key", default=os.getenv("VAPI_API_KEY"), help="Vapi API Key")
    parser.add_argument(
        "--server-url",
        default=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
        help="Public URL reachable by Vapi (e.g. ngrok HTTPS URL)",
    )
    parser.add_argument(
        "--assistant-id",
        default=os.getenv("VAPI_ASSISTANT_ID"),
        help="Existing Assistant ID to update (optional)",
    )
    args = parser.parse_args()

    api_key = args.api_key
    if not api_key or api_key == "your_vapi_api_key_here":
        print("\033[1;31m[ERROR]\033[0m VAPI_API_KEY is missing!")
        print("Please provide it via --api-key or set VAPI_API_KEY in your .env file.")
        print("Get a free API key with $10 free credits at https://dashboard.vapi.ai")
        sys.exit(1)

    server_url = args.server_url.rstrip("/")
    webhook_url = f"{server_url}/api/voice/webhook"

    print("=" * 65)
    print("   GERTA AI — VAPI ASSISTANT PROVISIONING")
    print("=" * 65)
    print(f"Server Webhook Target: {webhook_url}")

    # Build assistant payload from the app's single-source-of-truth
    payload = _build_assistant_config()
    payload["serverUrl"] = webhook_url

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(base_url=VAPI_BASE_URL, headers=headers, timeout=30.0) as client:
        assistant_id = args.assistant_id

        if assistant_id:
            print(f"Updating existing Vapi assistant: {assistant_id}...")
            resp = client.patch(f"/assistant/{assistant_id}", json=payload)
        else:
            print("Creating new Vapi assistant for Sarah (Patient Intake Coordinator)...")
            resp = client.post("/assistant", json=payload)

        if resp.status_code in (200, 201):
            data = resp.json()
            created_id = data.get("id", assistant_id)
            print("\n\033[1;32m[SUCCESS]\033[0m Assistant configured successfully!")
            print(f"  Assistant ID:   {created_id}")
            print(f"  Assistant Name: {data.get('name')}")
            print(f"  Webhook URL:    {webhook_url}")
            print("\n" + "=" * 65)
            print("NEXT STEPS TO TEST WITH A REAL PHONE NUMBER:")
            print("1. Go to https://dashboard.vapi.ai/phone-numbers")
            print("2. Click 'Buy Number' (free trial includes U.S. numbers) or import your Twilio number.")
            print(f"3. In the phone number settings, select '{data.get('name')}' as the Inbound Assistant.")
            print("4. Dial the number from your mobile phone and speak with Sarah!")
            print("5. Your FastAPI backend will receive the webhooks and register the patient in your DB.")
            print("=" * 65)
        else:
            print(f"\n\033[1;31m[FAILED]\033[0m Vapi API responded with status {resp.status_code}:")
            print(resp.text)
            sys.exit(1)


if __name__ == "__main__":
    main()
