***REMOVED*** tests/contract/test_k8s_postgres_init_parity_contract.py
"""Contract: K8s postgres-init ConfigMap must mirror docker init scripts.

Closes ***REMOVED***1402.

Problem reproduced: ``docker/postgres/init/`` contains eight SQL bootstrap
scripts (00, 02, 03, 04, 05, 06, 07, 08) that the Compose stack mounts into
``/docker-entrypoint-initdb.d/`` for first-boot Postgres initialization. The
K8s ConfigMap at ``k8s/base/configmaps/postgres-init.yaml`` previously
embedded only 00, 02, 03 — leaving voice transcripts (04), real-estate CRM
(05), lead scoring (06), nurturing analytics (07) and user favorites (08)
schemas uncreated on K8s-deployed Postgres pods.

This contract pins three things:

1. The ConfigMap parses as valid YAML and is shaped as a Kubernetes
   ConfigMap (kind, data mapping).
2. Every ``*.sql`` file in ``docker/postgres/init/`` has a corresponding
   ``data:`` key in the ConfigMap (so kubelet projects it into the init
   directory at the same filename).
3. For the scripts synchronized by issue ***REMOVED***1402 (04 through 08), the
   ConfigMap value is byte-identical to the docker source — they MUST be
   copied verbatim so the K8s and Compose paths produce the same schema.

The pre-existing keys 00/02/03 are NOT enforced byte-identical here because
they have intentional K8s-only divergence (e.g. an additional ``mlflow``
database) that pre-dates this issue and is out of scope for the sync.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKER_INIT_DIR = REPO_ROOT / "docker" / "postgres" / "init"
K8S_CONFIGMAP = REPO_ROOT / "k8s" / "base" / "configmaps" / "postgres-init.yaml"

***REMOVED*** Scripts explicitly synchronized by issue ***REMOVED***1402. Their ConfigMap value
***REMOVED*** must be byte-identical to the docker source.
SYNCED_SCRIPTS = (
    "04-voice-schema.sql",
    "05-realestate-schema.sql",
    "06-lead-scoring-sync.sql",
    "07-nurturing-funnel-analytics.sql",
    "08-user-favorites.sql",
)


def _load_configmap() -> dict:
    """Parse the postgres-init ConfigMap as YAML."""
    with open(K8S_CONFIGMAP, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_configmap_parses_as_valid_yaml() -> None:
    """The ConfigMap must be valid YAML and a Kubernetes ConfigMap."""
    doc = _load_configmap()
    assert isinstance(doc, dict), "ConfigMap must be a YAML mapping"
    assert doc.get("kind") == "ConfigMap", (
        f"expected kind=ConfigMap, got {doc.get('kind')!r}"
    )
    assert "data" in doc and isinstance(doc["data"], dict), (
        "ConfigMap must have a non-empty `data:` mapping"
    )


def test_every_docker_init_script_has_a_configmap_key() -> None:
    """Every ``*.sql`` in ``docker/postgres/init/`` must be embedded.

    Kubelet projects each ``data:`` key as a file at the same path under
    the volume mount (``/docker-entrypoint-initdb.d/``), so missing keys
    mean missing files at first-boot init.
    """
    docker_scripts = sorted(p.name for p in DOCKER_INIT_DIR.glob("*.sql"))
    assert docker_scripts, (
        "expected SQL init scripts under docker/postgres/init/"
    )
    data = _load_configmap()["data"]
    missing = [name for name in docker_scripts if name not in data]
    assert not missing, (
        "K8s postgres-init ConfigMap is missing keys for these docker "
        "init scripts (Compose stack runs them, K8s does not):\n"
        + "\n".join(f"  - {name}" for name in missing)
    )


@pytest.mark.parametrize("script_name", SYNCED_SCRIPTS)
def test_synced_script_content_matches_docker(script_name: str) -> None:
    """Newly-synced scripts (04-08) must be byte-identical to docker.

    These scripts are pure SQL with no shell or env interpolation, so the
    Compose path runs the file directly while the K8s path runs the
    ConfigMap projection. To guarantee parity, the embedded value must
    equal the docker source character-for-character (including trailing
    newline). Any drift means K8s Postgres has a different schema than
    Compose Postgres.
    """
    docker_path = DOCKER_INIT_DIR / script_name
    assert docker_path.exists(), (
        f"docker source missing: {docker_path}"
    )
    docker_content = docker_path.read_text(encoding="utf-8")

    data = _load_configmap()["data"]
    assert script_name in data, (
        f"{script_name} not found in ConfigMap data — sync the docker "
        f"init script into k8s/base/configmaps/postgres-init.yaml"
    )
    k8s_content = data[script_name]

    assert k8s_content == docker_content, (
        f"{script_name} drifted between docker source and K8s ConfigMap.\n"
        f"  docker bytes: {len(docker_content)}\n"
        f"  k8s    bytes: {len(k8s_content)}\n"
        f"Copy verbatim from docker/postgres/init/{script_name}."
    )
