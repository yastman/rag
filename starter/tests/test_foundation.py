from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from rag.cli import main
from rag.settings import Command, Settings, SettingsConfigurationError


ROOT = Path(__file__).resolve().parents[1]


class FoundationTests(unittest.TestCase):
    def test_registered_commands_render_help(self) -> None:
        script = Path(sys.executable).with_name("rag.exe" if os.name == "nt" else "rag")

        for command in ("ingest", "bot", "smoke"):
            result = subprocess.run(
                [script, command, "--help"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout)

    def test_ingest_does_not_require_bot_or_llm_secrets(self) -> None:
        with patch.dict(os.environ, {"RAG_COLLECTION": "documents"}, clear=True):
            Settings().validate_for(Command.INGEST)

    def test_bot_requires_its_own_secrets(self) -> None:
        with patch.dict(os.environ, {"RAG_COLLECTION": "documents"}, clear=True):
            with self.assertRaises(SettingsConfigurationError) as raised:
                Settings().validate_for(Command.BOT)

        self.assertEqual(
            raised.exception.missing,
            (
                "RAG_LITELLM_API_KEY",
                "RAG_TELEGRAM_BOT_TOKEN",
                "RAG_TELEGRAM_ALLOWED_USER_IDS",
            ),
        )

    def test_bot_rejects_non_ascii_user_ids(self) -> None:
        environment = {
            "RAG_COLLECTION": "documents",
            "RAG_LITELLM_API_KEY": "test-key",
            "RAG_TELEGRAM_BOT_TOKEN": "token",
            "RAG_TELEGRAM_ALLOWED_USER_IDS": "١",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(SettingsConfigurationError) as raised:
                Settings().validate_for(Command.BOT)

        self.assertEqual(raised.exception.invalid, ("RAG_TELEGRAM_ALLOWED_USER_IDS",))

    def test_smoke_does_not_require_telegram_settings(self) -> None:
        with patch.dict(os.environ, {"RAG_LITELLM_API_KEY": "test-key"}, clear=True):
            Settings().validate_for(Command.SMOKE, collection="smoke-documents")

    def test_smoke_requires_a_nonempty_collection(self) -> None:
        with patch.dict(os.environ, {"RAG_LITELLM_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(SettingsConfigurationError) as raised:
                Settings().validate_for(Command.SMOKE, collection="")

        self.assertEqual(raised.exception.missing, ("--collection",))

    def test_cli_redacts_malformed_settings_value(self) -> None:
        secret = "credential-that-must-not-leak"
        environment = {
            "RAG_COLLECTION": "documents",
            "RAG_QDRANT_URL": f"http://user:{secret}@127.0.0.1:not-a-port",
        }
        stderr = StringIO()

        with patch.dict(os.environ, environment, clear=True), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["ingest", "documents"])

        self.assertEqual(raised.exception.code, 2)
        output = stderr.getvalue()
        self.assertIn("ingest configuration requires: RAG_QDRANT_URL", output)
        self.assertNotIn(secret, output)
        self.assertNotIn("Traceback", output)

    def test_release_manifest_records_bge_contract(self) -> None:
        manifest = json.loads((ROOT / "release" / "bge-m3-contract.json").read_text())

        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["model"]["id"], "BAAI/bge-m3")
        self.assertRegex(manifest["model"]["revision"], r"^[0-9a-f]{40}$")
        self.assertRegex(manifest["model"]["tokenizer"]["artifact_sha256"], r"^[0-9a-f]{64}$")
        artifacts = manifest["model"]["artifacts"]
        self.assertEqual(
            [artifact["path"] for artifact in artifacts],
            ["pytorch_model.bin", "colbert_linear.pt", "sparse_linear.pt"],
        )
        for artifact in artifacts:
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
        self.assertIs(manifest["embedding"]["normalize"], True)
        self.assertEqual(manifest["embedding"]["dense_dimensions"], 1024)
        self.assertEqual(manifest["embedding"]["sparse"]["format"], "indices-and-values")
        self.assertEqual(manifest["sidecar"]["max_batch_size"], 64)
        self.assertEqual(manifest["sidecar"]["default_batch_size"], 32)
        self.assertRegex(manifest["sidecar"]["build"]["base_image"], r"@sha256:[0-9a-f]{64}$")

    def test_lockfile_keeps_hashed_resolution(self) -> None:
        lockfile = (ROOT / "uv.lock").read_text()

        self.assertIn('name = "pydantic-settings"', lockfile)
        self.assertRegex(lockfile, r'hash = "sha256:[0-9a-f]{64}"')

    def test_lockfile_hashes_the_build_backend(self) -> None:
        lockfile = (ROOT / "uv.lock").read_text()

        self.assertRegex(
            lockfile,
            r'(?s)\[\[package\]\]\nname = "uv-build".*?hash = "sha256:[0-9a-f]{64}"',
        )

    def test_lockfile_excludes_product_frameworks(self) -> None:
        lockfile = (ROOT / "uv.lock").read_text()

        for package in (
            "asyncpg",
            "langchain",
            "langgraph",
            "llama-index",
            "psycopg",
            "sqlalchemy",
        ):
            self.assertNotIn(f'name = "{package}"', lockfile)

    def test_compose_has_only_pinned_sidecars(self) -> None:
        result = subprocess.run(
            ["docker", "compose", "-f", "compose.yml", "config", "--format", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]

        self.assertEqual(set(services), {"qdrant", "redis", "bge-m3"})
        self.assertTrue(all("@sha256:" in services[name]["image"] for name in ("qdrant", "redis")))
        self.assertEqual(
            services["bge-m3"]["build"]["context"],
            str((ROOT / "sidecar" / "bge-m3").resolve()),
        )


class BgeM3ProviderTests(unittest.TestCase):
    def load_provider(self) -> ModuleType:
        fastapi = ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str) -> None:
                super().__init__(detail)
                self.status_code = status_code

        class FastAPI:
            def __init__(self, **_: object) -> None:
                pass

            def get(self, _: str):
                return lambda function: function

            def post(self, _: str, **__: object):
                return lambda function: function

        pydantic = ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **values: object) -> None:
                self.__dict__.update(values)

        fastapi.FastAPI = FastAPI
        fastapi.HTTPException = HTTPException
        pydantic.BaseModel = BaseModel
        pydantic.Field = lambda **_: None
        module_name = f"bge_m3_provider_{uuid4().hex}"
        spec = spec_from_file_location(module_name, ROOT / "sidecar" / "bge-m3" / "app.py")
        assert spec and spec.loader
        with patch.dict(sys.modules, {"fastapi": fastapi, "pydantic": pydantic}):
            module = module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        self.addCleanup(sys.modules.pop, module_name, None)
        return module

    def test_provider_enforces_batch_bounds_and_validates_hybrid_output(self) -> None:
        provider = self.load_provider()

        class FakeModel:
            def encode(self, texts: list[str], **_: object) -> dict[str, object]:
                return {
                    "dense_vecs": [[float(text)] * 1024 for text in texts],
                    "lexical_weights": [{text: 0.25} for text in texts],
                }

        with patch.object(provider, "model", return_value=FakeModel()):
            for count in (1, 32, 64):
                response = provider.encode_hybrid(
                    SimpleNamespace(texts=[str(index) for index in range(count)])
                )
                self.assertEqual(len(response.dense_vecs), count)
                self.assertEqual(len(response.sparse_vecs), count)
                self.assertEqual(
                    [vector[0] for vector in response.dense_vecs],
                    [float(index) for index in range(count)],
                )
                self.assertEqual(
                    [sparse.indices for sparse in response.sparse_vecs],
                    [[index] for index in range(count)],
                )
                for vector in response.dense_vecs:
                    self.assertEqual(len(vector), 1024)
                    self.assertTrue(all(math.isfinite(value) for value in vector))
                for sparse in response.sparse_vecs:
                    self.assertTrue(all(index >= 0 for index in sparse.indices))
                    self.assertTrue(
                        all(math.isfinite(value) and value >= 0 for value in sparse.values)
                    )

            for count in (0, 65):
                with self.assertRaises(provider.HTTPException) as raised:
                    provider.encode_hybrid(SimpleNamespace(texts=["x"] * count))
                self.assertEqual(raised.exception.status_code, 500)

        class NonFiniteModel:
            def encode(self, texts: list[str], **_: object) -> dict[str, object]:
                return {
                    "dense_vecs": [[float("nan")] * 1024 for _ in texts],
                    "lexical_weights": [{"2": 0.25} for _ in texts],
                }

        with patch.object(provider, "model", return_value=NonFiniteModel()):
            with self.assertRaises(provider.HTTPException) as raised:
                provider.encode_hybrid(SimpleNamespace(texts=["x"]))
        self.assertEqual(raised.exception.status_code, 500)

        class InvalidSparseModel:
            def encode(self, texts: list[str], **_: object) -> dict[str, object]:
                return {
                    "dense_vecs": [[0.0] * 1024 for _ in texts],
                    "lexical_weights": [{"-1": 0.25}],
                }

        with patch.object(provider, "model", return_value=InvalidSparseModel()):
            with self.assertRaises(provider.HTTPException) as raised:
                provider.encode_hybrid(SimpleNamespace(texts=["0"]))
        self.assertEqual(raised.exception.status_code, 500)

    def test_provider_fails_closed_for_missing_or_invalid_artifacts(self) -> None:
        provider = self.load_provider()
        hub = ModuleType("huggingface_hub")
        with TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            hub.snapshot_download = lambda *_args, **_kwargs: str(artifact_root)
            with patch.dict(sys.modules, {"huggingface_hub": hub}):
                with self.assertRaises(FileNotFoundError):
                    provider.verified_model_path()

                for name in provider.MODEL_ARTIFACTS:
                    (artifact_root / name).write_bytes(b"not the verified model")
                with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
                    provider.verified_model_path()


if __name__ == "__main__":
    unittest.main()
