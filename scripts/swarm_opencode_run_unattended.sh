#!/usr/bin/env bash
# scripts/swarm_opencode_run_unattended.sh
#
# Wrapper for invoking OpenCode in unattended ("non-interactive") mode from
# swarm worker launchers (e.g. ~/.codex/skills/tmux-swarm-orchestration/
# scripts/launch_opencode_*.sh).
#
# Issue #1306 reports that swarm OpenCode workers stop and require manual
# permission confirmation, breaking the unattended-worker contract. The
# existing launcher exports OPENCODE_PERMISSION='{"*":"allow"}', but
# OpenCode does not recognise that variable. The canonical mechanism is the
# `permission` field in opencode.json, which can be injected at runtime via:
#
#   * a project-local opencode.json (highest precedence),
#   * OPENCODE_CONFIG=/path/to/file.json (explicit config file),
#   * OPENCODE_CONFIG_CONTENT='{"permission":"allow"}' (inline JSON).
#
# Source: Context7 /anomalyco/opencode docs/permissions.mdx + docs/config.mdx.
#
# This wrapper:
#
#   * If neither OPENCODE_CONFIG nor OPENCODE_CONFIG_CONTENT is set in the
#     caller's environment, sets OPENCODE_CONFIG_CONTENT to a permissive
#     JSON document so worker tool-calls do not block on a prompt.
#   * Otherwise, leaves both variables alone — the caller has stronger
#     opinions and the wrapper must not silently override them.
#   * Execs `opencode` with every positional argument passed through
#     verbatim, so callers can use it for `opencode run ...`,
#     `opencode tui`, or any future subcommand.
#
# Usage:
#
#   bash scripts/swarm_opencode_run_unattended.sh run "Explain Go context"
#   bash scripts/swarm_opencode_run_unattended.sh tui
#
# Refs #1306.

set -euo pipefail

# Only inject the permissive config when the caller hasn't expressed an
# opinion. We treat *either* OPENCODE_CONFIG or OPENCODE_CONFIG_CONTENT as
# a signal that the caller is in control. Touching either path while the
# other is set produces ambiguous load behaviour that is hard to debug.
if [[ -z "${OPENCODE_CONFIG_CONTENT:-}" && -z "${OPENCODE_CONFIG:-}" ]]; then
  # Single source of truth for the permissive payload. Kept minimal so
  # callers can see at a glance what the wrapper grants.
  export OPENCODE_CONFIG_CONTENT='{"$schema":"https://opencode.ai/config.json","permission":"allow"}'
fi

# Use `command -v` to give a friendlier diagnostic than the raw exec
# failure when opencode is not on PATH; in either case we exit non-zero.
if ! command -v opencode >/dev/null 2>&1; then
  echo "swarm_opencode_run_unattended.sh: 'opencode' is not on PATH" >&2
  exit 127
fi

exec opencode "$@"
