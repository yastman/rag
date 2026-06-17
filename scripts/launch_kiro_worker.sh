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
PROMPT_TMP="$(mktemp "${PROMPT_DIR}/.${WORKER_NAME}.XXXXXX.tmp")"
sed "s|{{ORCH_TARGET}}|${ORCH_TARGET}|g; s|__ORCH_TARGET__|${ORCH_TARGET}|g" \
  "$PROMPT_SRC" > "$PROMPT_TMP"
mv "$PROMPT_TMP" "$PROMPT_FILE"

# Worker guidance comes from the prompt's Required / Forbidden Superpowers plus
# the RESOLVED REQUIRED SKILL SOURCES appended below (#2305 — removed the
# hardcoded per-role SKILLS_HINT that duplicated/contradicted the prompt).
WORKER_LOG="$LOG_DIR/${WORKER_NAME}.kiro.log"
REPORT_FILE="logs/${WORKER_NAME}.md"

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
WORKER_TIMEOUT="${WORKER_TIMEOUT:-1800}"
SIGNAL_FLAG="$LOG_DIR/.${WORKER_NAME}.signaled"
rm -f "$SIGNAL_FLAG"

# --- Wrapper-скрипт для воркера ---
WRAPPER="$LOG_DIR/${WORKER_NAME}.wrapper.sh"
cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$WORKER_CWD"

# Single-fire wake-up: only the first caller actually wakes the orchestrator, so
# the agent's own wake-up (channel a) and the failsafe below can never
# double-send (kills the legacy double-wake). RAIL ONLY: forward a terminal
# signal verbatim; the orchestrator (swarm-acceptance) owns accept/PR/merge.
send_signal() {
  if ( set -o noclobber; : > "$SIGNAL_FLAG" ) 2>/dev/null; then
    for _retry in 1 2 3 4 5; do
      tmux send-keys -t "$ORCH_TARGET" -l "\$1" 2>/dev/null && break || true
      sleep 2
    done
    sleep 0.25
    tmux send-keys -t "$ORCH_TARGET" C-m 2>/dev/null || true
  fi
}

# (c) Timeout failsafe: if no terminal signal appears within the budget, wake the
# orchestrator with [FAILED] so it never hangs on a crashed/idle worker. The
# agent's own wake-up emitted from the prompt (channel a) remains primary.
(
  _deadline=\$(( \$(date +%s) + $WORKER_TIMEOUT ))
  while [[ \$(date +%s) -lt \$_deadline ]]; do
    grep -qE '\[(DONE|FAILED|BLOCKED)\]' "$WORKER_LOG" 2>/dev/null && exit 0
    sleep 10
  done
  send_signal "[FAILED] $WORKER_NAME $REPORT_FILE (timeout: no terminal signal after ${WORKER_TIMEOUT}s)"
) &
_watchdog=\$!

# Full kiro-cli session (channel a: the agent emits its own wake-up on finish).
kiro-cli chat \\
  --trust-all-tools \\
  ${WORKER_MODEL:+--model "$WORKER_MODEL"} \\
  ${WORKER_AGENT:+--agent "$WORKER_AGENT"} \\
  "$PROMPT_LINK" \\
  2>&1 | tee "$WORKER_LOG"

# If kiro-cli exited, stop the watchdog and reconcile: when a terminal signal is
# present the agent already woke the orchestrator; otherwise fail-safe. The
# single-fire guard makes a double wake-up impossible.
kill "\$_watchdog" 2>/dev/null || true
grep -qE '\[(DONE|FAILED|BLOCKED)\]' "$WORKER_LOG" 2>/dev/null || \\
  send_signal "[FAILED] $WORKER_NAME $REPORT_FILE (worker exited without a terminal signal)"
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
