"""Compatibility helpers for deprecated package-level exports."""

from __future__ import annotations

import warnings
from importlib import import_module
from typing import Any


DeprecatedExport = tuple[str, str, str]


def load_deprecated_package_export(
    *,
    module_name: str,
    attr_name: str,
    target: DeprecatedExport,
) -> Any:
    """Resolve a deprecated package export and emit a deprecation warning."""
    target_module_name, target_attr_name, replacement = target
    warnings.warn(
        (
            f"{module_name}.{attr_name} is a deprecated package export; "
            f"import {replacement} instead."
        ),
        DeprecationWarning,
        stacklevel=2,
    )
    module = import_module(target_module_name)
    return getattr(module, target_attr_name)
