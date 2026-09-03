"""Contract: the test-only retrieve compatibility shim stays deleted (#3250).

``telegram_bot/graph/nodes/retrieve.py`` was a minimal compatibility shim
kept only so legacy latency-unit assertions could import ``retrieve_node``
after the legacy StateGraph stack was removed. It had no kept runtime,
handler, entrypoint, deployment, factory, or dynamic-registration caller,
and its unannotated ``documents`` list broke the authoritative MyPy gate.

This assertion pins the deletion so the shim cannot quietly return to
``dev``. The live retrieval path is the assistant-core pipeline (the
``telegram_bot/agents`` history-graph island was removed in #3216); the
broader ``telegram_bot/graph/`` compatibility façade remains owned by
#2697/#3220, not by this leaf.

Re-introducing a graph retrieve node requires an explicit decision and
removing this assertion.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_graph_nodes_retrieve_shim_is_gone() -> None:
    """``telegram_bot/graph/nodes/retrieve.py`` must remain deleted (#3250)."""
    path = REPO_ROOT / "telegram_bot" / "graph" / "nodes" / "retrieve.py"
    assert not path.exists(), (
        f"#3250 regression: {path.relative_to(REPO_ROOT)} reappeared after "
        f"the test-only shim deletion. Live retrieval lives in the "
        f"assistant-core pipeline; do not recreate the compatibility shim."
    )


def test_no_references_to_graph_retrieve_shim() -> None:
    """No kept module may import the deleted ``graph.nodes.retrieve`` leaf."""
    self_path = Path(__file__).relative_to(REPO_ROOT).as_posix()
    offenders: list[str] = []
    for root in ("src", "telegram_bot", "tests"):
        base = REPO_ROOT / root
        for py in base.rglob("*.py"):
            if py.relative_to(REPO_ROOT).as_posix() == self_path:
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            if "graph.nodes.retrieve" in text or "graph/nodes/retrieve" in text:
                offenders.append(py.relative_to(REPO_ROOT).as_posix())
    assert not offenders, (
        f"#3250 regression: references to the deleted retrieve shim found in "
        f"{offenders}. The leaf was deleted because it was test-only and "
        f"unreachable; do not re-import it."
    )
