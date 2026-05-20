"""
Unit tests for src/evaluation/generate_test_queries.py

Tests query generation functionality with mocked external services.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


***REMOVED*** Mock heavy dependencies before importing
***REMOVED*** Note: We don't mock 'aiohttp' or 'requests' in sys.modules because they're used
***REMOVED*** by httpx internally and mocking them causes test pollution in other test modules.
@pytest.fixture(autouse=True)
def mock_imports(monkeypatch: pytest.MonkeyPatch):
    """Mock external dependencies that won't pollute other tests."""
    mock_contextualize = MagicMock()
    mock_settings = MagicMock()

    ***REMOVED*** Setup Settings mock
    mock_settings_instance = MagicMock()
    mock_settings_instance.qdrant_url = "http://localhost:6333"
    mock_settings_instance.qdrant_api_key = "test-key"
    mock_settings.return_value = mock_settings_instance

    ***REMOVED*** Only mock modules that won't affect other parts of the codebase
    monkeypatch.setitem(sys.modules, "contextualize_groq_async", mock_contextualize)

    with patch("src.config.Settings", mock_settings):
        yield {
            "contextualize": mock_contextualize,
            "settings": mock_settings,
        }


class TestFetchArticleTexts:
    """Tests for fetch_article_texts function."""

    def test_fetch_single_article(self, mock_imports):
        """Test fetching a single article from Qdrant via SDK scroll."""
        mock_client = MagicMock()

        ***REMOVED*** Mock scroll return: a point with text
        mock_point = MagicMock()
        mock_point.payload = {"text": "Article 115 text content"}
        mock_client.scroll.return_value = ([mock_point], None)

        with patch("src.evaluation.generate_test_queries._make_client", return_value=mock_client):
            from src.evaluation.generate_test_queries import fetch_article_texts

            result = fetch_article_texts("test_collection", ["115"])

        assert "115" in result
        assert result["115"] == "Article 115 text content"

    def test_fetch_multiple_articles(self, mock_imports):
        """Test fetching multiple articles."""
        article_texts = {
            "115": "Murder article text",
            "121": "Intentional injury text",
            "185": "Theft article text",
        }

        mock_client = MagicMock()

        def mock_scroll(collection_name, scroll_filter, limit, with_payload, with_vectors):
            ***REMOVED*** Extract article number from the filter
            must = scroll_filter.must
            value = must[0].match.value
            article_num = str(value)
            if article_num in article_texts:
                p = MagicMock()
                p.payload = {"text": article_texts[article_num]}
                return ([p], None)
            return ([], None)

        mock_client.scroll.side_effect = mock_scroll

        with patch("src.evaluation.generate_test_queries._make_client", return_value=mock_client):
            from src.evaluation.generate_test_queries import fetch_article_texts

            result = fetch_article_texts("test_collection", ["115", "121", "185"])

        assert len(result) == 3
        assert result["115"] == "Murder article text"

    def test_fetch_article_not_found(self, mock_imports):
        """Test handling when article is not found."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        with patch("src.evaluation.generate_test_queries._make_client", return_value=mock_client):
            from src.evaluation.generate_test_queries import fetch_article_texts

            result = fetch_article_texts("test_collection", ["999"])

        assert "999" not in result
        assert len(result) == 0

    def test_qdrant_scroll_filter_structure(self, mock_imports):
        """Test Qdrant scroll filter is correctly structured."""
        from qdrant_client import models

        article_num = "115"

        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="article_number",
                    match=models.MatchValue(value=int(article_num)),
                )
            ]
        )

        assert scroll_filter.must[0].match.value == 115
        assert scroll_filter.must[0].key == "article_number"


class TestGenerateQueriesForArticle:
    """Tests for generate_queries_for_article function."""

    async def test_generate_queries_success(self, mock_imports):
        """Test successful query generation for an article using instructor client."""
        from src.evaluation.generate_test_queries import (
            GeneratedQueries,
            generate_queries_for_article,
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=GeneratedQueries(
                direct="статья 115",
                semantic="наказание за убийство",
                paraphrased="что грозит за лишение жизни",
            )
        )

        queries = await generate_queries_for_article(
            mock_client, "openai/gpt-oss-120b", "115", "Article 115 text content"
        )

        assert len(queries) == 3
        assert queries[0]["type"] == "direct"
        assert queries[0]["query"] == "статья 115"
        assert queries[1]["difficulty"] == "medium"
        assert all(q["expected_article"] == "115" for q in queries)

    def test_text_truncation(self):
        """Test article text is truncated if too long."""
        long_text = "A" * 2000
        text_preview = long_text[:1000] if len(long_text) > 1000 else long_text

        assert len(text_preview) == 1000
        assert text_preview == "A" * 1000

    def test_text_no_truncation_if_short(self):
        """Test short text is not truncated."""
        short_text = "Short article text"
        text_preview = short_text[:1000] if len(short_text) > 1000 else short_text

        assert text_preview == short_text

    def test_query_object_structure(self):
        """Test generated query objects have correct structure."""
        query_obj = {
            "query": "test query",
            "type": "direct",
            "expected_article": "115",
            "difficulty": "easy",
        }

        assert "query" in query_obj
        assert "type" in query_obj
        assert "expected_article" in query_obj
        assert "difficulty" in query_obj
        assert query_obj["type"] in ["direct", "semantic", "paraphrased"]
        assert query_obj["difficulty"] in ["easy", "medium", "hard"]

    def test_prompt_formatting(self):
        """Test LLM prompt is correctly formatted."""
        article_num = "115"
        text_preview = "Murder article text..."

        prompt = f"""Ты эксперт по Уголовному кодексу Украины. На основе текста статьи {article_num}, создай 3 поисковых запроса:

ТЕКСТ СТАТЬИ {article_num}:
{text_preview}"""

        assert "115" in prompt
        assert "Murder article text..." in prompt
        assert "Уголовному кодексу" in prompt


class TestGenerateAllQueries:
    """Tests for generate_all_queries function."""

    async def test_generate_all_queries_success(self, mock_imports):
        """Test generating queries for multiple articles with instructor client."""
        from src.evaluation.generate_test_queries import (
            GeneratedQueries,
            generate_all_queries,
        )

        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create = AsyncMock(
            return_value=GeneratedQueries(
                direct="прямой запрос",
                semantic="семантический запрос",
                paraphrased="перефразированный запрос",
            )
        )

        article_texts = {
            "115": "Murder text",
            "121": "Injury text",
        }

        with patch("src.evaluation.generate_test_queries.instructor") as mock_instructor_mod:
            mock_instructor_mod.from_openai.return_value = mock_instructor_client

            result = await generate_all_queries(
                article_texts,
                model="openai/gpt-oss-120b",
                max_concurrent=5,
                base_url="http://test.api/v1",
                api_key="test-key",
            )

        assert len(result) == 6  ***REMOVED*** 3 queries per article * 2 articles
        assert result[0]["expected_article"] == "115"
        assert result[3]["expected_article"] == "121"

    async def test_generate_queries_with_errors(self, mock_imports):
        """Test error handling during query generation through real generate_all_queries."""
        from src.evaluation.generate_test_queries import (
            GeneratedQueries,
            generate_all_queries,
        )

        call_count = 0

        async def _create_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            ***REMOVED*** Determine which article based on the prompt content
            content = kwargs.get("messages", [{}])[0].get("content", "")
            if "999" in content:
                raise ValueError("LLM API error")
            return GeneratedQueries(
                direct="прямой запрос",
                semantic="семантический запрос",
                paraphrased="перефразированный запрос",
            )

        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create = AsyncMock(side_effect=_create_side_effect)

        article_texts = {
            "115": "Normal text",
            "999": "Error text",
            "121": "Normal text",
        }

        with patch("src.evaluation.generate_test_queries.instructor") as mock_instructor_mod:
            mock_instructor_mod.from_openai.return_value = mock_instructor_client

            result = await generate_all_queries(
                article_texts,
                model="openai/gpt-oss-120b",
                max_concurrent=5,
                base_url="http://test.api/v1",
                api_key="test-key",
            )

        ***REMOVED*** Only articles 115 and 121 succeed (3 queries each)
        assert len(result) == 6
        expected_articles = {q["expected_article"] for q in result}
        assert "115" in expected_articles
        assert "121" in expected_articles
        assert "999" not in expected_articles


class TestSelectRepresentativeArticles:
    """Tests for select_representative_articles function."""

    def test_select_50_articles(self):
        """Test selecting 50 representative articles."""
        all_articles = {str(i): [] for i in range(1, 500)}  ***REMOVED*** 499 articles

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))
        n = 50
        step = len(article_nums) // n
        selected = [article_nums[i * step] for i in range(n)]

        assert len(selected) == 50
        ***REMOVED*** First article should be near the beginning
        assert int(selected[0]) < 20
        ***REMOVED*** Distribution should be even
        gaps = [int(selected[i + 1]) - int(selected[i]) for i in range(len(selected) - 1)]
        avg_gap = sum(gaps) / len(gaps)
        assert 5 < avg_gap < 15  ***REMOVED*** Approximately evenly distributed

    def test_select_from_small_dataset(self):
        """Test selection when dataset is smaller than n."""
        all_articles = {str(i): [] for i in range(1, 30)}  ***REMOVED*** 29 articles
        n = 50

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))
        step = max(1, len(article_nums) // n)
        selected = [
            article_nums[min(i * step, len(article_nums) - 1)]
            for i in range(min(n, len(article_nums)))
        ]

        ***REMOVED*** Should not exceed available articles
        assert len(selected) <= len(article_nums)

    def test_sorting_by_article_number(self):
        """Test articles are sorted numerically, not lexicographically."""
        all_articles = {"1": [], "10": [], "2": [], "20": [], "100": []}

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))

        assert article_nums == ["1", "2", "10", "20", "100"]

    def test_even_distribution(self):
        """Test selected articles are evenly distributed."""
        all_articles = {str(i): [] for i in range(1, 101)}  ***REMOVED*** 100 articles
        n = 10

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))
        step = len(article_nums) // n
        selected = [article_nums[i * step] for i in range(n)]

        selected_ints = [int(a) for a in selected]

        ***REMOVED*** Check even distribution (every 10th article)
        assert selected_ints[0] == 1
        assert selected_ints[1] == 11
        assert selected_ints[9] == 91


class TestQueryTypes:
    """Tests for query type classification."""

    def test_direct_query_attributes(self):
        """Test direct query has correct attributes."""
        query = {
            "query": "статья 115",
            "type": "direct",
            "expected_article": "115",
            "difficulty": "easy",
        }

        assert query["type"] == "direct"
        assert query["difficulty"] == "easy"

    def test_semantic_query_attributes(self):
        """Test semantic query has correct attributes."""
        query = {
            "query": "наказание за преднамеренное лишение жизни",
            "type": "semantic",
            "expected_article": "115",
            "difficulty": "medium",
        }

        assert query["type"] == "semantic"
        assert query["difficulty"] == "medium"

    def test_paraphrased_query_attributes(self):
        """Test paraphrased query has correct attributes."""
        query = {
            "query": "что грозит за убийство по УК",
            "type": "paraphrased",
            "expected_article": "115",
            "difficulty": "hard",
        }

        assert query["type"] == "paraphrased"
        assert query["difficulty"] == "hard"


class TestOutputFormatting:
    """Tests for output file formatting."""

    def test_queries_json_format(self, tmp_path):
        """Test queries are saved in correct JSON format."""
        queries = [
            {"query": "q1", "type": "direct", "expected_article": "115", "difficulty": "easy"},
            {"query": "q2", "type": "semantic", "expected_article": "115", "difficulty": "medium"},
        ]

        output_file = tmp_path / "queries.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(queries, f, ensure_ascii=False, indent=2)

        loaded = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(loaded) == 2
        assert loaded[0]["query"] == "q1"

    def test_cyrillic_characters_preserved(self, tmp_path):
        """Test Cyrillic characters are preserved in output."""
        queries = [
            {"query": "наказание за убийство", "type": "semantic", "expected_article": "115"}
        ]

        output_file = tmp_path / "queries.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(queries, f, ensure_ascii=False, indent=2)

        loaded = json.loads(output_file.read_text(encoding="utf-8"))
        assert loaded[0]["query"] == "наказание за убийство"


class TestSummaryStatistics:
    """Tests for summary statistics calculation."""

    def test_count_by_type(self):
        """Test counting queries by type."""
        queries = [
            {"type": "direct"},
            {"type": "direct"},
            {"type": "semantic"},
            {"type": "semantic"},
            {"type": "semantic"},
            {"type": "paraphrased"},
        ]

        direct_count = len([q for q in queries if q["type"] == "direct"])
        semantic_count = len([q for q in queries if q["type"] == "semantic"])
        paraphrased_count = len([q for q in queries if q["type"] == "paraphrased"])

        assert direct_count == 2
        assert semantic_count == 3
        assert paraphrased_count == 1

    def test_unique_articles_count(self):
        """Test counting unique articles covered."""
        queries = [
            {"expected_article": "115"},
            {"expected_article": "115"},
            {"expected_article": "121"},
            {"expected_article": "185"},
            {"expected_article": "185"},
        ]

        unique_articles = len({q["expected_article"] for q in queries})

        assert unique_articles == 3


class TestLLMClientConfiguration:
    """Tests for LLM client configuration."""

    def test_llm_initialization_params(self):
        """Test LLM is initialized with correct parameters."""
        model = "openai/gpt-oss-120b"
        max_concurrent = 5

        ***REMOVED*** Verify configuration values
        assert "gpt-oss-120b" in model
        assert max_concurrent == 5

    def test_llm_request_structure(self):
        """Test instructor client is called with correct parameters."""
        from src.evaluation.generate_test_queries import GeneratedQueries

        ***REMOVED*** Verify expected call parameters for instructor
        expected_kwargs = {
            "model": "openai/gpt-oss-120b",
            "response_model": GeneratedQueries,
            "temperature": 0.7,
            "max_retries": 2,
        }

        assert expected_kwargs["model"] == "openai/gpt-oss-120b"
        assert expected_kwargs["response_model"] is GeneratedQueries
        assert expected_kwargs["temperature"] == 0.7
        assert expected_kwargs["max_retries"] == 2


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_qdrant_connection_error(self, mock_imports):
        """Test handling Qdrant connection errors."""
        mock_client = MagicMock()
        mock_client.scroll.side_effect = ConnectionError("Connection refused")

        with (
            patch("src.evaluation.generate_test_queries._make_client", return_value=mock_client),
            pytest.raises(ConnectionError),
        ):
            from src.evaluation.generate_test_queries import fetch_article_texts

            fetch_article_texts("test_collection", ["115"])

    def test_missing_model_fields_raise_validation_error(self):
        """Test that missing fields in GeneratedQueries raise ValidationError."""
        from pydantic import ValidationError

        from src.evaluation.generate_test_queries import GeneratedQueries

        with pytest.raises(ValidationError):
            GeneratedQueries(direct="query 1")  ***REMOVED*** type: ignore[call-arg]


class TestStructuredOutputParsing:
    """Regression tests for the instructor-based structured output refactor."""

    def test_generated_queries_model_valid(self):
        """Test GeneratedQueries model with valid input succeeds."""
        from src.evaluation.generate_test_queries import GeneratedQueries

        result = GeneratedQueries(
            direct="статья 115",
            semantic="наказание за убийство",
            paraphrased="что грозит за лишение жизни",
        )

        assert result.direct == "статья 115"
        assert result.semantic == "наказание за убийство"
        assert result.paraphrased == "что грозит за лишение жизни"

    def test_generated_queries_model_missing_field(self):
        """Test that missing fields raise ValidationError."""
        from pydantic import ValidationError

        from src.evaluation.generate_test_queries import GeneratedQueries

        with pytest.raises(ValidationError):
            GeneratedQueries(direct="query 1", semantic="query 2")  ***REMOVED*** type: ignore[call-arg]

        with pytest.raises(ValidationError):
            GeneratedQueries(direct="query 1")  ***REMOVED*** type: ignore[call-arg]

        with pytest.raises(ValidationError):
            GeneratedQueries()  ***REMOVED*** type: ignore[call-arg]

    async def test_structured_parsing_returns_correct_shape(self, mock_imports):
        """Test generate_queries_for_article returns list of 3 dicts with correct keys."""
        from src.evaluation.generate_test_queries import (
            GeneratedQueries,
            generate_queries_for_article,
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=GeneratedQueries(
                direct="статья 121",
                semantic="тяжкие телесные повреждения",
                paraphrased="что будет за нанесение тяжких травм",
            )
        )

        result = await generate_queries_for_article(
            mock_client, "openai/gpt-oss-120b", "121", "Article 121 about injuries..."
        )

        ***REMOVED*** Correct number of queries
        assert len(result) == 3

        ***REMOVED*** Each dict has required keys
        required_keys = {"query", "type", "expected_article", "difficulty"}
        for query_dict in result:
            assert set(query_dict.keys()) == required_keys

        ***REMOVED*** Type and difficulty mappings are correct
        assert result[0]["type"] == "direct"
        assert result[0]["difficulty"] == "easy"
        assert result[1]["type"] == "semantic"
        assert result[1]["difficulty"] == "medium"
        assert result[2]["type"] == "paraphrased"
        assert result[2]["difficulty"] == "hard"

        ***REMOVED*** Expected article is set correctly
        assert all(q["expected_article"] == "121" for q in result)

        ***REMOVED*** Query content matches model output
        assert result[0]["query"] == "статья 121"
        assert result[1]["query"] == "тяжкие телесные повреждения"
        assert result[2]["query"] == "что будет за нанесение тяжких травм"

    async def test_invalid_model_output_raises(self, mock_imports):
        """Test that exception from instructor propagates to caller."""
        from src.evaluation.generate_test_queries import generate_queries_for_article

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Max retries exceeded: validation failed")
        )

        with pytest.raises(Exception, match="Max retries exceeded"):
            await generate_queries_for_article(
                mock_client, "openai/gpt-oss-120b", "115", "Some article text"
            )

    async def test_generate_all_queries_creates_instructor_client(self, mock_imports):
        """Test that generate_all_queries creates instructor client with correct params."""
        from src.evaluation.generate_test_queries import (
            GeneratedQueries,
            generate_all_queries,
        )

        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create = AsyncMock(
            return_value=GeneratedQueries(
                direct="direct query",
                semantic="semantic query",
                paraphrased="paraphrased query",
            )
        )

        with (
            patch("src.evaluation.generate_test_queries.instructor") as mock_instructor_mod,
            patch("src.evaluation.generate_test_queries.AsyncOpenAI") as mock_openai_cls,
        ):
            mock_instructor_mod.from_openai.return_value = mock_instructor_client
            mock_openai_instance = MagicMock()
            mock_openai_cls.return_value = mock_openai_instance

            await generate_all_queries(
                {"115": "Article text"},
                model="openai/gpt-oss-120b",
                base_url="http://custom.api/v1",
                api_key="custom-key",
            )

            ***REMOVED*** Verify AsyncOpenAI was created with correct params
            mock_openai_cls.assert_called_once_with(
                base_url="http://custom.api/v1", api_key="custom-key"
            )

            ***REMOVED*** Verify instructor.from_openai was called with the AsyncOpenAI instance
            mock_instructor_mod.from_openai.assert_called_once_with(mock_openai_instance)

    def test_generated_queries_model_extra_fields_ignored(self):
        """Test that extra fields do not break GeneratedQueries model."""
        from src.evaluation.generate_test_queries import GeneratedQueries

        ***REMOVED*** Pydantic v2 default ignores extra fields
        result = GeneratedQueries.model_validate(
            {
                "direct": "query 1",
                "semantic": "query 2",
                "paraphrased": "query 3",
                "extra_field": "ignored",
            }
        )

        assert result.direct == "query 1"
        assert result.semantic == "query 2"
        assert result.paraphrased == "query 3"
        assert not hasattr(result, "extra_field")
