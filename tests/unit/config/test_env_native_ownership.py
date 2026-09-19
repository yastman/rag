"""Native owner drift and environment timing regressions for #3437."""

from pathlib import Path

import pytest
from pydantic import Field
from pydantic_settings import BaseSettings

from src.ingestion.unified.config import UnifiedConfig
from tests.contract import test_env_example_completeness_contract as contract


def test_removed_typed_alias_is_detected(monkeypatch):
    class Owner(BaseSettings):
        value: str = Field(default="", validation_alias="OPERATOR_INPUT")

    monkeypatch.setattr(contract, "_parse_env_example", lambda: {"OPERATOR_INPUT"})
    monkeypatch.setattr(contract, "_compose_env_names", lambda: set())
    monkeypatch.setattr(
        contract, "_settings_env_names", lambda: contract._model_field_env_names(Owner)
    )
    contract.test_every_documented_variable_has_a_native_owner()
    Owner.model_fields["value"].validation_alias = "RENAMED_INPUT"
    with pytest.raises(AssertionError, match="OPERATOR_INPUT"):
        contract.test_every_documented_variable_has_a_native_owner()


def test_removed_compose_interpolation_is_detected(monkeypatch, tmp_path):
    compose = tmp_path / "compose.yml"
    compose.write_text('services:\n  app:\n    image: "example:${OPERATOR_IMAGE_TAG:-latest}"\n')
    native_names = contract._compose_env_names
    monkeypatch.setattr(contract, "_parse_env_example", lambda: {"OPERATOR_IMAGE_TAG"})
    monkeypatch.setattr(contract, "_settings_env_names", lambda: set())
    monkeypatch.setattr(contract, "_compose_env_names", lambda: native_names(compose))
    contract.test_every_documented_variable_has_a_native_owner()
    compose.write_text('services:\n  app:\n    image: "example:latest"\n')
    with pytest.raises(AssertionError, match="OPERATOR_IMAGE_TAG"):
        contract.test_every_documented_variable_has_a_native_owner()


def test_ingestion_alias_precedence_and_explicit_arguments(monkeypatch):
    monkeypatch.setenv("SYNC_DIR", "neutral")
    monkeypatch.setenv("GDRIVE_SYNC_DIR", "legacy")
    monkeypatch.setenv("COLLECTION_NAME", "first")
    monkeypatch.setenv("UNIFIED_COLLECTION_NAME", "second")
    monkeypatch.setenv("GDRIVE_COLLECTION_NAME", "third")
    assert UnifiedConfig().sync_dir == Path("neutral")
    assert UnifiedConfig().collection_name == "first"
    assert (
        UnifiedConfig(sync_dir=Path("explicit"), collection_name="explicit").collection_name
        == "explicit"
    )
    assert UnifiedConfig(sync_dir=Path("explicit")).sync_dir == Path("explicit")
    monkeypatch.delenv("SYNC_DIR")
    monkeypatch.delenv("COLLECTION_NAME")
    assert UnifiedConfig().sync_dir == Path("legacy")
    assert UnifiedConfig().collection_name == "second"
    monkeypatch.delenv("UNIFIED_COLLECTION_NAME")
    assert UnifiedConfig().collection_name == "third"


def test_ingestion_empty_manifest_and_argument_override_invalid_env(monkeypatch):
    monkeypatch.setenv("MANIFEST_DIR", "")
    monkeypatch.setenv("BGE_M3_CONCURRENCY", "invalid")
    assert UnifiedConfig(bge_m3_concurrency=3).manifest_dir is None
    assert UnifiedConfig(bge_m3_concurrency=3).bge_m3_concurrency == 3


def test_ingestion_constructor_only_options_remain_environment_independent(monkeypatch):
    monkeypatch.setenv("MAX_TOKENS_PER_CHUNK", "123")
    monkeypatch.setenv("PIPELINE_VERSION", "unexpected")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("SUPPORTED_EXTENSIONS", "not-json-and-unused")
    config = UnifiedConfig()
    assert config.max_tokens_per_chunk == 512
    assert config.pipeline_version == "v3.2.1"
    assert config.poll_interval_seconds == 60
    assert config.supported_extensions == frozenset({".md"})
    assert UnifiedConfig(max_tokens_per_chunk=123).max_tokens_per_chunk == 123
