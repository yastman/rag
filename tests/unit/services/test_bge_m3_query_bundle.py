from telegram_bot.services.bge_m3_query_bundle import (
    BGE_M3_QUERY_BUNDLE_VERSION,
    BgeM3QueryVectorBundle,
    make_bge_m3_query_bundle_key_material,
)


def test_bundle_round_trips_json_dict() -> None:
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1, 0.2],
        sparse={"indices": [1, 2], "values": [0.3, 0.4]},
        colbert=[[0.5, 0.6], [0.7, 0.8]],
        model="BAAI/bge-m3",
        max_length=512,
        version=BGE_M3_QUERY_BUNDLE_VERSION,
    )

    parsed = BgeM3QueryVectorBundle.from_json_dict(bundle.to_json_dict())

    assert parsed == bundle
    assert parsed.is_complete()


def test_bundle_rejects_missing_colbert() -> None:
    payload = {
        "dense": [0.1],
        "sparse": {"indices": [1], "values": [0.2]},
        "colbert": [],
        "model": "BAAI/bge-m3",
        "max_length": 512,
        "version": BGE_M3_QUERY_BUNDLE_VERSION,
    }

    parsed = BgeM3QueryVectorBundle.from_json_dict(payload)

    assert parsed is None


def test_bundle_rejects_non_dict() -> None:
    assert BgeM3QueryVectorBundle.from_json_dict("not a dict") is None
    assert BgeM3QueryVectorBundle.from_json_dict(None) is None
    assert BgeM3QueryVectorBundle.from_json_dict(42) is None


def test_bundle_rejects_missing_sparse_fields() -> None:
    payload = {
        "dense": [0.1],
        "sparse": {"indices": [1]},
        "colbert": [[0.5]],
    }
    assert BgeM3QueryVectorBundle.from_json_dict(payload) is None


def test_bundle_rejects_empty_dense() -> None:
    payload = {
        "dense": [],
        "sparse": {"indices": [1], "values": [0.2]},
        "colbert": [[0.5]],
    }
    assert BgeM3QueryVectorBundle.from_json_dict(payload) is None


def test_bundle_uses_defaults_for_optional_fields() -> None:
    payload = {
        "dense": [0.1],
        "sparse": {"indices": [1], "values": [0.2]},
        "colbert": [[0.5]],
    }
    parsed = BgeM3QueryVectorBundle.from_json_dict(payload)
    assert parsed is not None
    assert parsed.model == "BAAI/bge-m3"
    assert parsed.max_length == 512
    assert parsed.version == "v1"


def test_key_material_normalizes_query_and_includes_model_contract() -> None:
    a = make_bge_m3_query_bundle_key_material("ВНЖ?", model="BAAI/bge-m3", max_length=512)
    b = make_bge_m3_query_bundle_key_material("  внж  ", model="BAAI/bge-m3", max_length=512)
    c = make_bge_m3_query_bundle_key_material("внж", model="other", max_length=512)

    assert a == b
    assert a != c
    assert "BAAI/bge-m3" in a


def test_key_material_includes_version_and_max_length() -> None:
    material = make_bge_m3_query_bundle_key_material("hello", model="BAAI/bge-m3", max_length=512)
    assert "v1" in material
    assert "512" in material
    assert "hello" in material
