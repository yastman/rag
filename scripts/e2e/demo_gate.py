"""Automated five-minute real-estate Telegram demo gate (#3205).

Drives the frozen client-journey story against a REAL deployed bot over the
real Telegram userbot transport (``scripts.e2e.telegram_client``) and fails
before client exposure when any required surface is missing:

  1. Clean start (``/start``) -> client root menu (persistent reply keyboard).
  2. Apartment search #1 — reply «🎯 Демонстрация» -> inline «Подбор
     апартаментов» -> click the first offered example button -> catalog
     results ("Найдено N вариантов", N >= 1).
  3. Apartment search #2 — type ``GOLDEN_DEMO_QUERIES[0]`` at the results
     prompt -> catalog results with N >= ``GOLDEN_QUERY_MIN_RESULTS``.
  4. Return navigation — reply «🏠 Главное меню» -> root menu again.
  5. Grounded Q&A — reply «💬 Задать вопрос» -> click the popular-question
     inline button (``ask:docs`` route) -> exactly one grounded answer.
  6. Safe no-answer — type ``UNSUPPORTED_QUESTION`` -> exactly one safe
     response, never a fabricated listing.
  7. Clean close (``/start``) — leaves the chat in the root state so the
     next run needs no manual state repair.

Readiness snapshot (fail-fast, before the bot is contacted; skipped surfaces
FAIL, they are never tolerated):
  - exact tested Git SHA + clean tracked tree (artifact reproducibility),
  - real Telegram userbot credentials + authorized session,
  - BOTH Qdrant collections (knowledge + apartments) with required vectors
    and point minimums (colbert recorded, advisory),
  - golden-query data probe through the PRODUCTION extraction + filter path
    (``ApartmentFilterExtractor`` -> ``ApartmentsService.scroll_with_filters``),
  - BGE-M3 service health (``GET {BGE_M3_URL}/health``),
  - configured LLM credentials,
  - Redis reachable + the polling-lock key in a sane state (#3199 contract).

The artifact (JSON) is tied to the exact SHA and records per-step timings,
message ids, route metadata, and single-send counts. The whole journey must
finish within ``FIVE_MINUTE_BUDGET_S``.

Honest scope (this repo cannot fabricate the rest): the semantic quality of
the grounded answer is asserted structurally here (grounded response family,
no fabricated listing); LLM-as-judge semantics stay with the presentation
runbook, as the issue's non-goals require.

Run:  ``make demo-gate`` (full gate) or
      ``make demo-gate MODE=--prerequisites-only`` (readiness snapshot only).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table


sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.e2e.config import E2EConfig
from scripts.e2e.qdrant_preflight import CollectionRequirement, run_qdrant_preflight
from scripts.e2e.telegram_client import (
    E2ETelegramClient,
    JourneyButtonNotFound,
    JourneyTimeout,
    ReceivedMessage,
)
from src.runtime.domain_defaults import GOLDEN_DEMO_QUERIES, GOLDEN_QUERY_MIN_RESULTS
from telegram_bot.keyboards.catalog_keyboard import CATALOG_ACTION_TO_FALLBACK_TEXT
from telegram_bot.keyboards.client_keyboard import ACTIONS_TO_TEXT


console = Console()

#: Wall-clock budget for the journey phase (the "five-minute" gate).
FIVE_MINUTE_BUDGET_S = 300.0

#: Default per-step terminal timeout (streaming + LLM latency headroom).
STEP_TIMEOUT_S = 75.0

#: Extra drain window after the terminal message to count trailing sends.
SETTLE_S = 2.5

ARTIFACT_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Frozen journey surface texts (single sources of truth in the repo)
# ---------------------------------------------------------------------------

# Reply-menu labels come from the production keyboard modules (#628).
DEMO_REPLY_LABEL: str = ACTIONS_TO_TEXT["demo"]  # «🎯 Демонстрация»
ASK_REPLY_LABEL: str = ACTIONS_TO_TEXT["ask"]  # «💬 Задать вопрос»
CATALOG_HOME_LABEL: str = CATALOG_ACTION_TO_FALLBACK_TEXT["catalog_home"]  # «🏠 Главное меню»

#: Inline button on the demo menu (telegram_bot/keyboards/demo_keyboard.py).
DEMO_MENU_BUTTON_LOCATOR = "Подбор апартаментов"

#: Marker of the demo menu message (handlers/demo_handler.handle_demo_button).
DEMO_MENU_MARKER = "Демонстрация возможностей"

#: Marker of the demo intro prompt (dialogs/demo.py intro_getter).
DEMO_INTRO_MARKER = "Или выберите пример"

#: Marker of the Ask prompt (handlers/catalog._handle_ask fallback text).
ASK_PROMPT_MARKER = "Напишите вопрос"

#: Popular-question inline button clicked for the grounded Q&A step. Its
#: ``ask:docs`` callback is dispatched through the deterministic #3204 route
#: (single owner -> handle_menu_action_text -> handle_query).
GROUNDED_QA_BUTTON_LOCATOR = "документы нужны для покупки"

#: Safe no-answer surface question (frozen by #3200 characterization).
UNSUPPORTED_QUESTION = "Найди замок в Софии с частным аэропортом и вертолётной площадкой"

#: Catalog results header produced by the demo/catalog search path.
_CATALOG_RESULTS_RE = re.compile(r"Найдено\s+(\d+)\s+вариант")
_CATALOG_EMPTY_MARKER = "ничего не найдено"

#: Status messages that must NOT be treated as terminal responses.
STATUS_MARKERS: tuple[str, ...] = (
    "Ищу подходящие",
    "Распознаю голос",
)

#: Markers of the safe / canned response families (generation policy safe
#: fallback, no-claim answer, off-topic canned text).
SAFE_RESPONSE_MARKERS: tuple[str, ...] = (
    "Извините",
    "временно недоступен",
    "В базе нет информации",
    "Уточните",
    "Уточните, пожалуйста",
    "специализируюсь только на недвижимости",
    "отвечаю по теме недвижимости",
)


# ---------------------------------------------------------------------------
# Terminal predicates
# ---------------------------------------------------------------------------

CatalogMatch = re.Match[str] | None


def terminal_root_menu(text: str) -> bool:
    """Root menu: the welcome/root message (validated further by the step)."""
    return bool(text.strip())


def terminal_demo_menu(text: str) -> bool:
    return DEMO_MENU_MARKER in text


def terminal_demo_intro(text: str) -> bool:
    return DEMO_INTRO_MARKER in text or DEMO_MENU_BUTTON_LOCATOR.lower() in text.lower()


def terminal_ask_prompt(text: str) -> bool:
    return ASK_PROMPT_MARKER in text


def terminal_any_answer(text: str) -> bool:
    """Q&A steps: the first non-status incoming message is the answer."""
    return bool(text.strip())


def catalog_result_count(text: str) -> int | None:
    """Extract the advertised listing count from a catalog results message."""
    match = _CATALOG_RESULTS_RE.search(text)
    return int(match.group(1)) if match else None


def terminal_catalog_results(text: str) -> bool:
    """Search steps: results header, or the explicit empty state (which the
    threshold check then fails with a data diagnostic)."""
    return _CATALOG_RESULTS_RE.search(text) is not None or _CATALOG_EMPTY_MARKER in text


def is_status_message(text: str) -> bool:
    """True for bot status/progress messages that are not terminal answers."""
    return any(marker in text for marker in STATUS_MARKERS)


def matches_safe_family(text: str) -> bool:
    return any(marker in text for marker in SAFE_RESPONSE_MARKERS)


def is_fabricated_listing(text: str) -> bool:
    """True when a Q&A answer smuggled in catalog results / price rows."""
    return _CATALOG_RESULTS_RE.search(text) is not None and "€" in text


# ---------------------------------------------------------------------------
# Journey step definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JourneyAction:
    """What the gate does to trigger the step (route metadata)."""

    kind: str  # "text" | "reply_button" | "inline_button"
    value: str  # text to send, or inline button locator
    from_step: str | None = None  # step whose message carries the buttons
    first_button: bool = False  # click the first button instead of matching


@dataclass
class StepRecord:
    """Observed outcome of one journey step (artifact payload)."""

    id: str
    title: str
    route: str
    action: str
    status: str = "pending"
    message_ids: list[int] = field(default_factory=list)
    message_count: int = 0
    status_message_count: int = 0
    post_terminal_count: int = 0
    single_send: bool | None = None
    terminal_message_id: int | None = None
    terminal_text: str = ""
    clicked_label: str | None = None
    result_count: int | None = None
    duration_ms: int = 0
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "route": self.route,
            "action": self.action,
            "status": self.status,
            "message_ids": self.message_ids,
            "message_count": self.message_count,
            "status_message_count": self.status_message_count,
            "post_terminal_count": self.post_terminal_count,
            "single_send": self.single_send,
            "terminal_message_id": self.terminal_message_id,
            "terminal_text": self.terminal_text[:1200],
            "clicked_label": self.clicked_label,
            "result_count": self.result_count,
            "duration_ms": self.duration_ms,
            "failure": self.failure,
        }


@dataclass(frozen=True)
class JourneyStep:
    """One frozen step of the five-minute story."""

    id: str
    title: str
    action: JourneyAction
    route: str  # human-readable route metadata (e.g. "reply:demo")
    terminal: Callable[[str], bool]
    expects_reply_buttons: tuple[str, ...] = ()
    min_result_count: int | None = None
    require_single_send: bool = False
    forbid_safe_family: bool = False
    require_safe_family: bool = False
    require_inline_button: str | None = None
    timeout_s: float = STEP_TIMEOUT_S


def build_journey_steps() -> list[JourneyStep]:
    """The frozen five-minute real-estate story (#3205 order)."""
    return [
        JourneyStep(
            id="clean_start",
            title="Clean start -> client root menu",
            action=JourneyAction(kind="text", value="/start"),
            route="command:/start",
            terminal=terminal_root_menu,
            expects_reply_buttons=(DEMO_REPLY_LABEL, ASK_REPLY_LABEL),
        ),
        JourneyStep(
            id="demo_open",
            title="Reply menu «Демонстрация» -> inline demo menu",
            action=JourneyAction(kind="reply_button", value=DEMO_REPLY_LABEL),
            route="reply_keyboard:demo -> inline demo menu",
            terminal=terminal_demo_menu,
            require_inline_button=DEMO_MENU_BUTTON_LOCATOR,
        ),
        JourneyStep(
            id="demo_apartments",
            title="Inline «Подбор апартаментов» -> example queries",
            action=JourneyAction(
                kind="inline_button",
                value=DEMO_MENU_BUTTON_LOCATOR,
                from_step="demo_open",
            ),
            route="inline:demo:apartments -> DemoSG.intro",
            terminal=terminal_demo_intro,
        ),
        JourneyStep(
            id="apartment_search_1",
            title="Apartment search #1 (inline example click)",
            action=JourneyAction(
                kind="inline_button",
                value="",
                from_step="demo_apartments",
                first_button=True,
            ),
            route="inline:demo:example -> catalog results",
            terminal=terminal_catalog_results,
            min_result_count=1,  # dynamic examples guarantee >= 1 (#3203)
        ),
        JourneyStep(
            id="apartment_search_2",
            title="Apartment search #2 (typed golden query)",
            action=JourneyAction(kind="text", value=GOLDEN_DEMO_QUERIES[0]),
            route="text -> catalog MessageInput -> catalog results",
            terminal=terminal_catalog_results,
            min_result_count=GOLDEN_QUERY_MIN_RESULTS,
        ),
        JourneyStep(
            id="return_navigation",
            title="Return navigation «Главное меню» -> root menu",
            action=JourneyAction(kind="reply_button", value=CATALOG_HOME_LABEL),
            route="reply_keyboard:catalog_home -> client root",
            terminal=terminal_root_menu,
        ),
        JourneyStep(
            id="ask_open",
            title="Reply menu «Задать вопрос» -> Ask prompt",
            action=JourneyAction(kind="reply_button", value=ASK_REPLY_LABEL),
            route="reply_keyboard:ask -> Ask prompt (#3204 exit-to-root)",
            terminal=terminal_ask_prompt,
            require_inline_button=GROUNDED_QA_BUTTON_LOCATOR,
        ),
        JourneyStep(
            id="grounded_qa",
            title="Grounded Q&A (popular-question inline button)",
            action=JourneyAction(
                kind="inline_button",
                value=GROUNDED_QA_BUTTON_LOCATOR,
                from_step="ask_open",
            ),
            route="inline:ask:docs -> handle_query (grounded RAG)",
            terminal=terminal_any_answer,
            require_single_send=True,
            forbid_safe_family=True,
        ),
        JourneyStep(
            id="safe_no_answer",
            title="Safe no-answer (unsupported question)",
            action=JourneyAction(kind="text", value=UNSUPPORTED_QUESTION),
            route="text -> catch-all handle_query (safe fallback)",
            terminal=terminal_any_answer,
            require_single_send=True,
            require_safe_family=True,
        ),
        JourneyStep(
            id="clean_close",
            title="Clean close (/start) for the next run",
            action=JourneyAction(kind="text", value="/start"),
            route="command:/start",
            terminal=terminal_root_menu,
            expects_reply_buttons=(DEMO_REPLY_LABEL, ASK_REPLY_LABEL),
        ),
    ]


# ---------------------------------------------------------------------------
# Journey executor (transport-agnostic; tests inject a fake transport)
# ---------------------------------------------------------------------------


class JourneyTransportError(RuntimeError):
    """Transport-level step failure (timeout / missing button)."""


async def execute_step(
    session: Any,
    step: JourneyStep,
    step_records: dict[str, StepRecord],
) -> StepRecord:
    """Run one frozen step against the journey session and validate it."""
    record = StepRecord(
        id=step.id, title=step.title, route=step.route, action=_describe(step.action)
    )
    started = time.monotonic()
    # Test seam: scripted fake sessions key their replay by step id.
    set_step = getattr(session, "set_step", None)
    if callable(set_step):
        set_step(step.id)
    try:
        await _perform_action(session, step.action, step_records, record)
        collected: list[ReceivedMessage] = await session.collect_until_terminal(
            is_terminal=step.terminal,
            is_status=is_status_message,
            timeout_s=step.timeout_s,
            settle=SETTLE_S,
        )
    except JourneyTimeout as exc:
        record.status = "failed"
        record.failure = f"timeout: {exc}"
        return record
    except JourneyButtonNotFound as exc:
        record.status = "failed"
        record.failure = f"required surface missing: {exc}"
        return record
    except Exception as exc:  # transport failure — surface it, never skip
        record.status = "failed"
        record.failure = f"transport error: {exc}"
        return record
    finally:
        record.duration_ms = int((time.monotonic() - started) * 1000)

    if not collected:
        record.status = "failed"
        record.failure = "no bot messages observed"
        return record

    # Partition status/progress messages from the real responses so the
    # single-send counts stay truthful for the demo search path (which
    # always emits one status before the terminal results message).
    statuses = [msg for msg in collected if is_status_message(msg.text)]
    responses = [msg for msg in collected if not is_status_message(msg.text)]
    terminal = responses[0]
    terminal_index = collected.index(terminal)

    record.message_ids = [msg.message_id for msg in responses]
    record.message_count = len(responses)
    record.status_message_count = len(statuses)
    record.post_terminal_count = max(len(collected) - terminal_index - 1, 0)
    record.terminal_message_id = terminal.message_id
    record.terminal_text = terminal.text
    record.single_send = len(responses) == 1
    record.result_count = catalog_result_count(terminal.text)
    record.status = "passed"

    failure = _validate_step(step, terminal, collected, record)
    if failure:
        record.status = "failed"
        record.failure = failure
    return record


def _describe(action: JourneyAction) -> str:
    if action.kind == "inline_button":
        target = action.value or "<first example button>"
        return f"click inline {target!r}"
    if action.kind == "reply_button":
        return f"press reply button {action.value!r}"
    return f"send text {action.value!r}"


async def _perform_action(
    session: Any,
    action: JourneyAction,
    step_records: dict[str, StepRecord],
    record: StepRecord,
) -> None:
    if action.kind in {"text", "reply_button"}:
        await session.send_text(action.value)
        return
    from_id: int | None = None
    if action.from_step is not None:
        source = step_records.get(action.from_step)
        if source is None or source.terminal_message_id is None:
            raise JourneyButtonNotFound(f"step {action.from_step!r} produced no message to click")
        from_id = source.terminal_message_id
    record.clicked_label = await session.click_inline_button(
        action.value,
        message_id=from_id,
        first=action.first_button,
    )


def _validate_step(
    step: JourneyStep,
    terminal: ReceivedMessage,
    collected: list[ReceivedMessage],
    record: StepRecord,
) -> str | None:
    """Post-conditions; return a failure message or None."""
    if step.expects_reply_buttons:
        missing = [
            label
            for label in step.expects_reply_buttons
            if not any(
                label.lower() in candidate.lower() for candidate in terminal.reply_button_labels
            )
        ]
        if missing or not terminal.has_reply_keyboard:
            return (
                "root menu did not show the client reply keyboard "
                f"(missing labels={missing}); deployment mismatch"
            )
    if step.require_inline_button and not terminal.button_labels_matching(
        step.require_inline_button
    ):
        return (
            f"expected inline button matching {step.require_inline_button!r} "
            f"(labels={terminal.button_labels})"
        )
    if step.min_result_count is not None:
        if record.result_count is None:
            if _CATALOG_EMPTY_MARKER in terminal.text:
                return (
                    f"search returned the empty state (0 listings) but ≥ "
                    f"{step.min_result_count} required — demo data does not "
                    "match the frozen query (re-ingest the shipped seed)"
                )
            return "terminal message did not advertise a result count"
        if record.result_count < step.min_result_count:
            return (
                f"only {record.result_count} listings shown, ≥ "
                f"{step.min_result_count} required by the frozen script"
            )
    if step.require_single_send and not record.single_send:
        return (
            f"expected exactly one answer message, got {record.message_count} "
            f"(ids={record.message_ids})"
        )
    combined = terminal.text
    if step.forbid_safe_family:
        if matches_safe_family(combined):
            return (
                "answer matched a safe/canned response family — grounded Q&A "
                "did not produce a grounded answer"
            )
        if is_fabricated_listing(combined):
            return "answer contained catalog listing rows instead of a grounded answer"
    if step.require_safe_family:
        if is_fabricated_listing(combined):
            return "unsupported question produced fabricated catalog listings"
        if not matches_safe_family(combined):
            return (
                "answer did not match any known safe no-answer family "
                f"(markers={SAFE_RESPONSE_MARKERS})"
            )
    return None


async def run_journey(session: Any, steps: list[JourneyStep]) -> tuple[list[StepRecord], bool]:
    """Run all frozen steps; stop at the first failure (fail-fast gate)."""
    records: list[StepRecord] = []
    by_id: dict[str, StepRecord] = {}
    for step in steps:
        console.print(f"[cyan]step[/] {step.id}: {step.title}")
        record = await execute_step(session, step, by_id)
        records.append(record)
        by_id[step.id] = record
        if record.status != "passed":
            console.print(f"  [red]FAIL[/] {record.id}: {record.failure}")
            break
        console.print(
            f"  [green]PASS[/] {record.id} "
            f"({record.duration_ms} ms, messages={record.message_count}, "
            f"results={record.result_count})"
        )
        await asyncio.sleep(0.5)
    return records, all(r.status == "passed" for r in records)


# ---------------------------------------------------------------------------
# Prerequisites (fail-fast before client exposure)
# ---------------------------------------------------------------------------

CheckProbe = Callable[[], Awaitable["CheckOutcome"]]

#: Every required readiness surface. A probe set that omits one is itself a
#: failure — skipped required surfaces must FAIL, never pass silently.
REQUIRED_CHECKS: tuple[str, ...] = (
    "git",
    "telegram",
    "qdrant",
    "golden_queries",
    "bge",
    "llm",
    "redis",
)


@dataclass(frozen=True)
class CheckOutcome:
    """Result of one readiness probe."""

    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)
    failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, **self.detail}


def _git_probe(cwd: Path | None = None) -> CheckOutcome:
    """Exact tested SHA + clean tracked tree (artifact reproducibility)."""
    workdir = str(cwd or Path(__file__).parent.parent.parent)
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=workdir,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
            cwd=workdir,
        )
    except subprocess.CalledProcessError as exc:
        return CheckOutcome(ok=False, failures=(f"git probe failed: {exc.stderr}",))
    dirty_lines = [line for line in status.stdout.splitlines() if line.strip()]
    failures: list[str] = []
    if dirty_lines:
        failures.append(
            "tracked working tree is dirty — the artifact must be tied to one "
            "exact tested SHA; commit all tracked changes first: " + "; ".join(dirty_lines[:5])
        )
    return CheckOutcome(
        ok=not failures,
        detail={"git_sha": sha, "tracked_tree_clean": not dirty_lines},
        failures=tuple(failures),
    )


def _telegram_probe(config: E2EConfig) -> CheckOutcome:
    """Real Telegram userbot credentials + authorized session file."""
    errors = config.validation_errors(judge_required=False)
    session_path = Path(f"{config.telegram_session}.session")
    failures = [f"telegram: {error}" for error in errors]
    if not session_path.exists():
        failures.append(
            f"telegram: session file {session_path} not found — run "
            "'uv run python -m scripts.e2e.auth' to authorize the e2e userbot"
        )
    return CheckOutcome(
        ok=not failures,
        detail={
            "bot_username": config.bot_username,
            "session": config.telegram_session,
            "session_present": session_path.exists(),
        },
        failures=tuple(failures),
    )


def _qdrant_probe(config: E2EConfig) -> CheckOutcome:
    """Both required collections with schema/minimums (colbert advisory)."""
    requirements = (
        CollectionRequirement(
            name=config.qdrant_doc_collection,
            min_points=config.qdrant_min_doc_points,
            required_vectors=frozenset({"dense", "bm42"}),
        ),
        CollectionRequirement(
            name=config.qdrant_apartment_collection,
            min_points=config.qdrant_min_apartment_points,
            required_vectors=frozenset({"dense", "bm42"}),
        ),
    )
    preflight = run_qdrant_preflight(qdrant_url=config.qdrant_url, requirements=requirements)
    advisory: list[str] = []
    for item in preflight.checked:
        raw_vectors = item.get("vectors", [])
        vectors = {str(v) for v in raw_vectors} if isinstance(raw_vectors, (list, tuple)) else set()
        if "colbert" not in vectors:
            advisory.append(f"{item.get('collection')}: colbert missing (RRF fallback)")
    failures = [line for line in preflight.message.splitlines() if line.startswith("- ")]
    if not preflight.ok and not failures:
        failures = [preflight.message]
    return CheckOutcome(
        ok=preflight.ok,
        detail={
            "qdrant_url": config.qdrant_url,
            "collections": preflight.checked,
            "advisory": advisory,
        },
        failures=tuple(f.strip("- ").strip() for f in failures),
    )


async def _golden_query_probe(config: E2EConfig) -> CheckOutcome:
    """Golden queries must be answerable through the production filter path."""
    from src.runtime.qdrant.service import QdrantService
    from telegram_bot.services.apartment.apartment_filter_extractor import (
        ApartmentFilterExtractor,
    )
    from telegram_bot.services.apartment.apartments_service import ApartmentsService

    extractor = ApartmentFilterExtractor()
    qdrant = QdrantService(
        url=config.qdrant_url,
        collection_name=config.qdrant_apartment_collection,
    )
    service = ApartmentsService(qdrant)
    per_query: dict[str, int] = {}
    failures: list[str] = []
    try:
        for query in GOLDEN_DEMO_QUERIES:
            filters = extractor.parse(query).to_filters_dict()
            _results, total_count, _next, _ids = await service.scroll_with_filters(
                filters=filters or None,
                limit=GOLDEN_QUERY_MIN_RESULTS,
            )
            per_query[query] = total_count
            if total_count < GOLDEN_QUERY_MIN_RESULTS:
                failures.append(
                    f"golden query {query!r} returns {total_count} listings "
                    f"(≥ {GOLDEN_QUERY_MIN_RESULTS} required) — re-ingest the "
                    "shipped demo seed: uv run python -m src.ingestion.apartments.runner"
                )
    except Exception as exc:
        message = str(exc)
        if "doesn't exist" in message:
            message = (
                f"collection {config.qdrant_apartment_collection!r} is missing — "
                "create and ingest the demo data before running the gate "
                "(scripts/apartments/setup_collection.py + "
                "python -m src.ingestion.apartments.runner)"
            )
        failures.append(f"golden query probe failed: {message}")
    finally:
        await qdrant.close()
    return CheckOutcome(
        ok=not failures,
        detail={"golden_queries": per_query, "min_results": GOLDEN_QUERY_MIN_RESULTS},
        failures=tuple(failures),
    )


async def _bge_probe(config: E2EConfig) -> CheckOutcome:
    """BGE-M3 embedding service health (required by knowledge Q&A)."""
    url = os.getenv("BGE_M3_URL", "http://localhost:8000").rstrip("/")
    health_url = f"{url}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
            ok = response.status_code == 200
    except Exception as exc:
        return CheckOutcome(
            ok=False,
            detail={"bge_health_url": health_url},
            failures=(
                f"BGE-M3 service unreachable at {health_url}: {exc} — start the "
                "BGE-M3 service before running the demo gate",
            ),
        )
    return CheckOutcome(
        ok=ok,
        detail={"bge_health_url": health_url, "status_code": response.status_code},
        failures=()
        if ok
        else (f"BGE-M3 health returned HTTP {response.status_code} at {health_url}",),
    )


def _llm_probe() -> CheckOutcome:
    """Configured LLM credentials (the journey itself proves the live call)."""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    model = os.getenv("LLM_MODEL", "")
    base_url = os.getenv("LLM_BASE_URL", "")
    ok = bool(api_key.strip())
    return CheckOutcome(
        ok=ok,
        detail={"llm_model": model, "llm_base_url_configured": bool(base_url)},
        failures=()
        if ok
        else (
            "LLM is not configured: set LLM_API_KEY (or OPENAI_API_KEY) — the "
            "grounded Q&A and safe no-answer steps require a configured LLM",
        ),
    )


def _redis_probe() -> CheckOutcome:
    """Redis reachable + polling-lock key sane (#3199 single-poller contract)."""
    try:
        import redis
    except ImportError:
        return CheckOutcome(ok=False, failures=("redis-py is not installed",))

    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    polling_key = os.getenv("POLLING_LOCK_KEY", "telegram-bot:polling")
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=3.0)
        pong = client.ping()
        raw = client.get(polling_key)
        ttl_ms = client.pttl(polling_key)
    except Exception as exc:
        return CheckOutcome(
            ok=False,
            detail={"redis_url": url},
            failures=(f"Redis unreachable at {url}: {exc}",),
        )
    failures: list[str] = []
    owner: str | None = None
    ttl_ms = int(ttl_ms) if isinstance(ttl_ms, (int, float)) else -1
    if raw is not None:
        owner = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
        if ttl_ms <= 0:
            failures.append(
                f"polling lock key {polling_key!r} exists WITHOUT a TTL "
                f"(owner={owner}) — a stale permanent lease would block bot "
                "startup; release it with: make release-polling-lock"
            )
    return CheckOutcome(
        ok=not failures and bool(pong),
        detail={
            "redis_url": url,
            "polling_lock_key": polling_key,
            "polling_lock_owner": owner,
            "polling_lock_pttl_ms": ttl_ms,
        },
        failures=tuple(failures),
    )


async def run_prerequisites(
    *,
    config: E2EConfig | None = None,
    probes: dict[str, CheckProbe] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Run every required readiness probe; skipped surfaces are NOT allowed.

    Returns ``(snapshot, failures)`` — ``failures`` non-empty means the gate
    fails before the bot is contacted.
    """
    cfg = config or E2EConfig()
    # Callables are lazily invoked (and awaited) so overridden probes never
    # leave un-awaited default coroutines behind.
    checks: dict[str, CheckProbe] = {
        "git": lambda: _wrap(_git_probe),
        "telegram": lambda: _wrap(lambda: _telegram_probe(cfg)),
        "qdrant": lambda: _wrap(lambda: _qdrant_probe(cfg)),
        "golden_queries": lambda: _golden_query_probe(cfg),
        "bge": lambda: _bge_probe(cfg),
        "llm": lambda: _wrap(_llm_probe),
        "redis": lambda: _wrap(_redis_probe),
    }
    snapshot: dict[str, Any] = {}
    failures: list[str] = []
    if probes is not None:
        # Skipped required surfaces fail the gate before anything runs.
        for missing in [name for name in REQUIRED_CHECKS if name not in probes]:
            failures.append(f"[{missing}] required readiness surface was skipped (no probe)")
        checks = {name: probes[name] for name in probes}

    for name, probe_factory in checks.items():
        try:
            outcome = await probe_factory()
        except Exception as exc:
            outcome = CheckOutcome(ok=False, failures=(f"{name} probe crashed: {exc}",))
        snapshot[name] = outcome.to_dict()
        for failure in outcome.failures:
            failures.append(f"[{name}] {failure}")
    return snapshot, failures


async def _wrap(sync_probe: Callable[[], CheckOutcome]) -> CheckOutcome:
    return sync_probe()


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


def build_artifact(
    *,
    git_sha: str,
    readiness: dict[str, Any],
    steps: list[StepRecord],
    journey_seconds: float,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    step_payloads = [step.to_dict() for step in steps]
    all_passed = bool(steps) and all(step.status == "passed" for step in steps)
    within_budget = journey_seconds <= FIVE_MINUTE_BUDGET_S
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "issue": 3205,
        "git_sha": git_sha,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_duration_ms": int(journey_seconds * 1000),
        "five_minute_budget_ms": int(FIVE_MINUTE_BUDGET_S * 1000),
        "within_budget": within_budget,
        "readiness_snapshot": readiness,
        "steps": step_payloads,
        "single_send_summary": {
            step["id"]: step["single_send"]
            for step in step_payloads
            if step["single_send"] is not None
        },
        "verdict": "passed" if all_passed and within_budget else "failed",
    }


def write_artifact(artifact: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    sha8 = artifact["git_sha"][:8]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"demo-gate-{sha8}-{stamp}.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_summary(artifact: dict[str, Any]) -> None:
    table = Table(title="Demo gate (#3205) — five-minute real-estate journey")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("ms", justify="right")
    table.add_column("Msgs", justify="right")
    table.add_column("Results", justify="right")
    for step in artifact["steps"]:
        status = "[green]PASS[/]" if step["status"] == "passed" else "[red]FAIL[/]"
        results = "—" if step["result_count"] is None else str(step["result_count"])
        table.add_row(
            step["id"],
            status,
            str(step["duration_ms"]),
            str(step["message_count"]),
            results,
        )
    console.print(table)
    verdict = artifact["verdict"]
    color = "green" if verdict == "passed" else "red"
    console.print(
        f"[{color}]verdict: {verdict}[/] · sha={artifact['git_sha'][:12]} · "
        f"journey={artifact['total_duration_ms'] / 1000:.1f}s / "
        f"budget={artifact['five_minute_budget_ms'] // 1000}s"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def _run_gate(*, prerequisites_only: bool, output_dir: Path) -> int:
    started_at = datetime.now(UTC).isoformat()
    readiness, failures = await run_prerequisites()
    for name, check in readiness.items():
        mark = "[green]ok[/]" if check.get("ok") else "[red]fail[/]"
        console.print(f"readiness {name}: {mark}")
    if failures:
        console.print("[red]Readiness gate failed — the bot was NOT contacted.[/]")
        for failure in failures:
            console.print(f"  - {failure}", markup=False)
        artifact = build_artifact(
            git_sha=str(readiness.get("git", {}).get("git_sha", "")),
            readiness=readiness,
            steps=[],
            journey_seconds=0.0,
            started_at=started_at,
            finished_at=datetime.now(UTC).isoformat(),
        )
        path = write_artifact(artifact, output_dir)
        console.print(f"[dim]Artifact: {path}[/]")
        return 1

    if prerequisites_only:
        console.print("[green]Readiness snapshot complete (prerequisites-only mode).[/]")
        artifact = build_artifact(
            git_sha=str(readiness.get("git", {}).get("git_sha", "")),
            readiness=readiness,
            steps=[],
            journey_seconds=0.0,
            started_at=started_at,
            finished_at=datetime.now(UTC).isoformat(),
        )
        path = write_artifact(artifact, output_dir)
        console.print(f"[dim]Artifact: {path}[/]")
        return 0

    client = E2ETelegramClient(E2EConfig())
    journey_start = time.monotonic()
    try:
        await client.connect()
    except Exception as exc:
        console.print(f"[red]Telegram connect failed:[/] {exc}")
        return 1
    try:
        async with client.journey() as session:
            steps, _ok = await run_journey(session, build_journey_steps())
    finally:
        await client.disconnect()
    journey_seconds = time.monotonic() - journey_start

    git_sha = str(readiness.get("git", {}).get("git_sha", ""))
    artifact = build_artifact(
        git_sha=git_sha,
        readiness=readiness,
        steps=steps,
        journey_seconds=journey_seconds,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
    )
    print_summary(artifact)
    path = write_artifact(artifact, output_dir)
    console.print(f"[dim]Artifact: {path}[/]")
    return 0 if artifact["verdict"] == "passed" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Automated five-minute Telegram demo gate")
    parser.add_argument(
        "--prerequisites-only",
        action="store_true",
        help="Run the readiness snapshot only (never contacts the bot)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/demo-gate"),
        help="Artifact output directory (default: reports/demo-gate)",
    )
    args = parser.parse_args(argv)
    try:
        return asyncio.run(
            _run_gate(
                prerequisites_only=args.prerequisites_only,
                output_dir=args.output_dir,
            )
        )
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted[/]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
