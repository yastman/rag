"""Contract: no broken relative Markdown links in the repository.

Runs scripts/check_markdown_links.py and asserts exit 0 (zero broken links).
This is a static file scan — no network access, fast.

Prevents dead-link regressions after doc moves or file deletions.
Ref: card_65f42e4b1dfa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_markdown_links.py"


def test_no_broken_markdown_links() -> None:
    """scripts/check_markdown_links.py must exit 0 (0 broken relative links)."""
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"Broken relative Markdown links detected:\n{result.stdout}{result.stderr}\n"
        "Fix the links or update the target files before merging."
    )
