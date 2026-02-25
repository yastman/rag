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


_TOKEN_LIMIT_KEYS = {"max_tokens", "max_completion_tokens"}


def _normalize_token_limit(params: dict) -> int | None:
    for key in _TOKEN_LIMIT_KEYS:
        if key in params:
            return int(params[key])
    return None


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
            docker_params = docker_models[name]
            k8s_params = k8s_models[name]

            # provider model must match exactly
            assert docker_params.get("model") == k8s_params.get("model"), (
                f"Model '{name}' provider model: docker={docker_params.get('model')!r}, "
                f"k8s={k8s_params.get('model')!r}"
            )

            # token limits must match (normalized across key names)
            docker_limit = _normalize_token_limit(docker_params)
            k8s_limit = _normalize_token_limit(k8s_params)
            assert docker_limit == k8s_limit, (
                f"Model '{name}' token limit: docker={docker_limit} (from {docker_params!r}), "
                f"k8s={k8s_limit} (from {k8s_params!r})"
            )

            # merge_reasoning_content_in_choices must match if present in either
            docker_merge = docker_params.get("merge_reasoning_content_in_choices")
            k8s_merge = k8s_params.get("merge_reasoning_content_in_choices")
            assert docker_merge == k8s_merge, (
                f"Model '{name}' merge_reasoning_content_in_choices: "
                f"docker={docker_merge}, k8s={k8s_merge}"
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

    def test_token_limit_keys_consistent(self):
        """Both configs must have the same normalized token limit for each model."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()

        docker_models = {m["model_name"]: m["litellm_params"] for m in docker["model_list"]}
        k8s_models = {m["model_name"]: m["litellm_params"] for m in k8s["model_list"]}

        mismatches = []
        for name in set(docker_models) & set(k8s_models):
            docker_limit = _normalize_token_limit(docker_models[name])
            k8s_limit = _normalize_token_limit(k8s_models[name])

            if docker_limit is None and k8s_limit is None:
                continue  # both have no token limit — OK

            if docker_limit != k8s_limit:
                mismatches.append(f"  '{name}': docker={docker_limit}, k8s={k8s_limit}")

        assert not mismatches, "Token limit drift detected:\n" + "\n".join(mismatches)

    def test_drift_detected_on_value_mismatch(self):
        """Normalization check catches value drift when patched in memory."""
        docker_params = {"max_completion_tokens": 1024}
        k8s_params_drifted = {"max_completion_tokens": 2048}

        docker_limit = _normalize_token_limit(docker_params)
        k8s_limit = _normalize_token_limit(k8s_params_drifted)

        assert docker_limit != k8s_limit, (
            "Drift detection failed: normalization should catch 1024 vs 2048 mismatch"
        )

    def test_token_limit_key_names_match(self):
        """Both configs should use the same token-limit key name for each model."""
        docker = _load_docker_config()
        k8s = _load_k8s_config()

        docker_models = {m["model_name"]: m["litellm_params"] for m in docker["model_list"]}
        k8s_models = {m["model_name"]: m["litellm_params"] for m in k8s["model_list"]}

        mismatches = []
        for name in set(docker_models) & set(k8s_models):
            docker_key = next((k for k in _TOKEN_LIMIT_KEYS if k in docker_models[name]), None)
            k8s_key = next((k for k in _TOKEN_LIMIT_KEYS if k in k8s_models[name]), None)

            if docker_key is None and k8s_key is None:
                continue  # both absent — OK

            if docker_key != k8s_key:
                mismatches.append(f"  '{name}': docker uses {docker_key!r}, k8s uses {k8s_key!r}")

        assert not mismatches, "Token limit key name drift detected:\n" + "\n".join(mismatches)
