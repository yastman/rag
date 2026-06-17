#!/usr/bin/env bash
# set_orchestrator_window.sh — назначить текущее tmux-окно оркестратором
#
# Переименовывает текущее окно в уникальное имя orch-<task>-YYYYMMDDTHHMMSS-<hex>
# и сохраняет маркер в .signals/orchestrator-window.json
#
# Использование:
#   ./scripts/set_orchestrator_window.sh [--ensure-window-name] [--force] <task-slug>
#   eval $(./scripts/set_orchestrator_window.sh <task-slug>)   # экспортирует ORCH_TARGET
#
# Флаги:
#   --ensure-window-name  Идемпотентно: если текущее окно УЖЕ оркестратор для
#                         этого task (маркер совпадает), только обновить set_at
#                         без переименования. Иначе — назначить.
#   --force               Перетереть активный маркер, даже если он указывает на
#                         другое живое окно/таск (по умолчанию это запрещено —
#                         см. guard ниже, fix B).
#
# Guard (fix B): по умолчанию скрипт ОТКАЗЫВАЕТСЯ перебивать существующий маркер,
# если он указывает на ЖИВОЕ окно с ДРУГИМ таском и это окно не текущее. Это не
# даёт случайно заклеймить оркестратором окно, занятое другой работой, и увести
# к нему wake-up воркеров. Запусти из того окна, передай --force, или сменись.

set -euo pipefail

ENSURE=0
FORCE=0
TASK=""
for arg in "$@"; do
    case "$arg" in
        --ensure-window-name) ENSURE=1 ;;
        --force) FORCE=1 ;;
        -*) echo "ERROR: unknown flag: $arg" >&2; exit 2 ;;
        *) if [[ -z "$TASK" ]]; then TASK="$arg"; else echo "ERROR: unexpected arg: $arg" >&2; exit 2; fi ;;
    esac
done
TASK="${TASK:-main}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIGNALS_DIR="$REPO_ROOT/.signals"
mkdir -p "$SIGNALS_DIR"
MARKER_FILE="$SIGNALS_DIR/orchestrator-window.json"

SESSION="$(tmux display-message -p '#{session_name}')"
CURRENT_WINDOW="$(tmux display-message -p '#{window_name}')"

# --- Guard B: refuse to clobber an active marker pointing at a different live window ---
marker_window_is_live() {
    # echoes "1" if the marker's session:window currently exists
    python3 - "$MARKER_FILE" <<'PY' 2>/dev/null || true
import json, subprocess, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
sess = d.get("orchestrator_session_name", "")
win = d.get("orchestrator_window_name", "")
if not sess or not win:
    sys.exit(0)
r = subprocess.run(["tmux", "list-windows", "-t", sess, "-F", "#{window_name}"],
                   capture_output=True, text=True)
if r.returncode == 0 and win in r.stdout.split("\n"):
    print("1")
PY
}

if [[ -f "$MARKER_FILE" && "$FORCE" -eq 0 ]]; then
    MARKER_WINDOW="$(python3 -c "import json;print(json.load(open('$MARKER_FILE')).get('orchestrator_window_name',''))" 2>/dev/null || true)"
    MARKER_TASK="$(python3 -c "import json;print(json.load(open('$MARKER_FILE')).get('task',''))" 2>/dev/null || true)"
    if [[ -n "$MARKER_WINDOW" && "$MARKER_WINDOW" != "$CURRENT_WINDOW" && "$(marker_window_is_live)" == "1" ]]; then
        # --ensure-window-name targeting the same task as a live marker on another
        # window is still a conflict: the orchestrator already lives elsewhere.
        echo "ERROR: an active orchestrator marker already points at a live window:" >&2
        echo "       window='${MARKER_WINDOW}' task='${MARKER_TASK}'" >&2
        echo "       Run set_orchestrator_window.sh from that window, pass --force to override," >&2
        echo "       or close that window first. (guard B)" >&2
        exit 3
    fi
fi

# --- Idempotent ensure (fix H): we are already the orchestrator for this task ---
if [[ "$ENSURE" -eq 1 && -f "$MARKER_FILE" ]]; then
    MARKER_WINDOW="$(python3 -c "import json;print(json.load(open('$MARKER_FILE')).get('orchestrator_window_name',''))" 2>/dev/null || true)"
    MARKER_TASK="$(python3 -c "import json;print(json.load(open('$MARKER_FILE')).get('task',''))" 2>/dev/null || true)"
    if [[ "$MARKER_WINDOW" == "$CURRENT_WINDOW" && "$MARKER_TASK" == "$TASK" ]]; then
        ORCH_TARGET="${SESSION}:${CURRENT_WINDOW}"
        python3 - <<PY
import json
from pathlib import Path
p = Path("$MARKER_FILE")
d = json.loads(p.read_text())
d["set_at"] = "$(date -Iseconds)"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
PY
        echo "export ORCH_TARGET='${ORCH_TARGET}'"
        echo "# Marker refreshed (already orchestrator): $ORCH_TARGET" >&2
        exit 0
    fi
fi

NOW="$(date -u '+%Y%m%dT%H%M%S')"
HEX="$(head -c 4 /dev/urandom | xxd -p)"
WINDOW_NAME="orch-${TASK}-${NOW}-${HEX}"

# Переименовать текущее окно
tmux rename-window "$WINDOW_NAME"

ORCH_TARGET="${SESSION}:${WINDOW_NAME}"

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
