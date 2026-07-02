"""Shared helpers for bot error inspection."""

from __future__ import annotations

from collections.abc import Iterator


def walk_traceback_frames(exc: BaseException) -> Iterator[tuple[str, str]]:
    """Yield traceback frames as normalized ``(filename, function_name)`` pairs."""
    tb = exc.__traceback__
    while tb is not None:
        yield tb.tb_frame.f_code.co_filename.lower(), tb.tb_frame.f_code.co_name
        tb = tb.tb_next
