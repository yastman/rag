"""Tests for scripts/eval/calibrate_judge.py (TDD — RED first).

Issue #761: Judge Calibration — Score Analytics + Cohen's Kappa
Tests: matched pairs fetching, binarization, kappa, TPR/TNR, disagreement report.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock


def _load_module() -> Any:
    """Load calibrate_judge as a module without executing main()."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "calibrate_judge.py"
    spec = importlib.util.spec_from_file_location("calibrate_judge", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_meta(total_pages: int = 1, page: int = 1) -> SimpleNamespace:
    return SimpleNamespace(total_pages=total_pages, page=page)


def _make_score(trace_id: str, name: str, value: float) -> SimpleNamespace:
    return SimpleNamespace(trace_id=trace_id, name=name, value=value)


# ---------------------------------------------------------------------------
# binarize_judge
# ---------------------------------------------------------------------------


class TestBinarizeJudge:
    def test_score_above_threshold_returns_one(self):
        """Score >= threshold → 1 (judge pass)."""
        m = _load_module()
        assert m.binarize_judge(0.8, threshold=0.75) == 1

    def test_score_equal_threshold_returns_one(self):
        """Score == threshold → 1 (judge pass, inclusive lower bound)."""
        m = _load_module()
        assert m.binarize_judge(0.75, threshold=0.75) == 1

    def test_score_below_threshold_returns_zero(self):
        """Score < threshold → 0 (judge fail)."""
        m = _load_module()
        assert m.binarize_judge(0.5, threshold=0.75) == 0

    def test_zero_score_returns_zero(self):
        """Score = 0.0 → 0 (always fail)."""
        m = _load_module()
        assert m.binarize_judge(0.0, threshold=0.75) == 0

    def test_one_score_returns_one(self):
        """Score = 1.0 → 1 (always pass)."""
        m = _load_module()
        assert m.binarize_judge(1.0, threshold=0.75) == 1


# ---------------------------------------------------------------------------
# compute_kappa
# ---------------------------------------------------------------------------


class TestComputeKappa:
    def test_perfect_agreement_returns_one(self):
        """Identical label lists → kappa = 1.0."""
        m = _load_module()
        human = [1, 0, 1, 0, 1, 0, 1, 0]
        judge = [1, 0, 1, 0, 1, 0, 1, 0]
        kappa = m.compute_kappa(human, judge)
        assert abs(kappa - 1.0) < 1e-9

    def test_chance_agreement_returns_zero(self):
        """50/50 random agreement with uniform prior → kappa ≈ 0.0."""
        m = _load_module()
        # balanced classes, exactly chance-level agreement
        human = [1, 1, 1, 1, 0, 0, 0, 0]
        judge = [1, 1, 0, 0, 1, 1, 0, 0]
        # po = 4/8 = 0.5, pe = 0.5*0.5 + 0.5*0.5 = 0.5
        kappa = m.compute_kappa(human, judge)
        assert abs(kappa - 0.0) < 1e-9

    def test_total_disagreement_returns_negative_one(self):
        """Inverted labels → kappa = -1.0."""
        m = _load_module()
        human = [1, 0, 1, 0]
        judge = [0, 1, 0, 1]
        kappa = m.compute_kappa(human, judge)
        assert abs(kappa - (-1.0)) < 1e-9

    def test_degenerate_all_same_class_returns_one_when_agree(self):
        """When all labels are identical and both agree → kappa = 1.0."""
        m = _load_module()
        human = [1, 1, 1, 1]
        judge = [1, 1, 1, 1]
        kappa = m.compute_kappa(human, judge)
        assert abs(kappa - 1.0) < 1e-9

    def test_partial_agreement_returns_expected_kappa(self):
        """Known case: po=0.75, pe=0.5 → kappa=0.5."""
        m = _load_module()
        # 6 out of 8 agree, balanced prior
        # human: [1,1,1,1,0,0,0,0], judge: [1,1,1,0,0,0,1,0]
        # Agreements: pos 0,1,2,4,5,7 = 6 → po = 6/8 = 0.75
        # p_human_1 = 0.5, p_judge_1 = 0.5 → pe = 0.5
        # kappa = (0.75 - 0.5) / 0.5 = 0.5
        human = [1, 1, 1, 1, 0, 0, 0, 0]
        judge = [1, 1, 1, 0, 0, 0, 1, 0]
        kappa = m.compute_kappa(human, judge)
        assert abs(kappa - 0.5) < 1e-9

    def test_empty_lists_return_zero(self):
        """Empty label lists → kappa = 0.0."""
        m = _load_module()
        kappa = m.compute_kappa([], [])
        assert kappa == 0.0


# ---------------------------------------------------------------------------
# compute_tpr_tnr
# ---------------------------------------------------------------------------


class TestComputeTprTnr:
    """TPR = judge catches bad responses / all human-disliked.
    TNR = judge correctly passes good responses / all human-liked.
    Positive class = "bad" (human dislike = 0, judge fail = 0).
    """

    def test_perfect_detection_returns_one_one(self):
        """Judge perfectly agrees with human → TPR=1.0, TNR=1.0."""
        m = _load_module()
        human = [0, 0, 1, 1]
        judge = [0, 0, 1, 1]
        tpr, tnr = m.compute_tpr_tnr(human, judge)
        assert abs(tpr - 1.0) < 1e-9
        assert abs(tnr - 1.0) < 1e-9

    def test_judge_misses_all_bad_returns_zero_tpr(self):
        """Judge passes everything → TPR=0.0 (all FN), TNR=1.0."""
        m = _load_module()
        human = [0, 0, 1, 1]
        judge = [1, 1, 1, 1]  # judge says all good
        tpr, tnr = m.compute_tpr_tnr(human, judge)
        assert abs(tpr - 0.0) < 1e-9
        assert abs(tnr - 1.0) < 1e-9

    def test_judge_flags_everything_returns_zero_tnr(self):
        """Judge fails everything → TPR=1.0, TNR=0.0 (all FP)."""
        m = _load_module()
        human = [0, 0, 1, 1]
        judge = [0, 0, 0, 0]  # judge says all bad
        tpr, tnr = m.compute_tpr_tnr(human, judge)
        assert abs(tpr - 1.0) < 1e-9
        assert abs(tnr - 0.0) < 1e-9

    def test_partial_detection(self):
        """Known case: TPR=2/3, TNR=2/3."""
        m = _load_module()
        # human=[0,0,1,1,0,1], judge=[0,1,1,1,0,0]
        # TP=2 (pos 0,4), FN=1 (pos 1), TN=2 (pos 2,3), FP=1 (pos 5)
        human = [0, 0, 1, 1, 0, 1]
        judge = [0, 1, 1, 1, 0, 0]
        tpr, tnr = m.compute_tpr_tnr(human, judge)
        assert abs(tpr - 2 / 3) < 1e-9
        assert abs(tnr - 2 / 3) < 1e-9

    def test_no_positive_class_returns_zero_tpr(self):
        """No human dislikes → TPR = 0.0 (undefined, returns 0)."""
        m = _load_module()
        human = [1, 1, 1, 1]
        judge = [1, 0, 1, 0]
        tpr, _tnr = m.compute_tpr_tnr(human, judge)
        assert tpr == 0.0

    def test_no_negative_class_returns_zero_tnr(self):
        """No human likes → TNR = 0.0 (undefined, returns 0)."""
        m = _load_module()
        human = [0, 0, 0, 0]
        judge = [0, 1, 0, 1]
        _tpr, tnr = m.compute_tpr_tnr(human, judge)
        assert tnr == 0.0


# ---------------------------------------------------------------------------
# fetch_matched_pairs
# ---------------------------------------------------------------------------


class TestFetchMatchedPairs:
    def test_returns_pairs_for_traces_with_both_scores(self):
        """Returns (user_feedback, judge_faithfulness) for traces having both."""
        m = _load_module()

        uf_score = _make_score("trace-A", "user_feedback", 0.0)
        jf_score = _make_score("trace-A", "judge_faithfulness", 0.8)

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            # user_feedback call
            SimpleNamespace(data=[uf_score], meta=_make_meta()),
            # judge_faithfulness call
            SimpleNamespace(data=[jf_score], meta=_make_meta()),
        ]

        pairs = m.fetch_matched_pairs(mock_api, hours=168)

        assert len(pairs) == 1
        assert pairs[0] == (0.0, 0.8)

    def test_ignores_traces_with_only_one_score(self):
        """Traces missing either score are excluded."""
        m = _load_module()

        # trace-A has user_feedback only
        # trace-B has judge_faithfulness only
        # trace-C has both
        uf_a = _make_score("trace-A", "user_feedback", 1.0)
        uf_c = _make_score("trace-C", "user_feedback", 0.0)
        jf_b = _make_score("trace-B", "judge_faithfulness", 0.5)
        jf_c = _make_score("trace-C", "judge_faithfulness", 0.9)

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            SimpleNamespace(data=[uf_a, uf_c], meta=_make_meta()),
            SimpleNamespace(data=[jf_b, jf_c], meta=_make_meta()),
        ]

        pairs = m.fetch_matched_pairs(mock_api, hours=168)

        assert len(pairs) == 1
        assert pairs[0] == (0.0, 0.9)

    def test_uses_score_v2_api_for_both_score_names(self):
        """Calls score_v_2.get with user_feedback and judge_faithfulness."""
        m = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(data=[], meta=_make_meta())

        m.fetch_matched_pairs(mock_api, hours=24)

        calls = mock_api.score_v_2.get.call_args_list
        names_called = [c.kwargs.get("name") for c in calls]
        assert "user_feedback" in names_called
        assert "judge_faithfulness" in names_called

    def test_deduplicates_multiple_scores_per_trace(self):
        """When trace has multiple scores for same name, uses last value."""
        m = _load_module()

        uf1 = _make_score("trace-X", "user_feedback", 0.0)
        uf2 = _make_score("trace-X", "user_feedback", 1.0)  # duplicate
        jf = _make_score("trace-X", "judge_faithfulness", 0.6)

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            SimpleNamespace(data=[uf1, uf2], meta=_make_meta()),
            SimpleNamespace(data=[jf], meta=_make_meta()),
        ]

        pairs = m.fetch_matched_pairs(mock_api, hours=168)

        # One pair per trace
        assert len(pairs) == 1

    def test_returns_empty_when_no_overlap(self):
        """Returns empty list when no traces have both scores."""
        m = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            SimpleNamespace(data=[], meta=_make_meta()),
            SimpleNamespace(data=[], meta=_make_meta()),
        ]

        pairs = m.fetch_matched_pairs(mock_api, hours=168)
        assert pairs == []

    def test_paginates_both_score_names(self):
        """Paginates through all pages for both score names."""
        m = _load_module()

        uf_p1 = _make_score("t1", "user_feedback", 0.0)
        uf_p2 = _make_score("t2", "user_feedback", 1.0)
        jf_p1 = _make_score("t1", "judge_faithfulness", 0.8)
        jf_p2 = _make_score("t2", "judge_faithfulness", 0.3)

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            # user_feedback page 1 of 2
            SimpleNamespace(data=[uf_p1], meta=_make_meta(total_pages=2, page=1)),
            # user_feedback page 2 of 2
            SimpleNamespace(data=[uf_p2], meta=_make_meta(total_pages=2, page=2)),
            # judge_faithfulness page 1 of 2
            SimpleNamespace(data=[jf_p1], meta=_make_meta(total_pages=2, page=1)),
            # judge_faithfulness page 2 of 2
            SimpleNamespace(data=[jf_p2], meta=_make_meta(total_pages=2, page=2)),
        ]

        pairs = m.fetch_matched_pairs(mock_api, hours=168)

        assert len(pairs) == 2


# ---------------------------------------------------------------------------
# build_disagreement_report
# ---------------------------------------------------------------------------


class TestBuildDisagreementReport:
    def test_report_contains_required_keys(self):
        """Report dict contains all expected keys."""
        m = _load_module()
        pairs = [(0.0, 0.5), (1.0, 0.8), (0.0, 0.3)]
        report = m.build_disagreement_report(pairs, threshold=0.75)

        required = {"n_pairs", "kappa", "tpr", "tnr", "n_agreements", "n_disagreements"}
        assert required.issubset(report.keys())

    def test_perfect_agreement_report(self):
        """When judge perfectly matches human → kappa=1, tpr=1, tnr=1."""
        m = _load_module()
        # user_feedback=0 (dislike) paired with judge < 0.75 → binary judge=0 (bad)
        # user_feedback=1 (like) paired with judge >= 0.75 → binary judge=1 (good)
        pairs = [(0.0, 0.5), (0.0, 0.6), (1.0, 0.8), (1.0, 0.9)]
        report = m.build_disagreement_report(pairs, threshold=0.75)

        assert abs(report["kappa"] - 1.0) < 1e-9
        assert abs(report["tpr"] - 1.0) < 1e-9
        assert abs(report["tnr"] - 1.0) < 1e-9
        assert report["n_agreements"] == 4
        assert report["n_disagreements"] == 0

    def test_total_disagreement_report(self):
        """When judge inverts human → kappa=-1, disagreements=n_pairs."""
        m = _load_module()
        # human=0 (dislike) → judge high (pass), human=1 (like) → judge low (fail)
        pairs = [(0.0, 0.9), (0.0, 0.8), (1.0, 0.5), (1.0, 0.4)]
        report = m.build_disagreement_report(pairs, threshold=0.75)

        assert abs(report["kappa"] - (-1.0)) < 1e-9
        assert report["n_disagreements"] == 4
        assert report["n_agreements"] == 0

    def test_n_pairs_matches_input_length(self):
        """n_pairs equals length of input pairs."""
        m = _load_module()
        pairs = [(0.0, 0.5), (1.0, 0.9), (0.0, 0.2), (1.0, 0.8), (0.0, 0.7)]
        report = m.build_disagreement_report(pairs, threshold=0.75)
        assert report["n_pairs"] == 5

    def test_empty_pairs_returns_zero_metrics(self):
        """Empty pairs → all zero metrics."""
        m = _load_module()
        report = m.build_disagreement_report([], threshold=0.75)
        assert report["n_pairs"] == 0
        assert report["kappa"] == 0.0
        assert report["tpr"] == 0.0
        assert report["tnr"] == 0.0


# ---------------------------------------------------------------------------
# run_calibration — insufficient data gate
# ---------------------------------------------------------------------------


class TestRunCalibrationInsufficientData:
    def test_raises_when_fewer_than_min_pairs(self):
        """Raises ValueError if fewer than min_pairs matched traces found."""
        m = _load_module()

        mock_api = MagicMock()
        # Only 2 pairs returned, well below min_pairs=50
        uf = _make_score("t1", "user_feedback", 0.0)
        jf = _make_score("t1", "judge_faithfulness", 0.5)
        mock_api.score_v_2.get.side_effect = [
            SimpleNamespace(data=[uf], meta=_make_meta()),
            SimpleNamespace(data=[jf], meta=_make_meta()),
        ]

        import pytest

        with pytest.raises(ValueError, match="50"):
            m.run_calibration(mock_api, hours=168, threshold=0.75, min_pairs=50)

    def test_succeeds_when_enough_pairs(self):
        """Does not raise when >= min_pairs matched traces found."""
        m = _load_module()

        # Build 10 matching pairs (min_pairs=5 for speed)
        uf_scores = [_make_score(f"t{i}", "user_feedback", float(i % 2)) for i in range(10)]
        jf_scores = [
            _make_score(f"t{i}", "judge_faithfulness", 0.8 if i % 2 == 0 else 0.4)
            for i in range(10)
        ]

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            SimpleNamespace(data=uf_scores, meta=_make_meta()),
            SimpleNamespace(data=jf_scores, meta=_make_meta()),
        ]

        # Should not raise
        report = m.run_calibration(mock_api, hours=168, threshold=0.75, min_pairs=5)
        assert report["n_pairs"] == 10
