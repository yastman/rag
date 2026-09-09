"""Operator env gate contract (#3367).

Real full-stack commands (``make docker-full-up`` and the other build/up
targets) must never fall back to ``tests/fixtures/compose.ci.env``. The
operator env file is explicit and is validated — file existence, required
secret presence/shape, native host path semantics, and the pinned BGE-M3
artifact manifest/hash — *before* Compose runs.

Two layers are contracted here:

1. Table-driven command tests against ``scripts/validate_operator_env.py``
   (the command the Makefile guard target executes).
2. Static Makefile/CI wiring contracts that keep CI-render env selection
   separate from operator full-stack selection.

These tests are hermetic: they never start containers and never need Docker.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "scripts" / "validate_operator_env.py"
REPO_PIN = REPO_ROOT / "services" / "bge-m3-api" / "artifact_manifest.json"
CI_FIXTURE_ENV = REPO_ROOT / "tests" / "fixtures" / "compose.ci.env"
MAKEFILE = REPO_ROOT / "Makefile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Valid-shaped operator values used as the happy-path baseline. Each is
# deliberately distinct so the redaction assertions can prove none of them is
# ever echoed by the validator.
VALID_ENV: dict[str, str] = {
    "COMPOSE_PROJECT_NAME": "dev",
    "TELEGRAM_BOT_TOKEN": "987654321:ZyXwVuTsRqPoNmLkJiHgFeDcBaZyxwvutsrqponm",
    "POSTGRES_PASSWORD": "op-postgres-secret-3367",
    "REDIS_PASSWORD": "op-redis-secret-3367",
    "ENCRYPTION_KEY": "a1" * 32,
    "SALT": "op-salt-secret-3367-abcdef",
    "NEXTAUTH_SECRET": "op-nextauth-secret-3367-abcdef",
    "CEREBRAS_API_KEY": "csk-op-cerebras-secret-3367",
    "BGE_M3_ONNX_MODEL_HOST_DIR": "<filled per-test>",
}


def _run_validator(
    env_file: Path | str,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    """Run the operator env validator the same way the Makefile guard does."""
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--env-file",
            str(env_file),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )


def _write_env(path: Path, values: dict[str, str]) -> Path:
    lines = [f"{key}={value}" for key, value in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _valid_env_values(bge_dir: Path) -> dict[str, str]:
    values = dict(VALID_ENV)
    values["BGE_M3_ONNX_MODEL_HOST_DIR"] = str(bge_dir)
    return values


def _ci_fixture_values() -> dict[str, str]:
    """Parse KEY=VALUE pairs from the CI fixture (mirrors its exact dummies)."""
    values: dict[str, str] = {}
    for line in CI_FIXTURE_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _make_pinned_artifact(base: Path) -> tuple[Path, Path]:
    """Build a tiny synthetic artifact directory plus its matching pin.

    The real repository pin describes a ~6.8 GB artifact, so the happy-path
    command test proves the gate's acceptance logic against a synthetic pin
    passed via ``--pin-manifest`` (the same parameter the Makefile gate leaves
    at the repository default).
    """
    artifact = base / "bge-artifact"
    files: dict[str, bytes] = {
        "model.onnx": b"synthetic-onnx-model-bytes",
        "model.onnx_data": b"synthetic-external-data-bytes",
        "tokenizer/tokenizer.json": b"{}\n",
    }
    entries = []
    for name, data in files.items():
        target = artifact / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries.append(
            {
                "name": name,
                "role": (
                    "model"
                    if name == "model.onnx"
                    else "external_data"
                    if name == "model.onnx_data"
                    else "tokenizer"
                ),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    pin = base / "pin.json"
    pin.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": {"outputs": ["dense_vecs", "sparse_vecs", "colbert_vecs"]},
                "source": {"revision": "a" * 40},
                "upstream_model": {"repo_id": "synthetic/bge-m3"},
                "files": entries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    shutil.copyfile(pin, artifact / "artifact_manifest.json")
    return artifact, pin


# =============================================================================
# Command tests — table-driven failure and success cases (#3367 "Test first")
# =============================================================================


class TestValidatorCommandCases:
    """Table-driven cases: the seven behaviors the issue names."""

    def test_missing_env_file_fails_with_actionable_message(self, tmp_path: Path) -> None:
        result = _run_validator(tmp_path / "does-not-exist.env")
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "operator env file not found" in output
        assert ".env.example" in output, "failure must name the remediation source"
        assert "copy tests/fixtures" not in output, (
            "the missing-env message must not point operators at the CI fixture"
        )

    def test_dummy_ci_token_rejected_and_value_redacted(self, tmp_path: Path) -> None:
        fixture = _ci_fixture_values()
        dummy_token = fixture["TELEGRAM_BOT_TOKEN"]
        values = _valid_env_values(tmp_path / "bge-artifact")
        values["TELEGRAM_BOT_TOKEN"] = dummy_token
        env_file = _write_env(tmp_path / "dummy-token.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "TELEGRAM_BOT_TOKEN" in output, "failure must name the offending key"
        assert dummy_token not in output, "the token value must never be printed"
        assert "dummy" in output.lower()

    def test_placeholder_password_rejected(self, tmp_path: Path) -> None:
        values = _valid_env_values(tmp_path / "bge-artifact")
        values["POSTGRES_PASSWORD"] = "<change-me>"
        env_file = _write_env(tmp_path / "placeholder.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "POSTGRES_PASSWORD" in output

    def test_all_zero_encryption_key_rejected(self, tmp_path: Path) -> None:
        values = _valid_env_values(tmp_path / "bge-artifact")
        values["ENCRYPTION_KEY"] = "0" * 64
        env_file = _write_env(tmp_path / "zero-key.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "ENCRYPTION_KEY" in output

    def test_missing_llm_key_is_reported(self, tmp_path: Path) -> None:
        values = _valid_env_values(tmp_path / "bge-artifact")
        for key in ("CEREBRAS_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
            values.pop(key, None)
        env_file = _write_env(tmp_path / "no-llm.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        for key in ("CEREBRAS_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
            assert key in output, f"the any-of failure must name {key}"

    def test_nonexistent_bge_path_rejected(self, tmp_path: Path) -> None:
        missing_dir = tmp_path / "no-such-model-dir"
        values = _valid_env_values(missing_dir)
        env_file = _write_env(tmp_path / "missing-path.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "BGE_M3_ONNX_MODEL_HOST_DIR" in output
        assert "does not exist" in output
        assert str(missing_dir) in output, "paths are not secrets and must be shown"

    def test_non_native_path_rejected(self, tmp_path: Path) -> None:
        """Cross-platform path semantics fail on the host that cannot bind them."""
        values = _valid_env_values(tmp_path / "unused")
        if os.name == "nt":
            values["BGE_M3_ONNX_MODEL_HOST_DIR"] = "/mnt/c/models/bge_m3_onnx_int8"
            wsl_hints = ("WSL", "/mnt/")
        else:
            values["BGE_M3_ONNX_MODEL_HOST_DIR"] = "C:\\models\\bge_m3_onnx_int8"
            wsl_hints = ("Windows", "drive")
        env_file = _write_env(tmp_path / "wsl-path.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "BGE_M3_ONNX_MODEL_HOST_DIR" in output
        assert any(hint.lower() in output.lower() for hint in wsl_hints), (
            f"failure must explain the native-path problem, got: {output}"
        )

    def test_invalid_bge_fixture_fails_artifact_verification(self, tmp_path: Path) -> None:
        """The 41-byte dummy fixture must fail the pinned-artifact check."""
        fixture_dir = REPO_ROOT / "tests" / "fixtures" / "bge_m3_onnx_model"
        values = _valid_env_values(fixture_dir)
        env_file = _write_env(tmp_path / "invalid-model.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "BGE" in output and ("artifact" in output.lower()), (
            f"failure must come from the artifact gate, got: {output}"
        )

    def test_valid_native_path_with_pinned_artifact_passes(self, tmp_path: Path) -> None:
        artifact, pin = _make_pinned_artifact(tmp_path)
        values = _valid_env_values(artifact)
        env_file = _write_env(tmp_path / "valid.env", values)
        result = _run_validator(env_file, "--pin-manifest", str(pin))
        assert result.returncode == 0, (
            f"valid operator env must pass; got:\n{result.stdout}\n{result.stderr}"
        )
        assert "OPERATOR ENV OK" in result.stdout + result.stderr

    def test_repo_ci_fixture_env_is_rejected_as_operator_env(self, tmp_path: Path) -> None:
        """The audit scenario: the CI fixture itself is not a valid operator env."""
        result = _run_validator(CI_FIXTURE_ENV)
        assert result.returncode != 0

    def test_diagnostics_never_print_secret_values(self, tmp_path: Path) -> None:
        fixture_token = _ci_fixture_values()["TELEGRAM_BOT_TOKEN"]
        secrets = {
            "TELEGRAM_BOT_TOKEN": fixture_token,
            "REDIS_PASSWORD": "super-secret-redis-value-3367",
            "SALT": "super-secret-salt-value-3367",
            "NEXTAUTH_SECRET": "super-secret-nextauth-value-3367",
        }
        values = _valid_env_values(tmp_path / "bge-artifact")
        values.update(secrets)
        # SALT/NEXTAUTH are valid-shaped; make the run fail via the dummy token
        # so output definitely exists while every other secret stays embedded.
        env_file = _write_env(tmp_path / "redaction.env", values)
        result = _run_validator(env_file)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        for value in secrets.values():
            assert value not in output, f"secret value {value[:8]}… leaked into diagnostics"

    def test_gdrive_sync_dir_validated_when_set(self, tmp_path: Path) -> None:
        artifact, pin = _make_pinned_artifact(tmp_path)
        values = _valid_env_values(artifact)
        values["GDRIVE_SYNC_DIR"] = str(tmp_path / "no-such-drive-dir")
        env_file = _write_env(tmp_path / "gdrive.env", values)
        result = _run_validator(env_file, "--pin-manifest", str(pin))
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "GDRIVE_SYNC_DIR" in output
        assert "does not exist" in output


# =============================================================================
# Makefile / CI wiring contracts — env selection separation (#3367 scope)
# =============================================================================


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def test_makefile_has_no_implicit_ci_env_fallback() -> None:
    """The CI fixture may be referenced only by named CI/static-validation
    surfaces (tests and the hosted compose-config job), never by the Makefile."""
    assert "tests/fixtures/compose.ci.env" not in _makefile_text()
    assert "compose.ci.env" not in _makefile_text()


def test_local_compose_cmd_uses_explicit_operator_env() -> None:
    text = _makefile_text()
    assert "OPERATOR_ENV ?= .env" in text, "Makefile must define the explicit operator env file"
    local_cmd = next(line for line in text.splitlines() if line.startswith("LOCAL_COMPOSE_CMD :="))
    assert "--env-file $(OPERATOR_ENV)" in local_cmd
    assert "[ -f .env ]" not in local_cmd, "no silent existence fallback may remain"


@pytest.mark.parametrize(
    "target",
    [
        "docker-core-up",
        "docker-bot-up",
        "docker-ai-up",
        "docker-ingest-up",
        "docker-full-up",
        "local-up",
        "local-up-ingest",
        "local-build",
    ],
)
def test_build_and_up_targets_require_operator_env_check(target: str) -> None:
    text = _makefile_text()
    match = next(
        (line for line in text.splitlines() if line.startswith(f"{target}:")),
        None,
    )
    assert match is not None, f"{target} target not found"
    assert "operator-env-check" in match, (
        f"{target} must depend on operator-env-check so validation runs before build/up"
    )


def test_operator_env_check_target_invokes_validator() -> None:
    text = _makefile_text()
    assert "operator-env-check:" in text
    assert "scripts/validate_operator_env.py" in text
    assert '--env-file "$(OPERATOR_ENV)"' in text


def test_runtime_env_file_defaults_to_operator_env() -> None:
    text = _makefile_text()
    match = next(line for line in text.splitlines() if line.startswith("RAG_RUNTIME_ENV_FILE"))
    assert "compose.ci.env" not in match
    assert "$(OPERATOR_ENV)" in match
    assert "export RAG_RUNTIME_ENV_FILE" in text


def test_runtime_commands_require_existing_env() -> None:
    """Native-run bot commands keep the explicit env indirection (no literals)."""
    text = _makefile_text()
    for target in ("run-bot:", "bot:", "e2e-telegram-test:"):
        line = next(ln for ln in text.splitlines() if ln.startswith(target))
        assert "operator-env-exists" in line, f"{target} must guard on the operator env existing"


def test_ci_compose_rendering_keeps_explicit_fixture() -> None:
    """CI static Compose rendering remains hermetic via the named fixture."""
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "--env-file tests/fixtures/compose.ci.env" in ci_text
    assert "config --quiet" in ci_text


def test_compose_dev_header_documents_explicit_operator_env() -> None:
    dev_text = (REPO_ROOT / "compose.dev.yml").read_text(encoding="utf-8")
    assert "fall back to tests/fixtures/compose.ci.env" not in dev_text
    assert "explicit" in dev_text


def test_env_example_documents_operator_gate_and_native_path_examples() -> None:
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "make operator-env-check" in example, ".env.example must name the validation command"
    assert "C:/" in example, "a native Windows absolute path example must be present"
    assert "/srv/" in example or "/opt/" in example, (
        "a native POSIX absolute path example must be present"
    )
    assert "/mnt/" not in example, "WSL paths must not be suggested as examples"


def test_docker_doc_names_gate_and_failure_behavior() -> None:
    doc = (REPO_ROOT / "DOCKER.md").read_text(encoding="utf-8")
    assert "make operator-env-check" in doc
    assert "nonzero" in doc.lower() or "exit" in doc.lower(), (
        "DOCKER.md must describe the failure behavior of the gate"
    )


def test_docker_doc_keeps_ci_fixture_out_of_operator_commands() -> None:
    doc = (REPO_ROOT / "DOCKER.md").read_text(encoding="utf-8")
    assert "compose.ci.env" not in doc, (
        "operator documentation must not suggest the CI fixture for real stacks"
    )
