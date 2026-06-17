"""Contract tests for Makefile remote-core-* MacBook staging targets."""

from pathlib import Path


ROOT = Path(__file__).parents[2]
MAKEFILE = ROOT / "Makefile"


def test_remote_core_services_are_minimal() -> None:
    text = MAKEFILE.read_text()
    assert "REMOTE_CORE_SERVICES" in text
    for service in ["postgres", "redis", "qdrant", "bge-m3", "bot"]:
        assert service in text
    for service in ["clickhouse", "minio", "langfuse"]:
        core_line = next(
            line for line in text.splitlines() if line.startswith("REMOTE_CORE_SERVICES")
        )
        assert service not in core_line


def test_remote_core_up_uses_bot_profile() -> None:
    text = MAKEFILE.read_text()
    assert "remote-core-up:" in text
    section = text[text.index("remote-core-up:") : text.index("remote-full-up:")]
    assert "--profile bot" in section
    assert "$(REMOTE_CORE_SERVICES)" in section


def test_remote_core_health_checks_full_core() -> None:
    text = MAKEFILE.read_text()
    assert "remote-core-health:" in text
    section = text[text.index("remote-core-health:") : text.index("remote-service-health:")]
    for expected in ["qdrant", "bge-m3", "postgres", "redis", "restarts:"]:
        assert expected in section
