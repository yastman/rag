#!/usr/bin/env python3
"""Read-only watchdog snapshot for swarm worker state (issue #1275).

The orchestrator (Codex/Kiro) currently wastes context tokens periodically
running ``sleep; find .signals; git status`` while waiting for workers.
Issue #1275 proposes an event-driven flow where the orchestrator instead
ends its turn after launching workers and resumes only when:

* a worker writes its signal JSON and wakes the orchestrator via tmux
  ``send-keys -l '[DONE] <worker> <path>' ; sleep 0.25 ; send-keys C-m``
  (the canonical wake-up form pinned by issue #1721 and the contract test
  ``tests/contract/test_tmux_send_keys_pattern_contract.py``);
* the user explicitly asks for status.

Either way, the orchestrator should not have to scan ``.signals/``
manually. This script reads ``.signals/active-workers.jsonl`` plus each
worker's signal/heartbeat artifacts and emits one compact JSON snapshot
per call. A single ``cat ${watchdog --once}`` gives the orchestrator
everything it needs in one read.

Two modes:

* ``--once`` (default): scan, print a single JSON line on stdout, exit.
  Print ``[ALL_DONE]`` on its own line when every active worker has
  reached a terminal phase (``done``/``failed``/``blocked``). The marker
  makes it cheap for a tmux watcher pane to grep without parsing JSON.

* ``--watch``: run ``--once`` every ``--interval`` seconds until
  ``[ALL_DONE]`` is reported or ``--timeout`` elapses. Useful as a
  sidecar pane that wakes the orchestrator only on state transitions.

Phases reported:

* ``active`` — worker is registered, no terminal signal, heartbeat (if
  any) is fresh.
* ``done`` / ``failed`` / ``blocked`` — terminal status read from the
  worker's signal JSON.
* ``stale`` — no signal yet, but heartbeat is older than
  ``--stale-threshold`` seconds.

A corrupt signal JSON is reported as ``failed`` with an ``error`` field
rather than crashing the whole snapshot.

Refs #1275, #1721.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Statuses considered terminal (no further work expected from the worker).
_TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "failed", "blocked"})

# Default heartbeat staleness threshold. Workers that update a heartbeat
# but go quiet for longer than this (without a terminal signal) are
# reported as ``stale`` so the orchestrator can investigate.
DEFAULT_STALE_THRESHOLD_S: float = 600.0

# Default polling interval for ``--watch`` mode.
DEFAULT_WATCH_INTERVAL_S: float = 5.0

# Default registry path relative to CWD.
DEFAULT_REGISTRY_REL_PATH: str = ".signals/active-workers.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_active_workers(registry_path: Path | str) -> list[dict[str, Any]]:
    """Parse ``.signals/active-workers.jsonl`` into a list of worker entries.

    Missing files yield an empty list (not an error: the orchestrator may
    legitimately scan a clean session). Blank lines and malformed JSON
    lines are skipped without raising, so a partially-corrupt registry is
    still readable.
    """
    path = Path(registry_path)
    if not path.is_file():
        return []
    workers: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and "worker" in entry and "signal_file" in entry:
            workers.append(entry)
    return workers


def inspect_worker(
    worker: dict[str, Any],
    *,
    now: float,
    stale_threshold_s: float = DEFAULT_STALE_THRESHOLD_S,
) -> dict[str, Any]:
    """Return a single observation dict for ``worker``.

    Required keys in ``worker``: ``worker``, ``signal_file``.
    Optional keys: ``heartbeat_file``.

    The returned dict always contains:

    * ``worker``: the worker name (unchanged).
    * ``phase``: ``active`` | ``done`` | ``failed`` | ``blocked`` | ``stale``.
    * ``signal_exists``: bool.
    * ``signal_path``: str — the configured signal_file path (for diagnostics).
    * ``heartbeat_age_s``: float | None.

    Optional extras when relevant:

    * ``error``: str — present when the signal file exists but is
      unreadable/corrupt; phase is forced to ``failed``.
    * ``heartbeat_path``: str — present when ``heartbeat_file`` was set.
    """
    name = worker["worker"]
    signal_path = Path(worker["signal_file"])
    heartbeat_path: Path | None = None
    if worker.get("heartbeat_file"):
        heartbeat_path = Path(worker["heartbeat_file"])

    obs: dict[str, Any] = {
        "worker": name,
        "phase": "active",
        "signal_exists": False,
        "signal_path": str(signal_path),
        "heartbeat_age_s": None,
    }
    if heartbeat_path is not None:
        obs["heartbeat_path"] = str(heartbeat_path)

    # 1) Terminal signal takes precedence over everything else: a worker
    # that has finished is finished, even if its heartbeat went stale.
    if signal_path.exists():
        obs["signal_exists"] = True
        try:
            payload = json.loads(signal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            obs["phase"] = "failed"
            obs["error"] = f"corrupt signal file: {exc}"
            return obs
        status = str(payload.get("status", "")).lower()
        if status in _TERMINAL_STATUSES:
            obs["phase"] = status
            return obs
        # Signal exists but doesn't carry a recognised terminal status —
        # treat it as still active until the worker writes a real terminal
        # status. The signal_exists flag stays true so callers can see it.

    # 2) No terminal signal -> consult the heartbeat.
    if heartbeat_path is not None and heartbeat_path.exists():
        try:
            mtime = heartbeat_path.stat().st_mtime
            age = max(now - mtime, 0.0)
            obs["heartbeat_age_s"] = round(age, 3)
            if age > stale_threshold_s:
                obs["phase"] = "stale"
        except OSError as exc:
            obs["error"] = f"unreadable heartbeat: {exc}"

    return obs


def scan(
    registry_path: Path | str,
    *,
    now: float | None = None,
    stale_threshold_s: float = DEFAULT_STALE_THRESHOLD_S,
) -> dict[str, Any]:
    """Return a complete snapshot of every worker in the registry."""
    if now is None:
        now = time.time()
    registry = Path(registry_path)
    workers = load_active_workers(registry)
    observations = [
        inspect_worker(w, now=now, stale_threshold_s=stale_threshold_s) for w in workers
    ]
    return {
        "timestamp": _iso_utc(now),
        "signals_dir": str(registry.parent),
        "registry": str(registry),
        "workers": observations,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@dataclass
class _CLIArgs:
    once: bool
    watch: bool
    registry: Path
    interval: float
    timeout: float
    stale_threshold: float


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.watch:
        return _run_watch(args)
    return _run_once(args)


def _parse_args(argv: list[str] | None) -> _CLIArgs:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only watchdog for swarm worker state. Emits a single "
            "JSON snapshot on stdout (one line) plus an [ALL_DONE] marker "
            "when every worker has reached a terminal phase."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="scan once and exit (default)",
    )
    mode.add_argument(
        "--watch",
        action="store_true",
        help="poll every --interval seconds until [ALL_DONE] or --timeout",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path(DEFAULT_REGISTRY_REL_PATH),
        help=f"path to active-workers.jsonl (default: {DEFAULT_REGISTRY_REL_PATH})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_WATCH_INTERVAL_S,
        help=f"--watch poll interval in seconds (default: {DEFAULT_WATCH_INTERVAL_S})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        help="--watch timeout in seconds; 0 means no timeout",
    )
    parser.add_argument(
        "--stale-threshold",
        type=float,
        default=DEFAULT_STALE_THRESHOLD_S,
        help=(
            "heartbeat age in seconds beyond which a worker is reported as "
            f"stale (default: {DEFAULT_STALE_THRESHOLD_S})"
        ),
    )
    parsed = parser.parse_args(argv)
    return _CLIArgs(
        once=not parsed.watch,
        watch=parsed.watch,
        registry=parsed.registry,
        interval=parsed.interval,
        timeout=parsed.timeout,
        stale_threshold=parsed.stale_threshold,
    )


def _run_once(args: _CLIArgs) -> int:
    snap = scan(args.registry, stale_threshold_s=args.stale_threshold)
    print(json.dumps(snap, ensure_ascii=False))
    if _all_terminal(snap):
        print("[ALL_DONE]")
    return 0


def _run_watch(args: _CLIArgs) -> int:
    deadline = time.time() + args.timeout if args.timeout > 0 else None
    while True:
        snap = scan(args.registry, stale_threshold_s=args.stale_threshold)
        print(json.dumps(snap, ensure_ascii=False), flush=True)
        if _all_terminal(snap):
            print("[ALL_DONE]", flush=True)
            return 0
        if deadline is not None and time.time() >= deadline:
            print("[TIMEOUT]", flush=True)
            return 0
        with contextlib.suppress(KeyboardInterrupt):
            time.sleep(args.interval)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _all_terminal(snap: dict[str, Any]) -> bool:
    """True when every worker is in a terminal phase (or there are none)."""
    workers = snap.get("workers") or []
    return all(w["phase"] in _TERMINAL_STATUSES for w in workers)


def _iso_utc(epoch: float) -> str:
    """Return an ISO-8601 UTC timestamp without microseconds."""
    # Match the time.gmtime view rather than depending on the host TZ so the
    # snapshot is reproducible across machines.
    t = time.gmtime(epoch)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


# Silence unused-import warnings on minimal builds.


if __name__ == "__main__":
    raise SystemExit(main())
