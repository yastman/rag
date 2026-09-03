"""Contract: Dockerfile.ingestion must stay free of model-cache offline logic.

card_4972d1f2f598 introduced conditional HF offline gating for the Docling-era
model pre-warm. Issue #3235 removed the converter stack and every model
pre-warm layer, so the inverse now holds: the ingestion image must not
reference HuggingFace offline mode at all — there is no model cache to gate.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def test_hf_hub_offline_not_hardcoded_in_dockerfile() -> None:
    """HF_HUB_OFFLINE=1 must NOT appear as a hardcoded ENV in Dockerfile.ingestion.

    The ingestion image has no model cache (#3235); an offline flag would be
    pure legacy weight.
    """
    text = (REPO_ROOT / "Dockerfile.ingestion").read_text(encoding="utf-8")
    env_lines = [
        line.strip()
        for line in text.splitlines()
        if "HF_HUB_OFFLINE" in line and not line.lstrip().startswith("#")
    ]
    assert not env_lines, (
        f"Dockerfile.ingestion must not hardcode HF_HUB_OFFLINE; Found: {env_lines}"
    )


def test_entrypoint_has_no_model_cache_offline_logic() -> None:
    """entrypoint.sh must not gate HF offline mode — no model cache exists (#3235).

    The card_4972d1f2f598 conditional gate was removed together with the
    Docling/HuggingFace pre-warm layers; if it reappears, so did a model cache.
    """
    text = (REPO_ROOT / "docker/ingestion/entrypoint.sh").read_text(encoding="utf-8")
    for stale_marker in ("hf_offline", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_CACHE"):
        assert stale_marker not in text, (
            f"docker/ingestion/entrypoint.sh still references '{stale_marker}'; "
            "the HuggingFace model-cache offline authority was removed by #3235 "
            "(Markdown-only ingestion needs no local models)."
        )


def test_dockerfile_has_no_model_prewarm_layers() -> None:
    """Dockerfile.ingestion must not bake Docling or HuggingFace model caches."""
    text = (REPO_ROOT / "Dockerfile.ingestion").read_text(encoding="utf-8")
    for stale_marker in ("docling", "snapshot_download", "/opt/huggingface", "/opt/docling"):
        assert stale_marker not in text, (
            f"Dockerfile.ingestion still contains model pre-warm artifact "
            f"'{stale_marker}' removed by #3235."
        )
