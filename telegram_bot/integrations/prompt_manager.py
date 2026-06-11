"""Backward-compatible shim for runtime prompt management."""

from __future__ import annotations

import sys

from src.runtime.integrations import prompt_manager as _impl


sys.modules[__name__] = _impl
