from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_markdown_links.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_markdown_links_under_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_markdown_files_skips_temp_dependency_dirs(tmp_path) -> None:
    checker = _load_module()
    temp_readme = tmp_path / "tool" / "deps" / "tmp" / "package" / "README.md"
    temp_readme.parent.mkdir(parents=True)
    temp_readme.write_text("[missing](MISSING.md)\n", encoding="utf-8")

    assert temp_readme.resolve() not in checker.collect_markdown_files(tmp_path)


def test_current_repository_markdown_links_are_valid() -> None:
    checker = _load_module()

    assert checker.check_links(REPO_ROOT) == []


@pytest.mark.parametrize("relative", ["docs/README.md", "PROJECT.md", "src/AGENTS.override.md"])
def test_missing_links_are_checked_inside_a_linked_worktree(tmp_path, relative) -> None:
    checker = _load_module()
    root = tmp_path / ".worktrees" / "task"
    document = root / relative
    document.parent.mkdir(parents=True)
    document.write_text("[missing](missing.md)\n", encoding="utf-8")

    assert checker.check_links(root) == [
        (document.resolve(), 1, "missing.md", (document.parent / "missing.md").resolve())
    ]
