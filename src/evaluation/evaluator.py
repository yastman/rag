#!/usr/bin/env python3
"""
Evaluator for search engine performance.

Metrics:
- Recall@K: Found correct article in top-K results
- NDCG@10: Normalized Discounted Cumulative Gain (ranking quality)
- MRR: Mean Reciprocal Rank (position of first correct result)
- Precision@K: Proportion of relevant results in top-K
- Failure Rate: Queries with no correct results
"""

import json

import numpy as np
import pandas as pd


class SearchEvaluator:
    """Evaluates search engine performance using multiple metrics."""

    def __init__(self, ground_truth_file: str):
        """
        Initialize evaluator with ground truth data.

        Args:
            ground_truth_file: Path to ground_truth_articles.json
        """
        with open(ground_truth_file, encoding="utf-8") as f:
            self.ground_truth = json.load(f)

    def evaluate_query(
        self, query: dict, search_results: list[dict], k_values: list[int] | None = None
    ) -> dict:
        """
        Evaluate a single query's results.

        Args:
            query: Query dict with 'expected_article' field
            search_results: List of search results from search engine
            k_values: K values for Recall@K and Precision@K

        Returns:
            Dict with metrics for this query
        """
        if k_values is None:
            k_values = [1, 3, 5, 10]
        expected_article = query["expected_article"]
        retrieved_articles = [str(r["article_number"]) for r in search_results]

        metrics = {
            "query": query["query"],
            "expected_article": expected_article,
            "retrieved_articles": retrieved_articles[:10],
        }

        # Recall@K: Is expected article in top-K results?
        for k in k_values:
            metrics[f"recall@{k}"] = 1 if expected_article in retrieved_articles[:k] else 0

        # MRR: Position of first correct result
        try:
            rank = retrieved_articles.index(expected_article) + 1
            metrics["mrr"] = 1.0 / rank
            metrics["rank"] = rank
        except ValueError:
            metrics["mrr"] = 0.0
            metrics["rank"] = None

        # NDCG@10: Normalized Discounted Cumulative Gain
        metrics["ndcg@10"] = self._calculate_ndcg(expected_article, retrieved_articles[:10])

        # Precision@K: Proportion of relevant results
        for k in k_values:
            relevant_in_k = sum(1 for art in retrieved_articles[:k] if art == expected_article)
            metrics[f"precision@{k}"] = relevant_in_k / k

        return metrics

    def _calculate_ndcg(self, expected: str, retrieved: list[str]) -> float:
        """
        Calculate NDCG@10 for a query.

        For our case: relevance is binary (1 if matches expected_article, 0 otherwise).
        """
        # Relevance scores: 1 for expected article, 0 for others
        relevance = [1 if art == expected else 0 for art in retrieved]

        # DCG: sum of rel_i / log2(i+1)
        dcg = sum(
            rel / np.log2(i + 2)  # i+2 because i starts from 0
            for i, rel in enumerate(relevance)
        )

        # IDCG: best possible DCG (expected article at position 1)
        idcg = 1.0 / np.log2(2)  # 1 / log2(2) = 1.0

        # NDCG
        return dcg / idcg if idcg > 0 else 0.0

    def evaluate_queries(
        self,
        queries: list[dict],
        search_results_map: dict[str, list[dict]],
        k_values: list[int] | None = None,
    ) -> dict:
        """
        Evaluate multiple queries.

        Args:
            queries: List of query dicts
            search_results_map: Dict mapping query text -> search results
            k_values: K values for metrics

        Returns:
            Dict with aggregated metrics
        """
        if k_values is None:
            k_values = [1, 3, 5, 10]
        all_results = []

        for query in queries:
            query_text = query["query"]
            if query_text not in search_results_map:
                print(f"⚠️  No results for query: {query_text}")
                continue

            search_results = search_results_map[query_text]
            query_metrics = self.evaluate_query(query, search_results, k_values)
            query_metrics["query_type"] = query.get("type", "unknown")
            query_metrics["difficulty"] = query.get("difficulty", "unknown")
            all_results.append(query_metrics)

        # Aggregate metrics
        df = pd.DataFrame(all_results)

        aggregated = {"total_queries": len(all_results), "metrics": {}}

        # Recall@K
        for k in k_values:
            col = f"recall@{k}"
            if col in df.columns:  # type: ignore[index]
                aggregated["metrics"][col] = float(df[col].mean())  # type: ignore[index]

        # MRR
        if "mrr" in df.columns:  # type: ignore[index]
            aggregated["metrics"]["mrr"] = float(df["mrr"].mean())  # type: ignore[index]
        # type: ignore[index]
        # NDCG@10 # type: ignore[index]
        if "ndcg@10" in df.columns:  # type: ignore[index]
            aggregated["metrics"]["ndcg@10"] = float(df["ndcg@10"].mean())  # type: ignore[index]
        # type: ignore[index]
        # Precision@K # type: ignore[index]
        for k in k_values:  # type: ignore[index]
            col = f"precision@{k}"  # type: ignore[index]
            if col in df.columns:  # type: ignore[index]
                aggregated["metrics"][col] = float(df[col].mean())  # type: ignore[index]
        # type: ignore[index]
        # Failure rate: queries with no correct result in top-10 # type: ignore[index]
        if "recall@10" in df.columns:  # type: ignore[index]
            failure_rate = 1.0 - df["recall@10"].mean()  # type: ignore[index]
            aggregated["metrics"]["failure_rate"] = float(failure_rate)  # type: ignore[index]
        # type: ignore[index]
        # By query type # type: ignore[index]
        if "query_type" in df.columns:  # type: ignore[index]
            aggregated["by_query_type"] = {}  # type: ignore[index]
            for qtype in df["query_type"].unique():  # type: ignore[index]
                subset = df[df["query_type"] == qtype]  # type: ignore[index]
                aggregated["by_query_type"][qtype] = {  # type: ignore[index]
                    "count": len(subset),
                    "recall@10": float(subset["recall@10"].mean())
                    if "recall@10" in subset.columns
                    else 0,
                    "mrr": float(subset["mrr"].mean()) if "mrr" in subset.columns else 0,
                    "ndcg@10": float(subset["ndcg@10"].mean())
                    if "ndcg@10" in subset.columns
                    else 0,
                }

        # By difficulty
        if "difficulty" in df.columns:
            aggregated["by_difficulty"] = {}
            for difficulty in df["difficulty"].unique():
                subset = df[df["difficulty"] == difficulty]
                aggregated["by_difficulty"][difficulty] = {  # type: ignore[index]
                    "count": len(subset),
                    "recall@10": float(subset["recall@10"].mean())
                    if "recall@10" in subset.columns
                    else 0,
                    "mrr": float(subset["mrr"].mean()) if "mrr" in subset.columns else 0,
                    "ndcg@10": float(subset["ndcg@10"].mean())
                    if "ndcg@10" in subset.columns
                    else 0,
                }

        # Detailed results
        aggregated["detailed_results"] = all_results

        return aggregated

    def compare_engines(self, baseline_results: dict, hybrid_results: dict) -> dict:
        """
        Compare two search engines statistically.

        Args:
            baseline_results: Results from evaluate_queries() for baseline
            hybrid_results: Results from evaluate_queries() for hybrid

        Returns:
            Dict with comparison metrics and statistical significance
        """
        comparison = {
            "baseline": baseline_results["metrics"],
            "hybrid": hybrid_results["metrics"],
            "improvements": {},
            "statistical_significance": {},
        }

        # Calculate improvements
        for metric in baseline_results["metrics"]:
            baseline_val = baseline_results["metrics"][metric]
            hybrid_val = hybrid_results["metrics"][metric]

            if metric == "failure_rate":
                # Lower is better for failure rate
                improvement = (
                    (baseline_val - hybrid_val) / baseline_val * 100 if baseline_val > 0 else 0
                )
            else:
                # Higher is better for other metrics
                improvement = (
                    (hybrid_val - baseline_val) / baseline_val * 100 if baseline_val > 0 else 0
                )

            comparison["improvements"][metric] = {
                "baseline": baseline_val,
                "hybrid": hybrid_val,
                "absolute_diff": hybrid_val - baseline_val,
                "relative_improvement_pct": improvement,
            }

        # Statistical significance (simple paired t-test on Recall@10)
        baseline_detailed = baseline_results.get("detailed_results", [])
        hybrid_detailed = hybrid_results.get("detailed_results", [])

        if len(baseline_detailed) == len(hybrid_detailed) and len(baseline_detailed) > 1:
            from scipy import stats

            baseline_recall10 = [r.get("recall@10", 0) for r in baseline_detailed]
            hybrid_recall10 = [r.get("recall@10", 0) for r in hybrid_detailed]

            t_stat, p_value = stats.ttest_rel(hybrid_recall10, baseline_recall10)

            comparison["statistical_significance"]["recall@10"] = {
                "t_statistic": float(t_stat),
                "p_value": float(p_value),
                "significant_at_0.05": p_value < 0.05,
                "significant_at_0.01": p_value < 0.01,
            }

        return comparison


if __name__ == "__main__":
    # Quick test
    evaluator = SearchEvaluator("evaluation/data/ground_truth_articles.json")

    # Mock data for testing
    test_query = {"query": "test query", "expected_article": "185", "type": "semantic"}

    test_results = [
        {"point_id": 1, "article_number": "121", "score": 0.95},
        {"point_id": 2, "article_number": "185", "score": 0.89},  # Correct at position 2
        {"point_id": 3, "article_number": "289", "score": 0.85},
    ]

    metrics = evaluator.evaluate_query(test_query, test_results)
    print("Test metrics:")
    print(f"  Recall@1: {metrics['recall@1']}")
    print(f"  Recall@3: {metrics['recall@3']}")
    print(f"  MRR: {metrics['mrr']:.4f}")
    print(f"  NDCG@10: {metrics['ndcg@10']:.4f}")
    print(f"  Rank: {metrics['rank']}")
