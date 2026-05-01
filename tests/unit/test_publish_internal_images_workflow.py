from pathlib import Path


def test_publish_semver_major_minor_tags() -> None:
    text = Path(".github/workflows/publish-internal-images.yml").read_text(encoding="utf-8")
    assert "type=semver,pattern={{major}}.{{minor}}" in text


def test_publish_sbom_or_provenance_enabled() -> None:
    text = Path(".github/workflows/publish-internal-images.yml").read_text(encoding="utf-8")
    assert "provenance:" in text or "sbom:" in text


def test_publish_uses_build_push_action_with_cache() -> None:
    text = Path(".github/workflows/publish-internal-images.yml").read_text(encoding="utf-8")
    assert "docker/build-push-action@" in text
    assert "cache-from:" in text
    assert "cache-to:" in text
