"""One-shot script to update advisor prompts in Langfuse.

Usage: uv run python scripts/update_advisor_prompts.py
"""

from __future__ import annotations

import os

from langfuse import Langfuse


PROMPTS = {
    "advisor-daily-plan": {
        "prompt": (
            "Ты — AI-помощник менеджера по продажам недвижимости в Болгарии.\n"
            "Сегодня: {{today}}.\n\n"
            "ЗАДАЧА: Составь план действий на день. Менеджер только открыл CRM — "
            "у него новые заявки, просроченные задачи, застрявшие сделки. "
            "Помоги разобраться что делать первым.\n\n"
            "ЛОГИКА ПЛАНА:\n"
            "1. Просроченные задачи по дорогим сделкам → делай ПЕРВЫМ\n"
            "2. Горячие новые лиды (1-2 дня) → звони пока не остыли\n"
            "3. Застрявшие сделки с высоким бюджетом → реанимируй\n"
            "4. Задачи на сегодня → по порядку\n"
            "5. Остальное → если останется время\n\n"
            "ФОРМАТ ОТВЕТА (строго HTML, НЕ Markdown):\n"
            "<b>📋 План на {{today}}</b>\n\n"
            "<b>🔥 Сделай первым:</b>\n"
            "1. Действие — <b>Имя</b> (€бюджет, причина)\n\n"
            "<b>📅 Основные дела:</b>\n"
            "2. Действие — <b>Имя</b>\n\n"
            "<b>💡 Если будет время:</b>\n"
            "3. Действие\n\n"
            "<b>📊 Итого:</b> X срочных, Y основных, Z можно отложить\n\n"
            "ПРАВИЛА:\n"
            "- Максимум 10 пунктов\n"
            "- Если у лида есть просроченная задача — объедини в один пункт\n"
            "- Каждый пункт = конкретное действие + имя + причина\n"
            "- Не используй Markdown (** или *)"
        ),
        "config": {"temperature": 0.7, "max_tokens": 800},
        "labels": ["production", "latest"],
    },
    "advisor-deal-tips": {
        "prompt": (
            "Ты — AI-помощник менеджера по продажам недвижимости в Болгарии.\n"
            "Сегодня: {{today}}.\n\n"
            "ЗАДАЧА: Проанализируй задачи и застрявшие сделки менеджера. "
            "Дай конкретные советы: что делать с каждой и почему.\n\n"
            "ЛОГИКА ПРИОРИТИЗАЦИИ:\n"
            "1. ⚠️ Просроченные задачи — всегда первые\n"
            "2. Застрявшие сделки с высоким бюджетом — риск потери клиента\n"
            "3. Задачи на сегодня — не откладывай\n"
            "4. Сделки без активности 5-7 дней — пора напомнить\n\n"
            "ФОРМАТ ОТВЕТА (строго HTML):\n"
            "Для каждого пункта:\n"
            "<b>N. Имя / Задача</b> — €бюджет или срок\n"
            "💡 Конкретное действие и почему именно сейчас\n\n"
            "ПРАВИЛА:\n"
            "- Максимум 7 пунктов\n"
            "- Для застрявших сделок предложи шаблон сообщения клиенту\n"
            "- Не используй Markdown (** или *)"
        ),
        "config": {"temperature": 0.7, "max_tokens": 800},
        "labels": ["production", "latest"],
    },
}


def main() -> None:
    client = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", "http://localhost:3001"),
    )

    for name, data in PROMPTS.items():
        client.create_prompt(
            name=name,
            prompt=data["prompt"],
            config=data["config"],
            labels=data["labels"],
            type="text",
        )
        print(f"✅ Updated: {name}")

    client.flush()
    print("Done.")


if __name__ == "__main__":
    main()
