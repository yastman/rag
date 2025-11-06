"""LLM service for answer generation."""

import json
from typing import Any, AsyncGenerator

import httpx


class LLMService:
    """Generate answers using LLM (OpenAI-compatible API)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
    ):
        """Initialize LLM service.

        Args:
            api_key: OpenAI API key
            base_url: API base URL (for OpenAI-compatible APIs)
            model: Model name
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=60.0)

    async def generate_answer(
        self,
        question: str,
        context_chunks: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> str:
        """
        Generate answer based on question and retrieved context.

        Args:
            question: User question
            context_chunks: Retrieved chunks from Qdrant
            system_prompt: Custom system prompt

        Returns:
            Generated answer
        """
        # Build context from chunks
        context = self._format_context(context_chunks)

        # Default system prompt
        if not system_prompt:
            system_prompt = """Ты - ассистент по недвижимости в Болгарии.

Отвечай на вопросы пользователя на основе предоставленного контекста.
Если информации недостаточно, честно скажи об этом.
Всегда указывай цены в евро и расстояния в метрах.
Будь вежливым и полезным."""

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
                "max_tokens": 1000,
            },
        )
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def stream_answer(
        self,
        question: str,
        context_chunks: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream answer generation token by token (Task 2.3).

        Allows real-time display of LLM response in Telegram bot.
        Reduces perceived latency - user sees first tokens in ~0.1s.

        Args:
            question: User question
            context_chunks: Retrieved chunks from Qdrant
            system_prompt: Custom system prompt

        Yields:
            Text chunks as they arrive from LLM
        """
        # Build context
        context = self._format_context(context_chunks)

        # Default system prompt
        if not system_prompt:
            system_prompt = """Ты - ассистент по недвижимости в Болгарии.

Отвечай на вопросы пользователя на основе предоставленного контекста.
Если информации недостаточно, честно скажи об этом.
Всегда указывай цены в евро и расстояния в метрах.
Будь вежливым и полезным."""

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
                "max_tokens": 1000,
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

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
