# tests/unit/ingestion/test_package_deprecation_shims.py
"""Contract tests for the ``src.ingestion`` package-level deprecation shims.

Issue #1532 (https://github.com/yastman/rag/issues/1532) tracks the cleanup of
legacy ingestion modules. The audit recorded in
``tests/contract/test_legacy_ingestion_removed_contract.py`` shows that the
underlying modules (``docling_client.py``, ``service.py``) cannot yet be
deleted because the unified pipeline target itself still depends on them
(see ``src/ingestion/unified/targets/qdrant_hybrid_target.py``).

What *can* be locked down right now is the deprecation-shim contract: the
``_DEPRECATED_EXPORTS`` table in ``src/ingestion/__init__.py`` declares
package-level re-exports that emit ``DeprecationWarning`` at attribute-access
time. Those shims are written once and rarely re-validated; a typo in a
target module name, a renamed attribute, or a malformed replacement message
would only surface for users who actually trigger the deprecated path.

This module pins three properties for every entry in
``src.ingestion._DEPRECATED_EXPORTS``:

1. The target ``(module, attribute)`` resolves at runtime — no broken pointers.
2. Accessing the attribute on the package emits exactly one
   ``DeprecationWarning`` whose message contains the canonical replacement
   suggestion.
3. The replacement-suggestion string is itself a valid Python import that
   resolves to the same object (so following the deprecation message does
   not lead users to a dead end).

If a future change moves any of these targets (e.g. the eventual
``DoclingClient`` migration tracked in #1532), the shim table must be
updated in lockstep — these tests will catch the drift.
"""

from __future__ import annotations

import importlib
import re
import warnings
from collections.abc import Iterator
from typing import Any

import pytest


# Canonical regex for the replacement-suggestion grammar used by every shim
# in the package. Example: ``from src.ingestion.docling_client import DoclingClient``.
_REPLACEMENT_RE = re.compile(r"^from\s+([\w.]+)\s+import\s+(\w+)$")


def _shim_entries() -> Iterator[tuple[str, tuple[str, str, str]]]:
    """Yield ``(name, (module, attr, replacement))`` for every declared shim."""
    from src.ingestion import _DEPRECATED_EXPORTS

    yield from _DEPRECATED_EXPORTS.items()


def _shim_ids() -> list[str]:
    """Stable parametrize ids so test failures point at the broken shim by name."""
    return [name for name, _ in _shim_entries()]


def _shim_params() -> list[tuple[str, tuple[str, str, str]]]:
    return list(_shim_entries())


def _reset_package_attribute(name: str) -> None:
    """Drop the cached resolution so the shim re-runs on next attribute access.

    The package caches resolved deprecated attributes on ``globals()`` after the
    first access (see ``src/ingestion/__init__.py``). Without this reset, every
    test except the first parametrize variant would observe a cached value and
    no warning.
    """
    package = importlib.import_module("src.ingestion")
    if name in package.__dict__:
        del package.__dict__[name]


def _import_or_skip(module_name: str, *, shim_name: str, role: str) -> Any:
    """Import ``module_name`` or ``pytest.skip`` if an optional dependency is missing.

    Several shim targets (``src.ingestion.document_parser`` in particular) live
    under the ``ingest`` optional-extras group of this project. In a minimal
    test environment those extras are not installed, so a top-level
    ``import pymupdf``/``import docling`` will raise ``ModuleNotFoundError``
    *inside* the shim's target module — through no fault of the shim. Skip
    cleanly and surface the missing dependency name so CI logs are actionable.
    """
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Distinguish "the shim points at a non-existent module" (real bug)
        # from "an optional dependency required by the target module is not
        # installed in this environment" (env limitation).
        if exc.name == module_name:
            raise
        pytest.skip(
            f"Cannot exercise shim src.ingestion.{shim_name} in {role}: "
            f"target module {module_name} requires optional dependency "
            f"{exc.name!r} (likely from the `ingest` extras group). "
            f"Install with `uv sync --extra ingest` to validate this shim."
        )


@pytest.mark.parametrize(("name", "target"), _shim_params(), ids=_shim_ids())
def test_deprecated_export_target_module_imports(name: str, target: tuple[str, str, str]) -> None:
    """The shim's target module must be importable.

    A typo in the module name would only surface when a user actually
    accesses the deprecated attribute — pin it here instead.
    """
    target_module, _, _ = target
    _import_or_skip(target_module, shim_name=name, role="target module check")


@pytest.mark.parametrize(("name", "target"), _shim_params(), ids=_shim_ids())
def test_deprecated_export_target_attribute_exists(name: str, target: tuple[str, str, str]) -> None:
    """The shim must point at a real attribute on its target module."""
    target_module, target_attr, _ = target
    module = _import_or_skip(target_module, shim_name=name, role="attribute check")
    assert hasattr(module, target_attr), (
        f"src.ingestion._DEPRECATED_EXPORTS[{name!r}] points at "
        f"{target_module}.{target_attr}, but that attribute does not exist."
    )


@pytest.mark.parametrize(("name", "target"), _shim_params(), ids=_shim_ids())
def test_deprecated_export_replacement_message_is_valid_import(
    name: str, target: tuple[str, str, str]
) -> None:
    """The replacement message must itself be a runnable import statement.

    Users who follow the deprecation warning verbatim must land on a working
    import — otherwise the warning sends them into a dead end.
    """
    _, _, replacement = target
    match = _REPLACEMENT_RE.match(replacement)
    assert match is not None, (
        f"Replacement suggestion for src.ingestion.{name!r} is not parseable as "
        f"`from <module> import <attr>`: {replacement!r}"
    )
    suggested_module, suggested_attr = match.groups()
    module = _import_or_skip(suggested_module, shim_name=name, role="replacement-message check")
    assert hasattr(module, suggested_attr), (
        f"Replacement {replacement!r} for src.ingestion.{name!r} would fail at "
        f"runtime: {suggested_module} has no attribute {suggested_attr!r}."
    )


@pytest.mark.parametrize(("name", "target"), _shim_params(), ids=_shim_ids())
def test_deprecated_export_replacement_resolves_to_same_object(
    name: str, target: tuple[str, str, str]
) -> None:
    """The replacement suggestion must resolve to the same object as the shim.

    Otherwise the deprecation warning would silently change the user's import
    semantics — e.g. shadowing a class with an unrelated function of the same
    name.
    """
    target_module, target_attr, replacement = target
    match = _REPLACEMENT_RE.match(replacement)
    assert match is not None  # already covered by the previous test
    suggested_module, suggested_attr = match.groups()

    target_mod = _import_or_skip(
        target_module, shim_name=name, role="object-identity check (shim side)"
    )
    suggested_mod = _import_or_skip(
        suggested_module, shim_name=name, role="object-identity check (replacement side)"
    )
    shim_obj = getattr(target_mod, target_attr)
    suggested_obj = getattr(suggested_mod, suggested_attr)
    assert shim_obj is suggested_obj, (
        f"Replacement suggestion for src.ingestion.{name!r} resolves to a "
        f"different object than the shim: shim -> {shim_obj!r}, "
        f"replacement -> {suggested_obj!r}."
    )


@pytest.mark.parametrize(("name", "target"), _shim_params(), ids=_shim_ids())
def test_deprecated_export_attribute_access_emits_warning(
    name: str, target: tuple[str, str, str]
) -> None:
    """Accessing the deprecated attribute on the package emits exactly one
    ``DeprecationWarning`` whose message includes the canonical replacement.

    The first access resolves and caches the attribute on the package's
    ``globals()``; subsequent accesses go through the cached value and do
    *not* re-emit the warning. The fixture resets that cache so each shim is
    exercised through its lazy-resolution path.
    """
    # Pre-flight: if the target module needs an optional dep that isn't
    # installed, skip — same rule as the simpler tests above.
    target_module, _, _ = target
    _import_or_skip(target_module, shim_name=name, role="warning emission check")

    _reset_package_attribute(name)

    package = importlib.import_module("src.ingestion")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value: Any = getattr(package, name)

    assert value is not None

    deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation_warnings) == 1, (
        f"Expected exactly one DeprecationWarning when accessing "
        f"src.ingestion.{name}, got {len(deprecation_warnings)}: "
        f"{[str(w.message) for w in deprecation_warnings]}"
    )

    message = str(deprecation_warnings[0].message)
    _, _, replacement = target
    assert replacement in message, (
        f"DeprecationWarning for src.ingestion.{name} did not include the "
        f"canonical replacement {replacement!r}; got message {message!r}."
    )
    assert f"src.ingestion.{name}" in message, (
        f"DeprecationWarning for src.ingestion.{name} did not name the "
        f"deprecated attribute; got message {message!r}."
    )


def test_deprecated_exports_table_is_non_empty() -> None:
    """Sanity check: the audit assumes there is something to audit."""
    from src.ingestion import _DEPRECATED_EXPORTS

    assert _DEPRECATED_EXPORTS, (
        "src.ingestion._DEPRECATED_EXPORTS is unexpectedly empty. If the "
        "table was emptied as part of #1532, also remove this contract test "
        "and the per-package shim plumbing in src/ingestion/__init__.py."
    )
