"""Tests for services.yaml indexing script."""

import uuid


# ---------------------------------------------------------------------------
# Test: parsing services config
# ---------------------------------------------------------------------------


def test_extract_service_documents_returns_docs_with_card_text() -> None:
    """extract_service_documents returns docs for services that have card_text."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "vnzh": {"title": "ВНЖ", "card_text": "ВНЖ в Болгарии..."},
            "installment": {"title": "Рассрочка", "card_text": "Рассрочка от застройщика..."},
            "no_card": {"title": "Empty"},
        }
    }

    docs = extract_service_documents(config)

    assert len(docs) == 2
    keys = {d["service_key"] for d in docs}
    assert keys == {"vnzh", "installment"}


def test_extract_service_documents_text_combines_title_and_card_text() -> None:
    """Document text is title + newlines + card_text."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "vnzh": {"title": "ВНЖ", "card_text": "ВНЖ в Болгарии..."},
        }
    }

    docs = extract_service_documents(config)

    assert docs[0]["text"] == "ВНЖ\n\nВНЖ в Болгарии..."


def test_extract_service_documents_metadata() -> None:
    """Each document has source, service_key, title metadata."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "infotour": {"title": "Инфотур", "card_text": "Тур по Болгарии"},
        }
    }

    docs = extract_service_documents(config)
    doc = docs[0]

    assert doc["metadata"]["source"] == "services.yaml"
    assert doc["metadata"]["service_key"] == "infotour"
    assert doc["metadata"]["title"] == "Инфотур"


def test_extract_service_documents_skips_missing_card_text() -> None:
    """Services without card_text are not included."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "only_title": {"title": "No card"},
            "empty_card": {"title": "Empty", "card_text": ""},
        }
    }

    docs = extract_service_documents(config)

    assert docs == []


def test_extract_service_documents_empty_services() -> None:
    """Empty or missing services section returns empty list."""
    from scripts.index_services import extract_service_documents

    assert extract_service_documents({}) == []
    assert extract_service_documents({"services": {}}) == []


# ---------------------------------------------------------------------------
# Test: deterministic UUID
# ---------------------------------------------------------------------------


def test_deterministic_uuid_stable_for_same_key() -> None:
    """point_id is the same across multiple calls for the same service_key."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "vnzh": {"title": "ВНЖ", "card_text": "ВНЖ в Болгарии..."},
        }
    }

    docs1 = extract_service_documents(config)
    docs2 = extract_service_documents(config)

    assert docs1[0]["point_id"] == docs2[0]["point_id"]


def test_deterministic_uuid_matches_expected_value() -> None:
    """point_id equals uuid5(NAMESPACE_URL, 'services.yaml:vnzh')."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "vnzh": {"title": "ВНЖ", "card_text": "ВНЖ в Болгарии..."},
        }
    }

    docs = extract_service_documents(config)
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, "services.yaml:vnzh"))

    assert docs[0]["point_id"] == expected


def test_deterministic_uuid_different_for_different_keys() -> None:
    """Different service_key produces different point_id."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "vnzh": {"title": "ВНЖ", "card_text": "text1"},
            "installment": {"title": "Рассрочка", "card_text": "text2"},
        }
    }

    docs = extract_service_documents(config)
    ids = [d["point_id"] for d in docs]

    assert len(set(ids)) == 2


# ---------------------------------------------------------------------------
# Test: idempotent upsert (same point_id = no duplicates)
# ---------------------------------------------------------------------------


def test_idempotent_upsert_same_point_id() -> None:
    """Two calls with same service produce the same point_id — upsert is idempotent."""
    from scripts.index_services import extract_service_documents

    config = {
        "services": {
            "vnzh": {"title": "ВНЖ", "card_text": "ВНЖ в Болгарии..."},
        }
    }

    docs_first = extract_service_documents(config)
    docs_second = extract_service_documents(config)

    assert docs_first[0]["point_id"] == docs_second[0]["point_id"]
