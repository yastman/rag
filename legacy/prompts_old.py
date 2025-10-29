#!/usr/bin/env python3
"""
Prompt Templates for Contextual Retrieval - Ukrainian Legal Documents
Based on Anthropic's Contextual Retrieval methodology
"""

# Ukrainian Legal Document Context Prompt
DOCUMENT_CONTEXT_PROMPT = """<document>
Назва документа: {document_name}

Повний текст документа:
{doc_content}
</document>"""

# Ukrainian Legal Chunk Contextualization Prompt
CHUNK_CONTEXT_PROMPT = """Ось фрагмент тексту з юридичного документа:

<chunk>
{chunk_content}
</chunk>

Будь ласка, надай короткий контекст для цього фрагмента в рамках всього документа для покращення пошуку.

Контекст має включати (якщо є в документі):
- Назву книги (наприклад, "Книга перша. Загальні положення")
- Назву розділу (наприклад, "Розділ I. Загальні положення")
- Назву глави (наприклад, "Глава 2. Здійснення цивільних прав")
- Номер і назву статті (наприклад, "Стаття 13. Межі здійснення цивільних прав")

Відповідь має бути короткою (1-2 речення) і містити лише контекст для ідентифікації розташування фрагмента в документі. Не додавай зайвий текст, пояснення чи коментарі."""

# Alternative: More structured prompt (can experiment with this)
CHUNK_CONTEXT_PROMPT_STRUCTURED = """Проаналізуй фрагмент тексту з юридичного документа та надай його структурний контекст.

<document_name>{document_name}</document_name>

<chunk>
{chunk_content}
</chunk>

Відповідь має бути у форматі:
[Книга X] → [Розділ Y] → [Глава Z] → [Стаття N. Назва статті]

Якщо якась частина структури відсутня, пропусти її. Відповідь має містити лише структурну інформацію, без додаткового тексту."""

# ENHANCED: Context + Metadata + Relationships extraction (ONE API call)
ENHANCED_CHUNK_CONTEXT_PROMPT = """Проаналізуй фрагмент тексту з юридичного документа та надай:
1. Короткий контекст для пошуку (1-2 речення)
2. Структурні метадані у JSON форматі
3. Пов'язані статті (якщо згадуються)

<chunk>
{chunk_content}
</chunk>

Відповідь має бути у ТОЧНОМУ форматі (копіюй структуру):

КОНТЕКСТ: [Короткий опис розташування фрагмента в документі. Включи назву документа, книгу, розділ, главу, статтю - якщо є. Це використовується для покращення семантичного пошуку.]

МЕТАДАНІ:
{{
  "book": "Книга перша. Загальні положення",
  "book_number": 1,
  "section": "Розділ I. Загальні положення",
  "section_number": 1,
  "chapter": "Глава 2. Здійснення цивільних прав та виконання обов'язків",
  "chapter_number": 2,
  "article_number": 13,
  "article_title": "Межі здійснення цивільних прав",
  "related_articles": [12, 14, 25]
}}

ВАЖЛИВО:
- Якщо якесь поле відсутнє, використай null (не "null", а null без лапок)
- Для related_articles: включи номери статей, які ЯВНО згадуються в тексті (наприклад "відповідно до статті 25") або логічно пов'язані
- Якщо related_articles немає, використай пустий список []
- JSON має бути валідним (не додавай коментарі всередині JSON)
- Числа (book_number, article_number) мають бути числами, не рядками
- Для римських номерів розділів (I, II, III) конвертуй в арабські числа (1, 2, 3)"""

# System prompt for Claude (optional, for better instruction following)
SYSTEM_PROMPT = """Ти - експертна система для аналізу структури юридичних документів України.
Твоє завдання - надавати короткий, точний контекст для фрагментів юридичних текстів,
щоб покращити їх пошук та класифікацію.

Завжди відповідай українською мовою.
Твоя відповідь має бути максимально короткою та інформативною.
Включай лише структурну інформацію: книга, розділ, глава, стаття."""


# Helper function to format prompts
def format_document_context(
    doc_content: str, document_name: str = "Цивільний кодекс України"
) -> str:
    """Format the document context prompt with actual content."""
    return DOCUMENT_CONTEXT_PROMPT.format(document_name=document_name, doc_content=doc_content)


def format_chunk_context(
    chunk_content: str,
    use_structured: bool = False,
    document_name: str = "Цивільний кодекс України",
) -> str:
    """Format the chunk contextualization prompt."""
    if use_structured:
        return CHUNK_CONTEXT_PROMPT_STRUCTURED.format(
            chunk_content=chunk_content, document_name=document_name
        )
    return CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk_content)


def format_enhanced_chunk_context(chunk_content: str) -> str:
    """Format the ENHANCED chunk contextualization prompt (context + metadata + relationships)."""
    return ENHANCED_CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk_content)


# Example usage (for testing):
if __name__ == "__main__":
    # Test prompt formatting
    sample_doc = "Цивільний кодекс України. Книга перша. Загальні положення..."
    sample_chunk = "Стаття 13. При здійсненні своїх прав особа зобов'язана утримуватися..."

    doc_prompt = format_document_context(sample_doc)
    chunk_prompt = format_chunk_context(sample_chunk)

    print("=" * 80)
    print("DOCUMENT CONTEXT PROMPT:")
    print("=" * 80)
    print(doc_prompt[:500] + "..." if len(doc_prompt) > 500 else doc_prompt)
    print()

    print("=" * 80)
    print("CHUNK CONTEXT PROMPT:")
    print("=" * 80)
    print(chunk_prompt)
    print()

    print("✓ Prompts validated successfully!")
