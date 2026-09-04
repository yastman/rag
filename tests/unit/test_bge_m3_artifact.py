"""Artifact contract tests for the pinned BGE-M3 ONNX artifact (#3366).

Verifies that ``services/bge-m3-api/verify_artifact.py`` rejects dummy 41-byte
fixtures, missing files/external-data shards/tokenizer assets, and size or
SHA-256 mismatches BEFORE any model load, and that the committed
``artifact_manifest.json`` records the full immutable provenance required by
#3366 (source repo/revision, license, tokenizer pairing, ONNX I/O, opset).

All tests are stdlib-only and offline (no network, no onnxruntime).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_REPO_ROOT = Path(__file__).parents[2]
_SERVICE_DIR = _REPO_ROOT / "services" / "bge-m3-api"
_MANIFEST_PATH = _SERVICE_DIR / "artifact_manifest.json"

sys.path.insert(0, str(_SERVICE_DIR))

from fetch_artifact import DEFAULT_DEST, MANIFEST_PATH, build_url
from verify_artifact import ArtifactIntegrityError, load_manifest, verify_artifact_dir


DUMMY_CONTENT = b"placeholder for compose build gate only"  # the 41-byte tracked dummy


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(name: str, data: bytes, role: str = "model") -> dict:
    return {"name": name, "role": role, "bytes": len(data), "sha256": _sha256(data)}


@pytest.fixture()
def synthetic_artifact(tmp_path: Path) -> Path:
    """A tiny self-consistent artifact dir (fake model bytes, real manifest)."""
    model = b"fake-onnx-graph"
    shard = b"fake-external-data-shard"
    tok_json = b'{"tokenizer": true}'
    tok_cfg = b"{}"
    spm = b"fake-sentencepiece"
    mapping = {"model.onnx": (model, "model"), "model.onnx_data": (shard, "external_data")}
    mapping.update(
        {
            "tokenizer/tokenizer.json": (tok_json, "tokenizer"),
            "tokenizer/tokenizer_config.json": (tok_cfg, "tokenizer"),
            "tokenizer/special_tokens_map.json": (b"{}", "tokenizer"),
            "tokenizer/sentencepiece.bpe.model": (spm, "tokenizer"),
        }
    )
    manifest = {
        "schema_version": 1,
        "artifact": {"outputs": ["dense_vecs", "sparse_vecs", "colbert_vecs"]},
        "source": {"repo_id": "test/repo", "revision": "a" * 40, "license": "MIT"},
        "upstream_model": {"repo_id": "BAAI/bge-m3", "revision": "b" * 40},
        "files": [_entry(name, data, role) for name, (data, role) in mapping.items()],
    }
    for name, (data, _role) in mapping.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (tmp_path / "artifact_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


# ── Dummy 41-byte tracked fixtures must be rejected ────────────────────────────


def test_dummy_fixture_dir_rejected() -> None:
    """The tracked 41-byte fixture dir has no manifest and must fail verification."""
    fixtures = _REPO_ROOT / "tests" / "fixtures" / "bge_m3_onnx_model"
    dummy_files = [p for p in fixtures.iterdir() if p.is_file() and p.stat().st_size == 41]
    assert len(dummy_files) >= 2, "tracked 41-byte dummy fixtures must remain present"
    contents = {p.read_bytes() for p in dummy_files}
    assert len(contents) == 1, "all dummy fixtures must carry identical placeholder bytes"
    assert b"placeholder" in contents.pop()
    with pytest.raises(FileNotFoundError, match=r"artifact_manifest\.json"):
        verify_artifact_dir(fixtures)


def test_dummy_content_never_matches_manifest(synthetic_artifact: Path) -> None:
    """Same-size wrong bytes are a hash mismatch, never a pass."""
    model_path = synthetic_artifact / "model.onnx"
    model_path.write_bytes(b"X" * len(b"fake-onnx-graph"))  # same size, different content
    with pytest.raises(ArtifactIntegrityError, match="sha256 mismatch"):
        verify_artifact_dir(synthetic_artifact)


# ── Positive control ───────────────────────────────────────────────────────────


def test_consistent_artifact_verifies(synthetic_artifact: Path) -> None:
    manifest = verify_artifact_dir(synthetic_artifact)
    assert manifest["source"]["repo_id"] == "test/repo"


# ── Missing pieces must fail before inference ──────────────────────────────────


def test_missing_model_file_rejected(synthetic_artifact: Path) -> None:
    (synthetic_artifact / "model.onnx").unlink()
    with pytest.raises(FileNotFoundError, match=r"model\.onnx"):
        verify_artifact_dir(synthetic_artifact)


def test_missing_external_data_shard_rejected(synthetic_artifact: Path) -> None:
    (synthetic_artifact / "model.onnx_data").unlink()
    with pytest.raises(FileNotFoundError, match=r"model\.onnx_data"):
        verify_artifact_dir(synthetic_artifact)


def test_missing_tokenizer_asset_rejected(synthetic_artifact: Path) -> None:
    (synthetic_artifact / "tokenizer" / "tokenizer.json").unlink()
    with pytest.raises(FileNotFoundError, match=r"tokenizer\.json"):
        verify_artifact_dir(synthetic_artifact)


def test_hash_mismatch_rejected(synthetic_artifact: Path) -> None:
    (synthetic_artifact / "model.onnx_data").write_bytes(
        b"C" * len(b"fake-external-data-shard")  # same size, different content
    )
    with pytest.raises(ArtifactIntegrityError, match=r"sha256 mismatch.*model\.onnx_data"):
        verify_artifact_dir(synthetic_artifact)


def test_size_mismatch_rejected(synthetic_artifact: Path) -> None:
    (synthetic_artifact / "model.onnx").write_bytes(
        b"fake-onnx-graph!"
    )  # same hash family, new size
    with pytest.raises(ArtifactIntegrityError, match="byte size mismatch"):
        verify_artifact_dir(synthetic_artifact)


# ── Manifest schema gates ──────────────────────────────────────────────────────


def test_manifest_missing_files_section_rejected(synthetic_artifact: Path) -> None:
    bad = json.loads((synthetic_artifact / "artifact_manifest.json").read_text(encoding="utf-8"))
    del bad["files"]
    (synthetic_artifact / "artifact_manifest.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="files"):
        verify_artifact_dir(synthetic_artifact)


def test_manifest_missing_required_file_entry_rejected(synthetic_artifact: Path) -> None:
    bad = json.loads((synthetic_artifact / "artifact_manifest.json").read_text(encoding="utf-8"))
    bad["files"] = [e for e in bad["files"] if e["name"] != "model.onnx_data"]
    (synthetic_artifact / "artifact_manifest.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match=r"incomplete.*external_data"):
        verify_artifact_dir(synthetic_artifact)


# ── The committed manifest must pin full immutable provenance (#3366) ──────────


@pytest.fixture(scope="module")
def real_manifest() -> dict:
    return load_manifest(_MANIFEST_PATH)


class TestCommittedManifest:
    def test_source_revision_is_immutable_40hex(self, real_manifest: dict) -> None:
        rev = real_manifest["source"]["revision"]
        assert isinstance(rev, str) and len(rev) == 40
        int(rev, 16)

    def test_license_recorded_mit(self, real_manifest: dict) -> None:
        assert real_manifest["source"]["license"] == "MIT"

    def test_upstream_model_pinned(self, real_manifest: dict) -> None:
        upstream = real_manifest["upstream_model"]
        assert upstream["repo_id"] == "BAAI/bge-m3"
        assert upstream["revision"] == "5617a9f61b028005a4858fdac845db406aefb181"

    def test_onnx_contract_all_three_outputs(self, real_manifest: dict) -> None:
        onnx = real_manifest["artifact"]
        assert onnx["inputs"] == ["input_ids", "attention_mask"]
        assert onnx["outputs"] == ["dense_vecs", "sparse_vecs", "colbert_vecs"]
        assert isinstance(onnx["opset"], int) and onnx["opset"] >= 13

    def test_all_files_have_role_bytes_sha256(self, real_manifest: dict) -> None:
        roles = {f["name"]: f["role"] for f in real_manifest["files"]}
        assert roles["model.onnx"] == "model"
        assert roles["model.onnx_data"] == "external_data"
        tokenizer_files = [n for n, r in roles.items() if r == "tokenizer"]
        assert len(tokenizer_files) >= 4
        for entry in real_manifest["files"]:
            assert len(entry["sha256"]) == 64
            int(entry["sha256"], 16)
            assert entry["bytes"] > 0

    def test_manifest_consistent_with_service_dir(self, real_manifest: dict) -> None:
        """Every manifest entry verifies against the artifact next to the service
        when the artifact is fetched; here we only check the model entry sizes are
        the inspected HF values (regression lock against accidental manifest edits)."""
        by_name = {f["name"]: f for f in real_manifest["files"]}
        assert by_name["model.onnx"]["bytes"] == 521736
        assert by_name["model.onnx_data"]["bytes"] == 6813265968

    def test_load_manifest_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "absent.json")


class TestFetchCommand:
    """Pure (offline) gates for the reproducible fetch entry point."""

    def test_build_url_pins_immutable_revision(self, real_manifest: dict) -> None:
        url = build_url(real_manifest["source"], "model.onnx_data")
        assert url == (
            "https://huggingface.co/philipchung/bge-m3-onnx/resolve/"
            "92465a6ca57117003d558c98578592456005d5ca/model.onnx_data"
        )

    def test_default_dest_is_repo_relative_cache(self) -> None:
        assert str(DEFAULT_DEST).replace("\\", "/") == "logs/bge_m3_onnx_int8"

    def test_manifest_lives_next_to_service_code(self) -> None:
        assert MANIFEST_PATH.name == "artifact_manifest.json"
        assert MANIFEST_PATH.parent.name == "bge-m3-api"

    def test_app_never_imports_fetch_tool(self) -> None:
        """The runtime app must contain no download path (#3366 non-goal)."""
        app_source = (_SERVICE_DIR / "app.py").read_text(encoding="utf-8")
        assert "fetch_artifact" not in app_source
        assert "urllib.request" not in app_source
        assert "huggingface.co" not in app_source


# ── Offline runtime loading (get_model) ────────────────────────────────────────


def _import_app_with_contract_session():
    """Import the service app with heavy deps mocked and an ORT session mock
    whose I/O names match the artifact contract. Returns (app_module, mocks)."""
    import importlib.util
    from unittest.mock import MagicMock

    if importlib.util.find_spec("fastapi") is None:
        pytest.skip("fastapi not installed — run via the bge-extras lane")

    with pytest.MonkeyPatch.context() as mp:
        mock_ort = MagicMock()
        mock_ort.SessionOptions = MagicMock()
        mock_ort.GraphOptimizationLevel.ORT_ENABLE_ALL = 1
        mock_session = MagicMock()

        def _named(name: str) -> MagicMock:
            mock = MagicMock()
            mock.name = name
            return mock

        output_names = ("dense_vecs", "sparse_vecs", "colbert_vecs")
        mock_session.get_outputs.return_value = [_named(n) for n in output_names]
        mock_session.get_inputs.return_value = [_named(n) for n in ("input_ids", "attention_mask")]
        mock_ort.InferenceSession = MagicMock(return_value=mock_session)

        mock_transformers = MagicMock()
        mock_prom = MagicMock()
        for attr in ("Counter", "Gauge", "Histogram"):
            setattr(mock_prom, attr, MagicMock(return_value=MagicMock()))
        mock_prom.make_asgi_app = MagicMock(return_value=MagicMock())

        mp.setitem(sys.modules, "onnxruntime", mock_ort)
        mp.setitem(sys.modules, "transformers", mock_transformers)
        mp.setitem(sys.modules, "prometheus_client", mock_prom)
        mp.syspath_prepend(str(_SERVICE_DIR))
        sys.modules.pop("app", None)
        sys.modules.pop("config", None)
        import app as app_module

    return app_module, {"onnxruntime": mock_ort, "transformers": mock_transformers}


@pytest.fixture()
def offline_app_env(synthetic_artifact, monkeypatch):
    """Point a freshly imported app module at the synthetic verified artifact."""
    app_module, mocks = _import_app_with_contract_session()
    app_module._onnx_session = None
    app_module._tokenizer = None
    settings = MagicMock()
    settings.ONNX_MODEL_DIR = str(synthetic_artifact)
    settings.ARTIFACT_MANIFEST_NAME = "artifact_manifest.json"
    settings.ONNX_MODEL_FILENAME = "model.onnx"
    settings.NUM_THREADS = 1
    settings.TOKENIZER_DIR = str(synthetic_artifact / "tokenizer")
    app_module.settings = settings
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    yield app_module, mocks
    sys.modules.pop("app", None)
    sys.modules.pop("config", None)


@pytest.mark.no_services
def test_get_model_loads_tokenizer_local_only(offline_app_env) -> None:
    """Tokenizer must load from the baked local dir, local-only, no hub fallback."""
    import os

    app_module, mocks = offline_app_env

    model = app_module.get_model()

    call = mocks["transformers"].AutoTokenizer.from_pretrained.call_args
    assert call is not None, "tokenizer must be loaded via AutoTokenizer.from_pretrained"
    args, kwargs = call
    assert args == (app_module.settings.TOKENIZER_DIR,)
    assert kwargs.get("local_files_only") is True
    assert "revision" not in kwargs, "revision implies hub resolution — must not be used"
    assert "cache_dir" not in kwargs
    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"
    assert isinstance(model, app_module.ONNXEmbeddingModel)


@pytest.mark.no_services
def test_get_model_verifies_artifact_before_session(offline_app_env) -> None:
    """A hash-mismatched artifact must fail before InferenceSession is created."""
    from pathlib import Path

    from verify_artifact import ArtifactIntegrityError

    app_module, mocks = offline_app_env
    artifact_dir = Path(app_module.settings.ONNX_MODEL_DIR)
    (artifact_dir / "model.onnx").write_bytes(b"X" * len(b"fake-onnx-graph"))

    with pytest.raises(ArtifactIntegrityError):
        app_module.get_model()

    mocks["onnxruntime"].InferenceSession.assert_not_called()
