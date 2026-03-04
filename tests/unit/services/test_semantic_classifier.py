"""Unit tests for SemanticClassifier."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.services.semantic_classifier import SemanticClassifier


class TestSemanticClassifierInit:
    """Tests for SemanticClassifier initialization."""

    def test_available_when_router_succeeds(self):
        mock_router = MagicMock()
        with patch(
            "telegram_bot.services.semantic_classifier.SemanticClassifier.__init__",
            wraps=None,
        ):
            classifier = SemanticClassifier.__new__(SemanticClassifier)
            classifier._available = True
            classifier._router = mock_router
            assert classifier.available is True

    def test_unavailable_when_redis_fails(self):
        with patch(
            "telegram_bot.services.semantic_classifier.SemanticRouter",
            side_effect=ConnectionError("Redis unavailable"),
            create=True,
        ):
            with patch.dict(
                "sys.modules",
                {
                    "redisvl.extensions.router": MagicMock(
                        Route=MagicMock(),
                        SemanticRouter=MagicMock(side_effect=ConnectionError("Redis unavailable")),
                    )
                },
            ):
                classifier = SemanticClassifier(redis_url="redis://invalid:9999")
                assert classifier.available is False

    def test_init_uses_overwrite_true(self):
        mock_route = MagicMock()
        mock_router_cls = MagicMock()
        fake_module = MagicMock(Route=mock_route, SemanticRouter=mock_router_cls)

        with patch.dict("sys.modules", {"redisvl.extensions.router": fake_module}):
            SemanticClassifier(redis_url="redis://localhost:6379")

        assert mock_router_cls.call_args.kwargs["overwrite"] is True

    def test_available_false_by_default_on_import_error(self):
        with patch.dict("sys.modules", {"redisvl": None, "redisvl.extensions.router": None}):
            classifier = SemanticClassifier.__new__(SemanticClassifier)
            classifier._available = False
            classifier._router = None
            assert classifier.available is False


class TestSemanticClassifierClassify:
    """Tests for SemanticClassifier.classify() method."""

    def _make_classifier(self, route_name: str | None) -> SemanticClassifier:
        """Create a classifier with a mocked router that returns given route."""
        classifier = SemanticClassifier.__new__(SemanticClassifier)
        mock_router = MagicMock()
        mock_match = MagicMock()
        mock_match.name = route_name
        mock_router.return_value = mock_match
        classifier._router = mock_router
        classifier._available = True
        return classifier

    def test_classify_returns_faq(self):
        classifier = self._make_classifier("FAQ")
        assert classifier.classify("как оформить покупку") == "FAQ"

    def test_classify_returns_chitchat(self):
        classifier = self._make_classifier("CHITCHAT")
        assert classifier.classify("привет") == "CHITCHAT"

    def test_classify_returns_off_topic(self):
        classifier = self._make_classifier("OFF_TOPIC")
        assert classifier.classify("рецепт борща") == "OFF_TOPIC"

    def test_classify_returns_structured(self):
        classifier = self._make_classifier("STRUCTURED")
        assert classifier.classify("2 комнаты до 80000 евро") == "STRUCTURED"

    def test_classify_returns_entity(self):
        classifier = self._make_classifier("ENTITY")
        assert classifier.classify("квартира в Несебре") == "ENTITY"

    def test_classify_returns_general_when_no_match(self):
        classifier = self._make_classifier(None)
        assert classifier.classify("уютная квартира с видом на море") == "GENERAL"

    def test_classify_returns_general_when_match_name_is_none(self):
        classifier = SemanticClassifier.__new__(SemanticClassifier)
        mock_router = MagicMock()
        mock_match = MagicMock()
        mock_match.name = None
        mock_router.return_value = mock_match
        classifier._router = mock_router
        classifier._available = True
        assert classifier.classify("неопределённый запрос") == "GENERAL"

    def test_classify_raises_when_unavailable(self):
        classifier = SemanticClassifier.__new__(SemanticClassifier)
        classifier._available = False
        classifier._router = None
        with pytest.raises(RuntimeError, match="SemanticClassifier not available"):
            classifier.classify("любой запрос")

    def test_classify_passes_query_to_router(self):
        classifier = self._make_classifier("FAQ")
        query = "как оформить покупку"
        classifier.classify(query)
        classifier._router.assert_called_once_with(query)


class TestSemanticClassifierRouteConfig:
    """Tests for route configuration (references count)."""

    def test_has_reference_lists_populated(self):
        from telegram_bot.services.semantic_classifier import (
            _CHITCHAT_REFERENCES,
            _ENTITY_REFERENCES,
            _FAQ_REFERENCES,
            _OFF_TOPIC_REFERENCES,
            _STRUCTURED_REFERENCES,
        )

        assert len(_FAQ_REFERENCES) >= 5
        assert len(_CHITCHAT_REFERENCES) >= 5
        assert len(_OFF_TOPIC_REFERENCES) >= 5
        assert len(_STRUCTURED_REFERENCES) >= 5
        assert len(_ENTITY_REFERENCES) >= 5

    def test_all_references_are_strings(self):
        from telegram_bot.services.semantic_classifier import (
            _CHITCHAT_REFERENCES,
            _ENTITY_REFERENCES,
            _FAQ_REFERENCES,
            _OFF_TOPIC_REFERENCES,
            _STRUCTURED_REFERENCES,
        )

        for ref_list in [
            _FAQ_REFERENCES,
            _CHITCHAT_REFERENCES,
            _OFF_TOPIC_REFERENCES,
            _STRUCTURED_REFERENCES,
            _ENTITY_REFERENCES,
        ]:
            assert all(isinstance(r, str) for r in ref_list)
