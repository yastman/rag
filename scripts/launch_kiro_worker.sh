#!/usr/bin/env bash
# launch_kiro_worker.sh — запустить Kiro воркера в отдельном tmux-окне
#
# Использование:
#   ./scripts/launch_kiro_worker.sh <worker-name> <prompt-file>
#
# Переменные окружения:
#   ORCH_TARGET   — tmux target оркестратора (если не задан, читается из .signals/orchestrator-window.json)
#   WORKER_AGENT  — агент Kiro (optional, default: kiro_default)
#   WORKER_MODEL  — модель (optional)
#   WORKER_ROLE   — роль воркера для отчёта (default: research)
#
# Флоу (как opencode):
#   1. Определить ORCH_TARGET из маркера
#   2. Сохранить промт в logs/.codex/prompts/<worker>.md
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
PROMPT_FILE="$PROMPT_DIR/${WORKER_NAME}.md"
sed "s|{{ORCH_TARGET}}|${ORCH_TARGET}|g; s|__ORCH_TARGET__|${ORCH_TARGET}|g" \
  "$PROMPT_SRC" > "$PROMPT_FILE"

# Worker guidance comes from the prompt's Required / Forbidden Superpowers plus
# the RESOLVED REQUIRED SKILL SOURCES appended below (#2305 — removed the
# hardcoded per-role SKILLS_HINT that duplicated/contradicted the prompt).
WORKER_LOG="$LOG_DIR/${WORKER_NAME}.kiro.log"
REPORT_FILE="logs/${WORKER_NAME}.md"

# --- Resolve KIRO_REQUIRED_SKILLS and append to prompt file ---
if [[ -n "${KIRO_REQUIRED_SKILLS:-}" ]]; then
  skill_section=""$'\n'"## RESOLVED REQUIRED SKILL SOURCES"
  IFS=',' read -r -a _skills_raw <<< "$KIRO_REQUIRED_SKILLS"
  for _skill in "${_skills_raw[@]}"; do
    _skill="${_skill#"${_skill%%[![:space:]]*}"}"
    _skill="${_skill%"${_skill##*[![:space:]]}"}"
    [[ -z "$_skill" ]] && continue
    _skill_file=""
    for _candidate in \
        "$REPO_ROOT/.kiro/skills/${_skill}/SKILL.md" \
        "$HOME/.codex/skills/${_skill}/SKILL.md"; do
      if [[ -f "$_candidate" ]]; then
        _skill_file="$_candidate"
        break
      fi
    done
    if [[ -z "$_skill_file" ]]; then
      echo "WARNING: KIRO_REQUIRED_SKILLS skill not found: $_skill" >&2
      continue
    fi
    skill_section+=$'\n'"- ${_skill}: ${_skill_file}"
  done
  printf '\n%s\n' "$skill_section" >> "$PROMPT_FILE"
fi

# Короткий промт-линк как в opencode: агент сам читает файл
PROMPT_LINK="Read and execute the worker prompt file at: ${PROMPT_FILE}"

# --- Wrapper-скрипт для воркера ---
WRAPPER="$LOG_DIR/${WORKER_NAME}.wrapper.sh"
cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO_ROOT"

# Полноценная интерактивная сессия kiro-cli (как opencode --prompt)
kiro-cli chat \\
  --trust-all-tools \\
  ${WORKER_MODEL:+--model "$WORKER_MODEL"} \\
  ${WORKER_AGENT:+--agent "$WORKER_AGENT"} \\
  "$PROMPT_LINK" \\
  2>&1 | tee "$WORKER_LOG"

# Поймать статусную строку и послать оркестратору.
# RAIL ONLY (#2305 P0): forward the worker's terminal signal verbatim.
# No semantic acceptance, no auto-PR. The orchestrator (swarm-acceptance)
# decides accepted / needs_fix / PR / merge from the report.
STATUS_LINE=\$(grep -oE '\[(DONE|FAILED|BLOCKED)\][^\n]*' "$WORKER_LOG" | tail -1 || true)

if [[ -n "\$STATUS_LINE" ]]; then
  for _retry in 1 2 3 4 5; do
    tmux send-keys -t "$ORCH_TARGET" -l "\$STATUS_LINE" 2>/dev/null && break || true
    sleep 2
  done
else
  for _retry in 1 2 3 4 5; do
    tmux send-keys -t "$ORCH_TARGET" -l "[FAILED] ${WORKER_NAME} ${REPORT_FILE}" 2>/dev/null && break || true
    sleep 2
  done
fi
sleep 0.25
tmux send-keys -t "$ORCH_TARGET" C-m
WRAPPER_EOF
chmod +x "$WRAPPER"

# --- Запустить в новом tmux-окне (полноценный терминал) ---
SESSION_NAME="$(tmux display-message -p '#{session_name}')"
tmux new-window -t "${SESSION_NAME}:" -n "$WORKER_NAME" -c "$REPO_ROOT"
tmux send-keys -t "${SESSION_NAME}:${WORKER_NAME}" "bash '$WRAPPER'" C-m

echo "✓ Worker '${WORKER_NAME}' → tmux window '${SESSION_NAME}:${WORKER_NAME}'"
echo "  Model:        ${WORKER_MODEL:-default}"
echo "  Orchestrator: ${ORCH_TARGET}"
echo "  Prompt:       ${PROMPT_FILE}"
echo "  Report:       ${REPORT_FILE}"
echo "  Log:          ${WORKER_LOG}"
