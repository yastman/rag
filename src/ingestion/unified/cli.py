# SPDX-License-Identifier: MIT
"""Backward-compat re-export — split into commands + main."""

from src.ingestion.unified.commands import *  # noqa: F403
from src.ingestion.unified.main import main, setup_logging  # noqa: F401
