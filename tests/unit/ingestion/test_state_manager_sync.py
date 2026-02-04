# tests/unit/ingestion/test_state_manager_sync.py
"""Tests for sync methods in UnifiedStateManager."""

import asyncio


class TestStateManagerSyncMethods:
    """Verify sync methods exist and are not coroutines."""

    def test_sync_methods_exist(self):
        """All required sync methods should exist."""
        from src.ingestion.unified.state_manager import UnifiedStateManager

        required_methods = [
            "get_state_sync",
            "should_process_sync",
            "mark_processing_sync",
            "mark_indexed_sync",
            "mark_error_sync",
            "mark_deleted_sync",
            "add_to_dlq_sync",
        ]

        for method_name in required_methods:
            assert hasattr(UnifiedStateManager, method_name), f"Missing {method_name}"

    def test_sync_methods_are_not_coroutines(self):
        """Sync methods should not be async."""
        from src.ingestion.unified.state_manager import UnifiedStateManager

        sync_methods = [
            "get_state_sync",
            "should_process_sync",
            "mark_processing_sync",
            "mark_indexed_sync",
            "mark_error_sync",
            "mark_deleted_sync",
            "add_to_dlq_sync",
        ]

        for method_name in sync_methods:
            method = getattr(UnifiedStateManager, method_name)
            assert not asyncio.iscoroutinefunction(method), f"{method_name} should be sync"
