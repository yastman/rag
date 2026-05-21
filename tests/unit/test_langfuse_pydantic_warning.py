"""Contract tests for Issue ***REMOVED***1381: suppress Langfuse Pydantic V1 warning.

Langfuse SDK 4.3.x emits a ``UserWarning`` on every import under
Python 3.14 because its internal compat shim still touches
``pydantic.v1``::

    UserWarning: Core Pydantic V1 functionality isn't compatible with
    Python 3.14 or greater.

The warning is harmless today but pollutes every bot run, test, and
validation script. The fix is a *narrowly scoped* warning filter
installed by ``telegram_bot.observability`` before the Langfuse import
so the noise is gone in CI logs and ``logs/bot-run.log``.

These tests do not require Python 3.14 — they exercise the filter
helper directly with a synthetic warning, which is how aiogram's own
test-suite validates filter contracts.
"""

from __future__ import annotations

import warnings


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Filter helper contract
***REMOVED*** ---------------------------------------------------------------------------


def test_install_langfuse_warning_filters_is_exposed() -> None:
    """The observability module must expose the filter installer publicly."""
    from telegram_bot import observability

    assert hasattr(observability, "_install_langfuse_warning_filters"), (
        "telegram_bot.observability must expose `_install_langfuse_warning_filters` "
        "so the suppression target is documented and testable (issue ***REMOVED***1381)."
    )


def test_filter_suppresses_pydantic_v1_warning() -> None:
    """The installed filter must drop the Langfuse Pydantic V1 UserWarning."""
    from telegram_bot.observability import _install_langfuse_warning_filters

    with warnings.catch_warnings(record=True) as captured:
        warnings.resetwarnings()
        warnings.simplefilter("always")
        _install_langfuse_warning_filters()
        ***REMOVED*** Replay the exact warning Langfuse emits at import time.
        warnings.warn(
            "Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
            UserWarning,
            stacklevel=1,
        )

    pydantic_warnings = [w for w in captured if "Core Pydantic V1" in str(w.message)]
    assert not pydantic_warnings, (
        "issue ***REMOVED***1381: Langfuse Pydantic V1 UserWarning must be suppressed; "
        f"saw: {[str(w.message) for w in pydantic_warnings]!r}"
    )


def test_filter_does_not_swallow_unrelated_warnings() -> None:
    """The filter must be narrow — only the Pydantic V1 message is dropped."""
    from telegram_bot.observability import _install_langfuse_warning_filters

    with warnings.catch_warnings(record=True) as captured:
        warnings.resetwarnings()
        warnings.simplefilter("always")
        _install_langfuse_warning_filters()
        ***REMOVED*** Unrelated UserWarning must still surface.
        warnings.warn("totally unrelated warning", UserWarning, stacklevel=1)
        ***REMOVED*** DeprecationWarning must still surface.
        warnings.warn("totally unrelated deprecation", DeprecationWarning, stacklevel=1)

    user_msgs = [str(w.message) for w in captured if w.category is UserWarning]
    deprecation_msgs = [str(w.message) for w in captured if w.category is DeprecationWarning]
    assert "totally unrelated warning" in user_msgs, (
        "Filter must only drop the Pydantic V1 message; unrelated UserWarnings "
        f"must still be visible. Captured: {user_msgs!r}"
    )
    assert "totally unrelated deprecation" in deprecation_msgs, (
        f"Filter must not drop DeprecationWarning. Captured: {deprecation_msgs!r}"
    )


def test_filter_runs_at_module_import() -> None:
    """The filter must be applied as a side-effect of importing the module.

    Pytest's own ``filterwarnings`` plugin resets ``warnings.filters`` between
    tests, so we re-import the module under a clean filter state and then
    inspect ``warnings.filters`` to confirm the import installs the filter.
    """
    import importlib
    import sys

    ***REMOVED*** Reset filter state so we observe the import-time side effect cleanly.
    with warnings.catch_warnings():
        warnings.resetwarnings()
        ***REMOVED*** Force re-import so module-level code runs again.
        sys.modules.pop("telegram_bot.observability", None)
        importlib.import_module("telegram_bot.observability")

        ***REMOVED*** Each entry in warnings.filters is a 5-tuple:
        ***REMOVED*** (action, message-regex, category, module-regex, lineno).
        pydantic_filters = [
            f for f in warnings.filters if f[1] is not None and "Pydantic V1" in f[1].pattern
        ]
        assert pydantic_filters, (
            "issue ***REMOVED***1381: importing telegram_bot.observability must install a "
            "warnings filter targeting the Langfuse Pydantic V1 message"
        )
        actions = {f[0] for f in pydantic_filters}
        assert "ignore" in actions, (
            "The Pydantic V1 filter must use action='ignore' to suppress the warning; "
            f"saw actions={actions!r}"
        )


def test_no_blanket_userwarning_filter_added() -> None:
    """The fix must not blanket-ignore *all* UserWarnings."""
    from telegram_bot import observability  ***REMOVED*** noqa: F401

    ***REMOVED*** Look for any UserWarning filter without a message regex — that would be
    ***REMOVED*** a blanket suppression and would hide unrelated warnings.
    blanket = [
        f
        for f in warnings.filters
        if f[0] == "ignore" and f[2] is UserWarning and (f[1] is None or f[1].pattern in {".*", ""})
    ]
    assert not blanket, (
        "issue ***REMOVED***1381: filter must target the specific Langfuse Pydantic V1 "
        f"message, not blanket-ignore UserWarning. Found: {blanket!r}"
    )
