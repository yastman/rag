"""Pipeline factory resolver — the seam that closes #1948.

Before this module, ``src/api/main.py`` opened its FastAPI ``lifespan``
with a direct adapter import. This resolver keeps API/runtime code on a
runtime-owned default factory while still allowing adapters to override the
factory with ``RAG_GRAPH_FACTORY=some.module:factory``.
"""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable
from typing import Any, cast


logger = logging.getLogger(__name__)


DEFAULT_FACTORY_SPEC = "src.runtime.graph.graph:build_graph"
"""Default ``module:attribute`` factory spec.

Runtime-owned default pipeline factory. Adapters may override this with
their own ``module:attribute`` spec at process startup.
"""

ENV_VAR = "RAG_GRAPH_FACTORY"
"""Environment variable used to override :data:`DEFAULT_FACTORY_SPEC`."""


class PipelineFactoryError(RuntimeError):
    """Raised when the configured ``RAG_GRAPH_FACTORY`` cannot be resolved."""


def reset_pipeline_factory_cache() -> None:
    """No-op kept for API compatibility.

    The resolver intentionally does not cache: ``importlib.import_module``
    on an already-loaded module is a ``sys.modules`` dict lookup, and
    caching the resolved callable across pytest sessions caused stale
    references when other tests ``patch``-ed ``build_graph`` after the
    first resolution. Tests that mutate ``RAG_GRAPH_FACTORY`` per case
    therefore see a fresh resolution on every call.
    """


def resolve_pipeline_factory() -> Callable[..., Any]:
    """Return the configured pipeline factory callable.

    The factory spec follows the standard ``module:attribute`` form used
    by ``uvicorn`` / ``gunicorn`` / Django settings.

    Raises:
        PipelineFactoryError: spec is malformed, the module is missing,
            the attribute is missing, or the attribute is not callable.
    """
    spec = os.environ.get(ENV_VAR, DEFAULT_FACTORY_SPEC)
    if ":" not in spec:
        raise PipelineFactoryError(f"Invalid {ENV_VAR}={spec!r}: expected 'module:attribute' form.")

    module_name, _, attr_name = spec.partition(":")
    module_name = module_name.strip()
    attr_name = attr_name.strip()
    if not module_name or not attr_name:
        raise PipelineFactoryError(f"Invalid {ENV_VAR}={spec!r}: expected 'module:attribute' form.")

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise PipelineFactoryError(
            f"Cannot import pipeline factory module {module_name!r} (spec={spec!r}): {exc}"
        ) from exc

    try:
        candidate = getattr(module, attr_name)
    except AttributeError as exc:
        raise PipelineFactoryError(
            f"Pipeline factory module {module_name!r} has no attribute "
            f"{attr_name!r} (spec={spec!r})"
        ) from exc

    if not callable(candidate):
        raise PipelineFactoryError(
            f"Resolved pipeline factory {spec!r} is not callable (got {type(candidate).__name__})"
        )

    factory = cast(Callable[..., Any], candidate)
    logger.debug("Resolved pipeline factory %s -> %r", spec, factory)
    return factory


def build_pipeline(**kwargs: Any) -> Any:
    """Resolve the configured factory and call it with ``**kwargs``.

    Convenience wrapper used by ``src/api/main.py``'s ``lifespan`` so the
    call site stays a single line.
    """
    factory = resolve_pipeline_factory()
    return factory(**kwargs)


__all__ = [
    "DEFAULT_FACTORY_SPEC",
    "ENV_VAR",
    "PipelineFactoryError",
    "build_pipeline",
    "reset_pipeline_factory_cache",
    "resolve_pipeline_factory",
]
