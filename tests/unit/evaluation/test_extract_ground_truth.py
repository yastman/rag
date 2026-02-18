# tests/unit/evaluation/test_extract_ground_truth.py
"""Tests for ground truth extraction module."""

from unittest.mock import MagicMock, mock_open, patch


class TestExtractArticles:
    """Tests for extract_articles function."""

    @patch("src.evaluation.extract_ground_truth._make_client")
    def test_extract_articles_scrolls_collection(self, mock_make_client):
        """Test extract_articles scrolls through Qdrant collection."""
        mock_client = MagicMock()

        # First scroll returns points, second returns empty
        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "article_number": 121,
            "chunk_id": "chunk-1",
            "text": "Article 121 text",
        }

        mock_client.scroll.return_value = ([mock_point], None)
        mock_make_client.return_value = mock_client

        from src.evaluation.extract_ground_truth import extract_articles

        extract_articles("test_collection")

        mock_client.scroll.assert_called()
        call_kwargs = mock_client.scroll.call_args[1]
        assert call_kwargs["collection_name"] == "test_collection"

    @patch("src.evaluation.extract_ground_truth._make_client")
    def test_extract_articles_groups_by_article_number(self, mock_make_client):
        """Test extract_articles groups chunks by article number."""
        mock_client = MagicMock()

        mock_points = []
        for pid, article, chunk_id, text in [
            ("point-1", 121, "chunk-1", "A"),
            ("point-2", 121, "chunk-2", "B"),
            ("point-3", 122, "chunk-3", "C"),
        ]:
            p = MagicMock()
            p.id = pid
            p.payload = {"article_number": article, "chunk_id": chunk_id, "text": text}
            mock_points.append(p)

        mock_client.scroll.return_value = (mock_points, None)
        mock_make_client.return_value = mock_client

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test_collection")

        assert "121" in result
        assert "122" in result
        assert len(result["121"]) == 2
        assert len(result["122"]) == 1

    @patch("src.evaluation.extract_ground_truth._make_client")
    def test_extract_articles_handles_pagination(self, mock_make_client):
        """Test extract_articles handles multiple pages."""
        mock_client = MagicMock()

        # First page
        p1 = MagicMock()
        p1.id = "1"
        p1.payload = {"article_number": 1, "chunk_id": "c1", "text": "A"}

        # Second page
        p2 = MagicMock()
        p2.id = "2"
        p2.payload = {"article_number": 2, "chunk_id": "c2", "text": "B"}

        mock_client.scroll.side_effect = [
            ([p1], "offset-1"),
            ([p2], None),
        ]
        mock_make_client.return_value = mock_client

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        assert mock_client.scroll.call_count == 2
        assert "1" in result
        assert "2" in result

    @patch("src.evaluation.extract_ground_truth._make_client")
    def test_extract_articles_skips_points_without_article(self, mock_make_client):
        """Test extract_articles skips points without article_number."""
        mock_client = MagicMock()

        p1 = MagicMock()
        p1.id = "1"
        p1.payload = {"article_number": 121, "text": "A"}

        p2 = MagicMock()
        p2.id = "2"
        p2.payload = {"text": "No article number"}  # Missing article

        mock_client.scroll.return_value = ([p1, p2], None)
        mock_make_client.return_value = mock_client

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        assert "121" in result
        assert len(result) == 1  # Only one article extracted

    @patch("src.evaluation.extract_ground_truth._make_client")
    def test_extract_articles_uses_point_id_as_fallback(self, mock_make_client):
        """Test extract_articles uses point ID when chunk_id missing."""
        mock_client = MagicMock()

        p = MagicMock()
        p.id = "point-123"
        p.payload = {"article_number": 121, "text": "A"}

        mock_client.scroll.return_value = ([p], None)
        mock_make_client.return_value = mock_client

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        assert result["121"][0]["chunk_id"] == "point-123"

    @patch("src.evaluation.extract_ground_truth._make_client")
    def test_extract_articles_stores_text_preview(self, mock_make_client):
        """Test extract_articles stores truncated text preview."""
        mock_client = MagicMock()

        long_text = "A" * 200  # Longer than 100 chars
        p = MagicMock()
        p.id = "1"
        p.payload = {"article_number": 121, "chunk_id": "c1", "text": long_text}

        mock_client.scroll.return_value = ([p], None)
        mock_make_client.return_value = mock_client

        from src.evaluation.extract_ground_truth import extract_articles

        result = extract_articles("test")

        # Text preview should be truncated to 100 chars
        assert len(result["121"][0]["text_preview"]) == 100

    @patch("src.evaluation.extract_ground_truth._make_client")
    def test_extract_articles_empty_collection(self, mock_make_client):
        """Test extract_articles handles empty collection."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_make_client.return_value = mock_client

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

    def test_print_statistics_empty_dataset(self, capsys):
        """Test print_statistics handles empty dataset without crashing."""
        from src.evaluation.extract_ground_truth import print_statistics

        print_statistics({})

        captured = capsys.readouterr()
        assert "Total articles: 0" in captured.out
        assert "No articles to analyze" in captured.out


class TestMain:
    """Tests for main function."""

    @patch("src.evaluation.extract_ground_truth.extract_articles")
    @patch("src.evaluation.extract_ground_truth.print_statistics")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    def test_main_extracts_and_saves(self, mock_makedirs, mock_file, mock_stats, mock_extract):
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
        assert any("ground_truth_articles.json" in p for p in opened_paths)
        assert any("article_to_chunk_mapping.json" in p for p in opened_paths)
        # Verify no hardcoded /home/admin paths
        assert all("/home/admin" not in p for p in opened_paths)

    @patch("src.evaluation.extract_ground_truth.extract_articles")
    @patch("src.evaluation.extract_ground_truth.print_statistics")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    def test_main_creates_simplified_mapping(
        self, mock_makedirs, mock_file, mock_stats, mock_extract
    ):
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
    @patch("os.makedirs")
    def test_main_prints_completion_message(
        self, mock_makedirs, mock_file, mock_stats, mock_extract, capsys
    ):
        """Test main prints completion message."""
        mock_extract.return_value = {"121": [{"point_id": "p1"}]}

        from src.evaluation.extract_ground_truth import main

        main()

        captured = capsys.readouterr()
        assert "Ground truth extraction completed" in captured.out

    @patch("src.evaluation.extract_ground_truth.extract_articles")
    @patch("src.evaluation.extract_ground_truth.print_statistics")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    def test_main_uses_correct_collection(self, mock_makedirs, mock_file, mock_stats, mock_extract):
        """Test main uses correct collection name."""
        mock_extract.return_value = {}

        from src.evaluation.extract_ground_truth import main

        main()

        mock_extract.assert_called_once_with("ukraine_criminal_code_zai_full")
