"""Quick E2E bot test via Telethon.

Sends a test query to the bot and prints the response.
Usage: cd /opt/rag-fresh && uv run python -m scripts.e2e.quick_test
"""

import asyncio
import logging
import os
import sys
import time

from dotenv import load_dotenv
from telethon import TelegramClient


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
BOT_USERNAME = os.getenv("E2E_BOT_USERNAME", "@test_nika_homes_bot")
SESSION_PATH = "e2e_tester"
RESPONSE_TIMEOUT = 120
TEST_QUERY = "Расскажи про недвижимость в Болгарии"


async def main() -> int:
    if not API_ID or not API_HASH:
        logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        return 1

    logger.info(f"Connecting as Telethon userbot (session: {SESSION_PATH})")
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

    try:
        await client.start()
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        logger.error("Session may need re-authentication. Run: uv run python -m scripts.e2e.auth")
        return 1

    me = await client.get_me()
    logger.info(f"Connected as: {me.username or me.phone}")

    try:
        logger.info(f"Sending to {BOT_USERNAME}: {TEST_QUERY}")
        start = time.time()

        async with client.conversation(BOT_USERNAME, timeout=RESPONSE_TIMEOUT) as conv:
            await conv.send_message(TEST_QUERY)

            # Wait for initial response
            response = await conv.get_response()

            # Wait for streaming edits to finish
            await asyncio.sleep(2.0)
            try:
                final = await conv.get_edit(timeout=10)
                response = final
            except TimeoutError:
                pass

        elapsed_ms = int((time.time() - start) * 1000)

        print("\n" + "=" * 60)
        print(f"QUERY: {TEST_QUERY}")
        print(f"RESPONSE TIME: {elapsed_ms}ms")
        print("=" * 60)
        print(f"RESPONSE:\n{response.text}")
        print("=" * 60)

        if response.text and len(response.text) > 10:
            logger.info(f"SUCCESS: Got response ({len(response.text)} chars, {elapsed_ms}ms)")
            return 0
        logger.error("FAIL: Response too short or empty")
        return 1

    except TimeoutError:
        logger.error(f"FAIL: No response within {RESPONSE_TIMEOUT}s")
        return 1
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        return 1
    finally:
        await client.disconnect()
        logger.info("Disconnected")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
