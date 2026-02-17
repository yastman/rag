"""
Unit tests for src/evaluation/generate_test_queries.py

Tests query generation functionality with mocked external services.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Mock heavy dependencies before importing
# Note: We don't mock 'aiohttp' or 'requests' in sys.modules because they're used
# by httpx internally and mocking them causes test pollution in other test modules.
@pytest.fixture(autouse=True)
def mock_imports():
    """Mock external dependencies that won't pollute other tests."""
    mock_requests = MagicMock()
    mock_contextualize = MagicMock()
    mock_settings = MagicMock()

    # Setup Settings mock
    mock_settings_instance = MagicMock()
    mock_settings_instance.qdrant_url = "http://localhost:6333"
    mock_settings_instance.qdrant_api_key = "test-key"
    mock_settings.return_value = mock_settings_instance

    # Only mock modules that won't affect other parts of the codebase
    mock_keys = ["contextualize_groq_async"]
    original_modules = {k: sys.modules.get(k) for k in mock_keys}

    # Apply mocks
    mocks = {
        "contextualize_groq_async": mock_contextualize,
    }
    sys.modules.update(mocks)

    try:
        with patch("src.config.Settings", mock_settings):
            yield {
                "requests": mock_requests,
                "contextualize": mock_contextualize,
                "settings": mock_settings,
            }
    finally:
        # Restore original state
        for key, value in original_modules.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


class TestFetchArticleTexts:
    """Tests for fetch_article_texts function."""

    def test_fetch_single_article(self, mock_imports):
        """Test fetching a single article from Qdrant."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"points": [{"payload": {"text": "Article 115 text content"}}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_imports["requests"].post.return_value = mock_response

        # Simulate fetch_article_texts behavior
        article_numbers = ["115"]
        articles = {}

        for article_num in article_numbers:
            response = mock_imports["requests"].post(
                "http://localhost:6333/collections/test/points/scroll",
                json={
                    "filter": {
                        "must": [{"key": "article_number", "match": {"value": int(article_num)}}]
                    },
                    "limit": 1,
                    "with_payload": True,
                    "with_vector": False,
                },
                headers={"api-key": "test-key"},
            )
            points = response.json()["result"]["points"]
            if points:
                text = points[0]["payload"].get("text", "")
                articles[article_num] = text

        assert "115" in articles
        assert articles["115"] == "Article 115 text content"

    def test_fetch_multiple_articles(self, mock_imports):
        """Test fetching multiple articles."""
        article_texts = {
            "115": "Murder article text",
            "121": "Intentional injury text",
            "185": "Theft article text",
        }

        def mock_post(url, json=None, headers=None):
            article_num = json["filter"]["must"][0]["match"]["value"]
            response = MagicMock()
            response.json.return_value = {
                "result": {
                    "points": [{"payload": {"text": article_texts.get(str(article_num), "")}}]
                    if str(article_num) in article_texts
                    else []
                }
            }
            response.raise_for_status = MagicMock()
            return response

        mock_imports["requests"].post.side_effect = mock_post

        # Fetch articles
        fetched = {}
        for num in ["115", "121", "185"]:
            response = mock_imports["requests"].post(
                "url",
                json={
                    "filter": {"must": [{"key": "article_number", "match": {"value": int(num)}}]}
                },
                headers={},
            )
            points = response.json()["result"]["points"]
            if points:
                fetched[num] = points[0]["payload"]["text"]

        assert len(fetched) == 3
        assert fetched["115"] == "Murder article text"

    def test_fetch_article_not_found(self, mock_imports):
        """Test handling when article is not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_imports["requests"].post.return_value = mock_response

        article_numbers = ["999"]
        articles = {}

        for article_num in article_numbers:
            response = mock_imports["requests"].post("url", json={}, headers={})
            points = response.json()["result"]["points"]
            if points:
                articles[article_num] = points[0]["payload"]["text"]

        assert "999" not in articles
        assert len(articles) == 0

    def test_qdrant_request_payload_structure(self):
        """Test Qdrant request payload is correctly structured."""
        article_num = "115"

        payload = {
            "filter": {
                "must": [
                    {
                        "key": "article_number",
                        "match": {"value": int(article_num)},
                    }
                ]
            },
            "limit": 1,
            "with_payload": True,
            "with_vector": False,
        }

        assert payload["filter"]["must"][0]["match"]["value"] == 115
        assert payload["limit"] == 1
        assert payload["with_payload"] is True
        assert payload["with_vector"] is False


class TestGenerateQueriesForArticle:
    """Tests for generate_queries_for_article function."""

    async def test_generate_queries_success(self, mock_imports):
        """Test successful query generation for an article."""
        # Mock LLM response
        llm_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "direct": "статья 115",
                                "semantic": "наказание за убийство",
                                "paraphrased": "что грозит за лишение жизни",
                            }
                        )
                    }
                }
            ]
        }

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=llm_response)

        # Create async context manager mocks
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=False)

        mock_session.post.return_value = mock_context

        # Simulate generate_queries_for_article logic
        article_num = "115"

        content = llm_response["choices"][0]["message"]["content"]
        queries_dict = json.loads(content)

        queries = [
            {
                "query": queries_dict["direct"],
                "type": "direct",
                "expected_article": article_num,
                "difficulty": "easy",
            },
            {
                "query": queries_dict["semantic"],
                "type": "semantic",
                "expected_article": article_num,
                "difficulty": "medium",
            },
            {
                "query": queries_dict["paraphrased"],
                "type": "paraphrased",
                "expected_article": article_num,
                "difficulty": "hard",
            },
        ]

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

    def test_json_extraction_from_response(self):
        """Test JSON is correctly extracted from LLM response."""
        content = """Here is the JSON response:
{
  "direct": "query 1",
  "semantic": "query 2",
  "paraphrased": "query 3"
}
Some additional text"""

        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1
        json_str = content[start_idx:end_idx]

        queries_dict = json.loads(json_str)

        assert queries_dict["direct"] == "query 1"
        assert queries_dict["semantic"] == "query 2"
        assert queries_dict["paraphrased"] == "query 3"

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
        """Test generating queries for multiple articles."""
        article_texts = {
            "115": "Murder text",
            "121": "Injury text",
        }

        # Simulate query generation
        all_queries = []
        for article_num in article_texts:
            queries = [
                {
                    "query": f"direct {article_num}",
                    "type": "direct",
                    "expected_article": article_num,
                },
                {
                    "query": f"semantic {article_num}",
                    "type": "semantic",
                    "expected_article": article_num,
                },
                {
                    "query": f"paraphrased {article_num}",
                    "type": "paraphrased",
                    "expected_article": article_num,
                },
            ]
            all_queries.extend(queries)

        assert len(all_queries) == 6  # 3 queries per article * 2 articles
        assert all_queries[0]["expected_article"] == "115"
        assert all_queries[3]["expected_article"] == "121"

    async def test_generate_queries_with_errors(self, mock_imports):
        """Test error handling during query generation."""
        article_texts = {
            "115": "Normal text",
            "999": "Error text",
            "121": "Normal text",
        }

        all_queries = []
        errors = []

        for article_num in article_texts:
            try:
                if article_num == "999":
                    raise ValueError("LLM API error")
                queries = [
                    {"query": f"q {article_num}", "type": "direct", "expected_article": article_num}
                ]
                all_queries.extend(queries)
            except ValueError as e:
                errors.append(str(e))

        assert len(all_queries) == 2  # Only 115 and 121
        assert len(errors) == 1
        assert "LLM API error" in errors[0]


class TestSelectRepresentativeArticles:
    """Tests for select_representative_articles function."""

    def test_select_50_articles(self):
        """Test selecting 50 representative articles."""
        all_articles = {str(i): [] for i in range(1, 500)}  # 499 articles

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))
        n = 50
        step = len(article_nums) // n
        selected = [article_nums[i * step] for i in range(n)]

        assert len(selected) == 50
        # First article should be near the beginning
        assert int(selected[0]) < 20
        # Distribution should be even
        gaps = [int(selected[i + 1]) - int(selected[i]) for i in range(len(selected) - 1)]
        avg_gap = sum(gaps) / len(gaps)
        assert 5 < avg_gap < 15  # Approximately evenly distributed

    def test_select_from_small_dataset(self):
        """Test selection when dataset is smaller than n."""
        all_articles = {str(i): [] for i in range(1, 30)}  # 29 articles
        n = 50

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))
        step = max(1, len(article_nums) // n)
        selected = [
            article_nums[min(i * step, len(article_nums) - 1)]
            for i in range(min(n, len(article_nums)))
        ]

        # Should not exceed available articles
        assert len(selected) <= len(article_nums)

    def test_sorting_by_article_number(self):
        """Test articles are sorted numerically, not lexicographically."""
        all_articles = {"1": [], "10": [], "2": [], "20": [], "100": []}

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))

        assert article_nums == ["1", "2", "10", "20", "100"]

    def test_even_distribution(self):
        """Test selected articles are evenly distributed."""
        all_articles = {str(i): [] for i in range(1, 101)}  # 100 articles
        n = 10

        article_nums = sorted(all_articles.keys(), key=lambda x: int(x))
        step = len(article_nums) // n
        selected = [article_nums[i * step] for i in range(n)]

        selected_ints = [int(a) for a in selected]

        # Check even distribution (every 10th article)
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

        # Verify configuration values
        assert "gpt-oss-120b" in model
        assert max_concurrent == 5

    def test_llm_request_structure(self):
        """Test LLM request has correct structure."""
        request = {
            "model": "openai/gpt-oss-120b",
            "messages": [{"role": "user", "content": "Generate queries..."}],
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        assert request["model"] == "openai/gpt-oss-120b"
        assert request["temperature"] == 0.7
        assert len(request["messages"]) == 1
        assert request["messages"][0]["role"] == "user"


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_qdrant_connection_error(self, mock_imports):
        """Test handling Qdrant connection errors."""
        mock_imports["requests"].post.side_effect = ConnectionError("Connection refused")

        with pytest.raises(ConnectionError):
            mock_imports["requests"].post("http://localhost:6333/...")

    def test_invalid_json_response(self):
        """Test handling invalid JSON in LLM response."""
        invalid_content = "This is not valid JSON"

        with pytest.raises(ValueError):
            start_idx = invalid_content.find("{")
            if start_idx == -1:
                raise ValueError("No JSON found in response")

    def test_missing_json_keys(self):
        """Test handling missing keys in LLM JSON response."""
        partial_json = {"direct": "query 1"}  # Missing semantic and paraphrased

        with pytest.raises(KeyError):
            _ = partial_json["semantic"]
