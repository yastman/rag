"""Update identity survives slow processing and uncertain handler outcomes."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from telegram_bot.middlewares.update_dedup import UpdateDeduplicationMiddleware


def _update(update_id: int) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(UTC),
            chat=Chat(id=10, type="private"),
            from_user=User(id=10, is_bot=False, first_name="Client"),
            text="Question",
        ),
    )


async def test_dispatcher_absorbs_active_and_finished_replays_but_accepts_new_updates():
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(UpdateDeduplicationMiddleware())
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[int] = []

    async def handler(message: Message):
        calls.append(message.message_id)
        started.set()
        await release.wait()

    dispatcher.message.register(handler)
    async with Bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi") as bot:
        first = asyncio.create_task(dispatcher.feed_update(bot, _update(1)))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            await asyncio.wait_for(dispatcher.feed_update(bot, _update(1)), timeout=2)
            assert calls == [1]
        finally:
            release.set()
            await first
        await dispatcher.feed_update(bot, _update(1))
        await dispatcher.feed_update(bot, _update(2))
        assert calls == [1, 2]


@pytest.mark.parametrize("failure", [RuntimeError("after effect"), asyncio.CancelledError()])
async def test_uncertain_failed_attempt_is_not_replayed(failure):
    middleware = UpdateDeduplicationMiddleware()
    handler = AsyncMock(side_effect=failure)
    async with Bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi") as bot:
        with pytest.raises(type(failure)):
            await middleware(handler, _update(1), {"bot": bot})
        await middleware(handler, _update(1), {"bot": bot})
        handler.assert_awaited_once()


async def test_update_identity_is_scoped_to_bot():
    middleware = UpdateDeduplicationMiddleware()
    handler = AsyncMock()
    async with (
        Bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi") as first,
        Bot("987654321:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi") as second,
    ):
        await middleware(handler, _update(1), {"bot": first})
        await middleware(handler, _update(1), {"bot": second})
    assert handler.await_count == 2
