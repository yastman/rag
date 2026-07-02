"""Coverage numpy double-load fix (card_eaf203bc78b4).

Auto-imported at interpreter startup when this directory is on PYTHONPATH.
Pre-loads numpy's C extension BEFORE coverage.py installs its C-tracer, so
coverage's later source-package walk cannot trigger a second dlopen of
``numpy._multiarray_umath`` ("cannot load module more than once per process").

Only used for coverage runs (wired via PYTHONPATH in the Makefile test-cov
target and the CI coverage workflow steps); harmless everywhere else.
"""

try:
    import numpy  # noqa: F401
except Exception:  # pragma: no cover - numpy always present in test env
    pass
