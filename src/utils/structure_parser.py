#!/usr/bin/env python3
"""
Structure Parser for Ukrainian Legal Documents
Regex-based extraction (fallback when Claude API unavailable)
"""

import re


# Ukrainian number word to integer mapping
UKRAINIAN_NUMBERS = {
    "перша": 1,
    "перший": 1,
    "друга": 2,
    "другий": 2,
    "третя": 3,
    "третій": 3,
    "четверта": 4,
    "четвертий": 4,
    "п'ята": 5,
    "п'ятий": 5,
    "шоста": 6,
    "шостий": 6,
    "сьома": 7,
    "сьомий": 7,
    "восьма": 8,
    "восьмий": 8,
    "дев'ята": 9,
    "дев'ятий": 9,
    "десята": 10,
    "десятий": 10,
}

# Roman to Arabic conversion
ROMAN_NUMERALS = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
    "XVI": 16,
    "XVII": 17,
    "XVIII": 18,
    "XIX": 19,
    "XX": 20,
}


def roman_to_int(roman: str) -> int:
    """Convert Roman numeral to integer."""
    return ROMAN_NUMERALS.get(roman.upper())  # type: ignore


def ukrainian_number_to_int(word: str) -> int:
    """Convert Ukrainian number word to integer."""
    return UKRAINIAN_NUMBERS.get(word.lower())  # type: ignore


def parse_legal_structure(chunk_text: str) -> dict:
    """
    Extract legal document structure metadata using regex patterns.

    Args:
        chunk_text: Text chunk from legal document

    Returns:
        Dictionary with structure metadata
    """
    metadata = {  # type: ignore
        "book": None,
        "book_number": None,
        "section": None,
        "section_number": None,
        "chapter": None,
        "chapter_number": None,
        "article_number": None,
        "article_title": None,
        "related_articles": [],
    }

    # Extract Article (Стаття)
    article_patterns = [
        r"Стаття\s+(\d+)\.\s+(.+?)(?=\n|\r|$)",  # Standard format
        r"(?:^|\n)(\d+)\.\s+(.+?)(?=\n|\r|$)",  # Just number and title
    ]

    for pattern in article_patterns:
        article_match = re.search(pattern, chunk_text, re.MULTILINE)
        if article_match:
            metadata["article_number"] = int(article_match.group(1))  # type: ignore
            # Clean title (remove extra whitespace, newlines)
            title = article_match.group(2).strip()
            title = re.sub(r"\s+", " ", title)
            metadata["article_title"] = title  # type: ignore
            break

    # Extract Chapter (Глава)
    chapter_patterns = [
        r"Глава\s+(\d+)\.\s+(.+?)(?=\n|\r|$)",  # Arabic numerals
    ]

    for pattern in chapter_patterns:
        chapter_match = re.search(pattern, chunk_text, re.MULTILINE)
        if chapter_match:
            metadata["chapter_number"] = int(chapter_match.group(1))  # type: ignore
            title = chapter_match.group(2).strip()
            metadata["chapter"] = title  # type: ignore
            break

    # Extract Section (Розділ) - Roman numerals
    section_patterns = [
        r"Розділ\s+([IVX]+)\.\s+(.+?)(?=\n|\r|$)",
    ]

    for pattern in section_patterns:
        section_match = re.search(pattern, chunk_text, re.MULTILINE)
        if section_match:
            roman = section_match.group(1)
            metadata["section_number"] = roman_to_int(roman)  # type: ignore
            title = section_match.group(2).strip()
            metadata["section"] = title  # type: ignore
            break

    # Extract Book (Книга) - Ukrainian number words
    book_patterns = [
        r"Книга\s+(перша|друга|третя|четверта|п\'ята|шоста)\.\s+(.+?)(?=\n|\r|$)",
    ]

    for pattern in book_patterns:
        book_match = re.search(pattern, chunk_text, re.IGNORECASE | re.MULTILINE)
        if book_match:
            ukrainian_num = book_match.group(1)
            metadata["book_number"] = ukrainian_number_to_int(ukrainian_num)  # type: ignore
            title = book_match.group(2).strip()
            metadata["book"] = title  # type: ignore
            break

    # Extract related articles from text
    metadata["related_articles"] = extract_related_articles(chunk_text)

    return metadata


def extract_related_articles(chunk_text: str) -> list[int]:
    """
    Extract article numbers mentioned/referenced in the text.

    Patterns:
    - "статті 25"
    - "стаття 13"
    - "статтею 26"
    - "відповідно до статті 12"
    """
    related = []

    # Pattern for article references
    patterns = [
        r"статт[іяює]\s+(\d+)",  # статті/стаття/статтею/статтею + number
        r"статті\s+(\d+)",
        r"стаття\s+(\d+)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, chunk_text, re.IGNORECASE)
        for match in matches:
            article_num = int(match)
            if article_num not in related:
                related.append(article_num)

    # Sort and return
    return sorted(related)


def extract_contextual_prefix(
    metadata: dict, document_name: str = "Цивільний кодекс України"
) -> str:
    """
    Generate a contextual prefix from metadata.
    Fallback when Claude API is not available.

    Args:
        metadata: Parsed metadata dict
        document_name: Name of the document

    Returns:
        Contextual prefix string
    """
    parts = [f"Документ: {document_name}"]

    if metadata.get("book"):
        book_str = (
            f"Книга {metadata['book_number']}: {metadata['book']}"
            if metadata["book_number"]
            else metadata["book"]
        )
        parts.append(book_str)

    if metadata.get("section"):
        section_str = (
            f"Розділ {metadata['section_number']}: {metadata['section']}"
            if metadata["section_number"]
            else metadata["section"]
        )
        parts.append(section_str)

    if metadata.get("chapter"):
        chapter_str = (
            f"Глава {metadata['chapter_number']}: {metadata['chapter']}"
            if metadata["chapter_number"]
            else metadata["chapter"]
        )
        parts.append(chapter_str)

    if metadata.get("article_number"):
        article_str = f"Стаття {metadata['article_number']}"
        if metadata.get("article_title"):
            article_str += f": {metadata['article_title']}"
        parts.append(article_str)

    return "\n".join(parts)


def add_graph_edges(metadata: dict) -> dict:
    """
    Add graph relationship edges (prev/next article).

    Args:
        metadata: Parsed metadata dict

    Returns:
        Updated metadata with graph edges
    """
    if metadata.get("article_number"):
        article_num = metadata["article_number"]
        metadata["prev_article"] = article_num - 1 if article_num > 1 else None
        metadata["next_article"] = article_num + 1

    return metadata


# Example usage
if __name__ == "__main__":
    # Test cases
    test_cases = [
        {
            "name": "Full structure",
            "text": """Книга перша. Загальні положення

Розділ I. Загальні положення

Глава 2. Здійснення цивільних прав та виконання обов'язків

Стаття 13. Межі здійснення цивільних прав

1. Цивільні права особа здійснює у межах, наданих їй договором або актами цивільного законодавства.

2. При здійсненні своїх прав особа зобов'язана утримуватися від дій, які могли б порушити права інших осіб, зокрема відповідно до статті 12 та статті 25.""",
        },
        {
            "name": "Article only",
            "text": """Стаття 25. Цивільна правоздатність фізичної особи

1. Здатність мати цивільні права та обов'язки (цивільна правоздатність) мають усі фізичні особи.""",
        },
        {
            "name": "Chapter and article",
            "text": """Глава 3. Представництво. Довіреність

Стаття 31. Представник

Представником є особа, яка діє від імені іншої особи.""",
        },
    ]

    print("=" * 80)
    print("STRUCTURE PARSER - TEST CASES")
    print("=" * 80)

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print("-" * 80)
        print(f"Text ({len(test['text'])} chars):")
        print(test["text"][:200] + "..." if len(test["text"]) > 200 else test["text"])
        print()

        # Parse structure
        metadata = parse_legal_structure(test["text"])
        metadata = add_graph_edges(metadata)

        print("Extracted Metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")

        # Generate contextual prefix
        context = extract_contextual_prefix(metadata)
        print("\nContextual Prefix:")
        print(context)
        print("-" * 80)

    print("\n✓ All tests completed!")
