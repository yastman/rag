#!/usr/bin/env python3
"""
Quick test for MLflow integration in run_ab_test.py

Runs A/B test with just 5 queries to verify MLflow logging works.
"""

import json
import sys
import tempfile
from pathlib import Path


# Add parent path
sys.path.insert(0, str(Path(__file__).parent))

from run_ab_test import run_ab_test


def main():
    print("=" * 80)
    print("🧪 TESTING MLflow Integration in run_ab_test.py")
    print("=" * 80)
    print()

    # Create temporary queries file with just 5 queries for fast testing
    test_queries = [
        {"query": "статья 1 Уголовного кодекса Украины задачи", "expected_article": "1"},
        {
            "query": "статья 9 УК Украины правовые последствия осуждения за границ",
            "expected_article": "9",
        },
        {
            "query": "статья 17 добровольный отказ при неоконченном преступлении",
            "expected_article": "17",
        },
        {"query": "статья 25 неосторожность уголовный кодекс Украины", "expected_article": "25"},
        {"query": "статья 33 совокупность преступлений Украины", "expected_article": "33"},
    ]

    # Create temp file for queries
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(test_queries, f, ensure_ascii=False, indent=2)
        temp_queries_file = f.name

    try:
        print(f"📋 Using {len(test_queries)} test queries")
        print()

        # Run A/B test
        results = run_ab_test(
            queries_file=temp_queries_file,
            ground_truth_file="evaluation/data/ground_truth_articles.json",
            collection_name="uk_civil_code_v2",
            output_dir="evaluation/reports",
        )

        print()
        print("=" * 80)
        print("✅ MLflow Integration Test PASSED")
        print("=" * 80)
        print()
        print("📊 Check results:")
        print("   - MLflow UI: http://localhost:5000/#/experiments")
        print(f"   - Reports: {results['reports']}")
        print()

    finally:
        # Clean up temp file
        Path(temp_queries_file).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
