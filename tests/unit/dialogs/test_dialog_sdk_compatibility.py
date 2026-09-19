"""Exercise the SDK primitives used by the Telegram dialog boundary."""

from aiogram import Dispatcher, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window, setup_dialogs
from aiogram_dialog.test_tools import BotClient, MockMessageManager
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Const


class CompatibilitySG(StatesGroup):
    root = State()


class ChildSG(StatesGroup):
    child = State()


async def test_sdk_dialog_lifecycle_dispatch_and_serialization() -> None:
    dp = Dispatcher()
    commands = Router()
    catch_all = Router()
    observed = []
    messages = MockMessageManager()

    async def start(message: Message, dialog_manager: DialogManager) -> None:
        await dialog_manager.start(CompatibilitySG.root, mode=StartMode.RESET_STACK)

    async def navigate(message: Message, widget: MessageInput, manager: DialogManager) -> None:
        observed.append((message.text, manager.current_context().state))
        if message.text == "child":
            await manager.start(ChildSG.child)
        elif message.text == "done":
            await manager.done()
        elif message.text == "reset":
            await manager.reset_stack(remove_keyboard=True)

    async def free_text(message: Message) -> None:
        observed.append((message.text, None))

    commands.message.register(start, F.text == "/start")
    catch_all.message.register(free_text, StateFilter(None), F.text)
    dp.include_router(commands)
    dp.include_router(
        Dialog(
            Window(
                Const("Root"),
                Button(Const("Action"), id="action"),
                MessageInput(navigate),
                state=CompatibilitySG.root,
            )
        )
    )
    dp.include_router(Dialog(Window(Const("Child"), MessageInput(navigate), state=ChildSG.child)))
    dp.include_router(catch_all)
    setup_dialogs(dp, message_manager=messages)
    client = BotClient(dp)

    await client.send("before")
    await client.send("/start")
    rendered = messages.last_message()
    restored = Message.model_validate_json(rendered.model_dump_json(exclude_none=True))
    assert restored.text == "Root"
    assert restored.reply_markup is not None
    button = restored.reply_markup.inline_keyboard[0][0]
    assert button.text == "Action"
    assert button.callback_data and button.callback_data.endswith("action")
    await client.send("child")
    assert messages.last_message().text == "Child"
    await client.send("done")
    assert messages.last_message().text == "Root"
    await client.send("reset")
    state = dp.fsm.get_context(bot=client.bot, chat_id=client.chat.id, user_id=client.user.id)
    assert await state.get_state() is None
    await client.send("after reset")
    assert observed[-1] == ("after reset", None)
    await state.set_state("external:waiting")
    await client.send("blocked by state")
    await state.clear()
    await client.send("after")
    assert observed == [
        ("before", None),
        ("child", CompatibilitySG.root),
        ("done", ChildSG.child),
        ("reset", CompatibilitySG.root),
        ("after reset", None),
        ("after", None),
    ]
    assert messages.sent_messages[-1].reply_markup is None
    await dp.storage.close()
