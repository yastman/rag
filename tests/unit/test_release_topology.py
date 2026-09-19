"""Release entrypoints against a hermetic Docker CLI, without containers."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
if os.name == "nt":
    BASH = "C:/Program Files/Git/bin/bash.exe"


@pytest.fixture
def release(tmp_path):
    shutil.copytree(ROOT / "scripts", tmp_path / "scripts")
    shutil.copyfile(ROOT / "compose.yml", tmp_path / "compose.yml")
    (tmp_path / ".env").write_text(
        "POSTGRES_PASSWORD=long-password-3438\nREDIS_PASSWORD=long-password-3438\n"
        "TELEGRAM_BOT_TOKEN=secret-token\nOPENAI_API_KEY=secret-api-key\n"
        "GDRIVE_SYNC_DIR=./data\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'project=%s %s\\n' "${COMPOSE_PROJECT_NAME:-}" "$*" >> "$DOCKER_CALLS"
if [[ "$*" == *"config --services"* ]]; then
  [[ "${CONFIG_FAIL:-}" != 1 ]] || { echo secret-api-key >&2; exit 1; }
  printf '%s\\n' redis qdrant bge-m3 bot
  [[ "${OMIT_POSTGRES:-}" == 1 ]] || echo postgres
  [[ "$*" != *"--profile full"* ]] || echo ingestion
elif [[ "$*" == *"config"* ]]; then
  exit 0
elif [[ "$*" == *"ps -q"* ]]; then
  service="${@: -1}"
  [[ "$service" == "${MISSING_SERVICE:-}" ]] || echo "$service-id"
elif [[ "$1" == inspect ]]; then
  if [[ "$*" == *"${UNHEALTHY_SERVICE:-NONE}-id"* ]]; then
    echo running:unhealthy
  else
    echo running:healthy
  fi
elif [[ "$*" == *"exec -T bot"* ]]; then
  cat >/dev/null
  printf 'HANDOFF_ENABLED=false\\nMANAGERS_GROUP_ID=\\n'
else
  echo 'unexpected docker command: secret-api-key' >&2
  exit 99
fi
""",
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)
    disk = bin_dir / "df"
    disk.write_text(
        "#!/usr/bin/env bash\necho 'Filesystem Blocks Used Available Capacity Mounted'\necho 'disk 100 20 80 20% /'\n",
        encoding="utf-8",
        newline="\n",
    )
    disk.chmod(0o755)

    def run(script="probe/release_health_vps.sh", env_file_controls="", **overrides):
        with (tmp_path / ".env").open("a", encoding="utf-8") as env_file:
            env_file.write(env_file_controls)
        env = dict(os.environ)
        for key in (
            "COMPOSE_FILE",
            "COMPOSE_PROFILES",
            "COMPOSE_PROJECT_NAME",
            "COMPOSE_PATH_SEPARATOR",
            "RELEASE_TOPOLOGY",
        ):
            env.pop(key, None)
        env.update(
            PATH=str(bin_dir) + os.pathsep + env["PATH"],
            DOCKER_CALLS=str(tmp_path / "calls"),
            RELEASE_TEST_BIN=str(bin_dir),
            **overrides,
        )
        result = subprocess.run(
            [
                BASH,
                "-c",
                'cd "$RELEASE_TEST_BIN"; export PATH="$PWD:$PATH"; exec bash "$1"',
                "release-test",
                str(tmp_path / "scripts" / script),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        calls = tmp_path / "calls"
        return result, calls.read_text() if calls.exists() else ""

    return run


@pytest.mark.parametrize("mode", ["minimal", "full"])
def test_release_checks_every_rendered_service(release, mode):
    result, calls = release(RELEASE_TOPOLOGY=mode)
    assert result.returncode == 0, result.stdout + result.stderr
    for service in ["redis", "qdrant", "bge-m3", "bot", "postgres"]:
        assert f"ps -q {service}" in calls
    assert ("ps -q ingestion" in calls) == (mode == "full")
    assert "litellm" not in calls
    assert "compose.vps.yml" not in calls


@pytest.mark.parametrize("script", ["probe/release_health_vps.sh", "validate_prod_env.sh"])
def test_missing_explicit_override_fails_before_docker(release, script):
    result, calls = release(script, COMPOSE_FILE="compose.yml:absent.yml")
    assert result.returncode != 0
    assert "Compose file missing" in result.stderr
    assert not calls


@pytest.mark.parametrize("state", ["MISSING_SERVICE", "UNHEALTHY_SERVICE"])
def test_required_ingestion_failure_is_nonzero_and_redacted(release, state):
    result, _ = release(RELEASE_TOPOLOGY="full", **{state: "ingestion"})
    assert result.returncode != 0
    assert "ingestion" in result.stderr
    assert "secret-api-key" not in result.stdout + result.stderr


def test_production_full_validation_needs_no_retired_secrets(release):
    result, calls = release("validate_prod_env.sh", RELEASE_TOPOLOGY="full")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--profile full" in calls
    assert "compose.vps.yml" not in calls


@pytest.mark.parametrize("script", ["probe/release_health_vps.sh", "validate_prod_env.sh"])
@pytest.mark.parametrize("failure", ["CONFIG_FAIL", "OMIT_POSTGRES"])
def test_invalid_render_stops_before_container_probes(release, script, failure):
    result, calls = release(script, **{failure: "1"})
    assert result.returncode != 0
    assert "secret-api-key" not in result.stdout + result.stderr
    assert "ps -q" not in calls
    assert "inspect" not in calls


def test_ambient_profiles_cannot_silently_expand_minimal(release):
    result, calls = release(COMPOSE_PROFILES="full")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--profile postgres" in calls
    assert "ps -q ingestion" not in calls


@pytest.mark.parametrize("script", ["probe/release_health_vps.sh", "validate_prod_env.sh"])
def test_caller_missing_override_wins_over_dotenv(release, script):
    result, calls = release(
        script,
        env_file_controls="COMPOSE_FILE=compose.yml\nCOMPOSE_PATH_SEPARATOR=:\nRELEASE_TOPOLOGY=minimal\n",
        COMPOSE_FILE="compose.yml;absent.yml",
        COMPOSE_PATH_SEPARATOR=";",
        RELEASE_TOPOLOGY="full",
    )
    assert result.returncode != 0
    assert "Compose file missing: absent.yml" in result.stderr
    assert not calls


@pytest.mark.parametrize("script", ["probe/release_health_vps.sh", "validate_prod_env.sh"])
def test_caller_full_and_project_win_over_dotenv(release, script):
    result, calls = release(
        script,
        env_file_controls="RELEASE_TOPOLOGY=minimal\nCOMPOSE_PROJECT_NAME=wrong-project\n",
        RELEASE_TOPOLOGY="full",
        COMPOSE_PROJECT_NAME="vps",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--profile full" in calls
    assert "project=vps" in calls
    assert "wrong-project" not in calls


@pytest.mark.parametrize("script", ["probe/release_health_vps.sh", "validate_prod_env.sh"])
def test_dotenv_does_not_override_default_release_selection(release, script):
    result, calls = release(
        script,
        env_file_controls="COMPOSE_FILE=absent.yml\nCOMPOSE_PATH_SEPARATOR=;\nRELEASE_TOPOLOGY=full\nCOMPOSE_PROJECT_NAME=wrong-project\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--profile postgres" in calls
    assert "project=vps" in calls
    assert "wrong-project" not in calls
