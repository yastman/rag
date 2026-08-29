"""Contract for checkout-local dotenv loading in the shared pytest bootstrap."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CONFTEST = REPO_ROOT / "tests" / "conftest.py"


def test_root_conftest_scopes_dotenv_to_current_checkout() -> None:
    """A nested worktree must not discover an ancestor checkout's ``.env``."""
    tree = ast.parse(ROOT_CONFTEST.read_text(encoding="utf-8"), filename=str(ROOT_CONFTEST))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_dotenv"
    ]

    assert len(calls) == 1, "shared pytest bootstrap must load dotenv exactly once"
    call = calls[0]
    assert call.args or any(keyword.arg == "dotenv_path" for keyword in call.keywords), (
        "load_dotenv must receive an explicit checkout-local path"
    )
    path_expression = (
        call.args[0]
        if call.args
        else next(keyword.value for keyword in call.keywords if keyword.arg == "dotenv_path")
    )
    path_dump = ast.dump(path_expression)
    assert "__file__" in path_dump and ".env" in path_dump, (
        "dotenv path must be derived from tests/conftest.py and end at .env"
    )
    assert not any(keyword.arg == "override" for keyword in call.keywords), (
        "dotenv must keep its default non-overriding behavior"
    )

    guarded_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and "_env_disabled" in ast.dump(node.test)
        and call in set(ast.walk(ast.Module(body=node.body, type_ignores=[])))
    ]
    assert guarded_calls, "PYTHON_DOTENV_DISABLED must continue to guard dotenv loading"
