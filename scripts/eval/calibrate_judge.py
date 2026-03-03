#!/usr/bin/env python3
"""Judge Calibration — Score Analytics + Cohen's Kappa (Issue #761).

Compares LLM-as-Judge scores (judge_faithfulness) with human feedback
(user_feedback) to calibrate judge quality.

Prerequisite: min 50 traces with both user_feedback and judge_faithfulness scores.

Usage:
    uv run python scripts/eval/calibrate_judge.py
    uv run python scripts/eval/calibrate_judge.py --hours 168 --threshold 0.75
    uv run python scripts/eval/calibrate_judge.py --min-pairs 50 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCORE_USER_FEEDBACK = "user_feedback"
SCORE_JUDGE_FAITHFULNESS = "judge_faithfulness"
DEFAULT_THRESHOLD = 0.75
DEFAULT_MIN_PAIRS = 50
DEFAULT_HOURS = 168  # 1 week
BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Pure computation helpers (no Langfuse dependency)
# ---------------------------------------------------------------------------


def binarize_judge(score: float, *, threshold: float = DEFAULT_THRESHOLD) -> int:
    """Convert continuous judge score to binary pass/fail.

    Args:
        score: Judge faithfulness score in [0.0, 1.0].
        threshold: Minimum score to consider a pass (inclusive).

    Returns:
        1 if score >= threshold (judge pass), 0 otherwise (judge fail).
    """
    return 1 if score >= threshold else 0


def compute_kappa(human_labels: list[int], judge_labels: list[int]) -> float:
    """Compute Cohen's Kappa between human feedback and binarized judge labels.

    kappa = (po - pe) / (1 - pe)
    where po = observed agreement, pe = expected agreement by chance.

    Args:
        human_labels: Binary labels from human feedback (0=dislike, 1=like).
        judge_labels: Binary labels from judge (0=fail, 1=pass).

    Returns:
        Cohen's Kappa in [-1.0, 1.0]. 0.0 for empty input.
    """
    n = len(human_labels)
    if n == 0:
        return 0.0

    # Observed agreement
    agreements = sum(h == j for h, j in zip(human_labels, judge_labels, strict=True))
    po = agreements / n

    # Expected agreement by chance
    p_human_1 = sum(human_labels) / n
    p_human_0 = 1.0 - p_human_1
    p_judge_1 = sum(judge_labels) / n
    p_judge_0 = 1.0 - p_judge_1
    pe = p_human_1 * p_judge_1 + p_human_0 * p_judge_0

    # Degenerate case: all labels identical → pe = 1.0
    denominator = 1.0 - pe
    if abs(denominator) < 1e-12:
        return 1.0 if po >= 1.0 else 0.0

    return (po - pe) / denominator


def compute_tpr_tnr(human_labels: list[int], judge_labels: list[int]) -> tuple[float, float]:
    """Compute TPR and TNR treating "bad response" as the positive class.

    Positive class = bad response: human dislike (human=0) / judge fail (judge=0).
    TPR = TP / (TP + FN) — how often judge catches human-disliked responses.
    TNR = TN / (TN + FP) — how often judge correctly passes human-liked responses.

    Undefined rates (zero denominator) return 0.0.

    Args:
        human_labels: Binary human labels (0=dislike, 1=like).
        judge_labels: Binary judge labels (0=fail, 1=pass).

    Returns:
        (tpr, tnr) tuple in [0.0, 1.0].
    """
    tp = fn = tn = fp = 0

    for h, j in zip(human_labels, judge_labels, strict=True):
        if h == 0 and j == 0:
            tp += 1
        elif h == 0 and j == 1:
            fn += 1
        elif h == 1 and j == 1:
            tn += 1
        else:  # h == 1 and j == 0
            fp += 1

    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    tnr = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    return tpr, tnr


# ---------------------------------------------------------------------------
# Langfuse data fetching
# ---------------------------------------------------------------------------


def _fetch_scores_by_name(
    api: Any,
    score_name: str,
    *,
    from_ts: datetime,
    batch_size: int = BATCH_SIZE,
) -> dict[str, float]:
    """Fetch all scores for a given name and return {trace_id: value} dict.

    Uses paginated Scores API v2. For duplicate trace_ids, the last value wins.

    Args:
        api: Langfuse low-level API client (langfuse.api).
        score_name: Score name to fetch (e.g. "user_feedback").
        from_ts: Fetch scores from this timestamp onward.
        batch_size: Page size for the API call.

    Returns:
        Dict mapping trace_id → score value.
    """
    scores_by_trace: dict[str, float] = {}
    page = 1

    while True:
        response = api.score_v_2.get(
            name=score_name,
            from_timestamp=from_ts,
            page=page,
            limit=batch_size,
        )
        scores = response.data or []
        if not scores:
            break

        for score in scores:
            tid = score.trace_id
            if tid is not None:
                scores_by_trace[tid] = score.value

        meta = response.meta
        if meta is None or page >= meta.total_pages:
            break
        page += 1

    logger.info("Fetched %d scores for '%s'", len(scores_by_trace), score_name)
    return scores_by_trace


def fetch_matched_pairs(
    api: Any,
    *,
    hours: int = DEFAULT_HOURS,
    batch_size: int = BATCH_SIZE,
) -> list[tuple[float, float]]:
    """Fetch (user_feedback, judge_faithfulness) pairs for matching traces.

    Only traces with BOTH scores are included.

    Args:
        api: Langfuse low-level API client (langfuse.api).
        hours: Look-back window in hours.
        batch_size: Page size for the API calls.

    Returns:
        List of (user_feedback_value, judge_faithfulness_value) tuples.
    """
    from_ts = datetime.now(UTC) - timedelta(hours=hours)

    uf_scores = _fetch_scores_by_name(
        api, SCORE_USER_FEEDBACK, from_ts=from_ts, batch_size=batch_size
    )
    jf_scores = _fetch_scores_by_name(
        api, SCORE_JUDGE_FAITHFULNESS, from_ts=from_ts, batch_size=batch_size
    )

    common_trace_ids = set(uf_scores) & set(jf_scores)
    pairs = [(uf_scores[tid], jf_scores[tid]) for tid in sorted(common_trace_ids)]

    logger.info(
        "Matched %d traces with both '%s' and '%s' scores",
        len(pairs),
        SCORE_USER_FEEDBACK,
        SCORE_JUDGE_FAITHFULNESS,
    )
    return pairs


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def build_disagreement_report(
    pairs: list[tuple[float, float]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Build calibration report from matched (user_feedback, judge_faithfulness) pairs.

    Args:
        pairs: List of (user_feedback, judge_faithfulness) tuples.
        threshold: Threshold for binarizing judge scores.

    Returns:
        Dict with keys: n_pairs, kappa, tpr, tnr, n_agreements, n_disagreements.
    """
    if not pairs:
        return {
            "n_pairs": 0,
            "kappa": 0.0,
            "tpr": 0.0,
            "tnr": 0.0,
            "n_agreements": 0,
            "n_disagreements": 0,
        }

    human_labels = [int(uf) for uf, _ in pairs]
    judge_labels = [binarize_judge(jf, threshold=threshold) for _, jf in pairs]

    kappa = compute_kappa(human_labels, judge_labels)
    tpr, tnr = compute_tpr_tnr(human_labels, judge_labels)

    n_agreements = sum(h == j for h, j in zip(human_labels, judge_labels, strict=True))
    n_disagreements = len(pairs) - n_agreements

    return {
        "n_pairs": len(pairs),
        "kappa": kappa,
        "tpr": tpr,
        "tnr": tnr,
        "n_agreements": n_agreements,
        "n_disagreements": n_disagreements,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_calibration(
    api: Any,
    *,
    hours: int = DEFAULT_HOURS,
    threshold: float = DEFAULT_THRESHOLD,
    min_pairs: int = DEFAULT_MIN_PAIRS,
) -> dict[str, Any]:
    """Fetch matched pairs and compute judge calibration metrics.

    Args:
        api: Langfuse low-level API client (langfuse.api).
        hours: Look-back window in hours.
        threshold: Binarization threshold for judge scores.
        min_pairs: Minimum number of matched pairs required.

    Returns:
        Calibration report dict from build_disagreement_report().

    Raises:
        ValueError: If fewer than min_pairs matched traces are found.
    """
    pairs = fetch_matched_pairs(api, hours=hours)

    if len(pairs) < min_pairs:
        raise ValueError(
            f"Insufficient data: found {len(pairs)} matched pairs, "
            f"need at least {min_pairs}. "
            "Collect more traces with both user_feedback and judge_faithfulness scores."
        )

    return build_disagreement_report(pairs, threshold=threshold)


def _format_report(report: dict[str, Any]) -> str:
    """Format calibration report as human-readable text."""
    lines = [
        "=== Judge Calibration Report ===",
        f"Matched pairs:     {report['n_pairs']}",
        f"Cohen's Kappa:     {report['kappa']:.3f}",
        f"TPR (sensitivity): {report['tpr']:.1%}  (judge catches bad responses)",
        f"TNR (specificity): {report['tnr']:.1%}  (judge passes good responses)",
        f"Agreements:        {report['n_agreements']} / {report['n_pairs']}",
        f"Disagreements:     {report['n_disagreements']} / {report['n_pairs']}",
    ]

    # Interpretation
    kappa = report["kappa"]
    if kappa >= 0.8:
        quality = "Excellent (κ ≥ 0.8)"
    elif kappa >= 0.6:
        quality = "Substantial (0.6 ≤ κ < 0.8)"
    elif kappa >= 0.4:
        quality = "Moderate (0.4 ≤ κ < 0.6)"
    elif kappa >= 0.2:
        quality = "Fair (0.2 ≤ κ < 0.4)"
    else:
        quality = "Poor (κ < 0.2) — judge needs recalibration"

    lines.append(f"Judge quality:     {quality}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Judge Calibration — Cohen's Kappa")
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        help=f"Look-back window in hours (default: {DEFAULT_HOURS})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Judge binarization threshold (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--min-pairs",
        type=int,
        default=DEFAULT_MIN_PAIRS,
        dest="min_pairs",
        help=f"Minimum matched pairs required (default: {DEFAULT_MIN_PAIRS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print stats without computing metrics",
    )
    args = parser.parse_args()

    from langfuse import Langfuse

    lf = Langfuse()

    if args.dry_run:
        pairs = fetch_matched_pairs(lf.api, hours=args.hours)
        print(f"Found {len(pairs)} matched pairs (dry run, no metrics computed).")
        sys.exit(0)

    try:
        report = run_calibration(
            lf.api,
            hours=args.hours,
            threshold=args.threshold,
            min_pairs=args.min_pairs,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    print(_format_report(report))


if __name__ == "__main__":
    main()
