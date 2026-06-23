"""Contract: pipeline docs reflect the current dual-path architecture (#1955).

The bot has two RAG entrypoints with divergent orchestrators (see
ADR-0010 and #1538):

* Text path uses ``langchain.agents.create_agent`` in
  ``telegram_bot/agents/agent.py``.
* Voice path uses a custom ``StateGraph`` in
  ``telegram_bot/graph/graph.py``.

Three docs describe slices of this architecture:

* ``docs/PIPELINE_OVERVIEW.md`` — operational view of all flows
  (ingestion / query / voice).
* ``docs/PIPELINE_ROUTING.md`` — StateGraph routing rules; remains the
  source of truth for the voice path and the ``rag_search`` tool reused
  by the text path.
* ``docs/CLIENT_PIPELINE.md`` — canonical description of the
  dual-path split.

This contract pins three drift-prone properties:

1. Each doc carries a short header pointing at the other two so readers
   land on the right place.
2. ``CLIENT_PIPELINE.md`` is the single canonical dual-path home; the
   other two link to it.
3. Each doc references ADR-0010 and the SDK-native audit issue #1538
   so the migration plan is one click away.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

PIPELINE_OVERVIEW = REPO_ROOT / "docs" / "PIPELINE_OVERVIEW.md"
PIPELINE_ROUTING = REPO_ROOT / "docs" / "PIPELINE_ROUTING.md"
CLIENT_PIPELINE = REPO_ROOT / "docs" / "CLIENT_PIPELINE.md"

ALL_DOCS = (PIPELINE_OVERVIEW, PIPELINE_ROUTING, CLIENT_PIPELINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _header_block(text: str, lines: int = 12) -> str:
    return "\n".join(text.splitlines()[:lines])


@pytest.mark.parametrize("path", ALL_DOCS, ids=lambda p: p.name)
def test_doc_header_links_to_other_two(path: Path) -> None:
    """Each doc's first ~12 lines must point at the other two pipeline docs."""
    text = _header_block(_read(path))
    others = [d.name for d in ALL_DOCS if d != path]
    missing = [name for name in others if name not in text]
    assert not missing, (
        f"#{1955}: {path.name} header must reference both other pipeline docs so "
        f"readers can pivot to the right surface. Missing references: {missing}. "
        "Add a 'see also' line within the first ~12 lines."
    )


@pytest.mark.parametrize("path", (PIPELINE_OVERVIEW, PIPELINE_ROUTING), ids=lambda p: p.name)
def test_secondary_docs_point_at_canonical_dual_path(path: Path) -> None:
    """PIPELINE_OVERVIEW and PIPELINE_ROUTING must defer dual-path detail to CLIENT_PIPELINE.md."""
    text = _read(path)
    assert "CLIENT_PIPELINE.md" in text, (
        f"#{1955}: {path.name} must link to CLIENT_PIPELINE.md, the canonical home for the "
        "dual-path (text=create_agent / voice=StateGraph) architecture."
    )


@pytest.mark.parametrize("path", ALL_DOCS, ids=lambda p: p.name)
def test_doc_references_adr_0010_and_sdk_audit(path: Path) -> None:
    """Each doc must point at ADR-0010 (voice migration plan) and the SDK-native audit (#1538)."""
    text = _read(path)
    assert "0010" in text, (
        f"#{1955}: {path.name} must reference ADR-0010 (voice path migration). "
        "Link to docs/adr/0010-voice-path-create-agent-migration-plan.md."
    )
    assert "#1538" in text or "1538" in text, (
        f"#{1955}: {path.name} must reference the SDK-native audit issue "
        "(#1538) so the dual-path context is discoverable."
    )


def test_canonical_dual_path_doc_names_both_orchestrators() -> None:
    """CLIENT_PIPELINE.md must explicitly name both orchestrators."""
    text = _read(CLIENT_PIPELINE)
    assert "create_agent" in text, (
        "#1955: CLIENT_PIPELINE.md must name the create_agent SDK explicitly for the text path."
    )
    assert "StateGraph" in text or "build_graph" in text, (
        "#1955: CLIENT_PIPELINE.md must name the StateGraph orchestrator explicitly "
        "for the voice path so the asymmetry is documented."
    )


def test_pipeline_overview_does_not_misattribute_text_path_to_stategraph() -> None:
    """Stale claim guard: PIPELINE_OVERVIEW must not say the bot's main entry uses StateGraph alone.

    The pre-#1955 text said 'telegram_bot/graph/graph.py builds a LangGraph state machine'
    without mentioning that the text path uses create_agent. After #1955, that line either
    must be removed or qualified so readers don't conclude the entire bot runs on StateGraph.
    """
    text = _read(PIPELINE_OVERVIEW)
    if "telegram_bot/graph/graph.py builds a LangGraph state machine" in text:
        pytest.fail(
            "#1955: PIPELINE_OVERVIEW.md still claims 'telegram_bot/graph/graph.py builds a "
            "LangGraph state machine' without mentioning the create_agent text path. Qualify "
            "the statement (voice path) or remove it."
        )
