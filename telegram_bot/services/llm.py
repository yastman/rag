"""LLM service for answer generation."""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from langfuse import get_client, observe


logger = logging.getLogger(__name__)


class LLMService:
    """Generate answers using LLM (OpenAI-compatible API)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        client: httpx.AsyncClient | None = None,
    ):
        """Initialize LLM service.

        Args:
            api_key: OpenAI API key
            base_url: API base URL (for OpenAI-compatible APIs)
            model: Model name
            client: Optional httpx.AsyncClient for dependency injection (testing)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=60.0)

    @observe(name="llm-generate-answer", as_type="generation")
    async def generate_answer(
        self,
        question: str,
        context_chunks: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> str:
        """
        Generate answer based on question and retrieved context with graceful degradation.

        Args:
            question: User question
            context_chunks: Retrieved chunks from Qdrant
            system_prompt: Custom system prompt

        Returns:
            Generated answer. Returns fallback message on error.
        """
        langfuse = get_client()

        # Track generation start
        langfuse.update_current_generation(
            input={"question_preview": question[:100], "context_count": len(context_chunks)},
            model=self.model,
        )

        try:
            # Build context from chunks
            context = self._format_context(context_chunks)

            # Default system prompt
            if not system_prompt:
                system_prompt = """Ты - ассистент по недвижимости в Болгарии.

Отвечай на вопросы пользователя на основе предоставленного контекста.
Если информации недостаточно, честно скажи об этом.
Всегда указывай цены в евро и расстояния в метрах.
Будь вежливым и полезным.

Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."""

            # Build messages
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"""Контекст:
{context}

Вопрос: {question}

Ответь на вопрос на основе контекста выше.""",
                },
            ]

            # Call LLM API
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,  # Reduced for faster generation (2026 best practice)
                },
            )
            response.raise_for_status()

            data = response.json()
            answer = data["choices"][0]["message"]["content"]

            # Track completion with usage
            langfuse.update_current_generation(
                output={"answer_length": len(answer)},
                usage_details={
                    "input": data.get("usage", {}).get("prompt_tokens", 0),
                    "output": data.get("usage", {}).get("completion_tokens", 0),
                },
            )

            return answer

        except httpx.TimeoutException as e:
            logger.error(f"LLM API timeout: {e}")
            return self._get_fallback_answer(question, context_chunks)
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API HTTP error {e.response.status_code}: {e}")
            return self._get_fallback_answer(question, context_chunks)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            return self._get_fallback_answer(question, context_chunks)

    async def stream_answer(
        self,
        question: str,
        context_chunks: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream answer generation token by token with graceful degradation.

        Allows real-time display of LLM response in Telegram bot.
        Reduces perceived latency - user sees first tokens in ~0.1s.

        Args:
            question: User question
            context_chunks: Retrieved chunks from Qdrant
            system_prompt: Custom system prompt

        Yields:
            Text chunks as they arrive from LLM. Yields fallback on error.
        """
        try:
            # Build context
            context = self._format_context(context_chunks)

            # Default system prompt
            if not system_prompt:
                system_prompt = """Ты - ассистент по недвижимости в Болгарии.

Отвечай на вопросы пользователя на основе предоставленного контекста.
Если информации недостаточно, честно скажи об этом.
Всегда указывай цены в евро и расстояния в метрах.
Будь вежливым и полезным.

Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."""

            # Build messages
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"""Контекст:
{context}

Вопрос: {question}

Ответь на вопрос на основе контекста выше.""",
                },
            ]

            # Stream LLM response
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,  # Reduced for faster generation (2026 best practice)
                    "stream": True,  # Enable streaming
                },
                timeout=60.0,
            ) as response:
                response.raise_for_status()

                # Parse SSE stream
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    # SSE format: "data: {...}"
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        # Skip [DONE] marker
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")

                            if content:
                                yield content

                        except json.JSONDecodeError:
                            continue

        except httpx.TimeoutException as e:
            logger.error(f"LLM streaming timeout: {e}")
            yield self._get_fallback_answer(question, context_chunks)
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM streaming HTTP error {e.response.status_code}: {e}")
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
            score = chunk.get("score", 0)

            # Add metadata info if available
            meta_str = ""
            if "title" in metadata:
                meta_str += f"Название: {metadata['title']}\n"
            if "city" in metadata:
                meta_str += f"Город: {metadata['city']}\n"
            if "price" in metadata:
                meta_str += f"Цена: {metadata['price']:,}€\n"

            context_parts.append(f"[Объект {i}] (релевантность: {score:.2f})\n{meta_str}{text}")

        return "\n\n---\n\n".join(context_parts)

    def _get_fallback_answer(self, question: str, context_chunks: list[dict[str, Any]]) -> str:
        """
        Generate fallback answer when LLM API fails.

        Returns raw search results as a simple text response.

        Args:
            question: User question
            context_chunks: Retrieved context chunks

        Returns:
            Simple formatted answer with search results
        """
        if not context_chunks:
            return "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."

        # Format first 3 results as simple text
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

    async def generate(self, prompt: str, max_tokens: int = 200) -> str:
        """Simple text generation for internal use (CESC, preference extraction).

        Uses low temperature for more deterministic/structured output.

        Args:
            prompt: Text prompt to send to LLM
            max_tokens: Maximum tokens in response (default: 200)

        Returns:
            Generated text from LLM

        Raises:
            Exception: If LLM API call fails
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM generate failed: {e}")
            raise

    async def close(self):
        """Close HTTP client if owned by this instance."""
        if self._owns_client:
            await self.client.aclose()
