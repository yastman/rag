"""Unit tests for the automated five-minute demo gate (#3205).

All tests are OFFLINE: the journey executor runs against a fake transport
that replays scripted bot messages, and the readiness probes are injected.
No live Telegram/Qdrant/BGE/Redis access happens here — the live behavior is
proven by running ``make demo-gate MODE=--prerequisites-only`` against the
real stack.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.e2e import demo_gate
from scripts.e2e.config import E2EConfig
from scripts.e2e.demo_gate import (
    ARTIFACT_SCHEMA_VERSION,
    CheckOutcome,
    JourneyAction,
    JourneyStep,
    StepRecord,
    build_artifact,
    build_journey_steps,
    catalog_result_count,
    execute_step,
    is_fabricated_listing,
    is_status_message,
    matches_safe_family,
    run_journey,
    run_prerequisites,
    terminal_catalog_results,
    write_artifact,
)
from scripts.e2e.telegram_client import JourneyButtonNotFound, JourneyTimeout, ReceivedMessage

# The frozen no-answer question is owned by the #3200 characterization lock;
# the gate must use exactly that question (drift fails here).
from tests.characterization.test_grounded_qa_acceptance import (
    UNSUPPORTED_QUESTION as FROZEN_UNSUPPORTED_QUESTION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(
    text: str,
    message_id: int = 1,
    *,
    buttons: tuple[str, ...] = (),
    reply_buttons: tuple[str, ...] = (),
) -> ReceivedMessage:
    return ReceivedMessage(
        text=text,
        message_id=message_id,
        response_time_ms=10,
        button_labels=buttons,
        has_reply_keyboard=bool(reply_buttons),
        reply_button_labels=reply_buttons,
    )


def _step(**overrides: Any) -> JourneyStep:
    base: dict[str, Any] = {
        "id": "step",
        "title": "Step",
        "action": JourneyAction(kind="text", value="hi"),
        "route": "text",
        "terminal": demo_gate.terminal_any_answer,
    }
    base.update(overrides)
    return JourneyStep(**base)


class FakeSession:
    """Scripted transport: replays messages per step, records actions."""

    def __init__(self, script: dict[str, Any]):
        # script: step id -> {"messages": [ReceivedMessage], "click": label}
        # or an exception instance/type to raise instead.
        self.script = script
        self.sent: list[str] = []
        self.clicks: list[tuple[str, int | None, bool]] = []
        self.current_step = "step"

    def set_step(self, step_id: str) -> None:
        self.current_step = step_id

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def click_inline_button(
        self,
        locator: str,
        *,
        message_id: int | None = None,
        first: bool = False,
    ) -> str:
        self.clicks.append((locator, message_id, first))
        entry = self.script[self.current_step]
        if isinstance(entry, Exception):
            raise entry
        clicked = entry.get("click")
        if clicked is None and isinstance(entry.get("raise_click"), Exception):
            raise entry["raise_click"]
        return clicked or locator

    async def collect_until_terminal(self, **_kwargs: Any) -> list[ReceivedMessage]:
        entry = self.script[self.current_step]
        if isinstance(entry, Exception):
            raise entry
        if isinstance(entry.get("collect"), Exception):
            raise entry["collect"]
        return entry.get("messages", [])


# ---------------------------------------------------------------------------
# Frozen script definition (the five-minute story)
# ---------------------------------------------------------------------------


class TestFrozenScript:
    def test_step_order_covers_the_issue_story(self) -> None:
        ids = [step.id for step in build_journey_steps()]
        assert ids == [
            "clean_start",
            "demo_open",
            "demo_apartments",
            "apartment_search_1",
            "apartment_search_2",
            "return_navigation",
            "ask_open",
            "grounded_qa",
            "safe_no_answer",
            "clean_close",
        ]

    def test_two_apartment_searches_with_thresholds(self) -> None:
        steps = {step.id: step for step in build_journey_steps()}
        # Search #1: inline example click; dynamic examples guarantee >= 1.
        assert steps["apartment_search_1"].action.kind == "inline_button"
        assert steps["apartment_search_1"].action.first_button
        assert steps["apartment_search_1"].min_result_count == 1
        # Search #2: typed golden query through the production seed contract.
        assert steps["apartment_search_2"].action.kind == "text"
        assert steps["apartment_search_2"].action.value == demo_gate.GOLDEN_DEMO_QUERIES[0]
        assert steps["apartment_search_2"].min_result_count == demo_gate.GOLDEN_QUERY_MIN_RESULTS

    def test_reply_and_inline_buttons_are_both_exercised(self) -> None:
        steps = {step.id: step for step in build_journey_steps()}
        assert steps["demo_open"].action.kind == "reply_button"
        assert steps["return_navigation"].action.kind == "reply_button"
        assert steps["ask_open"].action.kind == "reply_button"
        assert steps["demo_apartments"].action.kind == "inline_button"
        assert steps["grounded_qa"].action.kind == "inline_button"

    def test_frozen_no_answer_question_matches_characterization_lock(self) -> None:
        assert demo_gate.UNSUPPORTED_QUESTION == FROZEN_UNSUPPORTED_QUESTION

    def test_labels_come_from_production_keyboards(self) -> None:
        assert demo_gate.DEMO_REPLY_LABEL == "🎯 Демонстрация"
        assert demo_gate.ASK_REPLY_LABEL == "💬 Задать вопрос"
        assert demo_gate.CATALOG_HOME_LABEL == "🏠 Главное меню"

    def test_clean_start_and_close_reset_the_chat(self) -> None:
        steps = {step.id: step for step in build_journey_steps()}
        for step_id in ("clean_start", "clean_close"):
            assert steps[step_id].action.value == "/start"
            assert steps[step_id].expects_reply_buttons  # root menu proof


# ---------------------------------------------------------------------------
# Terminal predicates and classifiers
# ---------------------------------------------------------------------------


class TestPredicates:
    def test_catalog_result_count_extraction(self) -> None:
        assert catalog_result_count("Найдено 12 вариантов:") == 12
        assert catalog_result_count("no results here") is None

    def test_status_messages_are_recognized(self) -> None:
        assert is_status_message("🔍 Ищу подходящие варианты...")
        assert not is_status_message("Найдено 3 вариантов:")

    def test_catalog_terminal_accepts_results_and_explicit_empty(self) -> None:
        assert terminal_catalog_results("Найдено 5 вариантов:")
        assert terminal_catalog_results("К сожалению, ничего не найдено")
        assert not terminal_catalog_results("🔍 Ищу подходящие варианты...")

    def test_safe_family_markers(self) -> None:
        assert matches_safe_family("⚠️ Извините, сервис временно недоступен.")
        assert matches_safe_family("Я отвечаю по теме недвижимости и связанных услуг.")
        assert not matches_safe_family("Студии в Sunny Beach стоят от 115 000 EUR.")

    def test_fabricated_listing_detection(self) -> None:
        assert is_fabricated_listing("Найдено 3 вариантов:\n1. X — 100 000€")
        assert not is_fabricated_listing("Документы для покупки: паспорт, договор.")


# ---------------------------------------------------------------------------
# Step executor against the fake transport
# ---------------------------------------------------------------------------


class TestExecuteStep:
    async def test_status_message_is_not_terminal_but_counted(self) -> None:
        step = _step(id="search", min_result_count=3)
        session = FakeSession(
            {
                "search": {
                    "messages": [
                        _msg("🔍 Ищу подходящие варианты...", 1),
                        _msg("Найдено 5 вариантов:", 2),
                    ]
                }
            }
        )
        record = await execute_step(session, step, {})
        assert record.status == "passed"
        assert record.message_count == 1
        assert record.status_message_count == 1
        assert record.terminal_message_id == 2
        assert record.result_count == 5
        assert record.single_send is True

    async def test_result_threshold_failure_has_data_diagnostic(self) -> None:
        step = _step(id="search", min_result_count=3)
        session = FakeSession({"search": {"messages": [_msg("Найдено 1 вариантов:", 2)]}})
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "only 1 listings" in record.failure
        assert "≥ 3 required" in record.failure

    async def test_empty_state_fails_with_seed_hint(self) -> None:
        step = _step(id="search", min_result_count=3)
        session = FakeSession({"search": {"messages": [_msg("К сожалению, ничего не найдено", 2)]}})
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "re-ingest the shipped seed" in record.failure

    async def test_timeout_fails_and_is_never_skipped(self) -> None:
        step = _step(id="search")
        session = FakeSession(
            {"search": {"collect": JourneyTimeout("No terminal response within 75s")}}
        )
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "timeout" in record.failure

    async def test_missing_inline_button_fails(self) -> None:
        step = _step(
            id="demo_apartments",
            action=JourneyAction(kind="inline_button", value="Подбор", from_step="demo_open"),
        )
        session = FakeSession(
            {
                "demo_apartments": {
                    "raise_click": JourneyButtonNotFound("no inline buttons"),
                    "messages": [_msg("intro", 3)],
                }
            }
        )
        record = await execute_step(
            session,
            step,
            {"demo_open": StepRecord(id="demo_open", title="t", route="r", action="a")},
        )
        assert record.status == "failed"
        assert "required surface missing" in record.failure

    async def test_transport_error_fails(self) -> None:
        step = _step(id="step")
        session = FakeSession({"step": RuntimeError("connection dropped")})
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "transport error" in record.failure

    async def test_single_send_violation_fails(self) -> None:
        step = _step(id="qa", require_single_send=True)
        session = FakeSession(
            {"qa": {"messages": [_msg("answer part 1", 1), _msg("answer part 2", 2)]}}
        )
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "exactly one answer" in record.failure

    async def test_root_menu_requires_client_reply_keyboard(self) -> None:
        step = _step(id="start", expects_reply_buttons=("🎯 Демонстрация",))
        session = FakeSession({"start": {"messages": [_msg("Привет!", 1)]}})
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "reply keyboard" in record.failure

        session_ok = FakeSession(
            {"start": {"messages": [_msg("Привет!", 1, reply_buttons=("🎯 Демонстрация",))]}}
        )
        record_ok = await execute_step(session_ok, step, {})
        assert record_ok.status == "passed"

    async def test_grounded_qa_rejects_safe_family_answers(self) -> None:
        step = _step(id="grounded_qa", require_single_send=True, forbid_safe_family=True)
        session = FakeSession(
            {"grounded_qa": {"messages": [_msg("⚠️ Извините, сервис временно недоступен.", 9)]}}
        )
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "safe/canned" in record.failure

        session_ok = FakeSession(
            {"grounded_qa": {"messages": [_msg("Для покупки нужны: паспорт, ИНН, договор.", 9)]}}
        )
        record_ok = await execute_step(session_ok, step, {})
        assert record_ok.status == "passed"

    async def test_grounded_qa_rejects_smuggled_listings(self) -> None:
        step = _step(id="grounded_qa", forbid_safe_family=True)
        session = FakeSession(
            {"grounded_qa": {"messages": [_msg("Найдено 3 вариантов:\n1. X — 5 000€", 9)]}}
        )
        record = await execute_step(session, step, {})
        assert record.status == "failed"
        assert "catalog listing rows" in record.failure

    async def test_safe_no_answer_requires_safe_family(self) -> None:
        step = _step(id="safe_no_answer", require_single_send=True, require_safe_family=True)
        unsafe = FakeSession(
            {"safe_no_answer": {"messages": [_msg("Замок стоит 1 000 000€, вот фото.", 9)]}}
        )
        record = await execute_step(unsafe, step, {})
        assert record.status == "failed"
        assert "safe no-answer family" in record.failure

        safe = FakeSession(
            {
                "safe_no_answer": {
                    "messages": [_msg("Я отвечаю по теме недвижимости и связанных услуг.", 9)]
                }
            }
        )
        record_ok = await execute_step(safe, step, {})
        assert record_ok.status == "passed"

    async def test_inline_button_requirement_on_prompt_steps(self) -> None:
        step = _step(id="ask_open", require_inline_button="документы нужны")
        session = FakeSession(
            {
                "ask_open": {
                    "messages": [
                        _msg(
                            "Напишите вопрос", 4, buttons=("📋 Какие документы нужны для покупки?",)
                        )
                    ]
                }
            }
        )
        record = await execute_step(session, step, {})
        assert record.status == "passed"

        session_bad = FakeSession({"ask_open": {"messages": [_msg("Напишите вопрос", 4)]}})
        record_bad = await execute_step(session_bad, step, {})
        assert record_bad.status == "failed"
        assert "expected inline button" in record_bad.failure

    async def test_inline_click_action_wires_from_step_message(self) -> None:
        source = StepRecord(id="demo_open", title="t", route="r", action="a")
        source.terminal_message_id = 42
        step = _step(
            id="demo_apartments",
            action=JourneyAction(kind="inline_button", value="Подбор", from_step="demo_open"),
        )
        session = FakeSession(
            {
                "demo_apartments": {
                    "click": "🏖 Подбор апартаментов",
                    "messages": [_msg("intro", 5)],
                }
            }
        )
        record = await execute_step(session, step, {"demo_open": source})
        assert record.status == "passed"
        assert record.clicked_label == "🏖 Подбор апартаментов"
        assert session.clicks == [("Подбор", 42, False)]


# ---------------------------------------------------------------------------
# Full journey + artifact
# ---------------------------------------------------------------------------


def _happy_script() -> dict[str, Any]:
    root_menu = _msg(
        "Привет! 👋",
        1,
        reply_buttons=("🎯 Демонстрация", "💬 Задать вопрос"),
    )
    return {
        "clean_start": {"messages": [root_menu]},
        "demo_open": {
            "messages": [
                _msg("🎯 Демонстрация возможностей", 2, buttons=("🏖 Подбор апартаментов",))
            ]
        },
        "demo_apartments": {
            "click": "Студия в Солнечном берегу до 100 000€",
            "messages": [
                _msg("🏖 Подбор апартаментов\n\nИли выберите пример:", 3, buttons=("Студия",))
            ],
        },
        "apartment_search_1": {
            "click": "Студия в Солнечном берегу до 100 000€",
            "messages": [
                _msg("🔍 Ищу подходящие варианты...", 4),
                _msg("Найдено 12 вариантов:", 5),
            ],
        },
        "apartment_search_2": {
            "messages": [
                _msg("🔍 Ищу подходящие варианты...", 6),
                _msg("Найдено 32 вариантов:", 7),
            ]
        },
        "return_navigation": {
            "messages": [_msg("Привет! 👋", 8, reply_buttons=("🎯 Демонстрация",))]
        },
        "ask_open": {
            "messages": [
                _msg("💬 Напишите вопрос", 9, buttons=("📋 Какие документы нужны для покупки?",))
            ]
        },
        "grounded_qa": {
            "click": "📋 Какие документы нужны для покупки?",
            "messages": [_msg("Для покупки нужны паспорт, ИНН и договор купли-продажи.", 10)],
        },
        "safe_no_answer": {
            "messages": [_msg("Я отвечаю по теме недвижимости и связанных услуг.", 11)]
        },
        "clean_close": {
            "messages": [
                _msg("Привет! 👋", 12, reply_buttons=("🎯 Демонстрация", "💬 Задать вопрос"))
            ]
        },
    }


class TestRunJourneyAndArtifact:
    async def test_happy_path_passes_every_step(self) -> None:
        session = FakeSession(_happy_script())
        records, ok = await run_journey(session, build_journey_steps())
        assert ok
        assert len(records) == 10
        # Reply-menu buttons pressed by label, inline buttons clicked.
        assert "🎯 Демонстрация" in session.sent
        assert "🏠 Главное меню" in session.sent
        assert "💬 Задать вопрос" in session.sent
        assert demo_gate.GOLDEN_DEMO_QUERIES[0] in session.sent
        assert demo_gate.UNSUPPORTED_QUESTION in session.sent
        assert session.sent.count("/start") == 2

    async def test_fail_fast_stops_at_first_failure(self) -> None:
        script = _happy_script()
        script["apartment_search_2"] = {"messages": [_msg("Найдено 0 вариантов:", 7)]}
        session = FakeSession(script)
        records, ok = await run_journey(session, build_journey_steps())
        assert not ok
        assert [r.id for r in records][-1] == "apartment_search_2"
        assert len(records) == 5  # clean_start .. apartment_search_2

    def test_artifact_verdict_and_budget(self) -> None:
        records = [
            StepRecord(id=f"s{i}", title="t", route="r", action="a", status="passed")
            for i in range(10)
        ]
        artifact = build_artifact(
            git_sha="abc1234",
            readiness={},
            steps=records,
            journey_seconds=42.0,
            started_at="2026-09-03T00:00:00+00:00",
            finished_at="2026-09-03T00:00:42+00:00",
        )
        assert artifact["verdict"] == "passed"
        assert artifact["within_budget"] is True
        assert artifact["schema_version"] == ARTIFACT_SCHEMA_VERSION

        artifact_fail = build_artifact(
            git_sha="abc1234",
            readiness={},
            steps=[
                *records[:1],
                StepRecord(id="bad", title="t", route="r", action="a", status="failed"),
            ],
            journey_seconds=999.0,
            started_at="x",
            finished_at="y",
        )
        assert artifact_fail["verdict"] == "failed"
        assert artifact_fail["within_budget"] is False

    def test_artifact_records_single_send_counts(self, tmp_path: Any) -> None:
        passing = StepRecord(id="grounded_qa", title="t", route="r", action="a", status="passed")
        passing.single_send = True
        artifact = build_artifact(
            git_sha="abc1234",
            readiness={},
            steps=[passing],
            journey_seconds=1.0,
            started_at="x",
            finished_at="y",
        )
        assert artifact["single_send_summary"] == {"grounded_qa": True}
        path = write_artifact(artifact, tmp_path)
        assert path.exists()
        assert artifact["git_sha"][:8] in path.name


# ---------------------------------------------------------------------------
# Readiness: skipped required surfaces FAIL
# ---------------------------------------------------------------------------


async def _ok() -> CheckOutcome:
    return CheckOutcome(ok=True)


def _fail_probe(name: str) -> Any:
    async def _probe() -> CheckOutcome:
        return CheckOutcome(ok=False, failures=(f"{name} is down — start it",))

    return _probe


class TestPrerequisites:
    async def test_all_required_surfaces_must_be_present(self) -> None:
        # A probe set missing a required surface (e.g. bge) is itself a
        # failure — skipped readiness surfaces can never pass silently.
        snapshot, failures = await run_prerequisites(
            probes={"git": _ok, "telegram": _ok, "qdrant": _ok}
        )
        assert failures
        assert any("[bge]" in failure for failure in failures)
        assert any("[golden_queries]" in failure for failure in failures)
        assert any("[llm]" in failure for failure in failures)
        assert any("[redis]" in failure for failure in failures)
        assert snapshot["git"]["ok"] is True

    async def test_failing_probe_aggregates_actionable_failures(self) -> None:
        probes: dict[str, Any] = dict.fromkeys(demo_gate.REQUIRED_CHECKS, _ok)
        probes["bge"] = _fail_probe("BGE-M3 service")
        probes["redis"] = _fail_probe("Redis")
        _snapshot, failures = await run_prerequisites(probes=probes)
        assert "[bge] BGE-M3 service is down — start it" in failures
        assert "[redis] Redis is down — start it" in failures
        assert len(failures) == 2

    async def test_probe_crash_is_recorded_not_raised(self) -> None:
        async def _crash() -> CheckOutcome:
            raise RuntimeError("boom")

        probes: dict[str, Any] = dict.fromkeys(demo_gate.REQUIRED_CHECKS, _ok)
        probes["qdrant"] = _crash
        _snapshot, failures = await run_prerequisites(probes=probes)
        assert any("[qdrant] qdrant probe crashed: boom" in failure for failure in failures)

    def test_llm_probe_requires_a_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        outcome = demo_gate._llm_probe()
        assert outcome.ok is False
        assert "LLM_API_KEY" in outcome.failures[0]

        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        assert demo_gate._llm_probe().ok is True

    def test_git_probe_reports_clean_tree_and_sha(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
        repo = tmp_path / "repo"
        repo.mkdir()
        run = lambda *args: subprocess.run(  # noqa: E731
            args, cwd=repo, check=True, capture_output=True, text=True
        )
        run("git", "init", "-q")
        run("git", "config", "user.email", "gate@example.com")
        run("git", "config", "user.name", "gate")
        (repo / "tracked.txt").write_text("hello")
        run("git", "add", "tracked.txt")
        run("git", "commit", "-q", "-m", "clean")

        outcome = demo_gate._git_probe(cwd=repo)
        assert outcome.ok is True, outcome.failures
        assert len(outcome.detail["git_sha"]) == 40
        assert outcome.detail["tracked_tree_clean"] is True

        (repo / "tracked.txt").write_text("dirty")
        outcome_dirty = demo_gate._git_probe(cwd=repo)
        assert outcome_dirty.ok is False
        assert any("dirty" in failure for failure in outcome_dirty.failures)

    def test_telegram_probe_requires_credentials_and_session(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        config = E2EConfig(TELEGRAM_API_ID=0, TELEGRAM_API_HASH="")
        outcome = demo_gate._telegram_probe(config)
        assert outcome.ok is False
        assert any("TELEGRAM_API_ID" in failure for failure in outcome.failures)
        assert any("scripts.e2e.auth" in failure for failure in outcome.failures)

        good = E2EConfig(TELEGRAM_API_ID=1, TELEGRAM_API_HASH="h")
        (tmp_path / "e2e_tester.session").write_text("session")
        assert demo_gate._telegram_probe(good).ok is True
