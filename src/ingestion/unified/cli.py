# SPDX-License-Identifier: MIT
"""Backward-compat re-export — split into commands + main."""

from src.ingestion.unified.commands import *  # noqa: F403
from src.ingestion.unified.main import main, setup_logging  # noqa: F401


if __name__ == "__main__":
    # #3235: the module previously re-exported main() without a __main__
    # guard, so `python -m src.ingestion.unified.cli ...` (the documented
    # entrypoint, Dockerfile.ingestion CMD, and Makefile targets) exited 0
    # without running anything.
    import sys

    sys.exit(main())
