from __future__ import annotations

from scripts.e2e.config import E2EConfig
from scripts.e2e.test_scenarios import SCENARIOS
from scripts.e2e.test_scenarios import TestGroup as _ScenarioGroup


def test_e2e_config_defaults_to_canonical_collection() -> None:
    cfg = E2EConfig()
    assert cfg.test_collection == "gdrive_documents_bge"
    assert cfg.test_collection != "contextual_bulgaria_test"


def test_scenarios_include_immigration_corpus_coverage() -> None:
    immigration = [s for s in SCENARIOS if s.group == _ScenarioGroup.IMMIGRATION]
    assert len(immigration) >= 5

    text = " ".join((s.query + " " + " ".join(s.expected_keywords)) for s in immigration).lower()
    for token in ("внж", "пмж", "digital nomad", "виза"):
        assert token in text
