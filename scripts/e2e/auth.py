#!/usr/bin/env python3
"""One-time Telethon authentication script.

Usage:
    # Step 1: Send code to phone
    python scripts/e2e/auth.py --phone REDACTED_PHONE

    # Step 2: Complete auth with received code
    python scripts/e2e/auth.py --phone REDACTED_PHONE --code 12345
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_NAME = "e2e_tester"
HASH_FILE = Path(".e2e_auth_hash.json")


async def main(phone: str, code: str | None = None, password: str | None = None):
    """Authenticate and create session file."""
    if not API_ID or not API_HASH:
        print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        sys.exit(1)

    print(f"API ID: {API_ID}")
    print(f"Phone: {phone}")
    print(f"Session: {SESSION_NAME}.session")
    print()

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        if code is None:
            # Step 1: Send code request and save hash
            result = await client.send_code_request(phone)
            HASH_FILE.write_text(
                json.dumps(
                    {
                        "phone": phone,
                        "phone_code_hash": result.phone_code_hash,
                    }
                )
            )
            print("Code sent to your Telegram app!")
            print()
            print("Run again with the code:")
            print(f"  python scripts/e2e/auth.py --phone {phone} --code <CODE>")
            await client.disconnect()
            return

        # Step 2: Sign in with code and saved hash
        if not HASH_FILE.exists():
            print("Error: No saved hash. Run without --code first.")
            await client.disconnect()
            sys.exit(1)

        data = json.loads(HASH_FILE.read_text())
        phone_code_hash = data["phone_code_hash"]

        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            HASH_FILE.unlink()  # Clean up
        except SessionPasswordNeededError:
            if not password:
                print("2FA enabled! Run with --password:")
                print(
                    f"  python scripts/e2e/auth.py --phone {phone} --code {code} --password <PASSWORD>"
                )
                await client.disconnect()
                return
            await client.sign_in(password=password)
            HASH_FILE.unlink()

    me = await client.get_me()
    print()
    print(f"Authenticated as: {me.first_name} (@{me.username})")
    print(f"Session saved: {SESSION_NAME}.session")
    print()
    print("Run E2E tests: make e2e-test")

    await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telethon auth for E2E tests")
    parser.add_argument("--phone", required=True, help="Phone number (REDACTED_PHONE)")
    parser.add_argument("--code", help="Verification code from Telegram")
    parser.add_argument("--password", help="2FA password (if enabled)")
    args = parser.parse_args()

    asyncio.run(main(args.phone, args.code, args.password))
