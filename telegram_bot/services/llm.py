"""Deprecated compatibility shim for legacy answer generation helpers.

Prefer telegram_bot.services.generate_response for active runtime paths.
"""

import logging
import warnings
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import instructor
import openai
from langfuse.openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator


logger = logging.getLogger(__name__)

# Default confidence threshold for triggering fallback response
LOW_CONFIDENCE_THRESHOLD = 0.3


class ConfidenceResponse(BaseModel):
    """Pydantic model for LLM confidence extraction via Instructor.

    Confidence is clamped to [0.0, 1.0] to preserve legacy clamp semantics:
    values outside this range are accepted but clipped, not rejected.
    """

    answer: str = Field(description="Generated answer text")
    confidence: float = Field(
        default=0.5,
        description="Confidence score — clamped to [0.0, 1.0] to match legacy behavior",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        """Clamp confidence to [0.0, 1.0], preserving legacy clamp semantics."""
        return max(0.0, min(1.0, float(v)))


@dataclass
class ConfidenceResult:
    """Result from LLM generation with confidence scoring.

    Attributes:
        answer: Generated answer text
        confidence: Confidence score (0.0-1.0)
        is_low_confidence: True if confidence < low_confidence_threshold
        raw_response: Original LLM response before parsing
    """

    answer: str
    confidence: float
    is_low_confidence: bool
    raw_response: str | None = None


class LLMService:
    """Generate answers using LLM (OpenAI-compatible API via LiteLLM)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    ):
        warnings.warn(
            "LLMService is deprecated and will be removed in a future release. "
            "Use generate_response() from telegram_bot.services.generate_response instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.low_confidence_threshold = low_confidence_threshold
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            max_retries=2,
            timeout=60.0,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=("Client should be an instance of openai.OpenAI or openai.AsyncOpenAI.*"),
                category=UserWarning,
            )
            self._instructor_client = instructor.from_openai(self.client)

    async def generate_answer(
        self,
        question: str,
        context_chunks: list[dict[str, Any]],
        system_prompt: str | None = None,
        with_confidence: bool = False,
    ) -> str | ConfidenceResult:
        """Generate answer based on question and retrieved context."""
        try:
            context = self._format_context(context_chunks)

            if not system_prompt:
                if with_confidence:
                    system_prompt = self._get_confidence_system_prompt()
                else:
                    system_prompt = (
                        "Ты - ассистент по недвижимости.\n\n"
                        "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
                        "Если информации недостаточно, честно скажи об этом.\n"
                        "Всегда указывай цены в евро и расстояния в метрах.\n"
                        "Будь вежливым и полезным.\n\n"
                        "Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."
                    )

            if with_confidence:
                user_content = (
                    f"Контекст:\n{context}\n\n"
                    f"Вопрос: {question}\n\n"
                    "Ответь на вопрос на основе контекста выше. "
                    'Верни JSON с полями "answer" и "confidence".'
                )
            else:
                user_content = (
                    f"Контекст:\n{context}\n\n"
                    f"Вопрос: {question}\n\n"
                    "Ответь на вопрос на основе контекста выше."
                )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            if with_confidence:
                response_model = await self._instructor_client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    response_model=ConfidenceResponse,
                    max_retries=2,
                    temperature=0.7,
                    max_tokens=4096,
                    name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
                )
                return ConfidenceResult(
                    answer=response_model.answer,
                    confidence=response_model.confidence,
                    is_low_confidence=response_model.confidence < self.low_confidence_threshold,
                    raw_response=None,
                )

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.7,
                max_tokens=4096,
                name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
            )

            message = response.choices[0].message
            return message.content or ""

        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            logger.error(f"LLM API timeout/connection: {e}")
            fallback = self._get_fallback_answer(question, context_chunks)
            if with_confidence:
                return ConfidenceResult(
                    answer=fallback, confidence=0.0, is_low_confidence=True, raw_response=None
                )
            return fallback
        except openai.RateLimitError as e:
            logger.error(f"LLM API rate limit: {e}")
            fallback = self._get_fallback_answer(question, context_chunks)
            if with_confidence:
                return ConfidenceResult(
                    answer=fallback, confidence=0.0, is_low_confidence=True, raw_response=None
                )
            return fallback
        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            fallback = self._get_fallback_answer(question, context_chunks)
            if with_confidence:
                return ConfidenceResult(
                    answer=fallback, confidence=0.0, is_low_confidence=True, raw_response=None
                )
            return fallback

    def _get_confidence_system_prompt(self) -> str:
        """Get system prompt that requests confidence scoring."""
        return (
            "Ты - ассистент по недвижимости.\n\n"
            "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
            "Всегда указывай цены в евро и расстояния в метрах.\n\n"
            "ВАЖНО: Верни ответ в формате JSON:\n"
            "{\n"
            '    "answer": "твой ответ здесь (используй Markdown: **жирный** для важного, • для списков)",\n'
            '    "confidence": 0.85\n'
            "}\n\n"
            "Оцени confidence (уверенность) от 0.0 до 1.0:\n"
            "- 0.9-1.0: Ответ полностью основан на контексте, все факты подтверждены\n"
            "- 0.7-0.9: Ответ в основном основан на контексте, минимальные допущения\n"
            "- 0.5-0.7: Частичный ответ, некоторая информация отсутствует в контексте\n"
            "- 0.3-0.5: Слабый ответ, много информации отсутствует\n"
            "- 0.0-0.3: Ответ не основан на контексте или контекст нерелевантен\n\n"
            "Если контекст не содержит релевантной информации, установи confidence < 0.5."
        )

    async def stream_answer(
        self,
        question: str,
        context_chunks: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream answer generation token by token."""
        try:
            context = self._format_context(context_chunks)

            if not system_prompt:
                system_prompt = (
                    "Ты - ассистент по недвижимости.\n\n"
                    "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
                    "Если информации недостаточно, честно скажи об этом.\n"
                    "Всегда указывай цены в евро и расстояния в метрах.\n"
                    "Будь вежливым и полезным.\n\n"
                    "Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."
                )

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Контекст:\n{context}\n\n"
                        f"Вопрос: {question}\n\n"
                        "Ответь на вопрос на основе контекста выше."
                    ),
                },
            ]

            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.7,
                max_tokens=4096,
                stream=True,
                stream_options={"include_usage": True},
                name="stream-answer",  # type: ignore[call-overload]  # langfuse kwarg
            )

            async for chunk in stream:
                if chunk.usage:
                    continue
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

        except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as e:
            logger.error(f"LLM streaming error: {e}")
            yield self._get_fallback_answer(question, context_chunks)
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}", exc_info=True)
            yield self._get_fallback_answer(question, context_chunks)

    def _format_context(self, chunks: list[dict[str, Any]]) -> str:
        """Format context chunks for LLM prompt."""
        if not chunks:
            return "Релевантной информации не найдено."

        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk["text"]
            metadata = chunk.get("metadata", {})

            meta_str = ""
            if "title" in metadata:
                meta_str += f"Название: {metadata['title']}\n"
            if "city" in metadata:
                meta_str += f"Город: {metadata['city']}\n"
            if "price" in metadata:
                meta_str += f"Цена: {metadata['price']:,}€\n"

            context_parts.append(f"[Объект {i}]\n{meta_str}{text}")

        return "\n\n---\n\n".join(context_parts)

    def _get_fallback_answer(self, question: str, context_chunks: list[dict[str, Any]]) -> str:
        """Generate fallback answer when LLM API fails."""
        if not context_chunks:
            return "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."

        fallback = "⚠️ Сервис генерации ответов временно недоступен.\n\n"
        fallback += "Вот найденные объекты по вашему запросу:\n\n"

        for i, chunk in enumerate(context_chunks[:3], 1):
            meta = chunk.get("metadata", {})
            fallback += f"{i}. "

            if "title" in meta:
                fallback += f"{meta['title']}\n"
            if "price" in meta:
                price = meta["price"]
                if isinstance(price, (int, float)):
                    fallback += f"   Цена: {price:,}€\n"
                else:
                    fallback += f"   Цена: {price}€\n"
            if "city" in meta:
                fallback += f"   Город: {meta['city']}\n"
            if "rooms" in meta:
                fallback += f"   Комнат: {meta['rooms']}\n"

            fallback += "\n"

        fallback += "Пожалуйста, попробуйте повторить запрос позже для получения детального ответа."

        return fallback

    def get_low_confidence_response(
        self, question: str, context_chunks: list[dict[str, Any]], confidence: float
    ) -> str:
        """Generate response when confidence is below threshold."""
        response = "⚠️ **Не уверен в точности ответа**\n\n"
        response += f"Моя уверенность в ответе: {confidence:.0%}\n\n"

        if not context_chunks:
            response += (
                "К сожалению, не нашёл релевантной информации по вашему запросу.\n"
                "Попробуйте уточнить запрос или переформулировать вопрос."
            )
            return response

        response += "Вот что удалось найти по вашему запросу:\n\n"

        for i, chunk in enumerate(context_chunks[:3], 1):
            meta = chunk.get("metadata", {})
            response += f"**{i}. "

            if "title" in meta:
                response += f"{meta['title']}**\n"
            else:
                response += "Объект**\n"

            if "price" in meta:
                price = meta["price"]
                if isinstance(price, (int, float)):
                    response += f"• Цена: {price:,}€\n"
                else:
                    response += f"• Цена: {price}€\n"
            if "city" in meta:
                response += f"• Город: {meta['city']}\n"
            if "rooms" in meta:
                response += f"• Комнат: {meta['rooms']}\n"

            response += "\n"

        response += "_Рекомендую уточнить запрос для получения более точного ответа._"

        return response

    async def generate(self, prompt: str, max_tokens: int = 200) -> str:
        """Simple text generation for internal use (CESC, preference extraction)."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],  # type: ignore[arg-type]
                temperature=0.3,
                max_tokens=max_tokens,
                name="generate-simple",  # type: ignore[call-overload]  # langfuse kwarg
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM generate failed: {e}")
            raise

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.close()
