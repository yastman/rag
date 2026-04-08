"""Guard against image tag drift between compose and k8s core services."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "compose.yml"
K8S_BASE = ROOT / "k8s" / "base"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _strip_digest(image: str) -> str:
    return image.split("@", 1)[0]


def _compose_image(service: str) -> str:
    compose = _load_yaml(COMPOSE)
    return _strip_digest(compose["services"][service]["image"])


def _k8s_image(deployment_path: Path, container_name: str) -> str:
    deployment = _load_yaml(deployment_path)
    containers = deployment["spec"]["template"]["spec"]["containers"]
    container = next(c for c in containers if c["name"] == container_name)
    return _strip_digest(container["image"])


@pytest.mark.parametrize(
    ("service", "deployment", "container"),
    [
        ("qdrant", K8S_BASE / "qdrant" / "deployment.yaml", "qdrant"),
        ("redis", K8S_BASE / "redis" / "deployment.yaml", "redis"),
        ("litellm", K8S_BASE / "litellm" / "deployment.yaml", "litellm"),
    ],
)
def test_k8s_image_matches_compose(service: str, deployment: Path, container: str) -> None:
    assert _k8s_image(deployment, container) == _compose_image(service), (
        f"{service} image drift: compose={_compose_image(service)!r}, "
        f"k8s={_k8s_image(deployment, container)!r}"
    )
