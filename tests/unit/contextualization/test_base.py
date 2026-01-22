"""Unit tests for contextualization base classes."""

from datetime import datetime
from typing import Optional

import pytest

from src.contextualization.base import ContextualizedChunk, ContextualizeProvider


# =============================================================================
# TestContextualizedChunkCreation
# =============================================================================


class TestContextualizedChunkCreation:
    """Tests for ContextualizedChunk dataclass creation."""

    def test_creation_with_required_fields(self):
        """Test chunk creation with only required fields."""
        chunk = ContextualizedChunk(
            original_text="Test text",
            contextual_summary="Test summary",
            article_number="Article 1",
        )
        assert chunk.original_text == "Test text"
        assert chunk.contextual_summary == "Test summary"
        assert chunk.article_number == "Article 1"

    def test_creation_with_all_fields(self):
        """Test chunk creation with all fields specified."""
        timestamp = datetime(2024, 1, 15, 12, 30, 0)
        chunk = ContextualizedChunk(
            original_text="Test text",
            contextual_summary="Test summary",
            article_number="Article 1",
            chapter="Chapter 1",
            section="Section A",
            context_method="claude",
            timestamp=timestamp,
        )
        assert chunk.original_text == "Test text"
        assert chunk.contextual_summary == "Test summary"
        assert chunk.article_number == "Article 1"
        assert chunk.chapter == "Chapter 1"
        assert chunk.section == "Section A"
        assert chunk.context_method == "claude"
        assert chunk.timestamp == timestamp

    def test_default_chapter_is_none(self):
        """Test that chapter defaults to None."""
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        assert chunk.chapter is None

    def test_default_section_is_none(self):
        """Test that section defaults to None."""
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        assert chunk.section is None

    def test_default_context_method_is_none(self):
        """Test that context_method defaults to 'none'."""
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        assert chunk.context_method == "none"

    def test_default_timestamp_is_set(self):
        """Test that timestamp is set to current time by default."""
        before = datetime.now()
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        after = datetime.now()
        assert before <= chunk.timestamp <= after

    def test_creation_with_empty_strings(self):
        """Test chunk creation with empty strings."""
        chunk = ContextualizedChunk(
            original_text="",
            contextual_summary="",
            article_number="",
        )
        assert chunk.original_text == ""
        assert chunk.contextual_summary == ""
        assert chunk.article_number == ""

    def test_creation_with_unicode_text(self):
        """Test chunk creation with cyrillic/unicode text."""
        chunk = ContextualizedChunk(
            original_text="Кримінальний кодекс України",
            contextual_summary="Стаття про відповідальність",
            article_number="Стаття 115",
            chapter="Розділ II",
        )
        assert chunk.original_text == "Кримінальний кодекс України"
        assert chunk.contextual_summary == "Стаття про відповідальність"
        assert chunk.article_number == "Стаття 115"
        assert chunk.chapter == "Розділ II"

    def test_creation_with_multiline_text(self):
        """Test chunk creation with multiline text."""
        text = "Line 1\nLine 2\nLine 3"
        summary = "Summary\nwith\nmultiple lines"
        chunk = ContextualizedChunk(
            original_text=text,
            contextual_summary=summary,
            article_number="Art 1",
        )
        assert chunk.original_text == text
        assert chunk.contextual_summary == summary

    def test_different_context_methods(self):
        """Test various context_method values."""
        methods = ["none", "claude", "openai", "groq", "custom"]
        for method in methods:
            chunk = ContextualizedChunk(
                original_text="Test",
                contextual_summary="Summary",
                article_number="Art 1",
                context_method=method,
            )
            assert chunk.context_method == method


# =============================================================================
# TestContextualizedChunkFullText
# =============================================================================


class TestContextualizedChunkFullText:
    """Tests for ContextualizedChunk.full_text property."""

    def test_full_text_combines_summary_and_original(self):
        """Test that full_text combines summary and original text."""
        chunk = ContextualizedChunk(
            original_text="Original content",
            contextual_summary="Summary content",
            article_number="Art 1",
        )
        expected = "Summary content\n\nOriginal content"
        assert chunk.full_text == expected

    def test_full_text_with_empty_summary(self):
        """Test full_text when summary is empty."""
        chunk = ContextualizedChunk(
            original_text="Original content",
            contextual_summary="",
            article_number="Art 1",
        )
        expected = "\n\nOriginal content"
        assert chunk.full_text == expected

    def test_full_text_with_empty_original(self):
        """Test full_text when original is empty."""
        chunk = ContextualizedChunk(
            original_text="",
            contextual_summary="Summary content",
            article_number="Art 1",
        )
        expected = "Summary content\n\n"
        assert chunk.full_text == expected

    def test_full_text_with_both_empty(self):
        """Test full_text when both are empty."""
        chunk = ContextualizedChunk(
            original_text="",
            contextual_summary="",
            article_number="Art 1",
        )
        expected = "\n\n"
        assert chunk.full_text == expected

    def test_full_text_is_property_not_method(self):
        """Test that full_text is a property, not a method."""
        chunk = ContextualizedChunk(
            original_text="Original",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        # Should be accessible without calling ()
        assert isinstance(chunk.full_text, str)
        # Verify it's a property
        assert isinstance(type(chunk).full_text, property)

    def test_full_text_with_unicode(self):
        """Test full_text with cyrillic text."""
        chunk = ContextualizedChunk(
            original_text="Кримінальне право",
            contextual_summary="Юридичний контекст",
            article_number="Art 1",
        )
        expected = "Юридичний контекст\n\nКримінальне право"
        assert chunk.full_text == expected


# =============================================================================
# TestContextualizedChunkToDict
# =============================================================================


class TestContextualizedChunkToDict:
    """Tests for ContextualizedChunk.to_dict method."""

    def test_to_dict_returns_dictionary(self):
        """Test that to_dict returns a dictionary."""
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        result = chunk.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_all_fields(self):
        """Test that to_dict contains all expected fields."""
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        result = chunk.to_dict()
        expected_keys = {
            "original_text",
            "contextual_summary",
            "article_number",
            "chapter",
            "section",
            "context_method",
            "timestamp",
            "full_text",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_field_values(self):
        """Test that to_dict returns correct field values."""
        timestamp = datetime(2024, 1, 15, 12, 30, 0)
        chunk = ContextualizedChunk(
            original_text="Original",
            contextual_summary="Summary",
            article_number="Article 115",
            chapter="Chapter 5",
            section="Section B",
            context_method="claude",
            timestamp=timestamp,
        )
        result = chunk.to_dict()

        assert result["original_text"] == "Original"
        assert result["contextual_summary"] == "Summary"
        assert result["article_number"] == "Article 115"
        assert result["chapter"] == "Chapter 5"
        assert result["section"] == "Section B"
        assert result["context_method"] == "claude"
        assert result["full_text"] == "Summary\n\nOriginal"

    def test_to_dict_timestamp_is_isoformat(self):
        """Test that timestamp is converted to ISO format string."""
        timestamp = datetime(2024, 1, 15, 12, 30, 45)
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
            timestamp=timestamp,
        )
        result = chunk.to_dict()
        assert result["timestamp"] == "2024-01-15T12:30:45"

    def test_to_dict_none_values_preserved(self):
        """Test that None values are preserved in dict."""
        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        result = chunk.to_dict()
        assert result["chapter"] is None
        assert result["section"] is None

    def test_to_dict_is_serializable(self):
        """Test that to_dict result can be JSON serialized."""
        import json

        chunk = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
            chapter="Ch 1",
            section="Sec A",
        )
        result = chunk.to_dict()
        # Should not raise
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

    def test_to_dict_with_unicode(self):
        """Test to_dict with cyrillic text."""
        chunk = ContextualizedChunk(
            original_text="Кримінальний кодекс",
            contextual_summary="Юридичний контекст",
            article_number="Стаття 115",
            chapter="Розділ II",
        )
        result = chunk.to_dict()
        assert result["original_text"] == "Кримінальний кодекс"
        assert result["contextual_summary"] == "Юридичний контекст"
        assert result["article_number"] == "Стаття 115"
        assert result["chapter"] == "Розділ II"


# =============================================================================
# TestContextualizedChunkEdgeCases
# =============================================================================


class TestContextualizedChunkEdgeCases:
    """Edge case tests for ContextualizedChunk."""

    def test_chunk_is_mutable(self):
        """Test that chunk fields can be modified after creation."""
        chunk = ContextualizedChunk(
            original_text="Original",
            contextual_summary="Summary",
            article_number="Art 1",
        )
        chunk.original_text = "Modified"
        assert chunk.original_text == "Modified"

    def test_chunk_with_special_characters(self):
        """Test chunk with special characters."""
        special_text = "Text with <html> & 'quotes' \"double\" and \\backslash"
        chunk = ContextualizedChunk(
            original_text=special_text,
            contextual_summary=special_text,
            article_number="Art<1>",
        )
        assert chunk.original_text == special_text
        assert chunk.contextual_summary == special_text

    def test_chunk_with_very_long_text(self):
        """Test chunk with very long text."""
        long_text = "A" * 100000
        chunk = ContextualizedChunk(
            original_text=long_text,
            contextual_summary=long_text,
            article_number="Art 1",
        )
        assert len(chunk.original_text) == 100000
        assert len(chunk.full_text) == 100000 * 2 + 2  # two texts + "\n\n"

    def test_chunk_equality(self):
        """Test that two chunks with same values are equal (dataclass)."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0)
        chunk1 = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
            timestamp=timestamp,
        )
        chunk2 = ContextualizedChunk(
            original_text="Test",
            contextual_summary="Summary",
            article_number="Art 1",
            timestamp=timestamp,
        )
        assert chunk1 == chunk2

    def test_chunk_inequality(self):
        """Test that two chunks with different values are not equal."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0)
        chunk1 = ContextualizedChunk(
            original_text="Test1",
            contextual_summary="Summary",
            article_number="Art 1",
            timestamp=timestamp,
        )
        chunk2 = ContextualizedChunk(
            original_text="Test2",
            contextual_summary="Summary",
            article_number="Art 1",
            timestamp=timestamp,
        )
        assert chunk1 != chunk2


# =============================================================================
# TestContextualizeProviderInterface
# =============================================================================


class TestContextualizeProviderInterface:
    """Tests for ContextualizeProvider abstract base class."""

    def test_cannot_instantiate_directly(self):
        """Test that ContextualizeProvider cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            ContextualizeProvider()
        assert "abstract" in str(exc_info.value).lower()

    def test_requires_contextualize_method(self):
        """Test that subclass must implement contextualize method."""

        class IncompleteProvider(ContextualizeProvider):
            async def contextualize_single(self, text, article_number, query=None):
                pass

        with pytest.raises(TypeError) as exc_info:
            IncompleteProvider()
        assert "contextualize" in str(exc_info.value)

    def test_requires_contextualize_single_method(self):
        """Test that subclass must implement contextualize_single method."""

        class IncompleteProvider(ContextualizeProvider):
            async def contextualize(self, chunks, query=None, context_window=3):
                pass

        with pytest.raises(TypeError) as exc_info:
            IncompleteProvider()
        assert "contextualize_single" in str(exc_info.value)

    def test_complete_implementation_can_be_instantiated(self):
        """Test that a complete implementation can be instantiated."""

        class CompleteProvider(ContextualizeProvider):
            async def contextualize(self, chunks, query=None, context_window=3):
                return []

            async def contextualize_single(self, text, article_number, query=None):
                return ContextualizedChunk(
                    original_text=text,
                    contextual_summary="Summary",
                    article_number=article_number,
                )

        # Should not raise
        provider = CompleteProvider()
        assert isinstance(provider, ContextualizeProvider)

    def test_get_system_prompt_is_static(self):
        """Test that get_system_prompt is a static method."""
        # Should be callable on the class without instance
        result = ContextualizeProvider.get_system_prompt()
        assert isinstance(result, str)

    def test_get_system_prompt_content(self):
        """Test that get_system_prompt returns expected content."""
        prompt = ContextualizeProvider.get_system_prompt()
        # Check for key phrases in the prompt
        assert "legal document analyzer" in prompt.lower()
        assert "ukrainian" in prompt.lower()
        assert "summary" in prompt.lower()
        assert "guidelines" in prompt.lower()

    def test_get_user_prompt_is_static(self):
        """Test that get_user_prompt is a static method."""
        # Should be callable on the class without instance
        result = ContextualizeProvider.get_user_prompt("Test text")
        assert isinstance(result, str)

    def test_get_user_prompt_without_query(self):
        """Test get_user_prompt without query parameter."""
        text = "Sample legal text"
        prompt = ContextualizeProvider.get_user_prompt(text)
        assert text in prompt
        assert "summarize" in prompt.lower()

    def test_get_user_prompt_with_query(self):
        """Test get_user_prompt with query parameter."""
        text = "Sample legal text"
        query = "What is the penalty?"
        prompt = ContextualizeProvider.get_user_prompt(text, query)
        assert text in prompt
        assert query in prompt
        assert "searching for" in prompt.lower()

    def test_get_user_prompt_with_empty_query(self):
        """Test get_user_prompt with empty query string."""
        text = "Sample legal text"
        prompt = ContextualizeProvider.get_user_prompt(text, "")
        # Empty query should still append the query section
        assert text in prompt

    def test_get_user_prompt_with_none_query(self):
        """Test get_user_prompt with None query."""
        text = "Sample legal text"
        prompt = ContextualizeProvider.get_user_prompt(text, None)
        assert text in prompt
        # Should not include query section when None
        assert "searching for" not in prompt.lower()


# =============================================================================
# TestContextualizeProviderImplementation
# =============================================================================


class TestContextualizeProviderImplementation:
    """Tests for ContextualizeProvider implementation patterns."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider implementation for testing."""

        class MockProvider(ContextualizeProvider):
            def __init__(self):
                self.contextualize_called = False
                self.contextualize_single_called = False

            async def contextualize(
                self, chunks: list[str], query: Optional[str] = None, context_window: int = 3
            ) -> list[ContextualizedChunk]:
                self.contextualize_called = True
                self.last_chunks = chunks
                self.last_query = query
                self.last_context_window = context_window
                return [
                    ContextualizedChunk(
                        original_text=chunk,
                        contextual_summary=f"Summary of: {chunk}",
                        article_number=f"Art {i}",
                    )
                    for i, chunk in enumerate(chunks)
                ]

            async def contextualize_single(
                self, text: str, article_number: str, query: Optional[str] = None
            ) -> ContextualizedChunk:
                self.contextualize_single_called = True
                self.last_text = text
                self.last_article_number = article_number
                self.last_query = query
                return ContextualizedChunk(
                    original_text=text,
                    contextual_summary=f"Summary of: {text}",
                    article_number=article_number,
                )

        return MockProvider()

    async def test_contextualize_method_signature(self, mock_provider):
        """Test that contextualize accepts expected parameters."""
        chunks = ["chunk1", "chunk2"]
        result = await mock_provider.contextualize(chunks, query="test", context_window=5)
        assert mock_provider.contextualize_called
        assert mock_provider.last_chunks == chunks
        assert mock_provider.last_query == "test"
        assert mock_provider.last_context_window == 5
        assert len(result) == 2

    async def test_contextualize_default_parameters(self, mock_provider):
        """Test that contextualize has correct default parameters."""
        chunks = ["chunk1"]
        await mock_provider.contextualize(chunks)
        assert mock_provider.last_query is None
        assert mock_provider.last_context_window == 3

    async def test_contextualize_returns_list_of_chunks(self, mock_provider):
        """Test that contextualize returns list of ContextualizedChunk."""
        chunks = ["chunk1", "chunk2", "chunk3"]
        result = await mock_provider.contextualize(chunks)
        assert isinstance(result, list)
        assert all(isinstance(c, ContextualizedChunk) for c in result)
        assert len(result) == 3

    async def test_contextualize_single_method_signature(self, mock_provider):
        """Test that contextualize_single accepts expected parameters."""
        result = await mock_provider.contextualize_single(
            text="Test text", article_number="Art 1", query="search query"
        )
        assert mock_provider.contextualize_single_called
        assert mock_provider.last_text == "Test text"
        assert mock_provider.last_article_number == "Art 1"
        assert mock_provider.last_query == "search query"
        assert isinstance(result, ContextualizedChunk)

    async def test_contextualize_single_default_query(self, mock_provider):
        """Test that contextualize_single has query=None default."""
        await mock_provider.contextualize_single(text="Test", article_number="Art 1")
        assert mock_provider.last_query is None

    async def test_contextualize_empty_chunks_list(self, mock_provider):
        """Test contextualize with empty chunks list."""
        result = await mock_provider.contextualize([])
        assert result == []

    async def test_inheritance_preserves_static_methods(self, mock_provider):
        """Test that static methods are inherited correctly."""
        # Should be accessible on instance
        system_prompt = mock_provider.get_system_prompt()
        user_prompt = mock_provider.get_user_prompt("text", "query")
        assert isinstance(system_prompt, str)
        assert isinstance(user_prompt, str)


# =============================================================================
# TestStaticPromptMethods
# =============================================================================


class TestStaticPromptMethods:
    """Detailed tests for static prompt methods."""

    def test_system_prompt_max_word_guideline(self):
        """Test that system prompt mentions max word count."""
        prompt = ContextualizeProvider.get_system_prompt()
        assert "100 words" in prompt.lower() or "100" in prompt

    def test_system_prompt_response_format(self):
        """Test that system prompt specifies response format."""
        prompt = ContextualizeProvider.get_system_prompt()
        assert "only" in prompt.lower()
        assert "summary" in prompt.lower()

    def test_user_prompt_format_with_text(self):
        """Test user prompt format with provided text."""
        text = "Article 115 of the Criminal Code"
        prompt = ContextualizeProvider.get_user_prompt(text)
        assert "Summarize this legal text" in prompt
        assert text in prompt

    def test_user_prompt_format_with_query(self):
        """Test user prompt format includes query section."""
        text = "Some legal text"
        query = "What is the punishment?"
        prompt = ContextualizeProvider.get_user_prompt(text, query)
        assert "User is searching for:" in prompt
        assert query in prompt

    def test_user_prompt_cyrillic_text(self):
        """Test user prompt with cyrillic text."""
        text = "Стаття 115 Кримінального кодексу"
        query = "Яке покарання?"
        prompt = ContextualizeProvider.get_user_prompt(text, query)
        assert text in prompt
        assert query in prompt
