"""Backward-compatible shim for runtime prompt templates."""

from __future__ import annotations

import sys

from src.runtime.integrations import prompt_templates as _impl


sys.modules[__name__] = _impl
