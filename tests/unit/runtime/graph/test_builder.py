"""Unit tests for ``src.runtime.graph.builder`` — pipeline factory resolution.

Closes the final layering offender for #1948: ``src/api/main.py`` previously
hard-imported ``telegram_bot.graph.graph.build_graph`` inside its FastAPI
``lifespan``. The new builder resolves the factory dynamically through
``RAG_GRAPH_FACTORY`` (default ``telegram_bot.graph.graph:build_graph``),
which is a string spec — no static ``from telegram_bot ...`` import remains
under ``src/`` once ``src/api/main.py`` is rewired.

Tests cover the resolver only. The actual ``build_graph`` implementation is
exercised by the existing graph-level tests; here we use a tiny stub module
so the tests have no LangGraph / ML dependency.
"""

from __future__ import annotations

import sys
import types

import pytest

from src.runtime.graph import builder


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Each test starts with a clean factory cache."""
    builder.reset_pipeline_factory_cache()
    yield
    builder.reset_pipeline_factory_cache()


def _install_stub_module(name: str, factory: object) -> None:
    """Register a synthetic module so the resolver has a target to import."""
    module = types.ModuleType(name)
    module.factory = factory  # type: ignore[attr-defined]
    sys.modules[name] = module


def test_resolve_pipeline_factory_uses_default_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default spec is ``telegram_bot.graph.graph:build_graph`` per the
    canonical bot wiring; we install a stub at that location so the test
    has no transitive ML imports.
    """
    monkeypatch.delenv("RAG_GRAPH_FACTORY", raising=False)

    def _fake_build_graph(*args: object, **kwargs: object) -> str:
        return "fake-graph"

    fake_module = types.ModuleType("telegram_bot.graph.graph")
    fake_module.build_graph = _fake_build_graph  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "telegram_bot.graph.graph", fake_module)

    factory = builder.resolve_pipeline_factory()

    assert factory is _fake_build_graph
    assert factory() == "fake-graph"


def test_resolve_pipeline_factory_honours_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``RAG_GRAPH_FACTORY`` overrides the default; this is the seam that
    lets ``src/api/main.py`` stay free of any static telegram_bot import.
    """

    def _custom(*args: object, **kwargs: object) -> str:
        return "custom"

    _install_stub_module("tests._fake_pipeline_module", _custom)
    monkeypatch.setenv("RAG_GRAPH_FACTORY", "tests._fake_pipeline_module:factory")

    factory = builder.resolve_pipeline_factory()

    assert factory is _custom
    assert factory() == "custom"


def test_resolve_pipeline_factory_resolves_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The resolver does NOT cache: a re-``patch`` of the target attribute
    must be observed on the next ``resolve_pipeline_factory`` call. This
    is the behaviour ``tests/unit/api/test_rag_api_runtime.py`` relies on
    when it ``patch``-es ``telegram_bot.graph.graph.build_graph`` from a
    fresh test that runs after this module has already resolved once.
    """
    fake_module = types.ModuleType("tests._fake_pipeline_recheck")

    def _v1(*args: object, **kwargs: object) -> str:
        return "v1"

    fake_module.factory = _v1  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tests._fake_pipeline_recheck", fake_module)
    monkeypatch.setenv("RAG_GRAPH_FACTORY", "tests._fake_pipeline_recheck:factory")

    a = builder.resolve_pipeline_factory()
    assert a() == "v1"

    def _v2(*args: object, **kwargs: object) -> str:
        return "v2"

    fake_module.factory = _v2  # type: ignore[attr-defined]
    b = builder.resolve_pipeline_factory()
    assert b() == "v2"


def test_resolve_pipeline_factory_rejects_malformed_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_GRAPH_FACTORY", "no_colon_separator")

    with pytest.raises(builder.PipelineFactoryError) as excinfo:
        builder.resolve_pipeline_factory()

    assert "module:attribute" in str(excinfo.value)


def test_resolve_pipeline_factory_rejects_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_GRAPH_FACTORY", "tests._does_not_exist_xyz_module_42:factory")

    with pytest.raises(builder.PipelineFactoryError) as excinfo:
        builder.resolve_pipeline_factory()

    msg = str(excinfo.value)
    assert "tests._does_not_exist_xyz_module_42" in msg


def test_resolve_pipeline_factory_rejects_missing_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub_module("tests._fake_pipeline_no_attr", object())
    monkeypatch.setenv("RAG_GRAPH_FACTORY", "tests._fake_pipeline_no_attr:not_a_real_attr")

    with pytest.raises(builder.PipelineFactoryError) as excinfo:
        builder.resolve_pipeline_factory()

    msg = str(excinfo.value)
    assert "not_a_real_attr" in msg


def test_resolve_pipeline_factory_rejects_non_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub_module("tests._fake_pipeline_non_callable", "not-a-callable")
    monkeypatch.setenv("RAG_GRAPH_FACTORY", "tests._fake_pipeline_non_callable:factory")

    with pytest.raises(builder.PipelineFactoryError) as excinfo:
        builder.resolve_pipeline_factory()

    assert "callable" in str(excinfo.value).lower()


def test_module_does_not_statically_import_telegram_bot() -> None:
    """Source-level guard: ``src/runtime/graph/builder.py`` is the seam that
    lets us delete the last ``telegram_bot`` static import from ``src/``.
    The seam itself must therefore not statically import ``telegram_bot``;
    the layering contract test (#1948) covers ``src/`` and ``mini_app/``
    transitively, but a direct check here keeps the regression message
    pointed at the right file.
    """
    import ast
    from pathlib import Path

    source = Path(builder.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("telegram_bot"), (
                f"src/runtime/graph/builder.py must not statically import "
                f"telegram_bot.* (found: {mod})"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("telegram_bot"), (
                    f"src/runtime/graph/builder.py must not statically "
                    f"import telegram_bot.* (found: {alias.name})"
                )
