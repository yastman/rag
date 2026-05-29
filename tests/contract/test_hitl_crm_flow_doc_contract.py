"""Contract: ``docs/HITL_CRM_FLOW.md`` matches the real HITL CRM code (#2213).

The HITL CRM write-confirmation flow is real and SDK-native:

* ``telegram_bot/agents/crm_tools.py`` write tools call
  ``hitl_guard(tool, preview, args)``;
* ``hitl_guard`` (``telegram_bot/agents/hitl.py``) calls LangGraph
  ``interrupt({...})``, pausing the graph;
* the bot detects ``result["__interrupt__"]`` and ``_send_hitl_confirmation``
  posts an inline keyboard (``hitl:approve`` / ``hitl:cancel``);
* ``handle_hitl_callback`` resumes via ``Command(resume={"action": ...})``.

The previous doc drifted: it listed tools that do not exist
(``schedule_viewing`` / ``transfer_lead`` / ``update_lead_status``), described
the *separate* manager-handoff state machine (``HandoffState`` /
``handoff:{client_id}`` Redis hash / 300s auto-reject) as if it were the HITL
CRM mechanism, and pointed at a non-existent test path. This contract pins the
doc to the real code so it cannot drift back.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "HITL_CRM_FLOW.md"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_doc_exists() -> None:
    assert DOC_PATH.exists(), f"missing: {DOC_PATH}"


def test_doc_describes_real_interrupt_resume_mechanism() -> None:
    text = _doc_text()
    for token in ("hitl_guard", "interrupt(", "Command(resume", "__interrupt__"):
        assert token in text, (
            f"docs/HITL_CRM_FLOW.md must describe the real HITL mechanism and "
            f"mention {token!r} (#2213)."
        )


def test_doc_describes_agent_taxonomy_without_mistyping_parent_span() -> None:
    text = _doc_text()
    assert 'telegram-rag-supervisor`, `as_type="agent"' not in text, (
        "docs/HITL_CRM_FLOW.md must not claim telegram-rag-supervisor is an "
        "agent span: that parent can return from pre-agent cache/direct-pipeline "
        "paths before any create_agent invocation (#2213/#2216)."
    )
    for token in ("telegram-rag-agent-stream", "telegram-rag-agent-invoke"):
        assert token in text, (
            "docs/HITL_CRM_FLOW.md must name the actual SDK agent invocation "
            f"span {token!r} as the as_type='agent' observation (#2213/#2216)."
        )
    assert "generic parent span" in text, (
        "docs/HITL_CRM_FLOW.md must explain that telegram-rag-supervisor stays "
        "a generic parent span around orchestration/pre-agent paths (#2213/#2216)."
    )


def test_doc_lists_real_hitl_wrapped_tools() -> None:
    """The doc's trigger list must be the tools that actually call hitl_guard."""
    text = _doc_text()
    real_tools = (
        "crm_create_lead",
        "crm_update_lead",
        "crm_upsert_contact",
        "crm_update_contact",
    )
    for tool in real_tools:
        assert tool in text, (
            f"docs/HITL_CRM_FLOW.md must list the real HITL-wrapped tool {tool!r} "
            "(it calls hitl_guard in telegram_bot/agents/crm_tools.py) (#2213)."
        )


def test_doc_does_not_reference_nonexistent_tools() -> None:
    """Stale tool names from the old doc must be gone."""
    text = _doc_text()
    for stale in ("schedule_viewing", "transfer_lead", "update_lead_status"):
        assert stale not in text, (
            f"docs/HITL_CRM_FLOW.md references {stale!r}, which is not a real HITL "
            "CRM tool. Remove the stale entry (#2213)."
        )


def test_doc_references_only_existing_code_locations() -> None:
    """Real code locations the doc points to must exist; stale ones must be absent."""
    text = _doc_text()
    must_exist = (
        "telegram_bot/agents/hitl.py",
        "telegram_bot/agents/crm_tools.py",
        "tests/unit/agents/test_hitl.py",
    )
    for rel in must_exist:
        assert rel in text, (
            f"docs/HITL_CRM_FLOW.md should reference the real location {rel!r} (#2213)."
        )
        assert (REPO_ROOT / rel).exists(), (
            f"doc references {rel!r} but it does not exist in the repo (#2213)."
        )
    # The old doc pointed at a test path that never existed.
    assert "tests/unit/telegram_bot/test_handoff.py" not in text, (
        "docs/HITL_CRM_FLOW.md references a non-existent test path "
        "tests/unit/telegram_bot/test_handoff.py; the real HITL tests live in "
        "tests/unit/agents/test_hitl.py (#2213)."
    )
