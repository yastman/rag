"""Shared sample data fixtures."""

import pytest


@pytest.fixture(scope="session")
def sample_context_chunks():
    """Sample context chunks for LLM tests (read-only, session-scoped)."""
    return [
        {
            "text": "Квартира в Солнечном берегу, 2 комнаты, 65 м².",
            "metadata": {"title": "Апартамент у моря", "city": "Солнечный берег", "price": 75000},
            "score": 0.92,
        },
        {
            "text": "Студия в Несебре, первая линия, 35 м².",
            "metadata": {"title": "Студия на первой линии", "city": "Несебр", "price": 45000},
            "score": 0.87,
        },
    ]


@pytest.fixture(scope="session")
def sample_texts():
    """Sample texts for embedding tests (read-only, session-scoped)."""
    return [
        "Кримінальний кодекс України визначає злочини та покарання.",
        "Стаття 115 передбачає відповідальність за умисне вбивство.",
        "Крадіжка є таємним викраденням чужого майна.",
    ]


@pytest.fixture(scope="session")
def sample_query():
    """Sample query for search tests (read-only, session-scoped)."""
    return "Яке покарання за крадіжку?"
