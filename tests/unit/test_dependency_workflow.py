import json
from pathlib import Path


def test_renovate_base_branch_is_dev() -> None:
    data = json.loads(Path("renovate.json").read_text(encoding="utf-8"))
    assert data["baseBranches"] == ["dev"]
