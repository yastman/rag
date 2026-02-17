"""
Comprehensive Unit Tests for Structure Parser.

Tests the regex-based parsing of Ukrainian legal documents including:
- Roman numeral conversion
- Ukrainian number word conversion
- Article extraction (Стаття)
- Chapter extraction (Глава)
- Section extraction (Розділ)
- Book extraction (Книга)
- Related articles extraction
- Contextual prefix generation
- Graph edges for article navigation
"""

import pytest

from src.utils.structure_parser import (
    ROMAN_NUMERALS,
    UKRAINIAN_NUMBERS,
    add_graph_edges,
    extract_contextual_prefix,
    extract_related_articles,
    parse_legal_structure,
    roman_to_int,
    ukrainian_number_to_int,
)


class TestRomanToInt:
    """Tests for Roman numeral to integer conversion."""

    @pytest.mark.parametrize(
        ("numeral", "expected"),
        [
            ("I", 1), ("II", 2), ("III", 3), ("IV", 4), ("V", 5),
            ("VI", 6), ("VII", 7), ("VIII", 8), ("IX", 9), ("X", 10),
            ("XI", 11), ("XII", 12), ("XV", 15), ("XVIII", 18), ("XIX", 19), ("XX", 20),
            # Case insensitive
            ("i", 1), ("iv", 4), ("x", 10), ("xv", 15),
        ],
    )
    def test_valid_roman_numerals(self, numeral, expected):
        assert roman_to_int(numeral) == expected

    @pytest.mark.parametrize(
        "numeral",
        [pytest.param("XXI", id="beyond_range"), pytest.param("INVALID", id="invalid"),
         pytest.param("", id="empty"), pytest.param("123", id="digits")],
    )
    def test_invalid_roman_numerals(self, numeral):
        assert roman_to_int(numeral) is None

    def test_roman_numerals_mapping_complete(self):
        assert len(ROMAN_NUMERALS) == 20
        assert ROMAN_NUMERALS["I"] == 1
        assert ROMAN_NUMERALS["XX"] == 20


class TestUkrainianNumberToInt:
    """Tests for Ukrainian number word to integer conversion."""

    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            # Feminine forms (used with 'Книга')
            ("перша", 1), ("друга", 2), ("третя", 3), ("четверта", 4), ("п'ята", 5),
            ("шоста", 6), ("сьома", 7), ("восьма", 8), ("дев'ята", 9), ("десята", 10),
            # Masculine forms
            ("перший", 1), ("другий", 2), ("третій", 3), ("четвертий", 4), ("п'ятий", 5),
            ("шостий", 6), ("сьомий", 7), ("восьмий", 8), ("дев'ятий", 9), ("десятий", 10),
            # Case insensitive
            ("ПЕРША", 1), ("Друга", 2), ("тРеТя", 3),
        ],
    )
    def test_valid_ukrainian_numbers(self, word, expected):
        assert ukrainian_number_to_int(word) == expected

    @pytest.mark.parametrize(
        "word",
        ["invalid", "", "одинадцята", "123"],
    )
    def test_invalid_words(self, word):
        assert ukrainian_number_to_int(word) is None

    def test_ukrainian_numbers_mapping_complete(self):
        assert len(UKRAINIAN_NUMBERS) == 20  # 10 feminine + 10 masculine
        assert UKRAINIAN_NUMBERS["перша"] == 1
        assert UKRAINIAN_NUMBERS["десятий"] == 10


class TestExtractRelatedArticles:
    """Tests for extracting article references from text."""

    def test_extract_single_reference(self):
        result = extract_related_articles("відповідно до статті 12")
        assert 12 in result

    def test_extract_multiple_references(self):
        result = extract_related_articles("згідно зі статті 25 та статті 30")
        assert 25 in result
        assert 30 in result

    def test_extract_various_forms(self):
        """Test extraction of various Ukrainian word forms."""
        text = """
        стаття 1 визначає загальні положення
        статті 2 стосується конкретних випадків
        статтю 3 передбачено особливості
        відповідно до статті 4
        """
        result = extract_related_articles(text)
        assert sorted(result) == [1, 2, 3, 4]

    def test_instrumental_case_limitation(self):
        """Known limitation: 'статтею' (instrumental) is NOT matched."""
        result = extract_related_articles("статтею 99 передбачено")
        assert 99 not in result

    def test_no_duplicates(self):
        result = extract_related_articles("стаття 10 та ще раз стаття 10 і знову статті 10")
        assert result.count(10) == 1

    def test_sorted_results(self):
        result = extract_related_articles("статті 50, статті 10, статті 30")
        assert result == sorted(result)

    def test_no_references(self):
        result = extract_related_articles("Цей текст не містить посилань на статті.")
        assert result == []

    def test_case_insensitivity(self):
        result = extract_related_articles("СТАТТЯ 15 та Статті 20")
        assert 15 in result
        assert 20 in result


class TestParseLegalStructure:
    """Tests for the main legal structure parsing function."""

    def test_parse_article_standard_format(self):
        metadata = parse_legal_structure("Стаття 25. Цивільна правоздатність фізичної особи")
        assert metadata["article_number"] == 25
        assert metadata["article_title"] == "Цивільна правоздатність фізичної особи"

    def test_parse_article_multiline_title(self):
        metadata = parse_legal_structure("Стаття 13.   Межі здійснення   цивільних прав")
        assert metadata["article_number"] == 13
        assert "  " not in metadata["article_title"]

    def test_parse_chapter(self):
        metadata = parse_legal_structure(
            "Глава 2. Здійснення цивільних прав та виконання обов'язків"
        )
        assert metadata["chapter_number"] == 2
        assert "Здійснення цивільних прав" in metadata["chapter"]

    @pytest.mark.parametrize(
        ("text", "expected_number", "expected_title"),
        [
            pytest.param("Розділ I. Загальні положення", 1, "Загальні положення", id="I"),
            pytest.param("Розділ II. Особи", 2, "Особи", id="II"),
            pytest.param("Розділ IV. Речі. Майно", 4, "Речі. Майно", id="IV"),
            pytest.param("Розділ IX. Зобов'язання", 9, "Зобов'язання", id="IX"),
            pytest.param("Розділ XV. Особливі положення", 15, "Особливі положення", id="XV"),
            pytest.param("Розділ XIX. Прикінцеві положення", 19, "Прикінцеві положення", id="XIX"),
        ],
    )
    def test_parse_section_roman_numerals(self, text, expected_number, expected_title):
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == expected_number
        assert metadata["section"] == expected_title

    @pytest.mark.parametrize(
        ("text", "expected_number", "expected_title"),
        [
            pytest.param("Книга перша. Загальні положення", 1, "Загальні положення", id="first"),
            pytest.param("Книга друга. Особлива частина", 2, "Особлива частина", id="second"),
            pytest.param("Книга третя. Авторське право", 3, "Авторське право", id="third"),
            pytest.param(
                "Книга четверта. Право інтелектуальної власності",
                4,
                "Право інтелектуальної власності",
                id="fourth",
            ),
            pytest.param("Книга п'ята. Зобов'язальне право", 5, "Зобов'язальне право", id="fifth"),
            pytest.param("Книга шоста. Спадкове право", 6, "Спадкове право", id="sixth"),
        ],
    )
    def test_parse_book(self, text, expected_number, expected_title):
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == expected_number
        assert metadata["book"] == expected_title

    def test_parse_full_structure(self):
        text = """Книга перша. Загальні положення

Розділ I. Загальні положення

Глава 2. Здійснення цивільних прав та виконання обов'язків

Стаття 13. Межі здійснення цивільних прав

1. Цивільні права особа здійснює у межах, наданих їй договором або актами цивільного законодавства.
"""
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == 1
        assert metadata["book"] == "Загальні положення"
        assert metadata["section_number"] == 1
        assert metadata["section"] == "Загальні положення"
        assert metadata["chapter_number"] == 2
        assert "Здійснення цивільних прав" in metadata["chapter"]
        assert metadata["article_number"] == 13
        assert "Межі здійснення цивільних прав" in metadata["article_title"]

    def test_parse_with_related_articles(self):
        text = """Стаття 13. Межі здійснення цивільних прав

При здійсненні своїх прав особа зобов'язана утримуватися від дій,
зокрема відповідно до статті 12 та статті 25.
"""
        metadata = parse_legal_structure(text)
        assert 12 in metadata["related_articles"]
        assert 25 in metadata["related_articles"]

    def test_parse_empty_text(self):
        metadata = parse_legal_structure("")
        assert metadata["book"] is None
        assert metadata["section"] is None
        assert metadata["chapter"] is None
        assert metadata["article_number"] is None
        assert metadata["article_title"] is None
        assert metadata["related_articles"] == []

    def test_parse_text_without_structure(self):
        metadata = parse_legal_structure("Це звичайний текст без структури документа.")
        assert metadata["book"] is None
        assert metadata["section"] is None
        assert metadata["chapter"] is None
        assert metadata["article_number"] is None

    def test_parse_article_only(self):
        text = """Стаття 25. Цивільна правоздатність фізичної особи

1. Здатність мати цивільні права та обов'язки мають усі фізичні особи."""
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 25
        assert metadata["article_title"] == "Цивільна правоздатність фізичної особи"
        assert metadata["book"] is None
        assert metadata["section"] is None
        assert metadata["chapter"] is None

    def test_metadata_structure(self):
        metadata = parse_legal_structure("Some text")
        for key in [
            "book", "book_number", "section", "section_number",
            "chapter", "chapter_number", "article_number", "article_title", "related_articles",
        ]:
            assert key in metadata


class TestExtractContextualPrefix:
    """Tests for contextual prefix generation."""

    def test_prefix_with_all_metadata(self):
        metadata = {
            "book": "Загальні положення", "book_number": 1,
            "section": "Загальні положення", "section_number": 1,
            "chapter": "Здійснення цивільних прав", "chapter_number": 2,
            "article_number": 13, "article_title": "Межі здійснення цивільних прав",
        }
        prefix = extract_contextual_prefix(metadata)
        assert "Документ: Цивільний кодекс України" in prefix
        assert "Книга 1: Загальні положення" in prefix
        assert "Розділ 1: Загальні положення" in prefix
        assert "Глава 2: Здійснення цивільних прав" in prefix
        assert "Стаття 13: Межі здійснення цивільних прав" in prefix

    def test_prefix_with_custom_document_name(self):
        metadata = {
            "article_number": 10, "article_title": "Тестова стаття",
            "book": None, "book_number": None,
            "section": None, "section_number": None,
            "chapter": None, "chapter_number": None,
        }
        prefix = extract_contextual_prefix(metadata, "Кримінальний кодекс України")
        assert "Документ: Кримінальний кодекс України" in prefix

    def test_prefix_with_article_only(self):
        metadata = {
            "book": None, "book_number": None,
            "section": None, "section_number": None,
            "chapter": None, "chapter_number": None,
            "article_number": 25, "article_title": "Цивільна правоздатність",
        }
        prefix = extract_contextual_prefix(metadata)
        assert "Документ:" in prefix
        assert "Стаття 25: Цивільна правоздатність" in prefix
        assert "Книга" not in prefix
        assert "Розділ" not in prefix
        assert "Глава" not in prefix

    def test_prefix_with_article_no_title(self):
        metadata = {
            "book": None, "book_number": None,
            "section": None, "section_number": None,
            "chapter": None, "chapter_number": None,
            "article_number": 100, "article_title": None,
        }
        prefix = extract_contextual_prefix(metadata)
        assert "Стаття 100" in prefix
        lines = prefix.split("\n")
        article_line = next(line for line in lines if "Стаття" in line)
        assert article_line == "Стаття 100"

    def test_prefix_empty_metadata(self):
        metadata = {
            "book": None, "book_number": None,
            "section": None, "section_number": None,
            "chapter": None, "chapter_number": None,
            "article_number": None, "article_title": None,
        }
        prefix = extract_contextual_prefix(metadata)
        assert prefix == "Документ: Цивільний кодекс України"


class TestAddGraphEdges:
    """Tests for graph edges (prev/next article) functionality."""

    @pytest.mark.parametrize(
        ("article_number", "expected_prev", "expected_next"),
        [
            pytest.param(25, 24, 26, id="middle"),
            pytest.param(1, None, 2, id="first"),
            pytest.param(999, 998, 1000, id="high"),
        ],
    )
    def test_graph_edges(self, article_number, expected_prev, expected_next):
        result = add_graph_edges({"article_number": article_number})
        assert result["prev_article"] == expected_prev
        assert result["next_article"] == expected_next

    def test_add_edges_no_article(self):
        result = add_graph_edges({"article_number": None})
        assert "prev_article" not in result or result.get("prev_article") is None
        assert "next_article" not in result or result.get("next_article") is None

    def test_original_metadata_preserved(self):
        metadata = {"article_number": 50, "article_title": "Test Article", "chapter": "Test Chapter"}
        result = add_graph_edges(metadata)
        assert result["article_number"] == 50
        assert result["article_title"] == "Test Article"
        assert result["chapter"] == "Test Chapter"


class TestEdgeCasesAndIntegration:
    """Integration tests and edge cases."""

    def test_full_parsing_workflow(self):
        text = """Книга друга. Особлива частина

Розділ VIII. Злочини проти власності

Глава 24. Крадіжка та грабіж

Стаття 185. Крадіжка

1. Таємне викрадення чужого майна (крадіжка) -
карається відповідно до статті 186 або статті 187.
"""
        metadata = parse_legal_structure(text)
        metadata = add_graph_edges(metadata)
        prefix = extract_contextual_prefix(metadata, "Кримінальний кодекс України")

        assert metadata["book_number"] == 2
        assert metadata["section_number"] == 8
        assert metadata["chapter_number"] == 24
        assert metadata["article_number"] == 185
        assert 186 in metadata["related_articles"]
        assert 187 in metadata["related_articles"]
        assert metadata["prev_article"] == 184
        assert metadata["next_article"] == 186
        assert "Кримінальний кодекс України" in prefix

    def test_text_with_special_characters(self):
        metadata = parse_legal_structure("Стаття 5. Застосування права України\n\nп'ята книга")
        assert metadata["article_number"] == 5

    def test_multiline_article_content(self):
        text = """Стаття 100. Довга назва статті

1. Перший пункт статті.
2. Другий пункт статті.
3. Третій пункт статті.
"""
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 100
        assert "Довга назва статті" in metadata["article_title"]

    def test_whitespace_handling(self):
        metadata = parse_legal_structure("Стаття   50.    Назва   статті   з   пробілами")
        assert metadata["article_number"] == 50
        assert "  " not in metadata["article_title"]

    def test_newline_in_structure(self):
        text = """Глава 10. Перша глава

Стаття 100. Стаття в першій главі

Глава 11. Друга глава (не повинна бути витягнута)
"""
        metadata = parse_legal_structure(text)
        assert metadata["chapter_number"] == 10
        assert "Перша глава" in metadata["chapter"]

    def test_mixed_numerals_in_same_text(self):
        text = """Розділ III. Зобов'язання

Глава 47. Загальні положення про зобов'язання

Стаття 509. Поняття зобов'язання
"""
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 3
        assert metadata["chapter_number"] == 47
        assert metadata["article_number"] == 509

    def test_partial_structure_chapter_article(self):
        text = """Глава 3. Представництво. Довіреність

Стаття 31. Представник

Представником є особа, яка діє від імені іншої особи."""
        metadata = parse_legal_structure(text)
        assert metadata["book"] is None
        assert metadata["section"] is None
        assert metadata["chapter_number"] == 3
        assert metadata["article_number"] == 31


class TestArticlePatternAlternatives:
    """Tests for alternative article patterns."""

    def test_numbered_format_without_stattya(self):
        text = """1. Загальні положення цього розділу

Текст статті."""
        parse_legal_structure(text)
