"""Runtime contract for the pytest bootstrap dotenv policy (#3447)."""

from __future__ import annotations

import os
import runpy
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CONFTEST = REPO_ROOT / "tests" / "conftest.py"


def test_root_conftest_never_loads_dotenv_and_disables_later_loads() -> None:
    """No repository .env is ever loaded in test processes (#3447).

    The bootstrap must not inherit ambient credentials/endpoints, and it
    must set ``PYTHON_DOTENV_DISABLED=1`` so no later import can load a
    dotenv file either — with or without an ambient ``PYTHON_DOTENV_DISABLED``
    in the invoking shell.
    """
    env = os.environ.copy()
    env.pop("PYTHON_DOTENV_DISABLED", None)

    with (
        patch.dict(os.environ, env, clear=True),
        patch("dotenv.load_dotenv") as load_dotenv,
    ):
        runpy.run_path(str(ROOT_CONFTEST), run_name="pytest_dotenv_scope_contract")
        assert os.environ.get("PYTHON_DOTENV_DISABLED") == "1"

    load_dotenv.assert_not_called()
