import json
from pathlib import Path


def test_renovate_base_branch_is_dev() -> None:
    data = json.loads(Path("renovate.json").read_text(encoding="utf-8"))
    assert data.get("baseBranchPatterns") == ["dev"]
    assert "baseBranches" not in data


def test_ci_validates_pull_requests_for_dev() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "branches: [main, dev]" in text


def test_deploy_remains_main_only() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "if: github.ref == 'refs/heads/main' && github.event_name == 'push'" in text
