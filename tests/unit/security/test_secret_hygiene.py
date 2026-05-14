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
        project_root / "compose.yml",
        project_root / "compose.dev.yml",
        project_root / "compose.vps.yml",
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


@pytest.mark.timeout(0)
def test_no_non_example_env_files_tracked():
    """Ensure no non-example .env files are tracked in git (#1325)."""
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    tracked_envs = [
        line
        for line in result.stdout.splitlines()
        if Path(line).name.startswith(".env") and not line.endswith(".example")
    ]
    assert not tracked_envs, (
        f"Real .env files must not be tracked in git: {tracked_envs}\n"
        "Add them to .gitignore and remove from the index."
    )


@pytest.mark.timeout(0)
def test_env_example_files_use_safe_placeholders():
    """Ensure .env.example files do not contain real-looking API key prefixes (#1325)."""
    import re
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent
    env_examples = [
        project_root / ".env.example",
        project_root / ".env.local.example",
        project_root / "telegram_bot" / ".env.example",
        project_root / "k8s" / "secrets" / ".env.example",
    ]

    # Common real API key prefixes that should not appear as example values
    bad_prefixes = [
        r"sk-ant-",
        r"sk-proj-",
        r"sk-",
        r"gsk_",
        r"csk-",
        r"pa-",
        r"pk-lf-",
        r"sk-lf-",
    ]
    prefix_pattern = re.compile(r"^\s*[A-Z_][A-Z0-9_]*=\s*.*(" + "|".join(bad_prefixes) + r")")
    # Allow placeholder-style values like <your-key> or empty values
    placeholder_pattern = re.compile(r"^\s*[A-Z_][A-Z0-9_]*=\s*(<.*>|\s*)$")

    errors = []
    for env_file in env_examples:
        if not env_file.exists():
            continue
        for lineno, line in enumerate(env_file.read_text().splitlines(), 1):
            if prefix_pattern.search(line) and not placeholder_pattern.search(line):
                errors.append(f"  {env_file.name}:{lineno}: {line.strip()}")

    assert not errors, (
        "Security violation: .env.example files contain values that resemble real API keys.\n"
        "Use placeholder format like <your-key-here> or leave empty.\n" + "\n".join(errors)
    )
