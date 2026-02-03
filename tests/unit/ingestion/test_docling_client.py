"""Tests for Docling-serve HTTP client helpers."""


def test_build_chunking_form_data_omits_invalid_tokenizer_word():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig(tokenizer="word"))
    data = client._build_chunking_form_data()

    assert "chunking_tokenizer" not in data


def test_build_chunking_form_data_omits_invalid_tokenizer_huggingface():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig(tokenizer="huggingface"))
    data = client._build_chunking_form_data()

    assert "chunking_tokenizer" not in data


def test_build_chunking_form_data_includes_hf_model_id():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig(tokenizer="sentence-transformers/all-MiniLM-L6-v2"))
    data = client._build_chunking_form_data()

    assert data["chunking_tokenizer"] == "sentence-transformers/all-MiniLM-L6-v2"


def test_parse_page_range_prefers_page_numbers():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig())
    raw_chunk = {"page_numbers": [3, 4, 5], "metadata": {"origin": {"filename": "x.pdf"}}}

    assert client._parse_page_range_from_chunk(raw_chunk) == (3, 5)


def test_parse_page_range_falls_back_to_meta():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig())
    raw_chunk = {"meta": {"page": 7}}

    assert client._parse_page_range_from_chunk(raw_chunk) == (7, 7)
