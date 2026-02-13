"""Tests for thresholds.yaml schema completeness."""

from pathlib import Path

import pytest
import yaml


THRESHOLDS_PATH = Path(__file__).parent / "thresholds.yaml"


@pytest.fixture
def thresholds():
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)


class TestThresholdsSchema:
    """Verify go_no_go section exists and has required keys."""

    REQUIRED_GO_NO_GO_KEYS = {
        "cold_p50_ms",
        "cold_p90_ms",
        "cold_over_10s_pct",
        "cache_hit_p50_ms",
        "generate_p50_ms",
        "multi_rewrite_pct",
        "rewrite_tokens_p50",
        "ttft_p50_ms",
        "ttft_min_sample",
    }

    def test_go_no_go_section_exists(self, thresholds):
        assert "go_no_go" in thresholds, "thresholds.yaml missing 'go_no_go' section"

    def test_go_no_go_has_all_keys(self, thresholds):
        go_no_go = thresholds["go_no_go"]
        missing = self.REQUIRED_GO_NO_GO_KEYS - set(go_no_go.keys())
        assert not missing, f"Missing go_no_go keys: {missing}"

    def test_go_no_go_values_are_positive(self, thresholds):
        go_no_go = thresholds["go_no_go"]
        for key in self.REQUIRED_GO_NO_GO_KEYS:
            assert go_no_go[key] > 0, f"go_no_go.{key} must be positive"

    def test_llm_factor_at_least_1_10(self, thresholds):
        """Issue #168: factor must be >= 1.10 to avoid false positives."""
        factor = thresholds["calls"]["llm_factor"]
        assert factor >= 1.10, f"llm_factor {factor} too tight, need >= 1.10"
