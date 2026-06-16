#!/usr/bin/env bash
# set_orchestrator_window.sh — назначить текущее tmux-окно оркестратором
#
# Переименовывает текущее окно в уникальное имя orch-<task>-YYYYMMDDTHHMMSS-<hex>
# и сохраняет маркер в .signals/orchestrator-window.json
#
# Использование:
#   ./scripts/set_orchestrator_window.sh <task-slug>
#   eval $(./scripts/set_orchestrator_window.sh <task-slug>)  # экспортирует ORCH_TARGET

set -euo pipefail

TASK="${1:-main}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIGNALS_DIR="$REPO_ROOT/.signals"
mkdir -p "$SIGNALS_DIR"

SESSION="$(tmux display-message -p '#{session_name}')"
NOW="$(date -u '+%Y%m%dT%H%M%S')"
HEX="$(head -c 4 /dev/urandom | xxd -p)"
WINDOW_NAME="orch-${TASK}-${NOW}-${HEX}"

# Переименовать текущее окно
tmux rename-window "$WINDOW_NAME"

ORCH_TARGET="${SESSION}:${WINDOW_NAME}"
MARKER_FILE="$SIGNALS_DIR/orchestrator-window.json"

# Сохранить маркер
python3 - <<PY
import json
from pathlib import Path
data = {
    "orchestrator_target": "$ORCH_TARGET",
    "orchestrator_window_name": "$WINDOW_NAME",
    "orchestrator_session_name": "$SESSION",
    "task": "$TASK",
    "set_at": "$(date -Iseconds)",
}
Path("$MARKER_FILE").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY

echo "export ORCH_TARGET='${ORCH_TARGET}'"
echo "# Marker: $MARKER_FILE" >&2
echo "# Window renamed to: $WINDOW_NAME" >&2
