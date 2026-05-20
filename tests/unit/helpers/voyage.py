"""Test helpers for optional Voyage AI dependencies."""

from __future__ import annotations

import importlib

import pytest


def skip_if_voyageai_unusable() -> None:
    """Skip tests when the optional voyageai extra cannot be imported.

    Under Python 3.14 the currently pinned voyageai package can raise a
    Pydantic V1 ``ValueError`` during import, not just ``ImportError``.
    """
    try:
        importlib.import_module("voyageai")
    except Exception as exc:
        pytest.skip(f"voyageai optional extra unusable: {exc!r}", allow_module_level=True)
