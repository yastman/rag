# tests/unit/test_crm_scores.py
"""Tests for CRM tool Langfuse scores (#440)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from telegram_bot.scoring import write_crm_scores


def _tool_msg(name: str, content: str, *, status: str | None = None) -> SimpleNamespace:
    """Create a minimal ToolMessage-like object."""
    return SimpleNamespace(type="tool", name=name, content=content, status=status)


def _human_msg(content: str = "hello") -> SimpleNamespace:
    return SimpleNamespace(type="human", content=content)


def _ai_msg(content: str = "sure") -> SimpleNamespace:
    return SimpleNamespace(type="ai", content=content)


def _make_lf() -> MagicMock:
    lf = MagicMock()
    lf.create_score = MagicMock()
    return lf


class TestWriteCrmScores:
    """write_crm_scores() unit tests."""

    def test_no_crm_tools(self):
        """No CRM tool calls → crm_tool_used=0, counts=0."""
        lf = _make_lf()
        messages = [
            _human_msg("find apartments"),
            _ai_msg("Here are results..."),
            _tool_msg("rag_search", "some RAG result"),
        ]

        write_crm_scores(lf, messages, trace_id="t-1")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_tool_used"] == 0
        assert calls["crm_tools_count"] == 0.0
        assert calls["crm_tools_success"] == 0.0
        assert calls["crm_tools_error"] == 0.0

    def test_mixed_success_and_error(self):
        """2 CRM calls: 1 success, 1 error → correct counts."""
        lf = _make_lf()
        messages = [
            _human_msg("create a deal"),
            _ai_msg("calling tools..."),
            _tool_msg("crm_create_lead", "Сделка создана: ID 42, Test Deal"),
            _tool_msg("crm_get_deal", "Ошибка при получении сделки: timeout"),
        ]

        write_crm_scores(lf, messages, trace_id="t-2")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_tool_used"] == 1
        assert calls["crm_tools_count"] == 2.0
        assert calls["crm_tools_success"] == 1.0
        assert calls["crm_tools_error"] == 1.0

    def test_crm_unavailable_counted_as_error(self):
        """CRM unavailable message → counted as error."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_get_contacts", "CRM недоступен. Обратитесь к администратору."),
        ]

        write_crm_scores(lf, messages, trace_id="t-3")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_tool_used"] == 1
        assert calls["crm_tools_count"] == 1.0
        assert calls["crm_tools_success"] == 0.0
        assert calls["crm_tools_error"] == 1.0

    def test_empty_trace_id_skips(self):
        """Empty trace_id → no scores written."""
        lf = _make_lf()
        write_crm_scores(lf, [_tool_msg("crm_get_deal", "ok")], trace_id="")

        lf.create_score.assert_not_called()

    def test_all_success(self):
        """3 successful CRM calls → all counted as success."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_create_lead", "Сделка создана: ID 1, New"),
            _tool_msg("crm_add_note", "Заметка добавлена: ID 10"),
            _tool_msg("crm_upsert_contact", "Контакт: ID 5, John"),
        ]

        write_crm_scores(lf, messages, trace_id="t-4")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_tool_used"] == 1
        assert calls["crm_tools_count"] == 3.0
        assert calls["crm_tools_success"] == 3.0
        assert calls["crm_tools_error"] == 0.0

    def test_non_crm_tools_ignored(self):
        """Non-CRM tool messages are not counted."""
        lf = _make_lf()
        messages = [
            _tool_msg("rag_search", "some results"),
            _tool_msg("history_search", "past conversations"),
            _tool_msg("crm_get_deal", '{"id": 42, "name": "Test"}'),
        ]

        write_crm_scores(lf, messages, trace_id="t-5")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_tools_count"] == 1.0

    def test_score_ids_use_trace_prefix(self):
        """Score IDs follow {trace_id}-{name} pattern."""
        lf = _make_lf()
        write_crm_scores(lf, [], trace_id="abc-123")

        for call in lf.create_score.call_args_list:
            score_id = call.kwargs["score_id"]
            score_name = call.kwargs["name"]
            assert score_id == f"abc-123-{score_name}"

    def test_tool_status_error_is_prioritized(self):
        """ToolMessage status=error should be counted as error even without error text."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_get_deal", '{"id": 42, "name": "Test"}', status="error"),
        ]

        write_crm_scores(lf, messages, trace_id="t-6")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_tools_count"] == 1.0
        assert calls["crm_tools_success"] == 0.0
        assert calls["crm_tools_error"] == 1.0

    def test_tool_status_success_is_prioritized(self):
        """ToolMessage status=success should be counted as success."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_get_deal", "Ошибка при получении сделки: timeout", status="success"),
        ]

        write_crm_scores(lf, messages, trace_id="t-7")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_tools_count"] == 1.0
        assert calls["crm_tools_success"] == 1.0
        assert calls["crm_tools_error"] == 0.0


class TestWriteCrmScoresPerTool:
    """Per-tool result score tests (#541)."""

    def test_per_tool_success_score(self):
        """Successful CRM call writes per-tool _result=success CATEGORICAL score."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_create_lead", "Сделка создана: ID 1, New"),
        ]

        write_crm_scores(lf, messages, trace_id="t-pt-1")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_create_lead_result"] == "success"
        # Verify data_type=CATEGORICAL
        dt_calls = {
            c.kwargs["name"]: c.kwargs.get("data_type") for c in lf.create_score.call_args_list
        }
        assert dt_calls["crm_create_lead_result"] == "CATEGORICAL"

    def test_per_tool_error_score(self):
        """Failed CRM call writes per-tool _result=error CATEGORICAL score."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_get_deal", "Ошибка при получении сделки: timeout"),
        ]

        write_crm_scores(lf, messages, trace_id="t-pt-2")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_get_deal_result"] == "error"

    def test_per_tool_mixed_results(self):
        """Multiple CRM calls write separate per-tool scores."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_create_lead", "Сделка создана: ID 1, New"),
            _tool_msg("crm_add_note", "Ошибка при добавлении заметки: 500"),
            _tool_msg("crm_get_contacts", "- Ivan Petrov (ID: 10)"),
        ]

        write_crm_scores(lf, messages, trace_id="t-pt-3")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_create_lead_result"] == "success"
        assert calls["crm_add_note_result"] == "error"
        assert calls["crm_get_contacts_result"] == "success"

    def test_per_tool_status_field_used(self):
        """status field on ToolMessage takes priority for per-tool score."""
        lf = _make_lf()
        messages = [
            _tool_msg("crm_get_deal", "some content", status="error"),
        ]

        write_crm_scores(lf, messages, trace_id="t-pt-4")

        calls = {c.kwargs["name"]: c.kwargs["value"] for c in lf.create_score.call_args_list}
        assert calls["crm_get_deal_result"] == "error"

    def test_no_per_tool_scores_when_no_crm_messages(self):
        """No per-tool scores when no CRM tool messages present."""
        lf = _make_lf()
        messages = [
            _tool_msg("rag_search", "RAG results"),
            _human_msg("hello"),
        ]

        write_crm_scores(lf, messages, trace_id="t-pt-5")

        score_names = {c.kwargs["name"] for c in lf.create_score.call_args_list}
        per_tool = {n for n in score_names if n.endswith("_result")}
        assert per_tool == set()
