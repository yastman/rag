"""Contract: no stale service-level ``requirements.txt`` manifests (***REMOVED***1620).

Two ``requirements.txt`` files used to live alongside ``pyproject.toml``
files at:

- ``telegram_bot/requirements.txt``
- ``services/user-base/requirements.txt``

They drifted from the active manifests (e.g. ``langfuse>=3.0.0`` while
``pyproject.toml`` requires ``>=4.0.0,<5.0``; ``sentence-transformers>=2.2.0``
while ``pyproject.toml`` uses ``>=3.2.0``). Docker builds do not consume
them — every Dockerfile in this repo runs ``uv sync`` against
``pyproject.toml`` / ``uv.lock``. Static search across the repo found no
caller that runs ``pip install -r ...requirements.txt``.

Removing them eliminates the drift surface. This contract guards the
removal: if a service-level ``requirements.txt`` is reintroduced, the
new file must be paired with a sync/check mechanism, which is out of
scope of the present cleanup. Until that exists, the contract fails
when these files reappear.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN: tuple[Path, ...] = (
    REPO_ROOT / "telegram_bot" / "requirements.txt",
    REPO_ROOT / "services" / "user-base" / "requirements.txt",
)


@pytest.mark.parametrize("path", FORBIDDEN, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_stale_requirements_txt_is_absent(path: Path) -> None:
    if path.exists():
        raise AssertionError(
            f"Stale '{path.relative_to(REPO_ROOT)}' has reappeared. "
            "Service runtimes use 'uv sync' against pyproject.toml/uv.lock; "
            "no caller runs 'pip install -r ...requirements.txt'. If a "
            "consumer truly needs a requirements.txt, add an automated "
            "sync/check tying it to pyproject.toml constraints (***REMOVED***1620)."
        )


def test_no_makefile_or_dockerfile_invokes_pip_install_dash_r() -> None:
    """Defensive: nothing in the repo should run ``pip install -r ...txt`` (***REMOVED***1620)."""
    repo_root = REPO_ROOT
    suspects: list[str] = []
    for pattern in ("**/Dockerfile*", "**/Makefile", "**/*.sh", "**/*.yml", "**/*.yaml"):
        for path in repo_root.glob(pattern):
            ***REMOVED*** Skip any auto-vendored or third-party trees
            if any(part in {".git", ".venv", "node_modules", "site"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if "pip install -r" in line and "requirements.txt" in line:
                    suspects.append(f"{path.relative_to(repo_root)}:{line_no}: {line.strip()}")
    assert not suspects, (
        "Found `pip install -r requirements.txt` references. Either keep the "
        "matching requirements.txt and add a sync mechanism, or migrate the "
        "consumer to `uv sync` (***REMOVED***1620):\n  - " + "\n  - ".join(suspects)
    )
