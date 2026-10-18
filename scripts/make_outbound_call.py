#!/usr/bin/env python3
"""
Trigger an Outbound Phone Call via Vapi.

Useful when you do not have a U.S. dialer to call your Vapi inbound number.
This script instructs Vapi to dial YOUR international or local mobile number directly.

Usage:
  python scripts/make_outbound_call.py --to +923001234567
"""

import argparse
import os
import sys
import httpx
from dotenv import load_dotenv

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Trigger Vapi Outbound Phone Call")
    parser.add_argument(
        "--to",
        required=True,
        help="Destination phone number in E.164 format (e.g. +923001234567, +447123456789)",
    )
    args = parser.parse_args()

    api_key = os.getenv("VAPI_API_KEY")
    phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")
    assistant_id = os.getenv("VAPI_ASSISTANT_ID")

    if not api_key:
        print("[ERROR] VAPI_API_KEY is missing in .env")
        sys.exit(1)
    if not phone_number_id:
        print("[ERROR] VAPI_PHONE_NUMBER_ID is missing in .env")
        sys.exit(1)
    if not assistant_id:
        print("[ERROR] VAPI_ASSISTANT_ID is missing in .env")
        sys.exit(1)

    print("=" * 65)
    print("   GERTA AI — INITIATING OUTBOUND VOICE CALL")
    print("=" * 65)
    print(f"Calling:        {args.to}")
    print(f"Assistant ID:   {assistant_id}")
    print(f"Phone Number ID:{phone_number_id}")
    print("Sending call request to Vapi...")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": args.to,
        },
    }

    try:
        resp = httpx.post(
            "https://api.vapi.ai/call/phone",
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            print("\n[SUCCESS] Call initiated successfully!")
            print(f"  Call ID: {data.get('id')}")
            print(f"  Status:  {data.get('status')}")
            print("\nYour phone should ring in a few seconds! Answer it to speak with Sarah.")
        else:
            print(f"\n[FAILED] Vapi returned status {resp.status_code}:")
            print(resp.text)
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
