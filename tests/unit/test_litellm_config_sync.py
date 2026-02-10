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
            for key in ("model", "max_tokens", "merge_reasoning_content_in_choices"):
                docker_val = docker_models[name].get(key)
                k8s_val = k8s_models[name].get(key)
                if docker_val is not None:
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
