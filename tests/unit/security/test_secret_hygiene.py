#!/usr/bin/env python3
"""Security hygiene tests - detect hardcoded secrets and IPs in test scripts."""

import pytest


@pytest.mark.timeout(0)  # Disable timeout for this test
def test_no_hardcoded_qdrant_secrets_in_integration_tests():
    """Ensure integration tests use environment variables for sensitive data."""
    import re
    from pathlib import Path

    test_file = Path(__file__).parent.parent.parent / "integration" / "test_basic_connection.py"

    if not test_file.exists():
        return  # File doesn't exist, skip

    content = test_file.read_text()

    # Check for hardcoded IP addresses
    ip_pattern = r'QDRANT_URL\s*=\s*["\']http://\d+\.\d+\.\d+\.\d+:\d+["\']'
    ip_matches = re.findall(ip_pattern, content)

    # Check for hardcoded API keys (long hex strings)
    key_pattern = r'QDRANT_API_KEY\s*=\s*["\'][a-f0-9]{64}["\']'
    key_matches = re.findall(key_pattern, content)

    errors = []
    if ip_matches:
        errors.append(f"Found hardcoded Qdrant URL: {ip_matches[0]}")
    if key_matches:
        errors.append('Found hardcoded API key: QDRANT_API_KEY = "***" (64 chars)')

    assert not errors, (
        f"Security violation: hardcoded secrets detected in {test_file.name}:\n"
        + "\n".join(f"  - {err}" for err in errors)
        + "\n\nUse os.getenv() or environment variables instead."
    )


@pytest.mark.timeout(0)
def test_compose_redis_uses_requirepass():
    """Ensure Docker Compose Redis services require authentication."""
    import re
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent
    compose_files = [
        project_root / "docker-compose.dev.yml",
        project_root / "docker-compose.vps.yml",
    ]

    errors = []
    for compose_file in compose_files:
        if not compose_file.exists():
            continue

        content = compose_file.read_text()

        # Find redis service block
        redis_service_match = re.search(r"^\s+redis:\s*\n((?:\s{2,}.+\n)*)", content, re.MULTILINE)

        if not redis_service_match:
            continue  # No redis service in this file

        redis_block = redis_service_match.group(1)

        # Check for --requirepass in command
        if "--requirepass" not in redis_block:
            errors.append(f"{compose_file.name}: Redis service missing --requirepass in command")

    assert not errors, (
        "Security violation: Redis authentication not enforced:\n"
        + "\n".join(f"  - {err}" for err in errors)
        + "\n\nAdd --requirepass ${REDIS_PASSWORD} to redis-server command."
    )


@pytest.mark.timeout(0)
def test_stack_doc_mentions_redis_auth_requirement():
    """Ensure PROJECT_STACK.md documents the REDIS_PASSWORD requirement."""
    from pathlib import Path

    content = (Path(__file__).parent.parent.parent.parent / "docs" / "PROJECT_STACK.md").read_text()
    assert "REDIS_PASSWORD" in content, (
        "docs/PROJECT_STACK.md must document the REDIS_PASSWORD requirement. "
        "Redis auth is enforced in compose and k8s — the stack doc should reflect this."
    )


@pytest.mark.timeout(0)
def test_k8s_bot_redis_password_declared_before_redis_url():
    """K8s expands $(VAR) only from previously declared env vars in the same list."""
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent
    deployment_file = project_root / "k8s" / "base" / "bot" / "deployment.yaml"

    if not deployment_file.exists():
        return

    content = deployment_file.read_text()
    redis_url_pos = content.find("- name: REDIS_URL")
    redis_password_pos = content.find("- name: REDIS_PASSWORD")

    assert redis_url_pos != -1, "k8s/base/bot/deployment.yaml missing REDIS_URL env var"
    assert redis_password_pos != -1, "k8s/base/bot/deployment.yaml missing REDIS_PASSWORD env var"
    assert redis_password_pos < redis_url_pos, (
        "REDIS_PASSWORD must be declared before REDIS_URL because Kubernetes "
        "expands $(REDIS_PASSWORD) only from previously defined env vars."
    )
