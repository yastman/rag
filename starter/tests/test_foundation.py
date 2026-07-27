from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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

    def test_bge_sidecar_builds_a_hybrid_contract_not_dense_only_tei(self) -> None:
        compose = (ROOT / "compose.yml").read_text()
        manifest = json.loads((ROOT / "release" / "bge-m3-contract.json").read_text())
        self.assertIn("build", manifest["sidecar"])
        if "build" not in manifest["sidecar"]:
            return
        sidecar = ROOT / manifest["sidecar"]["build"]["context"]
        app = (sidecar / "app.py").read_text()
        dockerfile = (sidecar / "Dockerfile").read_text()
        self.assertIn("build:", compose)
        self.assertNotIn("text-embeddings-inference", compose)
        self.assertEqual(manifest["embedding"]["contract_version"], 2)
        self.assertEqual(manifest["embedding"]["dense_dimensions"], 1024)
        self.assertEqual(manifest["embedding"]["sparse"]["format"], "indices-and-values")
        self.assertEqual(manifest["sidecar"]["endpoint"], "/encode/hybrid")
        self.assertRegex(manifest["sidecar"]["build"]["base_image"], r"@sha256:[0-9a-f]{64}$")
        self.assertIn("BGEM3FlagModel", app)
        self.assertIn('@app.post("/encode/hybrid",', app)
        self.assertIn("dense_vecs", app)
        self.assertIn("lexical_weights", app)
        self.assertIn("snapshot_download", app)
        self.assertIn("MODEL_ARTIFACTS", app)
        self.assertIn("max_length=64", app)
        self.assertIn(manifest["sidecar"]["build"]["base_image"], dockerfile)


if __name__ == "__main__":
    unittest.main()
