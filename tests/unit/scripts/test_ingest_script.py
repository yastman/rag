"""Regression guard: scripts/apartments/ingest.py must use encode_hybrid."""

from unittest import mock

from telegram_bot.services.bge_m3_client import HybridResult


class TestLegacyIngestUsesHybrid:
    """Regression guard: ingest() must call encode_hybrid, not 3 separate calls."""

    def test_ingest_uses_encode_hybrid_not_separate_calls(self, tmp_path):
        """ingest() calls bge.encode_hybrid once per batch, never encode_dense/sparse/colbert."""
        csv = tmp_path / "apts.csv"
        csv.write_text(
            "complex_name,city,section,apartment_number,rooms,floor_label,"
            "area_m2,view_raw,price_eur,price_bgn,is_furnished,"
            "has_floor_plan,has_photo,is_promotion,old_price_eur\n"
            "TestComplex,TestCity,A-1,101,2,3,75.0,sea,100000.00,195000.00,"
            "False,False,False,False,\n"
        )

        mock_hybrid_result = HybridResult(
            dense_vecs=[[0.1] * 1024],
            lexical_weights=[{"indices": [1, 2], "values": [0.5, 0.3]}],
            colbert_vecs=[[[0.1] * 1024] * 5],
        )

        with (
            mock.patch("scripts.apartments.ingest.BGEM3SyncClient") as MockBGE,
            mock.patch("scripts.apartments.ingest.QdrantClient") as MockQdrant,
        ):
            mock_bge = MockBGE.return_value
            mock_bge.encode_hybrid.return_value = mock_hybrid_result
            mock_bge.encode_dense = mock.MagicMock()
            mock_bge.encode_sparse = mock.MagicMock()
            mock_bge.encode_colbert = mock.MagicMock()

            mock_qdrant = MockQdrant.return_value
            mock_qdrant.upsert.return_value = None

            from scripts.apartments.ingest import ingest

            ingest(
                csv_path=str(csv),
                qdrant_url="http://localhost:6333",
                bge_url="http://localhost:8000",
            )

            mock_bge.encode_hybrid.assert_called_once()
            mock_bge.encode_dense.assert_not_called()
            mock_bge.encode_sparse.assert_not_called()
            mock_bge.encode_colbert.assert_not_called()
