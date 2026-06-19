#!/usr/bin/env python3
"""Setup Langfuse Score Configs — Langfuse removed (#2844).

This script is a no-op stub. The Langfuse ml stack was removed in #2844.
Score configs are no longer managed here.
"""

from __future__ import annotations

import logging
import sys


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.warning("Langfuse removed (#2844) — setup_score_configs is a no-op.")
    sys.exit(0)


if __name__ == "__main__":
    main()
