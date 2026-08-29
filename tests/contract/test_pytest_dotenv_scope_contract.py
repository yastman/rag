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
    evaluated_path = eval(
        compile(ast.Expression(path_expression), str(ROOT_CONFTEST), "eval"),
        {"Path": Path, "__file__": str(ROOT_CONFTEST), "__builtins__": {}},
    )
    assert evaluated_path == REPO_ROOT / ".env", (
        "dotenv path must resolve to the current checkout root's .env"
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
    assert len(guarded_calls) == 1, (
        "PYTHON_DOTENV_DISABLED must directly guard dotenv loading exactly once"
    )

    guard = guarded_calls[0]
    instrumented_guard = ast.If(
        test=guard.test,
        body=[
            ast.Expr(
                value=ast.Call(
                    func=ast.Name(id="_record_load", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                )
            )
        ],
        orelse=[],
    )
    guard_code = compile(
        ast.fix_missing_locations(ast.Module(body=[instrumented_guard], type_ignores=[])),
        str(ROOT_CONFTEST),
        "exec",
    )
    load_decisions = []
    for disabled in (False, True):
        loads = []
        exec(
            guard_code,
            {
                "_env_disabled": disabled,
                "_record_load": lambda loads=loads: loads.append(True),
                "__builtins__": {},
            },
        )
        load_decisions.append(bool(loads))

    assert load_decisions == [True, False], (
        "dotenv loading must run when enabled and be skipped when disabled"
    )
