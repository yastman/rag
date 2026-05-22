"""Contract test for issue #1951 — lifecycle Langfuse trace helpers stay
deduplicated.

`src/voice/observability.py` and `src/ingestion/unified/observability.py`
historically each carried their own copy of:

  * a ``{family}_session_id(key)`` builder
  * an ``update_{family}_trace(...)`` function that opened a Langfuse span
    via ``lf.start_as_current_observation(...)`` and propagated attributes
  * a ``{trace_or_try_*}_{family}_session(...)`` wrapper that swallowed
    exceptions

That was a ~70-line copy-paste between the two families. The shared kernel
now lives in ``src/observability.py``:

  * :func:`make_lifecycle_session_id`
  * :func:`update_lifecycle_trace`
  * :func:`try_update_lifecycle_trace_async`

This contract test prevents the duplication from coming back. The two
family modules MUST import the kernel and MUST NOT call the underlying
Langfuse SDK lifecycle primitives (``start_as_current_observation``,
``create_trace_id``) directly.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KERNEL_PATH = REPO / "src" / "observability.py"
VOICE_PATH = REPO / "src" / "voice" / "observability.py"
INGEST_PATH = REPO / "src" / "ingestion" / "unified" / "observability.py"

KERNEL_EXPORTS = (
    "make_lifecycle_session_id",
    "update_lifecycle_trace",
    "try_update_lifecycle_trace_async",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_kernel_exports_lifecycle_helpers() -> None:
    text = _read(KERNEL_PATH)
    for symbol in KERNEL_EXPORTS:
        assert f"def {symbol}(" in text or f"async def {symbol}(" in text, (
            f"src/observability.py must define {symbol}() — see issue #1951"
        )


def test_voice_observability_uses_shared_kernel() -> None:
    text = _read(VOICE_PATH)
    assert "from src.observability import" in text, (
        "src/voice/observability.py must import the shared lifecycle kernel"
    )
    for symbol in KERNEL_EXPORTS:
        assert symbol in text, f"src/voice/observability.py must reference shared {symbol}"


def test_ingestion_observability_uses_shared_kernel() -> None:
    text = _read(INGEST_PATH)
    assert "from src.observability import" in text, (
        "src/ingestion/unified/observability.py must import the shared lifecycle kernel"
    )
    # Ingestion only uses two of the three kernel helpers (it has no async
    # wrapper). Assert the two it does need.
    for symbol in ("make_lifecycle_session_id", "update_lifecycle_trace"):
        assert symbol in text, (
            f"src/ingestion/unified/observability.py must reference shared {symbol}"
        )


def _assert_no_direct_langfuse_lifecycle_primitives(path: Path) -> None:
    text = _read(path)
    for primitive in (
        "start_as_current_observation(",
        ".create_trace_id(",
    ):
        assert primitive not in text, (
            f"{path.relative_to(REPO)} must not call {primitive!r} directly; "
            f"go through src.observability.update_lifecycle_trace() instead "
            f"(issue #1951)."
        )


def test_voice_observability_does_not_reimplement_kernel() -> None:
    _assert_no_direct_langfuse_lifecycle_primitives(VOICE_PATH)


def test_ingestion_observability_does_not_reimplement_kernel() -> None:
    _assert_no_direct_langfuse_lifecycle_primitives(INGEST_PATH)


def _significant_lines(text: str) -> int:
    """Count non-blank, non-comment lines."""
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        count += 1
    return count


def test_voice_observability_stays_thin() -> None:
    """Issue #1951 acceptance: family modules ≤ ~75 significant LOC.

    Pre-refactor each family carried ~70 LOC of *duplicated kernel logic*.
    Post-refactor the kernel is shared and each family keeps only thin
    family-specific tag/metadata builders + wrappers. The hard guards live
    in :func:`test_voice_observability_does_not_reimplement_kernel` and
    :func:`test_ingestion_observability_does_not_reimplement_kernel` —
    this LOC bound is a soft drift signal, not a strict design rule.
    """
    sig = _significant_lines(_read(VOICE_PATH))
    assert sig <= 75, (
        f"src/voice/observability.py is back up to {sig} significant lines; "
        "if a new lifecycle concern is needed, push it into the shared kernel "
        "in src/observability.py instead of fattening the family module."
    )


def test_ingestion_observability_stays_thin() -> None:
    """Same intent as the voice variant."""
    sig = _significant_lines(_read(INGEST_PATH))
    assert sig <= 75, (
        f"src/ingestion/unified/observability.py is back up to {sig} "
        "significant lines; push new logic into the shared kernel instead."
    )
