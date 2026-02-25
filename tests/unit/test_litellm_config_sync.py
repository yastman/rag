"""Test that Docker and k8s LiteLLM configs are in sync."""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_docker_config() -> dict:
    path = Path("docker/litellm/config.yaml")
    return yaml.safe_load(path.read_text())


def _load_k8s_config() -> dict:
    path = Path("k8s/base/configmaps/litellm-config.yaml")
    cm = yaml.safe_load(path.read_text())
    return yaml.safe_load(cm["data"]["config.yaml"])


def _iter_model_entries(cfg: dict, provider_model: str) -> list[dict]:
    return [
        entry
        for entry in cfg["model_list"]
        if entry.get("litellm_params", {}).get("model") == provider_model
    ]


def _fallback_model_groups(cfg: dict) -> set[str]:
    # Prefer modern LiteLLM location, keep legacy fallback for compatibility.
    fallbacks = cfg.get("litellm_settings", {}).get("fallbacks")
    if not fallbacks:
        fallbacks = cfg.get("router_settings", {}).get("fallbacks", [])
    return {next(iter(item.keys())) for item in fallbacks if isinstance(item, dict) and item}


class TestLiteLLMConfigSync:
    def test_model_list_matches(self):
        """Docker and k8s model_list have same models with same params."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()

        docker_models = {m["model_name"]: m["litellm_params"] for m in docker["model_list"]}
        k8s_models = {m["model_name"]: m["litellm_params"] for m in k8s["model_list"]}

        assert set(docker_models.keys()) == set(k8s_models.keys()), (
            f"Model names differ: docker={set(docker_models.keys())}, k8s={set(k8s_models.keys())}"
        )

        for name in docker_models:
            for key in (
                "model",
                "max_tokens",
                "max_completion_tokens",
                "merge_reasoning_content_in_choices",
            ):
                docker_val = docker_models[name].get(key)
                k8s_val = k8s_models[name].get(key)
                if key in docker_models[name] or key in k8s_models[name]:
                    assert docker_val == k8s_val, (
                        f"Model '{name}' param '{key}': docker={docker_val}, k8s={k8s_val}"
                    )

    def test_router_settings_match(self):
        """Docker and k8s router_settings are identical."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()
        assert docker["router_settings"] == k8s["router_settings"]

    def test_litellm_settings_match(self):
        """Docker and k8s litellm_settings are identical."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()
        assert docker["litellm_settings"] == k8s["litellm_settings"]

    def test_cerebras_gpt_oss_models_do_not_set_reasoning_effort(self):
        """Guard against UnsupportedParamsError on cerebras/gpt-oss-120b."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()

        for source, cfg in (("docker", docker), ("k8s", k8s)):
            entries = _iter_model_entries(cfg, "cerebras/gpt-oss-120b")
            assert entries, f"No cerebras/gpt-oss-120b entries in {source} config"
            for entry in entries:
                params = entry["litellm_params"]
                assert "reasoning_effort" not in params, (
                    f"{source}:{entry['model_name']} must not set reasoning_effort for "
                    "cerebras/gpt-oss-120b"
                )

    def test_gpt_oss_120b_has_fallback_group(self):
        """Ensure gpt-oss-120b requests can fallback instead of hard-failing."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()

        assert "gpt-oss-120b" in _fallback_model_groups(docker)
        assert "gpt-oss-120b" in _fallback_model_groups(k8s)

    def test_drop_params_enabled_to_avoid_unsupported_params_error(self):
        """Guard against provider UnsupportedParamsError (e.g. reasoning_effort)."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()

        assert docker["litellm_settings"].get("drop_params") is True
        assert k8s["litellm_settings"].get("drop_params") is True

    def test_fallbacks_defined_in_litellm_settings(self):
        """Guard against missing fallback groups in runtime routing config."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()

        docker_groups = _fallback_model_groups(docker)
        k8s_groups = _fallback_model_groups(k8s)

        assert {"gpt-4o-mini", "gpt-oss-120b"}.issubset(docker_groups)
        assert {"gpt-4o-mini", "gpt-oss-120b"}.issubset(k8s_groups)
