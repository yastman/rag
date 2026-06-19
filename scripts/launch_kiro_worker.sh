#!/usr/bin/env bash
# launch_kiro_worker.sh — запустить Kiro воркера в отдельном tmux-окне
#
# Использование:
#   ./scripts/launch_kiro_worker.sh <worker-name> <prompt-file>
#
# Переменные окружения:
#   ORCH_TARGET   — tmux target оркестратора (если не задан, читается из .signals/orchestrator-window.json)
#   WORKER_AGENT    — агент Kiro (optional, default: kiro_default; prefer kiro-worker / kiro-worker-flash / kiro-worker-opus)
#   WORKER_MODEL    — модель (optional; e.g. claude-sonnet-4.6 / claude-haiku-4.5)
#   WORKER_ROLE     — роль воркера для отчёта (default: research)
#   WORKER_WORKTREE — изолированный git worktree воркера. REQUIRED для code-changing workers
#                     (implementation/plan-execution/quick/review-fix). Fallback на REPO_ROOT
#                     только для read-only/research ролей. Bypass: WORKER_WORKTREE_BYPASS=1.
#   WORKER_TIMEOUT  — failsafe-таймаут (сек): нет терминального сигнала за это время → шлём [FAILED] (default: 1800)
#
# Флоу (kiro-cli flow):
#   1. Определить ORCH_TARGET из маркера
#   2. Сохранить промт в logs/prompts/<worker>.md
#   3. Запустить полноценную сессию: kiro-cli chat -a [--model X] --trust-all-tools "Read and execute the worker prompt file at: <path>"
#   4. Поймать [DONE/FAILED/BLOCKED] в логе
#   5. Переслать строку статуса в ORCH_TARGET через tmux send-keys (без acceptance).
#      Решение accepted/needs_fix/PR/merge принимает оркестратор (swarm-acceptance).

set -euo pipefail

WORKER_NAME="${1:?Usage: $0 <worker-name> <prompt-file>}"
PROMPT_SRC="${2:?prompt file required}"

WORKER_ROLE="${WORKER_ROLE:-research}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIGNALS_DIR="$REPO_ROOT/.signals"
LOG_DIR="$REPO_ROOT/logs"
PROMPT_DIR="$REPO_ROOT/logs/prompts"
mkdir -p "$LOG_DIR" "$SIGNALS_DIR" "$PROMPT_DIR"

# --- Определить ORCH_TARGET ---
if [[ -z "${ORCH_TARGET:-}" ]]; then
  MARKER="$SIGNALS_DIR/orchestrator-window.json"
  if [[ ! -f "$MARKER" ]]; then
    echo "ERROR: ORCH_TARGET not set and no marker at $MARKER" >&2
    echo "Run: eval \$(./scripts/set_orchestrator_window.sh <task>)" >&2
    exit 2
  fi
  ORCH_TARGET="$(python3 -c "import json; print(json.load(open('$MARKER'))['orchestrator_target'])")"
fi

# --- Проверить что ORCH_TARGET жив ---
SESSION="${ORCH_TARGET%%:*}"
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: tmux session not found for ORCH_TARGET=$ORCH_TARGET" >&2
  exit 2
fi

# --- Сохранить промт в стабильный путь + подставить ORCH_TARGET ---
# Materialize through a temp file: when PROMPT_SRC == PROMPT_FILE (the natural
# case where the caller already wrote the prompt to logs/prompts/<worker>.md and
# passes that path), a direct `sed ... > "$PROMPT_FILE"` truncates the source to
# 0 bytes BEFORE sed reads it. Reading into a temp first, then mv, is safe even
# when source and destination are the same path.
PROMPT_FILE="$PROMPT_DIR/${WORKER_NAME}.md"

# Canonical report + status paths (#2305 done-signal protocol, #2820 wake-up
# hardening). Repo-root-relative REPORT_FILE is what the wake-up line and
# acceptance path-validation agree on; the absolute form is what the agent
# writes and what the wrapper checks for existence — so a worker running in an
# isolated worktree still writes into the repo-root logs/. STATUS_FILE carries
# the one-word terminal status the wrapper reads to decide DONE/FAILED/BLOCKED.
WORKER_LOG="$LOG_DIR/${WORKER_NAME}.kiro.log"
REPORT_FILE="logs/REPORT.${WORKER_NAME}.md"
REPORT_FILE_ABS="$LOG_DIR/REPORT.${WORKER_NAME}.md"
STATUS_FILE="$LOG_DIR/.${WORKER_NAME}.status"

PROMPT_TMP="$(mktemp "${PROMPT_DIR}/.${WORKER_NAME}.XXXXXX.tmp")"
sed "s|{{ORCH_TARGET}}|${ORCH_TARGET}|g; s|__ORCH_TARGET__|${ORCH_TARGET}|g; s|{{REPORT_FILE}}|${REPORT_FILE_ABS}|g; s|{{STATUS_FILE}}|${STATUS_FILE}|g" \
  "$PROMPT_SRC" > "$PROMPT_TMP"
mv "$PROMPT_TMP" "$PROMPT_FILE"

# Worker guidance comes from the prompt's Required / Forbidden Superpowers plus
# the RESOLVED REQUIRED SKILL SOURCES appended below (#2305 — removed the
# hardcoded per-role SKILLS_HINT that duplicated/contradicted the prompt).

# --- Resolve KIRO_REQUIRED_SKILLS and append to prompt file ---
if [[ -n "${KIRO_REQUIRED_SKILLS:-}" ]]; then
  skill_section=""$'\n'"## REQUIRED SKILL SOURCES — READ FIRST"
  skill_section+=$'\n'"**Before doing anything else**, read each skill file in full using your file-reading tools:"
  IFS=',' read -r -a _skills_raw <<< "$KIRO_REQUIRED_SKILLS"
  for _skill in "${_skills_raw[@]}"; do
    _skill="${_skill#"${_skill%%[![:space:]]*}"}"
    _skill="${_skill%"${_skill##*[![:space:]]}"}"
    [[ -z "$_skill" ]] && continue
    _skill_file=""
    for _candidate in \
        "$REPO_ROOT/.kiro/skills/${_skill}/SKILL.md" \
        "$HOME/.kiro/skills/${_skill}/SKILL.md"; do
      if [[ -f "$_candidate" ]]; then
        _skill_file="$_candidate"
        break
      fi
    done
    if [[ -z "$_skill_file" ]]; then
      echo "WARNING: KIRO_REQUIRED_SKILLS skill not found: $_skill" >&2
      continue
    fi
    skill_section+=$'\n'"- **${_skill}**: \`${_skill_file}\`"
  done
  skill_section+=$'\n'"Do not proceed to the task until all skill files above have been read."
  printf '\n%s\n' "$skill_section" >> "$PROMPT_FILE"
fi

# Короткий промт-линк как в kiro-cli: агент сам читает файл
PROMPT_LINK="Read and execute the worker prompt file at: ${PROMPT_FILE}"

# --- Worker cwd (E: worktree isolation) + failsafe budget ---
# HARD STOP: code-changing workers must run in an isolated worktree.
# Pass WORKER_WORKTREE=$(./scripts/create_worker_worktree.sh ...) before launch,
# or set WORKER_WORKTREE_BYPASS=1 only for an explicit orchestrator-approved exception.
_CODE_CHANGING_ROLES="implementation plan-execution quick review-fix"
if [[ -z "${WORKER_WORKTREE:-}" && -z "${WORKER_WORKTREE_BYPASS:-}" ]]; then
  for _cr in $_CODE_CHANGING_ROLES; do
    if [[ "$WORKER_ROLE" == "$_cr" ]]; then
      echo "ERROR: WORKER_WORKTREE is required for code-changing workers (WORKER_ROLE=$WORKER_ROLE)." >&2
      echo "  Create an isolated worktree first:" >&2
      echo "    WORKER_WORKTREE=\$(./scripts/create_worker_worktree.sh <branch> <path>)" >&2
      echo "  To bypass (orchestrator-approved only): set WORKER_WORKTREE_BYPASS=1" >&2
      exit 2
    fi
  done
fi
WORKER_CWD="${WORKER_WORKTREE:-$REPO_ROOT}"
if [[ -n "${WORKER_WORKTREE:-}" && ! -d "$WORKER_WORKTREE" ]]; then
  echo "ERROR: WORKER_WORKTREE is not a directory: $WORKER_WORKTREE" >&2
  exit 2
fi
# Bug 1 (#2820): normalize to an absolute path so the wrapper's `cd` works
# regardless of the caller's CWD. A relative WORKER_WORKTREE (e.g.
# ".worktrees/fix/x") otherwise produced `cd: No such file or directory` when
# the wrapper ran from a tmux window whose CWD was not the repo root.
WORKER_CWD="$(cd "$WORKER_CWD" && pwd)"
WORKER_TIMEOUT="${WORKER_TIMEOUT:-1800}"
SIGNAL_FLAG="$LOG_DIR/.${WORKER_NAME}.signaled"
# STATUS_FILE was defined above (alongside REPORT_FILE) for the prompt sed pass.
rm -f "$SIGNAL_FLAG" "$STATUS_FILE"

# --- Wrapper-скрипт для воркера ---
WRAPPER="$LOG_DIR/${WORKER_NAME}.wrapper.sh"
cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$WORKER_CWD"

# Bug 3 (#2820): the launcher wrapper is the SOLE wake-up channel. The agent
# writes its Markdown report and a one-word status file ($STATUS_FILE); it must
# NOT send tmux keys itself. The old design let the agent self-send a wake-up
# line AND reconciled by grepping the worker LOG for "[DONE]". When an agent
# *printed* the wake-up line as chat text instead of executing it, that text
# landed in the log, the grep matched, and the failsafe was suppressed — so the
# orchestrator was never actually woken. Keying the wake-up on a status/report
# FILE (which an agent writes reliably, and whose printed echo cannot forge)
# removes the false positive entirely.
send_signal() {
  # single-fire: only the first caller actually wakes the orchestrator
  if ( set -o noclobber; : > "$SIGNAL_FLAG" ) 2>/dev/null; then
    for _retry in 1 2 3 4 5; do
      tmux send-keys -t "$ORCH_TARGET" -l "\$1" 2>/dev/null && break || true
      sleep 2
    done
    sleep 0.25
    tmux send-keys -t "$ORCH_TARGET" C-m 2>/dev/null || true
  fi
}

# Resolve the terminal status from the agent's status file, falling back to
# report-file existence. NEVER from the worker LOG (printed text is not a real
# signal — that was the bug).
resolve_status() {
  local _s=""
  if [[ -f "$STATUS_FILE" ]]; then
    _s="\$(tr -d '[:space:]' < "$STATUS_FILE" | tr '[:lower:]' '[:upper:]')"
  fi
  case "\$_s" in
    DONE|FAILED|BLOCKED) echo "\$_s"; return ;;
  esac
  if [[ -s "$REPORT_FILE_ABS" ]]; then echo "DONE"; else echo "FAILED"; fi
}

# (c) Timeout failsafe: if the worker writes neither a status file nor a report
# within the budget, wake the orchestrator with [FAILED] so it never hangs on a
# crashed/idle worker. Keyed on the status/report FILE, not the log.
(
  _deadline=\$(( \$(date +%s) + $WORKER_TIMEOUT ))
  while [[ \$(date +%s) -lt \$_deadline ]]; do
    { [[ -f "$STATUS_FILE" ]] || [[ -s "$REPORT_FILE_ABS" ]]; } && exit 0
    sleep 10
  done
  send_signal "[FAILED] $WORKER_NAME $REPORT_FILE (timeout: no report after ${WORKER_TIMEOUT}s)"
) &
_watchdog=\$!

# Full kiro-cli session. The agent writes its report + status file and exits;
# the wrapper (below) delivers the single authoritative wake-up.
kiro-cli chat \\
  --trust-all-tools \\
  ${WORKER_MODEL:+--model "$WORKER_MODEL"} \\
  ${WORKER_AGENT:+--agent "$WORKER_AGENT"} \\
  "$PROMPT_LINK" \\
  2>&1 | tee "$WORKER_LOG"

# kiro-cli exited: stop the watchdog and deliver exactly one wake-up. The
# single-fire guard makes a double wake-up impossible even if the timeout
# failsafe already fired.
kill "\$_watchdog" 2>/dev/null || true
send_signal "[\$(resolve_status)] $WORKER_NAME $REPORT_FILE"
WRAPPER_EOF
chmod +x "$WRAPPER"

# --- Запустить в новом tmux-окне (полноценный терминал) ---
SESSION_NAME="$(tmux display-message -p '#{session_name}')"
tmux new-window -t "${SESSION_NAME}:" -n "$WORKER_NAME" -c "$WORKER_CWD"
tmux send-keys -t "${SESSION_NAME}:${WORKER_NAME}" "bash '$WRAPPER'" C-m

echo "✓ Worker '${WORKER_NAME}' → tmux window '${SESSION_NAME}:${WORKER_NAME}'"
echo "  Model:        ${WORKER_MODEL:-default}"
echo "  Orchestrator: ${ORCH_TARGET}"
echo "  Prompt:       ${PROMPT_FILE}"
echo "  Report:       ${REPORT_FILE}"
echo "  Log:          ${WORKER_LOG}"
