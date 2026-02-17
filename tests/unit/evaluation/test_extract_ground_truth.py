# tests/unit/evaluation/test_extract_ground_truth.py
"""Tests for ground truth extraction module."""

from unittest.mock import MagicMock, mock_open, patch


class TestExtractArticles:
    """Tests for extract_articles function."""

    @patch("src.evaluation.extract_ground_truth.requests")
    @patch("src.evaluation.extract_ground_truth._qdrant_api_key", new=lambda: "test_key")
    @patch("src.evaluation.extract_ground_truth._qdrant_url", new=lambda: "http://localhost:6333")
    def test_extract_articles_scrolls_collection(self, mock_requests):
        """Test extract_articles scrolls through Qdrant collection."""
        # First response with points
        first_response = MagicMock()
        first_response.json.return_value = {
            "result": {
                "points": [
                    {
                        "id": "point-1",
                        "payload": {
                            "article_number": 121,
                            "chunk_id": "chunk-1",
                            "text": "Article 121 text",
                        },
                    }
                ],
                "next_page_offset": None,
            }
        }
        first_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = first_response

        from src.evaluation.extract_ground_truth import extract_articles

        extract_articles("test_collection")

        mock_requests.post.assert_called()
        call_args = mock_requests.post.call_args
        assert "test_collection" in call_args[0][0]
        assert call_args[1]["headers"]["api-key"] == "test_key"

    @patch("src.evaluation.extract_ground_truth.requests")
    @patch("src.evaluation.extract_ground_truth._qdrant_api_key", new=lambda: "")
    @patch("src.evaluation.extract_ground_truth._qdrant_url", new=lambda: "http://localhost:6333")
    def test_extract_articles_groups_by_article_number(self, mock_requests):
        """Test extract_articles groups chunks by article number."""
        response = MagicMock()
        response.json.return_value = {
            "result": {
                "points": [
                    {
                        "id": "point-1",
                        "payload": {"article_number": 121, "chunk_id": "chunk-1", "text": "A"},
                    },
                    {
                        "id": "point-2",
                        "payload": {"article_number": 121, "chunk_id": "chunk-2", "text": "B"},
                    },
                    {
                        "id": "point-3",
                        "payload": {"article_number": 122, "chunk_id": "chunk-3", "text": "C"},
                    },
                ],
                "next_page_offset": None,
            }
        }
        response.raise_for_status = MagicMock()
        mock_requests.post.return_value = response

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test_collection")

        assert "121" in result
        assert "122" in result
        assert len(result["121"]) == 2
        assert len(result["122"]) == 1

    @patch("src.evaluation.extract_ground_truth.requests")
    @patch("src.evaluation.extract_ground_truth._qdrant_api_key", new=lambda: "")
    @patch("src.evaluation.extract_ground_truth._qdrant_url", new=lambda: "http://localhost:6333")
    def test_extract_articles_handles_pagination(self, mock_requests):
        """Test extract_articles handles multiple pages."""
        # First page
        first_response = MagicMock()
        first_response.json.return_value = {
            "result": {
                "points": [
                    {"id": "1", "payload": {"article_number": 1, "chunk_id": "c1", "text": "A"}}
                ],
                "next_page_offset": "offset-1",
            }
        }
        first_response.raise_for_status = MagicMock()

        # Second page
        second_response = MagicMock()
        second_response.json.return_value = {
            "result": {
                "points": [
                    {"id": "2", "payload": {"article_number": 2, "chunk_id": "c2", "text": "B"}}
                ],
                "next_page_offset": None,
            }
        }
        second_response.raise_for_status = MagicMock()

        mock_requests.post.side_effect = [first_response, second_response]

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        assert mock_requests.post.call_count == 2
        assert "1" in result
        assert "2" in result

    @patch("src.evaluation.extract_ground_truth.requests")
    @patch("src.evaluation.extract_ground_truth._qdrant_api_key", new=lambda: "")
    @patch("src.evaluation.extract_ground_truth._qdrant_url", new=lambda: "http://localhost:6333")
    def test_extract_articles_skips_points_without_article(self, mock_requests):
        """Test extract_articles skips points without article_number."""
        response = MagicMock()
        response.json.return_value = {
            "result": {
                "points": [
                    {"id": "1", "payload": {"article_number": 121, "text": "A"}},
                    {"id": "2", "payload": {"text": "No article number"}},  # Missing article
                ],
                "next_page_offset": None,
            }
        }
        response.raise_for_status = MagicMock()
        mock_requests.post.return_value = response

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        assert "121" in result
        assert len(result) == 1  # Only one article extracted

    @patch("src.evaluation.extract_ground_truth.requests")
    @patch("src.evaluation.extract_ground_truth._qdrant_api_key", new=lambda: "")
    @patch("src.evaluation.extract_ground_truth._qdrant_url", new=lambda: "http://localhost:6333")
    def test_extract_articles_uses_point_id_as_fallback(self, mock_requests):
        """Test extract_articles uses point ID when chunk_id missing."""
        response = MagicMock()
        response.json.return_value = {
            "result": {
                "points": [
                    {"id": "point-123", "payload": {"article_number": 121, "text": "A"}},
                ],
                "next_page_offset": None,
            }
        }
        response.raise_for_status = MagicMock()
        mock_requests.post.return_value = response

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        assert result["121"][0]["chunk_id"] == "point-123"

    @patch("src.evaluation.extract_ground_truth.requests")
    @patch("src.evaluation.extract_ground_truth._qdrant_api_key", new=lambda: "")
    @patch("src.evaluation.extract_ground_truth._qdrant_url", new=lambda: "http://localhost:6333")
    def test_extract_articles_stores_text_preview(self, mock_requests):
        """Test extract_articles stores truncated text preview."""
        long_text = "A" * 200  # Longer than 100 chars
        response = MagicMock()
        response.json.return_value = {
            "result": {
                "points": [
                    {
                        "id": "1",
                        "payload": {"article_number": 121, "chunk_id": "c1", "text": long_text},
                    }
                ],
                "next_page_offset": None,
            }
        }
        response.raise_for_status = MagicMock()
        mock_requests.post.return_value = response

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        # Text preview should be truncated to 100 chars
        assert len(result["121"][0]["text_preview"]) == 100

    @patch("src.evaluation.extract_ground_truth.requests")
    @patch("src.evaluation.extract_ground_truth._qdrant_api_key", new=lambda: "")
    @patch("src.evaluation.extract_ground_truth._qdrant_url", new=lambda: "http://localhost:6333")
    def test_extract_articles_empty_collection(self, mock_requests):
        """Test extract_articles handles empty collection."""
        response = MagicMock()
        response.json.return_value = {
            "result": {
                "points": [],
                "next_page_offset": None,
            }
        }
        response.raise_for_status = MagicMock()
        mock_requests.post.return_value = response

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("empty_collection")

        assert result == {}


class TestPrintStatistics:
    """Tests for print_statistics function."""

    def test_print_statistics_outputs_summary(self, capsys):
        """Test print_statistics outputs article summary."""
        from src.evaluation.extract_ground_truth import print_statistics

        articles = {
            "121": [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
            "122": [{"chunk_id": "c3"}],
            "123": [{"chunk_id": "c4"}, {"chunk_id": "c5"}, {"chunk_id": "c6"}],
        }

        print_statistics(articles)

        captured = capsys.readouterr()
        assert "Total articles: 3" in captured.out
        assert "Total chunks: 6" in captured.out

    def test_print_statistics_outputs_distribution(self, capsys):
        """Test print_statistics outputs chunks distribution."""
        from src.evaluation.extract_ground_truth import print_statistics

        articles = {
            "1": [{"chunk_id": "c1"}],
            "2": [{"chunk_id": "c2"}, {"chunk_id": "c3"}],
            "3": [{"chunk_id": "c4"}, {"chunk_id": "c5"}, {"chunk_id": "c6"}],
        }

        print_statistics(articles)

        captured = capsys.readouterr()
        assert "Min: 1" in captured.out
        assert "Max: 3" in captured.out
        assert "Avg: 2.0" in captured.out

    def test_print_statistics_shows_sample_articles(self, capsys):
        """Test print_statistics shows sample articles."""
        from src.evaluation.extract_ground_truth import print_statistics

        articles = {
            "1": [{"chunk_id": "c1"}],
            "5": [{"chunk_id": "c2"}],
            "10": [{"chunk_id": "c3"}],
        }

        print_statistics(articles)

        captured = capsys.readouterr()
        assert "Sample articles" in captured.out
        assert "Article 1" in captured.out


class TestMain:
    """Tests for main function."""

    @patch("src.evaluation.extract_ground_truth.extract_articles")
    @patch("src.evaluation.extract_ground_truth.print_statistics")
    @patch("builtins.open", new_callable=mock_open)
    def test_main_extracts_and_saves(self, mock_file, mock_stats, mock_extract):
        """Test main extracts articles and saves to files."""
        mock_extract.return_value = {
            "121": [{"chunk_id": "c1", "point_id": "p1", "text_preview": "text"}],
            "122": [{"chunk_id": "c2", "point_id": "p2", "text_preview": "text"}],
        }

        from src.evaluation.extract_ground_truth import main

        main()

        mock_extract.assert_called_once_with("ukraine_criminal_code_zai_full")
        mock_stats.assert_called_once()

        opened_paths = [call.args[0] for call in mock_file.call_args_list]
        assert (
            "/srv/app/evaluation/data/ground_truth_articles.json" in opened_paths
        )
        assert (
            "/srv/app/evaluation/data/article_to_chunk_mapping.json"
            in opened_paths
        )

    @patch("src.evaluation.extract_ground_truth.extract_articles")
    @patch("src.evaluation.extract_ground_truth.print_statistics")
    @patch("builtins.open", new_callable=mock_open)
    def test_main_creates_simplified_mapping(self, mock_file, mock_stats, mock_extract):
        """Test main creates simplified article-to-chunk mapping."""
        mock_extract.return_value = {
            "121": [
                {"chunk_id": "c1", "point_id": "p1", "text_preview": "first"},
                {"chunk_id": "c2", "point_id": "p2", "text_preview": "second"},
            ],
        }

        from src.evaluation.extract_ground_truth import main

        main()

        # Check that json.dump was called with simplified mapping
        write_calls = mock_file().write.call_args_list
        # At least one write should contain the simplified mapping (first point_id only)
        written_content = "".join(call[0][0] for call in write_calls)
        assert "p1" in written_content

    @patch("src.evaluation.extract_ground_truth.extract_articles")
    @patch("src.evaluation.extract_ground_truth.print_statistics")
    @patch("builtins.open", new_callable=mock_open)
    def test_main_prints_completion_message(self, mock_file, mock_stats, mock_extract, capsys):
        """Test main prints completion message."""
        mock_extract.return_value = {"121": [{"point_id": "p1"}]}

        from src.evaluation.extract_ground_truth import main

        main()

        captured = capsys.readouterr()
        assert "Ground truth extraction completed" in captured.out

    @patch("src.evaluation.extract_ground_truth.extract_articles")
    @patch("src.evaluation.extract_ground_truth.print_statistics")
    @patch("builtins.open", new_callable=mock_open)
    def test_main_uses_correct_collection(self, mock_file, mock_stats, mock_extract):
        """Test main uses correct collection name."""
        mock_extract.return_value = {}

        from src.evaluation.extract_ground_truth import main

        main()

        mock_extract.assert_called_once_with("ukraine_criminal_code_zai_full")
