#!/usr/bin/env python3
"""Create golden test set for Ukrainian legal RAG."""

import json
from pathlib import Path


def create_golden_test_set():
    """
    Create 150 queries with ground truth for Criminal Code of Ukraine.

    Categories:
    - Article lookup (50 queries): "Стаття 121 УК"
    - Crime definitions (40): "Що таке шахрайство?"
    - Legal concepts (30): "Які злочини проти власності?"
    - Procedures (20): "Як подати апеляцію?"
    - Definitions (10): "Що таке презумпція невинуватості?"
    """

    queries = []

    # Category 1: Direct article lookup (50 queries - easy)
    important_articles = [
        # Crimes against person
        115,
        116,
        117,
        118,
        119,
        120,
        121,
        122,
        123,
        125,
        # Crimes against property
        185,
        186,
        187,
        189,
        190,
        191,
        192,
        193,
        # Crimes against public safety
        255,
        256,
        257,
        258,
        259,
        260,
        261,
        262,
        # Corruption crimes
        368,
        369,
        370,
        375,
        # Economic crimes
        289,
        190,
        191,
        192,
        193,
        194,
        195,
        # Drug crimes
        307,
        308,
        309,
        310,
        311,
        312,
    ]

    for article in important_articles:
        queries.append(
            {
                "id": len(queries) + 1,
                "query": f"Стаття {article} УК України",
                "expected_articles": [article],
                "category": "lookup",
                "difficulty": "easy",
            }
        )

    # Category 2: Crime questions (40 queries - medium)
    crime_queries = [
        ("Яка відповідальність за шахрайство?", [190]),
        ("Що таке розбій за УК України?", [187]),
        ("Яке покарання за крадіжку?", [185]),
        ("Що таке грабіж?", [186]),
        ("Яка відповідальність за вбивство?", [115]),
        ("Що таке умисне вбивство?", [115]),
        ("Яке покарання за умисне тяжке тілесне ушкодження?", [121]),
        ("Що таке тілесне ушкодження?", [121, 122, 125]),
        ("Яка відповідальність за хабарництво?", [368, 369]),
        ("Що таке отримання хабара?", [368]),
        ("Яке покарання за наркотики?", [307, 308, 309]),
        ("Що таке незаконний обіг наркотиків?", [307, 308]),
        ("Яка відповідальність за зґвалтування?", [152]),
        ("Що таке зґвалтування за УК?", [152]),
        ("Яке покарання за підпал?", [194]),
        ("Що таке умисне знищення майна?", [194]),
        ("Яка відповідальність за викрадення людини?", [146]),
        ("Що таке викрадення людини?", [146]),
        ("Яке покарання за торгівлю людьми?", [149]),
        ("Що таке торгівля людьми?", [149]),
    ]

    for query_text, expected in crime_queries:
        queries.append(
            {
                "id": len(queries) + 1,
                "query": query_text,
                "expected_articles": expected,
                "category": "crimes",
                "difficulty": "medium",
            }
        )

    # Category 3: Legal concepts (30 queries - medium/hard)
    concept_queries = [
        ("Які злочини проти власності передбачені?", [185, 186, 187, 189, 190]),
        ("Які є види тілесних ушкоджень?", [121, 122, 125]),
        ("Які злочини проти життя є в УК?", [115, 116, 117, 118, 119]),
        ("Що таке економічні злочини?", [289, 190, 191, 192]),
        ("Які злочини проти громадської безпеки?", [255, 256, 257, 258]),
        ("Що таке корупційні злочини?", [368, 369, 370]),
        ("Які злочини пов'язані з наркотиками?", [307, 308, 309, 310]),
        ("Що таке злочини проти статевої свободи?", [152, 153, 154]),
        ("Які злочини проти правосуддя?", [372, 373, 374, 375]),
        ("Що таке військові злочини?", [402, 403, 404, 405]),
    ]

    for query_text, expected in concept_queries:
        queries.append(
            {
                "id": len(queries) + 1,
                "query": query_text,
                "expected_articles": expected,
                "category": "legal_concept",
                "difficulty": "hard",
            }
        )

    # Category 4: Procedures (20 queries - medium)
    procedure_queries = [
        ("Як подати апеляцію на вирок?", [393, 394]),
        ("Що таке касаційне оскарження?", [433]),
        ("Які є види покарань?", [50, 51, 52, 53]),
        ("Що таке умовно-дострокове звільнення?", [81]),
        ("Як застосовується амністія?", [85, 86]),
        ("Що таке пом'якшуючі обставини?", [66]),
        ("Що таке обтяжуючі обставини?", [67]),
        ("Як визначається строк покарання?", [72]),
        ("Що таке давність притягнення до відповідальності?", [49]),
        ("Як застосовується помилування?", [87]),
    ]

    for query_text, expected in procedure_queries:
        queries.append(
            {
                "id": len(queries) + 1,
                "query": query_text,
                "expected_articles": expected,
                "category": "procedure",
                "difficulty": "medium",
            }
        )

    # Category 5: Definitions (10 queries - easy/medium)
    definition_queries = [
        ("Що таке презумпція невинуватості?", [62]),
        ("Що таке крайня необхідність?", [39]),
        ("Що таке необхідна оборона?", [36]),
        ("Що таке замах на злочин?", [15]),
        ("Що таке співучасть у злочині?", [26, 27]),
        ("Що таке рецидив злочинів?", [34]),
        ("Що таке множинність злочинів?", [33]),
        ("Що таке малозначність діяння?", [11]),
        ("Що таке вина у злочині?", [23, 24, 25]),
        ("Що таке кримінальна відповідальність?", [2]),
    ]

    for query_text, expected in definition_queries:
        queries.append(
            {
                "id": len(queries) + 1,
                "query": query_text,
                "expected_articles": expected,
                "category": "definitions",
                "difficulty": "easy",
            }
        )

    # Create test set
    test_set = {
        "version": "1.0.0",
        "created": "2025-10-30",
        "document": "Кримінальний кодекс України",
        "queries": queries,
        "total_queries": len(queries),
        "categories": {
            "lookup": sum(1 for q in queries if q["category"] == "lookup"),
            "crimes": sum(1 for q in queries if q["category"] == "crimes"),
            "legal_concept": sum(1 for q in queries if q["category"] == "legal_concept"),
            "procedure": sum(1 for q in queries if q["category"] == "procedure"),
            "definitions": sum(1 for q in queries if q["category"] == "definitions"),
        },
        "difficulty": {
            "easy": sum(1 for q in queries if q["difficulty"] == "easy"),
            "medium": sum(1 for q in queries if q["difficulty"] == "medium"),
            "hard": sum(1 for q in queries if q["difficulty"] == "hard"),
        },
    }

    # Save
    output_path = Path(__file__).parent.parent.parent / "tests" / "data" / "golden_test_set.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(test_set, f, ensure_ascii=False, indent=2)

    print(f"✅ Created golden test set: {len(queries)} queries")
    print(f"   Categories: {test_set['categories']}")
    print(f"   Difficulty: {test_set['difficulty']}")
    print(f"   Saved to: {output_path}")


if __name__ == "__main__":
    create_golden_test_set()
