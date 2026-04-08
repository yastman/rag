"""Regression tests for the k3s secret template and generation flow."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


API_KEYS_REQUIRED = {
    "TELEGRAM_BOT_TOKEN",
    "LITELLM_MASTER_KEY",
    "REDIS_PASSWORD",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "KOMMO_ACCESS_TOKEN",
    "KOMMO_CLIENT_ID",
    "KOMMO_CLIENT_SECRET",
}
ROOT = Path(__file__).parents[2]


def _load_env_example_keys() -> set[str]:
    path = Path("k8s/secrets/.env.example")
    keys: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key = line.split("=", 1)[0]
            keys.add(key)
    return keys


def _load_container_env(path: Path, container_name: str) -> dict[str, dict[str, object]]:
    deployment = yaml.safe_load(path.read_text())
    containers = deployment["spec"]["template"]["spec"]["containers"]
    container = next(item for item in containers if item["name"] == container_name)
    return {entry["name"]: entry for entry in container.get("env", [])}


def _run_make_k3s_secrets(env_text: str) -> tuple[subprocess.CompletedProcess[str], str, str]:
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        env_path = root / "k8s" / "secrets" / ".env"
        env_path.parent.mkdir(parents=True)
        env_path.write_text(env_text)
        makefile_path = root / "Makefile"
        makefile_path.write_text((ROOT / "Makefile").read_text())

        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        kubectl_path = fake_bin / "kubectl"
        kubectl_path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail

                log_dir="${FAKE_KUBECTL_LOG_DIR:?}"

                if [ "$1" = "create" ] && [ "$2" = "secret" ] && [ "$3" = "generic" ]; then
                    name="$4"
                    env_file=""
                    for arg in "$@"; do
                        case "$arg" in
                            --from-env-file=*)
                                env_file="${arg#--from-env-file=}"
                                ;;
                        esac
                    done
                    if [ -n "$env_file" ]; then
                        cp "$env_file" "$log_dir/$name.env"
                    fi
                    printf 'apiVersion: v1\\nkind: Secret\\nmetadata:\\n  name: %s\\n' "$name"
                    exit 0
                fi

                if [ "$1" = "apply" ] && [ "$2" = "-f" ] && [ "$3" = "-" ]; then
                    cat >/dev/null
                    exit 0
                fi

                echo "unexpected kubectl invocation: $*" >&2
                exit 1
                """
            )
        )
        kubectl_path.chmod(0o755)

        log_dir = root / "kubectl-log"
        log_dir.mkdir()

        result = subprocess.run(
            ["make", "k3s-secrets"],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "FAKE_KUBECTL_LOG_DIR": str(log_dir),
            },
        )

        api_keys_path = log_dir / "api-keys.env"
        db_credentials_path = log_dir / "db-credentials.env"
        api_keys = api_keys_path.read_text() if api_keys_path.exists() else ""
        db_credentials = db_credentials_path.read_text() if db_credentials_path.exists() else ""
        return result, api_keys, db_credentials


def test_env_example_documents_current_api_keys_contract() -> None:
    keys = _load_env_example_keys()
    assert keys >= API_KEYS_REQUIRED


def test_env_example_documents_postgres_password_for_db_credentials() -> None:
    keys = _load_env_example_keys()
    assert "POSTGRES_PASSWORD" in keys


def test_make_k3s_secrets_preserves_literal_postgres_password() -> None:
    result, api_keys, db_credentials = _run_make_k3s_secrets(
        "LITELLM_MASTER_KEY=test-key\nPOSTGRES_PASSWORD=pa$$word\n"
    )

    assert result.returncode == 0, result.stderr
    assert "POSTGRES_PASSWORD=pa$$word" in db_credentials
    assert "POSTGRES_PASSWORD" not in api_keys
    assert "LITELLM_MASTER_KEY=test-key" in api_keys


def test_make_k3s_secrets_requires_postgres_password() -> None:
    result, _, _ = _run_make_k3s_secrets("LITELLM_MASTER_KEY=test-key\n")

    assert result.returncode != 0
    assert "POSTGRES_PASSWORD is required" in result.stderr


def test_bot_deployment_uses_db_secret_password_in_database_url() -> None:
    env = _load_container_env(ROOT / "k8s" / "base" / "bot" / "deployment.yaml", "bot")

    assert env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"] == {
        "name": "db-credentials",
        "key": "POSTGRES_PASSWORD",
    }
    assert env["REALESTATE_DATABASE_URL"]["value"] == (
        "postgresql://postgres:$(POSTGRES_PASSWORD)@postgres:5432/realestate"
    )


def test_ingestion_deployment_uses_db_secret_password_in_database_url() -> None:
    env = _load_container_env(ROOT / "k8s" / "base" / "ingestion" / "deployment.yaml", "ingestion")

    assert env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"] == {
        "name": "db-credentials",
        "key": "POSTGRES_PASSWORD",
    }
    assert env["INGESTION_DATABASE_URL"]["value"] == (
        "postgresql://postgres:$(POSTGRES_PASSWORD)@postgres:5432/cocoindex"
    )
