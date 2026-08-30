"""Runtime contract for checkout-local dotenv loading in pytest bootstrap."""

from __future__ import annotations

import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CONFTEST = REPO_ROOT / "tests" / "conftest.py"


@pytest.mark.parametrize(("disabled", "should_load"), ((None, True), ("1", False)))
def test_root_conftest_scopes_dotenv_to_current_checkout(
    disabled: str | None,
    should_load: bool,
) -> None:
    """The bootstrap loads only this checkout's dotenv file when enabled."""
    env = os.environ.copy()
    if disabled is None:
        env.pop("PYTHON_DOTENV_DISABLED", None)
    else:
        env["PYTHON_DOTENV_DISABLED"] = disabled

    with (
        patch.dict(os.environ, env, clear=True),
        patch("dotenv.load_dotenv") as load_dotenv,
    ):
        runpy.run_path(str(ROOT_CONFTEST), run_name="pytest_dotenv_scope_contract")

    if should_load:
        load_dotenv.assert_called_once_with(dotenv_path=REPO_ROOT / ".env")
    else:
        load_dotenv.assert_not_called()
