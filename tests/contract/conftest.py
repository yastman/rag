from pathlib import Path

import pytest
import yaml


CONTRACT_PATH = Path(__file__).resolve().parent.parent / "observability" / "trace_contract.yaml"


@pytest.fixture(scope="session")
def trace_contract():
    if not CONTRACT_PATH.exists():
        pytest.skip(
            f"trace_contract.yaml not found at {CONTRACT_PATH} — "
            "observability contract fixture absent after Langfuse removal; "
            "see #2983 for follow-up"
        )
    with open(CONTRACT_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def required_families(trace_contract):
    return trace_contract["required_families"]


@pytest.fixture(scope="session")
def all_contract_spans(trace_contract):
    spans = []
    for group in trace_contract["spans"].values():
        spans.extend(group)
    return spans


@pytest.fixture(scope="session")
def sensitive_spans(trace_contract):
    return trace_contract["sensitive_spans"]


@pytest.fixture(scope="session")
def score_keys(trace_contract):
    scores = []
    for group in trace_contract["scores"].values():
        scores.extend(group)
    return scores


@pytest.fixture(scope="session")
def coverage_tiers(trace_contract):
    return trace_contract.get("coverage_tiers", {})
