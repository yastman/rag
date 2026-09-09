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
from verify_artifact import (
    ArtifactIntegrityError,
    load_manifest,
    validate_pin_contract,
    verify_artifact_dir,
    verify_pinned_artifact,
)


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


# ── Tiny tracked dummy fixtures must be rejected ───────────────────────────────


def test_dummy_fixture_dir_rejected() -> None:
    """The tracked tiny fixture dir has no manifest and must fail verification."""
    fixtures = _REPO_ROOT / "tests" / "fixtures" / "bge_m3_onnx_model"
    dummy_files = [
        p
        for p in fixtures.iterdir()
        if p.is_file() and p.name != "README.md" and p.stat().st_size < 1024
    ]
    assert len(dummy_files) >= 2, "tracked tiny dummy fixtures must remain present"
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

    def test_tokenizer_urls_use_manifest_remote_paths(self, real_manifest: dict) -> None:
        """The upstream repo stores tokenizer files at its root while the
        artifact layout nests them under tokenizer/; manifest entries must
        carry the remote path the fetcher resolves (#3366 real-fetch fix)."""
        for entry in real_manifest["files"]:
            url = build_url(real_manifest["source"], entry.get("remote", entry["name"]))
            if entry["name"].startswith("tokenizer/"):
                assert f"/{entry['remote']}" in url, (
                    f"{entry['name']} must fetch from its recorded remote path"
                )
                assert "/tokenizer/tokenizer" not in url, (
                    "the upstream repo has no tokenizer/ subfolder at the pinned revision"
                )

    def test_real_manifest_records_remote_for_nested_files(self, real_manifest: dict) -> None:
        nested = [e for e in real_manifest["files"] if "/" in e["name"]]
        assert nested, "manifest nests tokenizer assets under tokenizer/"
        for entry in nested:
            assert "remote" in entry, f"{entry['name']} must record its remote upstream path"


class TestFetchVerifiesAgainstRepositoryPin:
    """The fetcher's final verification must be anchored to the repository
    pin manifest, not to the manifest copy sitting in the download folder
    (#3366 audit blocker)."""

    @staticmethod
    def _tiny_pin(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
        mapping = {
            "model.onnx": (b"fake-onnx-graph", "model"),
            "model.onnx_data": (b"fake-external-data-shard", "external_data"),
            "tokenizer/tokenizer.json": (b'{"tokenizer": true}', "tokenizer"),
            "tokenizer/tokenizer_config.json": (b"{}", "tokenizer"),
            "tokenizer/special_tokens_map.json": (b"{}", "tokenizer"),
            "tokenizer/sentencepiece.bpe.model": (b"fake-sentencepiece", "tokenizer"),
        }
        manifest = {
            "schema_version": 1,
            "artifact": {"outputs": ["dense_vecs", "sparse_vecs", "colbert_vecs"], "opset": 17},
            "source": {
                "kind": "huggingface",
                "repo_id": "test/repo",
                "revision": "a" * 40,
                "license": "MIT",
            },
            "upstream_model": {"repo_id": "BAAI/bge-m3", "revision": "b" * 40},
            "files": [_entry(name, data, role) for name, (data, role) in mapping.items()],
        }
        pin = tmp_path / "repository_pin.json"
        pin.write_text(json.dumps(manifest), encoding="utf-8")
        return pin, {name: data for name, (data, _role) in mapping.items()}

    def test_fetch_success_and_baked_manifest_is_the_pin(self, tmp_path, monkeypatch) -> None:
        import fetch_artifact as fetch_module

        pin, contents = self._tiny_pin(tmp_path)
        dest = tmp_path / "artifact"

        def fake_download(url: str, target) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents[target.relative_to(dest).as_posix()])

        monkeypatch.setattr(fetch_module, "_download", fake_download)
        assert fetch_module.fetch_artifact(dest, pin) == dest
        assert (dest / "artifact_manifest.json").read_text(encoding="utf-8") == pin.read_text(
            encoding="utf-8"
        )

    def test_fetch_rejects_folder_manifest_swapped_during_download(
        self, tmp_path, monkeypatch
    ) -> None:
        """Bytes matching the pin plus a re-signed folder manifest must fail:
        the folder manifest is input to compare, not authority."""
        import fetch_artifact as fetch_module
        from verify_artifact import ArtifactIntegrityError

        pin, contents = self._tiny_pin(tmp_path)
        pin_manifest = json.loads(pin.read_text(encoding="utf-8"))
        last_name = pin_manifest["files"][-1]["name"]
        dest = tmp_path / "artifact"

        def fake_download(url: str, target) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents[target.relative_to(dest).as_posix()])
            if target.relative_to(dest).as_posix() == last_name:
                tampered = json.loads(pin.read_text(encoding="utf-8"))
                tampered["source"]["revision"] = "c" * 40
                (dest / fetch_module.ARTIFACT_MANIFEST_NAME).write_text(
                    json.dumps(tampered), encoding="utf-8"
                )

        monkeypatch.setattr(fetch_module, "_download", fake_download)
        with pytest.raises(ArtifactIntegrityError, match="repository pin"):
            fetch_module.fetch_artifact(dest, pin)

    def test_fetch_fails_when_bytes_diverge_from_pin(self, tmp_path, monkeypatch) -> None:
        import fetch_artifact as fetch_module
        from verify_artifact import ArtifactIntegrityError

        pin, contents = self._tiny_pin(tmp_path)
        dest = tmp_path / "artifact"

        def lying_download(url: str, target) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"C" * len(contents[target.relative_to(dest).as_posix()]))

        monkeypatch.setattr(fetch_module, "_download", lying_download)
        with pytest.raises(ArtifactIntegrityError, match="sha256 mismatch"):
            fetch_module.fetch_artifact(dest, pin)

    def test_fetch_skips_completed_files_but_still_verifies_them(
        self, tmp_path, monkeypatch
    ) -> None:
        """An interrupted earlier fetch must not re-download completed files,
        and skipping must not bypass hash verification."""
        import fetch_artifact as fetch_module
        from verify_artifact import ArtifactIntegrityError

        pin, contents = self._tiny_pin(tmp_path)
        dest = tmp_path / "artifact"
        dest.mkdir(parents=True, exist_ok=True)
        completed = dest / "model.onnx"
        completed.write_bytes(b"X" * len(contents["model.onnx"]))  # right size, wrong bytes

        def fake_download(url: str, target) -> None:
            rel = target.relative_to(dest).as_posix()
            assert rel != "model.onnx", "completed file must not re-download"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents[rel])

        monkeypatch.setattr(fetch_module, "_download", fake_download)
        with pytest.raises(ArtifactIntegrityError, match=r"sha256 mismatch.*model\.onnx"):
            fetch_module.fetch_artifact(dest, pin)

    def test_fetch_resume_completes_partial_download(self, tmp_path, monkeypatch) -> None:
        import fetch_artifact as fetch_module

        pin, contents = self._tiny_pin(tmp_path)
        dest = tmp_path / "artifact"
        dest.mkdir(parents=True, exist_ok=True)
        completed = dest / "model.onnx"
        completed.write_bytes(contents["model.onnx"])  # correct bytes from an earlier run

        downloaded: list[str] = []

        def fake_download(url: str, target) -> None:
            downloaded.append(target.relative_to(dest).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents[target.relative_to(dest).as_posix()])

        monkeypatch.setattr(fetch_module, "_download", fake_download)
        fetch_module.fetch_artifact(dest, pin)
        assert "model.onnx" not in downloaded, "completed file must not re-download"
        assert downloaded, "remaining files must still download"


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


# ── Repository pin enforcement (#3366) ─────────────────────────────────────────


def make_pinned_artifact(tmp_path: Path) -> tuple[Path, Path]:
    """A small self-consistent artifact dir plus an identical trusted pin copy.

    Returns ``(artifact_dir, pin_path)`` where ``pin_path`` simulates the
    repository-committed ``artifact_manifest.json`` used as the trusted
    expected manifest at the build/runtime boundary.
    """
    artifact = tmp_path / "artifact"
    pin = tmp_path / "repository_pin.json"
    mapping = {
        "model.onnx": (b"fake-onnx-graph", "model"),
        "model.onnx_data": (b"fake-external-data-shard", "external_data"),
        "tokenizer/tokenizer.json": (b'{"tokenizer": true}', "tokenizer"),
        "tokenizer/tokenizer_config.json": (b"{}", "tokenizer"),
        "tokenizer/special_tokens_map.json": (b"{}", "tokenizer"),
        "tokenizer/sentencepiece.bpe.model": (b"fake-sentencepiece", "tokenizer"),
    }
    manifest = {
        "schema_version": 1,
        "artifact": {"outputs": ["dense_vecs", "sparse_vecs", "colbert_vecs"], "opset": 17},
        "source": {"repo_id": "test/repo", "revision": "a" * 40, "license": "MIT"},
        "upstream_model": {"repo_id": "BAAI/bge-m3", "revision": "b" * 40},
        "files": [_entry(name, data, role) for name, (data, role) in mapping.items()],
    }
    for name, (data, _role) in mapping.items():
        target = artifact / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    rendered = json.dumps(manifest, indent=2)
    pin.write_text(rendered, encoding="utf-8")
    (artifact / "artifact_manifest.json").write_text(rendered, encoding="utf-8")
    return artifact, pin


class TestRepositoryPinEnforcement:
    """Integrity must be anchored to the repository manifest, not to whatever
    manifest ships next to the downloaded bytes (#3366 audit blocker)."""

    def test_self_consistent_mutated_artifact_rejected_against_repo_pin(
        self, tmp_path: Path
    ) -> None:
        """The audit reproduction: replacing the model bytes AND the
        artifact-folder manifest together must still fail against the
        unchanged repository pin."""
        artifact, pin = make_pinned_artifact(tmp_path)
        # Attacker rewrites the model bytes and re-signs the artifact-folder
        # manifest so the folder is internally self-consistent.
        (artifact / "model.onnx").write_bytes(b"totally-different-model")
        folder_manifest = json.loads(
            (artifact / "artifact_manifest.json").read_text(encoding="utf-8")
        )
        for entry in folder_manifest["files"]:
            data = (artifact / entry["name"]).read_bytes()
            entry["bytes"] = len(data)
            entry["sha256"] = _sha256(data)
        (artifact / "artifact_manifest.json").write_text(
            json.dumps(folder_manifest), encoding="utf-8"
        )

        with pytest.raises(ArtifactIntegrityError, match="repository pin"):
            verify_pinned_artifact(artifact, pin)

    def test_pinned_positive_control_passes(self, tmp_path: Path) -> None:
        artifact, pin = make_pinned_artifact(tmp_path)
        manifest = verify_pinned_artifact(artifact, pin)
        assert manifest["source"]["revision"] == "a" * 40

    def test_pinned_manifest_text_drift_is_semantically_tolerated(self, tmp_path: Path) -> None:
        """Key order / whitespace in the artifact-folder manifest must not
        reject an otherwise identical pin; content equality is what counts."""
        artifact, pin = make_pinned_artifact(tmp_path)
        folder_manifest = json.loads(pin.read_text(encoding="utf-8"))
        reordered = dict(reversed(list(folder_manifest.items())))
        (artifact / "artifact_manifest.json").write_text(
            json.dumps(reordered, indent=1), encoding="utf-8"
        )
        manifest = verify_pinned_artifact(artifact, pin)
        assert manifest["source"]["repo_id"] == "test/repo"

    def test_pinned_wrong_revision_is_actionable(self, tmp_path: Path) -> None:
        artifact, pin = make_pinned_artifact(tmp_path)
        folder_manifest = json.loads(pin.read_text(encoding="utf-8"))
        folder_manifest["source"]["revision"] = "c" * 40
        (artifact / "artifact_manifest.json").write_text(
            json.dumps(folder_manifest), encoding="utf-8"
        )
        with pytest.raises(ArtifactIntegrityError, match=r"revision.*does not match"):
            verify_pinned_artifact(artifact, pin)

    def test_pinned_extra_file_rejected(self, tmp_path: Path) -> None:
        artifact, pin = make_pinned_artifact(tmp_path)
        (artifact / "model.onnx_data.part").write_bytes(b"partial download leftover")
        with pytest.raises(ArtifactIntegrityError, match=r"extra file.*model\.onnx_data\.part"):
            verify_pinned_artifact(artifact, pin)

    def test_pinned_missing_file_rejected(self, tmp_path: Path) -> None:
        artifact, pin = make_pinned_artifact(tmp_path)
        (artifact / "model.onnx_data").unlink()
        with pytest.raises(FileNotFoundError, match=r"model\.onnx_data"):
            verify_pinned_artifact(artifact, pin)

    def test_pinned_hash_mismatch_rejected(self, tmp_path: Path) -> None:
        artifact, pin = make_pinned_artifact(tmp_path)
        (artifact / "model.onnx").write_bytes(b"X" * len(b"fake-onnx-graph"))
        with pytest.raises(ArtifactIntegrityError, match=r"sha256 mismatch.*model\.onnx"):
            verify_pinned_artifact(artifact, pin)

    def test_pinned_missing_artifact_folder_manifest_rejected(self, tmp_path: Path) -> None:
        artifact, pin = make_pinned_artifact(tmp_path)
        (artifact / "artifact_manifest.json").unlink()
        with pytest.raises(FileNotFoundError, match=r"artifact_manifest\.json"):
            verify_pinned_artifact(artifact, pin)

    def test_real_repository_pin_rejects_folder_resigned_manifest(self, tmp_path: Path) -> None:
        """The committed artifact_manifest.json itself, used as the trusted
        pin, must reject a self-consistent synthetic substitute."""
        artifact, _pin = make_pinned_artifact(tmp_path)
        with pytest.raises(ArtifactIntegrityError, match="repository pin"):
            verify_pinned_artifact(artifact, _MANIFEST_PATH)


class TestPinContract:
    """The trusted pin must itself record the approved format contract."""

    def test_pin_requires_all_three_outputs(self) -> None:
        manifest = {
            "schema_version": 1,
            "artifact": {"outputs": ["dense_vecs", "sparse_vecs"]},
            "source": {"revision": "a" * 40},
            "upstream_model": {},
            "files": [_entry("model.onnx", b"x", "model")],
        }
        with pytest.raises(ArtifactIntegrityError, match="colbert_vecs"):
            validate_pin_contract(manifest)

    def test_pin_requires_immutable_40hex_revision(self) -> None:
        manifest = {
            "schema_version": 1,
            "artifact": {"outputs": ["dense_vecs", "sparse_vecs", "colbert_vecs"]},
            "source": {"revision": "main"},
            "upstream_model": {},
            "files": [_entry("model.onnx", b"x", "model")],
        }
        with pytest.raises(ArtifactIntegrityError, match="revision"):
            validate_pin_contract(manifest)

    def test_real_committed_manifest_satisfies_pin_contract(self) -> None:
        validate_pin_contract(load_manifest(_MANIFEST_PATH))


class TestPinCli:
    """The build-boundary CLI must take the trusted manifest explicitly."""

    def test_cli_expected_manifest_passes(self, tmp_path: Path, capsys) -> None:
        from verify_artifact import main as verify_main

        artifact, pin = make_pinned_artifact(tmp_path)
        assert verify_main(["--dir", str(artifact), "--expected-manifest", str(pin)]) == 0
        assert "ARTIFACT VERIFIED" in capsys.readouterr().out

    def test_cli_expected_manifest_rejects_resigned_artifact(self, tmp_path: Path, capsys) -> None:
        from verify_artifact import main as verify_main

        artifact, pin = make_pinned_artifact(tmp_path)
        folder_manifest = json.loads(pin.read_text(encoding="utf-8"))
        (artifact / "model.onnx").write_bytes(b"mutated")
        for entry in folder_manifest["files"]:
            data = (artifact / entry["name"]).read_bytes()
            entry["bytes"] = len(data)
            entry["sha256"] = _sha256(data)
        (artifact / "artifact_manifest.json").write_text(
            json.dumps(folder_manifest), encoding="utf-8"
        )

        assert verify_main(["--dir", str(artifact), "--expected-manifest", str(pin)]) == 1
        assert "ARTIFACT VERIFICATION FAILED" in capsys.readouterr().err
