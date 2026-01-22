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

    def test_basic_roman_numerals(self):
        """Test basic Roman numerals I-X."""
        assert roman_to_int("I") == 1
        assert roman_to_int("II") == 2
        assert roman_to_int("III") == 3
        assert roman_to_int("IV") == 4
        assert roman_to_int("V") == 5
        assert roman_to_int("VI") == 6
        assert roman_to_int("VII") == 7
        assert roman_to_int("VIII") == 8
        assert roman_to_int("IX") == 9
        assert roman_to_int("X") == 10

    def test_extended_roman_numerals(self):
        """Test extended Roman numerals XI-XX."""
        assert roman_to_int("XI") == 11
        assert roman_to_int("XII") == 12
        assert roman_to_int("XV") == 15
        assert roman_to_int("XVIII") == 18
        assert roman_to_int("XIX") == 19
        assert roman_to_int("XX") == 20

    def test_case_insensitivity(self):
        """Test that conversion is case-insensitive."""
        assert roman_to_int("i") == 1
        assert roman_to_int("iv") == 4
        assert roman_to_int("x") == 10
        assert roman_to_int("xv") == 15

    def test_invalid_roman_numeral(self):
        """Test that invalid Roman numerals return None."""
        assert roman_to_int("XXI") is None  # Beyond defined range
        assert roman_to_int("INVALID") is None
        assert roman_to_int("") is None
        assert roman_to_int("123") is None

    def test_roman_numerals_mapping_complete(self):
        """Test that ROMAN_NUMERALS mapping contains expected values."""
        assert len(ROMAN_NUMERALS) == 20
        assert ROMAN_NUMERALS["I"] == 1
        assert ROMAN_NUMERALS["XX"] == 20


class TestUkrainianNumberToInt:
    """Tests for Ukrainian number word to integer conversion."""

    def test_basic_feminine_forms(self):
        """Test feminine forms of Ukrainian numbers (used with 'Книга')."""
        assert ukrainian_number_to_int("перша") == 1
        assert ukrainian_number_to_int("друга") == 2
        assert ukrainian_number_to_int("третя") == 3
        assert ukrainian_number_to_int("четверта") == 4
        assert ukrainian_number_to_int("п'ята") == 5
        assert ukrainian_number_to_int("шоста") == 6
        assert ukrainian_number_to_int("сьома") == 7
        assert ukrainian_number_to_int("восьма") == 8
        assert ukrainian_number_to_int("дев'ята") == 9
        assert ukrainian_number_to_int("десята") == 10

    def test_basic_masculine_forms(self):
        """Test masculine forms of Ukrainian numbers."""
        assert ukrainian_number_to_int("перший") == 1
        assert ukrainian_number_to_int("другий") == 2
        assert ukrainian_number_to_int("третій") == 3
        assert ukrainian_number_to_int("четвертий") == 4
        assert ukrainian_number_to_int("п'ятий") == 5
        assert ukrainian_number_to_int("шостий") == 6
        assert ukrainian_number_to_int("сьомий") == 7
        assert ukrainian_number_to_int("восьмий") == 8
        assert ukrainian_number_to_int("дев'ятий") == 9
        assert ukrainian_number_to_int("десятий") == 10

    def test_case_insensitivity(self):
        """Test that conversion is case-insensitive."""
        assert ukrainian_number_to_int("ПЕРША") == 1
        assert ukrainian_number_to_int("Друга") == 2
        assert ukrainian_number_to_int("тРеТя") == 3

    def test_invalid_words(self):
        """Test that invalid words return None."""
        assert ukrainian_number_to_int("invalid") is None
        assert ukrainian_number_to_int("") is None
        assert ukrainian_number_to_int("одинадцята") is None  # 11 not in mapping
        assert ukrainian_number_to_int("123") is None

    def test_ukrainian_numbers_mapping_complete(self):
        """Test that UKRAINIAN_NUMBERS mapping contains expected values."""
        assert len(UKRAINIAN_NUMBERS) == 20  # 10 feminine + 10 masculine
        assert UKRAINIAN_NUMBERS["перша"] == 1
        assert UKRAINIAN_NUMBERS["десятий"] == 10


class TestExtractRelatedArticles:
    """Tests for extracting article references from text."""

    def test_extract_single_reference(self):
        """Test extracting a single article reference."""
        text = "відповідно до статті 12"
        result = extract_related_articles(text)
        assert 12 in result

    def test_extract_multiple_references(self):
        """Test extracting multiple article references."""
        text = "згідно зі статті 25 та статті 30"
        result = extract_related_articles(text)
        assert 25 in result
        assert 30 in result

    def test_extract_various_forms(self):
        """Test extraction of various Ukrainian word forms.

        Note: The current regex pattern `статт[іяює]` matches single characters
        after 'статт', so it captures:
        - стаття (nominative)
        - статті (genitive/locative)
        - статтю (accusative)
        But NOT 'статтею' (instrumental) which has two chars after 'статт'.
        """
        text = """
        стаття 1 визначає загальні положення
        статті 2 стосується конкретних випадків
        статтю 3 передбачено особливості
        відповідно до статті 4
        """
        result = extract_related_articles(text)
        assert sorted(result) == [1, 2, 3, 4]

    def test_instrumental_case_limitation(self):
        """Test that 'статтею' (instrumental case) is NOT matched.

        This documents a known limitation in the current regex pattern.
        The pattern `статт[іяює]` only matches single characters after 'статт',
        but 'статтею' has two characters ('е' + 'ю').
        """
        text = "статтею 99 передбачено"
        result = extract_related_articles(text)
        # This is a known limitation - instrumental case is not matched
        assert 99 not in result

    def test_no_duplicates(self):
        """Test that duplicate references are not included."""
        text = "стаття 10 та ще раз стаття 10 і знову статті 10"
        result = extract_related_articles(text)
        assert result.count(10) == 1

    def test_sorted_results(self):
        """Test that results are sorted."""
        text = "статті 50, статті 10, статті 30"
        result = extract_related_articles(text)
        assert result == sorted(result)

    def test_no_references(self):
        """Test text without article references."""
        text = "Цей текст не містить посилань на статті."
        result = extract_related_articles(text)
        assert result == []

    def test_case_insensitivity(self):
        """Test that extraction is case-insensitive."""
        text = "СТАТТЯ 15 та Статті 20"
        result = extract_related_articles(text)
        assert 15 in result
        assert 20 in result


class TestParseLegalStructure:
    """Tests for the main legal structure parsing function."""

    def test_parse_article_standard_format(self):
        """Test parsing article in standard format."""
        text = "Стаття 25. Цивільна правоздатність фізичної особи"
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 25
        assert metadata["article_title"] == "Цивільна правоздатність фізичної особи"

    def test_parse_article_multiline_title(self):
        """Test parsing article with title that might have extra whitespace."""
        text = "Стаття 13.   Межі здійснення   цивільних прав"
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 13
        # Whitespace should be normalized
        assert "  " not in metadata["article_title"]

    def test_parse_chapter(self):
        """Test parsing chapter (Глава)."""
        text = "Глава 2. Здійснення цивільних прав та виконання обов'язків"
        metadata = parse_legal_structure(text)
        assert metadata["chapter_number"] == 2
        assert "Здійснення цивільних прав" in metadata["chapter"]

    def test_parse_section_roman_numerals(self):
        """Test parsing section (Розділ) with Roman numerals."""
        text = "Розділ I. Загальні положення"
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 1
        assert metadata["section"] == "Загальні положення"

    def test_parse_section_higher_roman(self):
        """Test parsing section with higher Roman numerals."""
        text = "Розділ XV. Особливі положення"
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 15
        assert metadata["section"] == "Особливі положення"

    def test_parse_book_feminine_form(self):
        """Test parsing book (Книга) with feminine number word."""
        text = "Книга перша. Загальні положення"
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == 1
        assert metadata["book"] == "Загальні положення"

    def test_parse_book_second(self):
        """Test parsing second book."""
        text = "Книга друга. Особлива частина"
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == 2
        assert metadata["book"] == "Особлива частина"

    def test_parse_full_structure(self):
        """Test parsing document with full structure."""
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
        """Test that related articles are extracted."""
        text = """Стаття 13. Межі здійснення цивільних прав

При здійсненні своїх прав особа зобов'язана утримуватися від дій,
зокрема відповідно до статті 12 та статті 25.
"""
        metadata = parse_legal_structure(text)
        assert 12 in metadata["related_articles"]
        assert 25 in metadata["related_articles"]

    def test_parse_empty_text(self):
        """Test parsing empty text."""
        metadata = parse_legal_structure("")
        assert metadata["book"] is None
        assert metadata["section"] is None
        assert metadata["chapter"] is None
        assert metadata["article_number"] is None
        assert metadata["article_title"] is None
        assert metadata["related_articles"] == []

    def test_parse_text_without_structure(self):
        """Test parsing text without legal structure."""
        text = "Це звичайний текст без структури документа."
        metadata = parse_legal_structure(text)
        assert metadata["book"] is None
        assert metadata["section"] is None
        assert metadata["chapter"] is None
        assert metadata["article_number"] is None

    def test_parse_article_only(self):
        """Test parsing text with only article."""
        text = """Стаття 25. Цивільна правоздатність фізичної особи

1. Здатність мати цивільні права та обов'язки мають усі фізичні особи."""
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 25
        assert metadata["article_title"] == "Цивільна правоздатність фізичної особи"
        assert metadata["book"] is None
        assert metadata["section"] is None
        assert metadata["chapter"] is None

    def test_metadata_structure(self):
        """Test that returned metadata has all expected keys."""
        text = "Some text"
        metadata = parse_legal_structure(text)
        expected_keys = [
            "book",
            "book_number",
            "section",
            "section_number",
            "chapter",
            "chapter_number",
            "article_number",
            "article_title",
            "related_articles",
        ]
        for key in expected_keys:
            assert key in metadata


class TestExtractContextualPrefix:
    """Tests for contextual prefix generation."""

    def test_prefix_with_all_metadata(self):
        """Test prefix generation with full metadata."""
        metadata = {
            "book": "Загальні положення",
            "book_number": 1,
            "section": "Загальні положення",
            "section_number": 1,
            "chapter": "Здійснення цивільних прав",
            "chapter_number": 2,
            "article_number": 13,
            "article_title": "Межі здійснення цивільних прав",
        }
        prefix = extract_contextual_prefix(metadata)
        assert "Документ: Цивільний кодекс України" in prefix
        assert "Книга 1: Загальні положення" in prefix
        assert "Розділ 1: Загальні положення" in prefix
        assert "Глава 2: Здійснення цивільних прав" in prefix
        assert "Стаття 13: Межі здійснення цивільних прав" in prefix

    def test_prefix_with_custom_document_name(self):
        """Test prefix with custom document name."""
        metadata = {
            "article_number": 10,
            "article_title": "Тестова стаття",
            "book": None,
            "book_number": None,
            "section": None,
            "section_number": None,
            "chapter": None,
            "chapter_number": None,
        }
        prefix = extract_contextual_prefix(metadata, "Кримінальний кодекс України")
        assert "Документ: Кримінальний кодекс України" in prefix

    def test_prefix_with_article_only(self):
        """Test prefix with only article information."""
        metadata = {
            "book": None,
            "book_number": None,
            "section": None,
            "section_number": None,
            "chapter": None,
            "chapter_number": None,
            "article_number": 25,
            "article_title": "Цивільна правоздатність",
        }
        prefix = extract_contextual_prefix(metadata)
        assert "Документ:" in prefix
        assert "Стаття 25: Цивільна правоздатність" in prefix
        assert "Книга" not in prefix
        assert "Розділ" not in prefix
        assert "Глава" not in prefix

    def test_prefix_with_article_no_title(self):
        """Test prefix with article number but no title."""
        metadata = {
            "book": None,
            "book_number": None,
            "section": None,
            "section_number": None,
            "chapter": None,
            "chapter_number": None,
            "article_number": 100,
            "article_title": None,
        }
        prefix = extract_contextual_prefix(metadata)
        assert "Стаття 100" in prefix
        # Should not have colon if no title
        lines = prefix.split("\n")
        article_line = next(line for line in lines if "Стаття" in line)
        assert article_line == "Стаття 100"

    def test_prefix_empty_metadata(self):
        """Test prefix with empty/None metadata."""
        metadata = {
            "book": None,
            "book_number": None,
            "section": None,
            "section_number": None,
            "chapter": None,
            "chapter_number": None,
            "article_number": None,
            "article_title": None,
        }
        prefix = extract_contextual_prefix(metadata)
        # Should only contain document name
        assert prefix == "Документ: Цивільний кодекс України"


class TestAddGraphEdges:
    """Tests for graph edges (prev/next article) functionality."""

    def test_add_edges_middle_article(self):
        """Test adding edges for an article in the middle."""
        metadata = {"article_number": 25}
        result = add_graph_edges(metadata)
        assert result["prev_article"] == 24
        assert result["next_article"] == 26

    def test_add_edges_first_article(self):
        """Test adding edges for article 1 (no previous)."""
        metadata = {"article_number": 1}
        result = add_graph_edges(metadata)
        assert result["prev_article"] is None
        assert result["next_article"] == 2

    def test_add_edges_no_article(self):
        """Test that no edges are added when no article number."""
        metadata = {"article_number": None}
        result = add_graph_edges(metadata)
        assert "prev_article" not in result or result.get("prev_article") is None
        assert "next_article" not in result or result.get("next_article") is None

    def test_add_edges_high_article_number(self):
        """Test edges for high article numbers."""
        metadata = {"article_number": 999}
        result = add_graph_edges(metadata)
        assert result["prev_article"] == 998
        assert result["next_article"] == 1000

    def test_original_metadata_preserved(self):
        """Test that original metadata is preserved after adding edges."""
        metadata = {
            "article_number": 50,
            "article_title": "Test Article",
            "chapter": "Test Chapter",
        }
        result = add_graph_edges(metadata)
        assert result["article_number"] == 50
        assert result["article_title"] == "Test Article"
        assert result["chapter"] == "Test Chapter"


class TestEdgeCasesAndIntegration:
    """Integration tests and edge cases."""

    def test_full_parsing_workflow(self):
        """Test complete parsing workflow."""
        text = """Книга друга. Особлива частина

Розділ VIII. Злочини проти власності

Глава 24. Крадіжка та грабіж

Стаття 185. Крадіжка

1. Таємне викрадення чужого майна (крадіжка) -
карається відповідно до статті 186 або статті 187.
"""
        # Parse structure
        metadata = parse_legal_structure(text)

        # Add graph edges
        metadata = add_graph_edges(metadata)

        # Generate contextual prefix
        prefix = extract_contextual_prefix(metadata, "Кримінальний кодекс України")

        # Verify all components
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
        """Test parsing text with special Ukrainian characters."""
        text = "Стаття 5. Застосування права України\n\nп'ята книга"
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 5

    def test_multiline_article_content(self):
        """Test article with multiline content."""
        text = """Стаття 100. Довга назва статті

1. Перший пункт статті.
2. Другий пункт статті.
3. Третій пункт статті.
"""
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 100
        assert "Довга назва статті" in metadata["article_title"]

    def test_whitespace_handling(self):
        """Test handling of various whitespace."""
        text = "Стаття   50.    Назва   статті   з   пробілами"
        metadata = parse_legal_structure(text)
        assert metadata["article_number"] == 50
        # Title should have normalized whitespace
        assert "  " not in metadata["article_title"]

    def test_newline_in_structure(self):
        """Test that newlines properly delimit structures."""
        text = """Глава 10. Перша глава

Стаття 100. Стаття в першій главі

Глава 11. Друга глава (не повинна бути витягнута)
"""
        metadata = parse_legal_structure(text)
        # Should extract first chapter
        assert metadata["chapter_number"] == 10
        assert "Перша глава" in metadata["chapter"]

    def test_mixed_numerals_in_same_text(self):
        """Test text containing both Roman and Arabic numerals."""
        text = """Розділ III. Зобов'язання

Глава 47. Загальні положення про зобов'язання

Стаття 509. Поняття зобов'язання
"""
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 3  # From Roman III
        assert metadata["chapter_number"] == 47  # Arabic
        assert metadata["article_number"] == 509  # Arabic

    def test_partial_structure_chapter_article(self):
        """Test document with only chapter and article."""
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
        """Test pattern matching for numbered format."""
        text = """1. Загальні положення цього розділу

Текст статті."""
        parse_legal_structure(text)
        # The parser should attempt to match this pattern
        # Based on the code, this might or might not match depending on context


class TestBookVariants:
    """Tests for various book number forms."""

    def test_book_third(self):
        """Test parsing third book."""
        text = "Книга третя. Авторське право"
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == 3

    def test_book_fourth(self):
        """Test parsing fourth book."""
        text = "Книга четверта. Право інтелектуальної власності"
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == 4

    def test_book_fifth(self):
        """Test parsing fifth book."""
        text = "Книга п'ята. Зобов'язальне право"
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == 5

    def test_book_sixth(self):
        """Test parsing sixth book."""
        text = "Книга шоста. Спадкове право"
        metadata = parse_legal_structure(text)
        assert metadata["book_number"] == 6


class TestSectionRomanVariants:
    """Tests for various section Roman numeral formats."""

    def test_section_ii(self):
        """Test section II."""
        text = "Розділ II. Особи"
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 2

    def test_section_iv(self):
        """Test section IV."""
        text = "Розділ IV. Речі. Майно"
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 4

    def test_section_ix(self):
        """Test section IX."""
        text = "Розділ IX. Зобов'язання"
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 9

    def test_section_xix(self):
        """Test section XIX."""
        text = "Розділ XIX. Прикінцеві положення"
        metadata = parse_legal_structure(text)
        assert metadata["section_number"] == 19
