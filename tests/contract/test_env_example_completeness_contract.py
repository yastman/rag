"""Root operator examples have native Python/Compose owners (#3437).

Settings metadata defines supported Python inputs; Compose's own interpolation
report defines container inputs. Overlapping inputs are assigned to Python first.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.e2e.config import E2EConfig
from scripts.qdrant_snapshot import SnapshotSettings
from src.ingestion.unified.config import UnifiedConfig
from src.runtime.config import GraphConfig
from src.runtime.integrations.cache import RedisClientSettings
from telegram_bot.config import (
    BotConfig,
    BotLoggingSettings,
    BotStartupSettings,
    CoverageSettings,
    ThrottleSettings,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
# These SDKs consume these inputs directly; there is no application setting.
SDK_INPUTS = {"OPENAI_BASE_URL": "OpenAI AsyncOpenAI: telegram_bot/services/voice_transcription.py"}

_BGE_MODEL_FIELDS_SCRIPT = """
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("contract_bge_settings", sys.argv[1])
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(sorted(module.Settings.model_fields)))
"""


def _bge_settings_env_names() -> set[str]:
    environment = {
        name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "COMSPEC") if name in os.environ
    }
    with tempfile.TemporaryDirectory() as working_directory:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                _BGE_MODEL_FIELDS_SCRIPT,
                str(REPO_ROOT / "services" / "bge-m3-api" / "config.py"),
            ],
            cwd=working_directory,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    return set(json.loads(result.stdout))


def _model_field_env_names(settings_type: type) -> set[str]:
    names: set[str] = set()
    for field_name, model_field in settings_type.model_fields.items():
        alias = model_field.validation_alias or model_field.alias or field_name
        names.update(
            name
            for name in getattr(alias, "choices", (alias,))
            if isinstance(name, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
        )
    return names


def _settings_env_names() -> set[str]:
    names = _bge_settings_env_names()
    for model in (
        GraphConfig,
        BotConfig,
        E2EConfig,
        UnifiedConfig,
        RedisClientSettings,
        BotStartupSettings,
        BotLoggingSettings,
        ThrottleSettings,
        CoverageSettings,
        SnapshotSettings,
    ):
        names |= _model_field_env_names(model)
    return names


def _compose_env_names(*files: Path) -> set[str]:
    files = files or (REPO_ROOT / "compose.yml", REPO_ROOT / "compose.dev.yml")
    result = subprocess.run(
        [
            "docker",
            "compose",
            *[arg for file in files for arg in ("-f", str(file))],
            "config",
            "--variables",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {line.split(maxsplit=1)[0] for line in result.stdout.splitlines()[1:] if line.strip()}


def _parse_env_example() -> set[str]:
    return set(
        re.findall(
            r"^\s*(?:#\s*)?([A-Z][A-Z0-9_]*)=",
            (REPO_ROOT / ".env.example").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )


def test_every_documented_variable_has_a_native_owner() -> None:
    typed, compose = _settings_env_names(), _compose_env_names()
    owners = {"python": typed, "compose": compose - typed, "sdk": set(SDK_INPUTS) - typed - compose}
    undocumented = _parse_env_example() - set().union(*owners.values())
    assert not undocumented, f"Documented inputs without a native owner: {sorted(undocumented)}"


def test_compose_inputs_are_documented() -> None:
    assert not (_compose_env_names() - _parse_env_example())


def test_bge_settings_metadata_ignores_ambient_config(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text("PORT=not-a-sidecar-port\nOMP_NUM_THREADS=not-an-int\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORT", "not-a-sidecar-port")
    monkeypatch.setenv("OMP_NUM_THREADS", "not-an-int")
    assert "MODEL_NAME" in _settings_env_names()


def test_env_example_is_split_into_sections() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert text.count("# " + "=" * 78) >= 10
