from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "setup_langfuse_dashboards.py"
    spec = importlib.util.spec_from_file_location("setup_langfuse_dashboards", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_has_query_errors_detects_api_error():
    module = _load_script_module()
    metrics = {
        "llm_ttft_ms": {"error": "auth failed"},
        "llm_decode_ms": {"value_p95": 1200.0},
    }
    assert module.has_query_errors(metrics) is True


def test_has_query_errors_false_on_clean_data():
    module = _load_script_module()
    metrics = {
        "llm_ttft_ms": {"value_p95": 1200.0, "count_count": 10.0},
        "llm_decode_ms": {"value_p95": 800.0, "count_count": 10.0},
    }
    assert module.has_query_errors(metrics) is False
