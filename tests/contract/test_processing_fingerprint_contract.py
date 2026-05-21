***REMOVED*** tests/contract/test_processing_fingerprint_contract.py
"""Contract tests for processing fingerprint comparison in UnifiedStateManager.

Issue ***REMOVED***1604: should_process must compare not only content_hash but also
embedding_model and pipeline_version, so that re-embedding with a new model
or pipeline version triggers reprocessing even when file bytes did not change.

Two layers of guarantees:

1. Static (AST):
   - `should_process_sync` and `should_process` must accept
     `embedding_model` and `pipeline_version` parameters (or a single
     `processing_fingerprint` arg).

2. Behavioral (unit):
   - A pure helper `_should_reprocess(state, content_hash, embedding_model,
     pipeline_version)` lives in `state_manager.py` and is sensitive to
     each of the three fingerprint dimensions.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.ingestion.unified.state_manager import (
    FileState,
    UnifiedStateManager,
    _should_reprocess,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_MANAGER_PATH = REPO_ROOT / "src" / "ingestion" / "unified" / "state_manager.py"


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Static AST contract: signatures include fingerprint parameters
***REMOVED*** ---------------------------------------------------------------------------


def _arg_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func_node.args
    return {a.arg for a in (args.args + args.kwonlyargs)}


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _state_manager_tree() -> ast.Module:
    return ast.parse(STATE_MANAGER_PATH.read_text())


_FINGERPRINT_PARAM_SETS = (
    {"embedding_model", "pipeline_version"},
    {"processing_fingerprint"},
)


def _has_fingerprint_params(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    names = _arg_names(func_node)
    return any(required.issubset(names) for required in _FINGERPRINT_PARAM_SETS)


class TestStaticContract:
    """Function signatures of state_manager must accept fingerprint params."""

    def test_should_process_sync_accepts_fingerprint_params(self) -> None:
        tree = _state_manager_tree()
        func = _find_function(tree, "should_process_sync")
        assert func is not None, "should_process_sync must exist in state_manager.py"
        assert _has_fingerprint_params(func), (
            "should_process_sync must accept embedding_model + pipeline_version "
            "(or processing_fingerprint). Issue ***REMOVED***1604."
        )

    def test_should_process_async_accepts_fingerprint_params(self) -> None:
        tree = _state_manager_tree()
        func = _find_function(tree, "should_process")
        assert func is not None, "should_process must exist in state_manager.py"
        assert _has_fingerprint_params(func), (
            "should_process (async) must accept embedding_model + pipeline_version "
            "(or processing_fingerprint). Issue ***REMOVED***1604."
        )

    def test_should_reprocess_helper_exists(self) -> None:
        """A pure helper `_should_reprocess` must exist for testable comparisons."""
        tree = _state_manager_tree()
        func = _find_function(tree, "_should_reprocess")
        assert func is not None, (
            "Module-level `_should_reprocess(state, content_hash, embedding_model, "
            "pipeline_version)` helper must exist. Issue ***REMOVED***1604."
        )
        names = _arg_names(func)
        for required in ("state", "content_hash", "embedding_model", "pipeline_version"):
            assert required in names, (
                f"_should_reprocess must accept '{required}' parameter. Issue ***REMOVED***1604."
            )

    def test_runtime_signatures_match_ast(self) -> None:
        """Runtime introspection mirrors the AST contract (defensive double-check)."""
        sync_sig = inspect.signature(UnifiedStateManager.should_process_sync)
        async_sig = inspect.signature(UnifiedStateManager.should_process)
        for sig, name in ((sync_sig, "should_process_sync"), (async_sig, "should_process")):
            params = set(sig.parameters)
            matches_pair = {"embedding_model", "pipeline_version"}.issubset(params)
            matches_fp = "processing_fingerprint" in params
            assert matches_pair or matches_fp, (
                f"{name}: signature must accept fingerprint params (issue ***REMOVED***1604), got {params}"
            )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Behavioral contract: _should_reprocess helper
***REMOVED*** ---------------------------------------------------------------------------


def _indexed_state(
    *,
    content_hash: str = "h",
    embedding_model: str = "voyage-4-large",
    pipeline_version: str = "v3.2.1",
) -> FileState:
    return FileState(
        file_id="f1",
        content_hash=content_hash,
        embedding_model=embedding_model,
        pipeline_version=pipeline_version,
        status="indexed",
    )


class TestShouldReprocessHelper:
    """Pure-function comparison logic for the processing fingerprint."""

    def test_returns_false_when_all_three_fields_match(self) -> None:
        state = _indexed_state(
            content_hash="h", embedding_model="voyage-4-large", pipeline_version="v3.2.1"
        )
        assert (
            _should_reprocess(
                state,
                content_hash="h",
                embedding_model="voyage-4-large",
                pipeline_version="v3.2.1",
            )
            is False
        )

    def test_returns_true_when_only_embedding_model_differs(self) -> None:
        state = _indexed_state(embedding_model="voyage-4-large")
        assert (
            _should_reprocess(
                state,
                content_hash="h",
                embedding_model="bge-m3-api",
                pipeline_version="v3.2.1",
            )
            is True
        )

    def test_returns_true_when_only_pipeline_version_differs(self) -> None:
        state = _indexed_state(pipeline_version="v3.2.1")
        assert (
            _should_reprocess(
                state,
                content_hash="h",
                embedding_model="voyage-4-large",
                pipeline_version="v3.3.0",
            )
            is True
        )

    def test_returns_true_when_only_content_hash_differs(self) -> None:
        state = _indexed_state(content_hash="old")
        assert (
            _should_reprocess(
                state,
                content_hash="new",
                embedding_model="voyage-4-large",
                pipeline_version="v3.2.1",
            )
            is True
        )

    def test_none_fingerprint_args_preserve_legacy_hash_only_behavior(self) -> None:
        """When embedding_model/pipeline_version are None, the helper falls back
        to legacy hash-only comparison (backward compatibility)."""
        state = _indexed_state(embedding_model="voyage-4-large", pipeline_version="v3.2.1")
        ***REMOVED*** Legacy callers pass None for fingerprint pieces — should match on hash only.
        assert (
            _should_reprocess(
                state,
                content_hash="h",
                embedding_model=None,
                pipeline_version=None,
            )
            is False
        )
        assert (
            _should_reprocess(
                state,
                content_hash="different",
                embedding_model=None,
                pipeline_version=None,
            )
            is True
        )

    def test_returns_true_when_state_is_none(self) -> None:
        """No prior state means the file is new — always reprocess."""
        assert (
            _should_reprocess(
                None,
                content_hash="h",
                embedding_model="voyage-4-large",
                pipeline_version="v3.2.1",
            )
            is True
        )

    def test_returns_true_when_state_status_is_not_indexed(self) -> None:
        """Pending / error states with matching fingerprint still need to run.

        The DLQ / backoff gating lives in the parent function; this helper only
        encodes the 'fingerprint changed?' question. A non-indexed state is
        treated as 'no successful processing yet' so reprocess is required.
        """
        state = FileState(
            file_id="f1",
            content_hash="h",
            embedding_model="voyage-4-large",
            pipeline_version="v3.2.1",
            status="pending",
        )
        assert (
            _should_reprocess(
                state,
                content_hash="h",
                embedding_model="voyage-4-large",
                pipeline_version="v3.2.1",
            )
            is True
        )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Integration-ish: should_process_sync routes through the helper
***REMOVED*** ---------------------------------------------------------------------------


class TestShouldProcessSyncFingerprintIntegration:
    """Verify that should_process_sync honors the fingerprint params end-to-end."""

    def _patched_get_state(self, mgr: UnifiedStateManager, state: FileState | None):
        async def _fake_get_state(_self, _file_id: str) -> FileState | None:
            return state

        return _fake_get_state

    def test_indexed_same_hash_different_embedding_returns_true(self, monkeypatch) -> None:
        state = _indexed_state(
            content_hash="h", embedding_model="voyage-4-large", pipeline_version="v3.2.1"
        )

        async def _fake_get_state(_self, _file_id: str) -> FileState | None:
            return state

        monkeypatch.setattr(UnifiedStateManager, "get_state", _fake_get_state)
        mgr = UnifiedStateManager(database_url="postgres://localhost/test")

        assert (
            mgr.should_process_sync(
                "f1",
                "h",
                embedding_model="bge-m3-api",
                pipeline_version="v3.2.1",
            )
            is True
        )

    def test_indexed_same_hash_different_pipeline_returns_true(self, monkeypatch) -> None:
        state = _indexed_state(
            content_hash="h", embedding_model="voyage-4-large", pipeline_version="v3.2.1"
        )

        async def _fake_get_state(_self, _file_id: str) -> FileState | None:
            return state

        monkeypatch.setattr(UnifiedStateManager, "get_state", _fake_get_state)
        mgr = UnifiedStateManager(database_url="postgres://localhost/test")

        assert (
            mgr.should_process_sync(
                "f1",
                "h",
                embedding_model="voyage-4-large",
                pipeline_version="v9.9.9",
            )
            is True
        )

    def test_indexed_all_match_returns_false(self, monkeypatch) -> None:
        state = _indexed_state(
            content_hash="h", embedding_model="voyage-4-large", pipeline_version="v3.2.1"
        )

        async def _fake_get_state(_self, _file_id: str) -> FileState | None:
            return state

        monkeypatch.setattr(UnifiedStateManager, "get_state", _fake_get_state)
        mgr = UnifiedStateManager(database_url="postgres://localhost/test")

        assert (
            mgr.should_process_sync(
                "f1",
                "h",
                embedding_model="voyage-4-large",
                pipeline_version="v3.2.1",
            )
            is False
        )

    def test_legacy_no_fingerprint_args_still_works(self, monkeypatch) -> None:
        """Backward compat: callers that don't pass fingerprint args get hash-only check."""
        state = _indexed_state(
            content_hash="h", embedding_model="voyage-4-large", pipeline_version="v3.2.1"
        )

        async def _fake_get_state(_self, _file_id: str) -> FileState | None:
            return state

        monkeypatch.setattr(UnifiedStateManager, "get_state", _fake_get_state)
        mgr = UnifiedStateManager(database_url="postgres://localhost/test")

        ***REMOVED*** Legacy call: should still skip when hash matches.
        assert mgr.should_process_sync("f1", "h") is False
        ***REMOVED*** Legacy call with different hash: still reprocesses.
        assert mgr.should_process_sync("f1", "different") is True


if __name__ == "__main__":  ***REMOVED*** pragma: no cover
    pytest.main([__file__, "-v"])
