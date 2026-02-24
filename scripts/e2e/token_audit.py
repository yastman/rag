"""Send 10 test queries via Telethon and collect response stats.

Usage: cd /home/user/projects/rag-fresh && uv run python -m scripts.e2e.token_audit
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

QUERIES = [
    "Какие квартиры есть в Несебре?",
    "Сколько стоит студия у моря?",
    "Виды ВНЖ в Болгарии?",
    "Что нужно для покупки недвижимости иностранцу?",
    "Есть квартиры до 50000 евро?",
    "Расскажи про Солнечный Берег",
    "Какие налоги при покупке недвижимости?",
    "Двухкомнатные квартиры в Бургасе",
    "Как получить ПМЖ через недвижимость?",
    "Что выгоднее: Несебр или Святой Влас?",
]


async def main() -> int:
    if not API_ID or not API_HASH:
        logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        return 1

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    try:
        await client.start()
    except Exception as e:
        logger.error("Failed to connect: %s", e)
        return 1

    me = await client.get_me()
    logger.info("Connected as: %s", me.username or me.phone)

    results = []
    for i, query in enumerate(QUERIES, 1):
        logger.info("[%d/%d] Sending: %s", i, len(QUERIES), query)
        start = time.time()

        try:
            async with client.conversation(BOT_USERNAME, timeout=RESPONSE_TIMEOUT) as conv:
                await conv.send_message(query)
                response = await conv.get_response()

                # Wait for streaming edits
                await asyncio.sleep(2.0)
                try:
                    final = await conv.get_edit(timeout=10)
                    response = final
                except TimeoutError:
                    pass

            elapsed_ms = int((time.time() - start) * 1000)
            text = response.text or ""
            words = len(text.split())
            chars = len(text)
            results.append(
                {
                    "query": query,
                    "words": words,
                    "chars": chars,
                    "time_ms": elapsed_ms,
                    "ok": True,
                }
            )
            logger.info("  -> %d words, %d chars, %dms", words, chars, elapsed_ms)

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            results.append(
                {
                    "query": query,
                    "words": 0,
                    "chars": 0,
                    "time_ms": elapsed_ms,
                    "ok": False,
                }
            )
            logger.error("  -> FAIL: %s (%dms)", e, elapsed_ms)

        # Pause between queries to avoid rate limiting
        if i < len(QUERIES):
            await asyncio.sleep(3)

    await client.disconnect()

    # Print summary
    print("\n" + "=" * 80)
    print(f"{'#':>2}  {'Query':<50}  {'Words':>5}  {'Chars':>5}  {'Time':>6}  {'OK'}")
    print("-" * 80)
    ok_results = [r for r in results if r["ok"]]
    for i, r in enumerate(results, 1):
        status = "OK" if r["ok"] else "FAIL"
        print(
            f"{i:>2}  {r['query']:<50}  {r['words']:>5}  {r['chars']:>5}  {r['time_ms']:>5}ms  {status}"
        )

    if ok_results:
        avg_words = sum(r["words"] for r in ok_results) / len(ok_results)
        avg_time = sum(r["time_ms"] for r in ok_results) / len(ok_results)
        max_words = max(r["words"] for r in ok_results)
        min_words = min(r["words"] for r in ok_results)
        print("-" * 80)
        print(
            f"    Avg words: {avg_words:.0f}  |  Range: {min_words}-{max_words}  |  Avg time: {avg_time:.0f}ms"
        )
        print(f"    Success: {len(ok_results)}/{len(results)}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
