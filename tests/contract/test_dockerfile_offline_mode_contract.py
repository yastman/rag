"""Contract: Dockerfile.ingestion offline-mode must be conditional, not hardcoded.

card_4972d1f2f598 — HF_HUB_OFFLINE=1 must not be a hardcoded ENV in the
Dockerfile; instead entrypoint.sh must gate it on cache presence (hf_offline
variable) so a failed build-time pre-warm doesn't brick the container at runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT: Path = Path(__file__).resolve().parents[2]


@pytest.mark.no_services
def test_hf_hub_offline_not_hardcoded_in_dockerfile() -> None:
    """HF_HUB_OFFLINE=1 must NOT appear as a hardcoded ENV in Dockerfile.ingestion.

    If pre-warm silently fails, a hardcoded offline flag leaves the container
    with no models and no ability to download them.
    """
    text = (REPO_ROOT / "Dockerfile.ingestion").read_text(encoding="utf-8")
    env_lines = [
        line.strip()
        for line in text.splitlines()
        if "HF_HUB_OFFLINE" in line and not line.lstrip().startswith("#")
    ]
    # No uncommented ENV assignment of HF_HUB_OFFLINE should exist
    assert not env_lines, (
        "Dockerfile.ingestion must not hardcode HF_HUB_OFFLINE; "
        "gate it conditionally in entrypoint.sh instead. "
        f"Found: {env_lines}"
    )


@pytest.mark.no_services
def test_entrypoint_has_conditional_hf_offline_logic() -> None:
    """entrypoint.sh must contain the hf_offline conditional gate (card_4972d1f2f598).

    The guard checks whether the HF model cache is populated before enforcing
    offline mode, allowing runtime download when build-time pre-warm failed.
    """
    text = (REPO_ROOT / "docker/ingestion/entrypoint.sh").read_text(encoding="utf-8")
    assert "hf_offline" in text, (
        "docker/ingestion/entrypoint.sh must contain 'hf_offline' conditional "
        "logic that gates HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE on cache presence. "
        "See card_4972d1f2f598."
    )
    assert "HF_HUB_OFFLINE" in text, (
        "docker/ingestion/entrypoint.sh must export HF_HUB_OFFLINE when cache is present."
    )
    assert "TRANSFORMERS_OFFLINE" in text, (
        "docker/ingestion/entrypoint.sh must export TRANSFORMERS_OFFLINE when cache is present."
    )
