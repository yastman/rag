"""E2E safety net for the 3 kept surfaces (Epic #2843 / Issue #2850).

Surfaces tested:
  1. Text RAG Chat  — entry: infer_agent_intent + run_client_pipeline
  2. Apartment Filter Dialog — entry: handle_demo_button + handle_demo_apartments
  3. Manager Reply (Forum Topics) — entry: ForumBridge.relay_to_topic + relay_to_client

Surfaces 2 and 3 require aiogram and are skipped in the lean venv;
they run under ``make test-unit-extras`` with ``--all-extras``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.no_services]


# ---------------------------------------------------------------------------
# Surface 1: Text RAG Chat
# ---------------------------------------------------------------------------

from telegram_bot.pipelines.client import infer_agent_intent, run_client_pipeline


class TestTextRagChatSurface:
    """Happy-path coverage for the Text RAG Chat surface."""

    def test_infer_agent_intent_empty_for_rag_query(self) -> None:
        """Plain real-estate query routes to RAG (empty intent)."""
        assert infer_agent_intent("Какие квартиры есть в Варне?") == ""

    def test_infer_agent_intent_detects_handoff(self) -> None:
        assert infer_agent_intent("Хочу поговорить с менеджером") == "handoff"

    def test_infer_agent_intent_detects_mortgage(self) -> None:
        assert infer_agent_intent("Расскажите про ипотеку") == "mortgage"

    def test_infer_agent_intent_detects_apartment(self) -> None:
        assert infer_agent_intent("Хочу подобрать апартаменты у моря") == "apartment"

    @pytest.mark.asyncio
    async def test_run_client_pipeline_rag_path_returns_answer(self) -> None:
        """run_client_pipeline produces a non-empty answer on the RAG happy path."""
        msg = MagicMock()
        msg.bot = MagicMock()
        msg.chat = MagicMock(id=100)
        msg.answer = AsyncMock()

        rag_result = {
            "response": "",
            "query_type": "FAQ",
            "documents": [{"content": "Квартиры от 50 000 EUR.", "id": "doc1"}],
            "reranked_documents": [],
            "cache_hit": False,
            "query_rewritten": False,
            "rewritten_query": None,
            "embedding_latency": 0.1,
            "search_latency": 0.2,
            "rerank_latency": 0.0,
            "confidence_score": 0.9,
            "grade_confidence": 0.9,
            "grounded": True,
            "latency_stages": {},
            "llm_call_count": 0,
        }
        gen_result = {
            "response": "Квартиры от 50 000 EUR.",
            "sources": [],
            "latency": 0.5,
            "model": "gpt-4o-mini",
            "grounded": True,
            "ground_truth_used": False,
            "response_sent": False,
            "llm_call_count": 1,
        }

        with (
            patch(
                "telegram_bot.pipelines.client.rag_pipeline",
                new=AsyncMock(return_value=rag_result),
            ),
            patch(
                "telegram_bot.pipelines.client.generate_response",
                new=AsyncMock(return_value=gen_result),
            ),
            patch("telegram_bot.pipelines.client.send_html_messages", new=AsyncMock()),
        ):
            result = await run_client_pipeline(
                user_text="Сколько стоят квартиры?",
                user_id=42,
                session_id="sess-1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=MagicMock(
                    show_sources=False,
                    streaming_enabled=False,
                    relevance_threshold_rrf=0.005,
                    get_collection_name=MagicMock(return_value="test_col"),
                ),
                query_type="FAQ",
            )

        assert result is not None
        assert result.answer == "Квартиры от 50 000 EUR."


class TestOneAnswerPerQuestion:
    """Issue #3200: exactly one Telegram answer is delivered per question.

    Covers the three demo delivery paths — grounded RAG answer, semantic-cache
    hit, and safe no-answer fallback — and locks one outgoing message each.
    Skipped when aiogram is not installed (lean venv); runs under extras lane.
    """

    @pytest.fixture(autouse=True)
    def _require_aiogram(self) -> None:
        pytest.importorskip("aiogram", reason="aiogram not installed (use extras lane)")

    @staticmethod
    def _message() -> MagicMock:
        msg = MagicMock()
        msg.bot = MagicMock()
        msg.chat = MagicMock(id=100)
        msg.answer = AsyncMock()
        return msg

    @staticmethod
    def _config() -> MagicMock:
        return MagicMock(
            show_sources=False,
            streaming_enabled=False,
            relevance_threshold_rrf=0.005,
            get_collection_name=MagicMock(return_value="i3200_col"),
        )

    async def _run_pipeline(
        self,
        *,
        rag_result: dict,
        gen_result: dict,
        user_text: str,
        query_type: str = "FAQ",
    ):
        msg = self._message()
        gen = AsyncMock(return_value=gen_result)
        with (
            patch(
                "telegram_bot.pipelines.client.rag_pipeline",
                new=AsyncMock(return_value=rag_result),
            ),
            patch("telegram_bot.pipelines.client.generate_response", new=gen),
            patch(
                "telegram_bot.pipelines.client.send_html_messages",
                new=AsyncMock(),
            ) as send,
        ):
            result = await run_client_pipeline(
                user_text=user_text,
                user_id=42,
                session_id="sess-i3200",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=self._config(),
                query_type=query_type,
            )
        return result, gen, send

    @pytest.mark.asyncio
    async def test_grounded_answer_is_sent_exactly_once(self) -> None:
        answer = "Стоимость студии в Sunny Beach — 115 000 EUR, бассейн включён."
        rag_result = {
            "response": "",
            "query_type": "FAQ",
            "documents": [
                {
                    "content": "Sunny Beach studio, 115 000 EUR, pool.",
                    "metadata": {
                        "source_id": "sunny_beach_studio",
                        "title": "Sunny Beach Studio",
                        "url": "fixture://sunny_beach_studio",
                    },
                }
            ],
            "cache_hit": False,
            "grade_confidence": 0.9,
            "grounded": True,
            "latency_stages": {},
            "llm_call_count": 0,
        }
        gen_result = {
            "response": answer,
            "grounded": True,
            "safe_fallback_used": False,
            "response_sent": False,
            "llm_call_count": 1,
        }

        result, gen, send = await self._run_pipeline(
            rag_result=rag_result,
            gen_result=gen_result,
            # No apartment-intent keywords ("студи", "апартамент", …): those
            # route to the apartment agent before RAG at this surface.
            user_text="Сколько стоит квартира у моря в Sunny Beach?",
        )

        gen.assert_awaited_once()
        send.assert_awaited_once()
        assert send.await_args.args[1] == answer
        assert result.answer == answer

    @pytest.mark.asyncio
    async def test_safe_no_answer_is_sent_exactly_once(self) -> None:
        safe_text = "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."
        rag_result = {
            "response": "",
            "query_type": "FAQ",
            "documents": [],
            "cache_hit": False,
            "grade_confidence": 0.1,
            "grounded": False,
            "latency_stages": {},
            "llm_call_count": 0,
        }
        gen_result = {
            "response": safe_text,
            "grounded": False,
            "safe_fallback_used": True,
            "response_sent": False,
            "llm_call_count": 0,
        }

        result, gen, send = await self._run_pipeline(
            rag_result=rag_result,
            gen_result=gen_result,
            user_text="Какие документы нужны для ВНЖ на несуществующем острове в базе?",
        )

        gen.assert_awaited_once()
        send.assert_awaited_once()
        assert send.await_args.args[1] == safe_text
        assert result.answer == safe_text

    @pytest.mark.asyncio
    async def test_cache_hit_answer_is_sent_exactly_once_without_generation(self) -> None:
        cached = "Студия в Sunny Beach — 115 000 EUR (из кэша)."
        rag_result = {
            "response": cached,
            "query_type": "FAQ",
            "documents": [],
            "cache_hit": True,
            "latency_stages": {},
            "llm_call_count": 0,
        }
        gen_result = {"response": "не должен вызываться", "response_sent": False}

        result, gen, send = await self._run_pipeline(
            rag_result=rag_result,
            gen_result=gen_result,
            # No apartment-intent keywords at this surface (see grounded test).
            user_text="Сколько стоит квартира у моря в Sunny Beach?",
        )

        gen.assert_not_awaited()
        send.assert_awaited_once()
        assert send.await_args.args[1] == cached
        assert result.answer == cached


# ---------------------------------------------------------------------------
# Surface 2: Apartment Filter Dialog
# ---------------------------------------------------------------------------


class TestApartmentFilterDialogSurface:
    """Happy-path coverage for the Apartment Filter Dialog surface.

    Skipped when aiogram is not installed (lean venv); runs under extras lane.
    """

    @pytest.fixture(autouse=True)
    def _require_aiogram(self) -> None:
        pytest.importorskip("aiogram", reason="aiogram not installed (use extras lane)")

    @pytest.mark.asyncio
    async def test_handle_demo_button_posts_menu(self) -> None:
        """handle_demo_button sends a reply with the demo keyboard markup."""
        from telegram_bot.handlers.demo_handler import handle_demo_button

        message = MagicMock()
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.demo_handler.build_demo_menu",
            return_value=MagicMock(),
        ):
            await handle_demo_button(message)

        message.answer.assert_called_once()
        text_arg = message.answer.call_args.args[0]
        assert "Демонстрация" in text_arg

    @pytest.mark.asyncio
    async def test_handle_demo_apartments_starts_dialog(self) -> None:
        """handle_demo_apartments acknowledges callback and starts DemoSG.intro."""
        from telegram_bot.dialogs.states import DemoSG
        from telegram_bot.handlers.demo_handler import handle_demo_apartments

        callback = AsyncMock()
        callback.answer = AsyncMock()
        dialog_manager = AsyncMock()
        dialog_manager.start = AsyncMock()

        await handle_demo_apartments(callback, dialog_manager)

        callback.answer.assert_called_once()
        dialog_manager.start.assert_called_once()
        assert dialog_manager.start.call_args.args[0] == DemoSG.intro

    def test_create_demo_router_is_named_demo(self) -> None:
        """create_demo_router returns a Router named 'demo'."""
        from telegram_bot.handlers.demo_handler import create_demo_router

        router = create_demo_router()
        assert router.name == "demo"


# ---------------------------------------------------------------------------
# Surface 3: Manager Reply (Forum Topics)
# ---------------------------------------------------------------------------


class TestManagerReplySurface:
    """Happy-path coverage for the Manager Reply / Forum Topics surface.

    Skipped when aiogram is not installed (lean venv); runs under extras lane.
    """

    @pytest.fixture(autouse=True)
    def _require_aiogram(self) -> None:
        pytest.importorskip("aiogram", reason="aiogram not installed (use extras lane)")

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        bot = AsyncMock()
        bot.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=99))
        bot.copy_message = AsyncMock()
        bot.send_message = AsyncMock(return_value=MagicMock(message_thread_id=99, message_id=1))
        bot.close_forum_topic = AsyncMock()
        return bot

    @pytest.fixture
    def bridge(self, mock_bot: MagicMock):  # type: ignore[no-untyped-def]
        from telegram_bot.services.forum_bridge import ForumBridge

        return ForumBridge(bot=mock_bot, managers_group_id=-100500)

    @pytest.mark.asyncio
    async def test_relay_to_topic_forwards_client_message(
        self, bridge: object, mock_bot: MagicMock
    ) -> None:
        """relay_to_topic copies the client message into the manager topic."""
        await bridge.relay_to_topic(from_chat_id=555, message_id=10, topic_id=99)  # type: ignore[attr-defined]
        mock_bot.copy_message.assert_called_once_with(
            chat_id=-100500,
            from_chat_id=555,
            message_id=10,
            message_thread_id=99,
        )

    @pytest.mark.asyncio
    async def test_relay_to_client_sends_manager_reply(
        self, bridge: object, mock_bot: MagicMock
    ) -> None:
        """relay_to_client copies the manager reply back to the client chat."""
        await bridge.relay_to_client(topic_id=99, message_id=77, client_chat_id=555)  # type: ignore[attr-defined]
        mock_bot.copy_message.assert_called_once_with(
            chat_id=555,
            from_chat_id=-100500,
            message_id=77,
        )

    @pytest.mark.asyncio
    async def test_create_topic_and_relay_full_flow(
        self, bridge: object, mock_bot: MagicMock
    ) -> None:
        """Full manager-reply flow: create topic → relay client msg → relay manager reply."""
        topic_id = await bridge.create_topic(client_name="Анна", goal="Покупка")  # type: ignore[attr-defined]
        assert topic_id == 99

        await bridge.relay_to_topic(from_chat_id=123, message_id=1, topic_id=topic_id)  # type: ignore[attr-defined]
        await bridge.relay_to_client(topic_id=topic_id, message_id=2, client_chat_id=123)  # type: ignore[attr-defined]

        assert mock_bot.copy_message.call_count == 2

    @pytest.mark.asyncio
    async def test_start_qualification_without_dialog_manager_sends_fallback(
        self,
    ) -> None:
        """start_qualification falls back to a plain text reply when dialog_manager is None."""
        from aiogram.types import Message

        from telegram_bot.handlers.handoff import start_qualification

        message = AsyncMock(spec=Message)
        message.answer = AsyncMock()

        await start_qualification(message, dialog_manager=None)

        message.answer.assert_called_once()
        reply_text = message.answer.call_args.args[0]
        assert len(reply_text) > 0
