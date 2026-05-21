from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/codeql.yml")


def test_codeql_workflow_actions_are_sha_pinned() -> None:
    """CodeQL workflow actions must follow the repo SHA-pinning convention."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github/codeql-action/init@9e0d7b8d25671d64c341c19c0152d693099fb5ba # v4" in text
    assert "github/codeql-action/analyze@9e0d7b8d25671d64c341c19c0152d693099fb5ba # v4" in text
    assert "github/codeql-action/init@v4" not in text
    assert "github/codeql-action/analyze@v4" not in text


def test_codeql_workflow_uses_least_privilege_permissions() -> None:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert data["permissions"] == {"contents": "read"}
    assert data["jobs"]["analyze"]["permissions"] == {
        "contents": "read",
        "security-events": "write",
    }
