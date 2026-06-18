#!/usr/bin/env bash
# set_orchestrator_window.sh — назначить текущее tmux-окно оркестратором
#
# Присваивает окну УНИКАЛЬНОЕ имя orch-<task>-YYYYMMDDTHHMMSS-<hex> ОДИН РАЗ за
# сессию и сохраняет маркер в .signals/orchestrator-window.json. Wake-up воркеров
# маршрутизируется по НЕИЗМЕНЯЕМОМУ tmux window-id (session:@id), а не по имени —
# поэтому [DONE] доходит до оркестратора даже если имя окна потом изменится.
#
# Использование:
#   ./scripts/set_orchestrator_window.sh [--ensure-window-name] [--force] <task-slug>
#   eval $(./scripts/set_orchestrator_window.sh <task-slug>)   # экспортирует ORCH_TARGET
#
# Set-once (главное свойство): если текущее окно УЖЕ оркестратор этой сессии
# (маркер указывает на это окно по window-id), скрипт НЕ переименовывает его.
# Новый таск только обновляет метаданные маркера (task/set_at) и при необходимости
# восстанавливает каноническое имя — без «текучки» имени на каждый таск.
#
# Маршрутизация по window-id (страховка): ORCH_TARGET = "<session>:<@window-id>".
# Имя окна — только для человека/гарда; доставка wake-up идёт по @id, который
# tmux не меняет на протяжении жизни окна. Дополнительно гасим automatic-rename и
# allow-rename, чтобы tmux/оболочка не откатили имя.
#
# Флаги:
#   --ensure-window-name  Историческая совместимость. Set-once теперь поведение по
#                         умолчанию, поэтому флаг ничего не меняет (no-op-friendly).
#   --force               Перетереть активный маркер, указывающий на ДРУГОЕ живое
#                         окно с другим таском (по умолчанию это запрещено гардом B).
#
# Guard B: по умолчанию скрипт ОТКАЗЫВАЕТСЯ перебивать существующий маркер, если он
# указывает на ЖИВОЕ окно с ДРУГИМ таском и это окно не текущее. Это не даёт
# случайно заклеймить оркестратором окно, занятое другой работой, и увести к нему
# wake-up воркеров. Запусти из того окна, передай --force, или закрой то окно.

set -euo pipefail

FORCE=0
TASK=""
for arg in "$@"; do
    case "$arg" in
        --ensure-window-name) ;; # accepted for backward compat, set-once is now default behaviour
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
# Immutable window id (e.g. @7). Stable for the whole life of the window — this is
# what wake-up routing keys on so a later rename can never misdeliver [DONE].
WINDOW_ID="$(tmux display-message -p '#{window_id}')"

# --- marker readers -----------------------------------------------------------
marker_get() {
    # marker_get <key> — echo a string field from the marker (empty if absent)
    [[ -f "$MARKER_FILE" ]] || return 0
    python3 -c "import json,sys;print(json.load(open('$MARKER_FILE')).get(sys.argv[1],''))" "$1" 2>/dev/null || true
}

# --- pin the window name against tmux auto-renaming ---------------------------
pin_window_name() {
    # Stop tmux (automatic-rename) and the program in the pane (allow-rename escape
    # sequences) from reverting the orchestrator window name. Best-effort.
    tmux set-window-option -t "$WINDOW_ID" automatic-rename off 2>/dev/null || true
    tmux set-window-option -t "$WINDOW_ID" allow-rename off 2>/dev/null || true
}

MARKER_WINDOW_ID="$(marker_get orchestrator_window_id)"
MARKER_WINDOW="$(marker_get orchestrator_window_name)"
MARKER_TASK="$(marker_get task)"

# --- Set-once: we are already the orchestrator window for this session --------
# Identify by the immutable window-id (preferred) or the recorded name (markers
# written before the id field existed). When it's us, DO NOT mint a new name:
# keep the existing one, restore it if it drifted, and only refresh metadata.
if [[ -f "$MARKER_FILE" ]]; then
    SAME_WINDOW=0
    if [[ -n "$MARKER_WINDOW_ID" && "$MARKER_WINDOW_ID" == "$WINDOW_ID" ]]; then
        SAME_WINDOW=1
    elif [[ -z "$MARKER_WINDOW_ID" && -n "$MARKER_WINDOW" && "$MARKER_WINDOW" == "$CURRENT_WINDOW" ]]; then
        SAME_WINDOW=1
    fi
    if [[ "$SAME_WINDOW" -eq 1 ]]; then
        KEEP_NAME="${MARKER_WINDOW:-$CURRENT_WINDOW}"
        # Restore the canonical name if it drifted (cosmetic — routing is id-based).
        if [[ "$CURRENT_WINDOW" != "$KEEP_NAME" ]]; then
            tmux rename-window -t "$WINDOW_ID" "$KEEP_NAME" 2>/dev/null || true
        fi
        pin_window_name
        ORCH_TARGET="${SESSION}:${WINDOW_ID}"
        python3 - <<PY
import json
from pathlib import Path
p = Path("$MARKER_FILE")
d = json.loads(p.read_text())
d["task"] = "$TASK"
d["set_at"] = "$(date -Iseconds)"
d["orchestrator_window_id"] = "$WINDOW_ID"
d["orchestrator_window_name"] = "$KEEP_NAME"
d["orchestrator_session_name"] = "$SESSION"
d["orchestrator_target"] = "$ORCH_TARGET"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
PY
        echo "export ORCH_TARGET='${ORCH_TARGET}'"
        echo "# Already orchestrator (set-once): kept window '${KEEP_NAME}' [${WINDOW_ID}], task → ${TASK}" >&2
        exit 0
    fi
fi

# --- Guard B: refuse to clobber an active marker pointing at a different live window ---
marker_window_is_live() {
    # echoes "1" if the marker's orchestrator window currently exists (by id first,
    # then by name for legacy markers)
    python3 - "$MARKER_FILE" <<'PY' 2>/dev/null || true
import json, subprocess, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
sess = d.get("orchestrator_session_name", "")
win_id = d.get("orchestrator_window_id", "")
win = d.get("orchestrator_window_name", "")
if not sess:
    sys.exit(0)
r = subprocess.run(["tmux", "list-windows", "-t", sess, "-F", "#{window_id}\t#{window_name}"],
                   capture_output=True, text=True)
if r.returncode != 0:
    sys.exit(0)
ids, names = set(), set()
for line in r.stdout.splitlines():
    parts = line.split("\t")
    if len(parts) == 2:
        ids.add(parts[0]); names.add(parts[1])
if (win_id and win_id in ids) or (win and win in names):
    print("1")
PY
}

if [[ -f "$MARKER_FILE" && "$FORCE" -eq 0 ]]; then
    if [[ -n "$MARKER_WINDOW" && "$MARKER_WINDOW" != "$CURRENT_WINDOW" && "$(marker_window_is_live)" == "1" ]]; then
        echo "ERROR: an active orchestrator marker already points at a live window:" >&2
        echo "       window='${MARKER_WINDOW}' id='${MARKER_WINDOW_ID}' task='${MARKER_TASK}'" >&2
        echo "       Run set_orchestrator_window.sh from that window, pass --force to override," >&2
        echo "       or close that window first. (guard B)" >&2
        exit 3
    fi
fi

# --- Fresh claim: mint a unique name ONCE and rename THIS window by its id -----
NOW="$(date -u '+%Y%m%dT%H%M%S')"
HEX="$(head -c 4 /dev/urandom | xxd -p)"
WINDOW_NAME="orch-${TASK}-${NOW}-${HEX}"

# Rename by explicit window-id, never by ambient "current window" — guarantees we
# rename the exact window we measured, not whatever happens to be active now.
tmux rename-window -t "$WINDOW_ID" "$WINDOW_NAME"
pin_window_name

# Wake-up target is the immutable id, so a later name change cannot misroute it.
ORCH_TARGET="${SESSION}:${WINDOW_ID}"

# Сохранить маркер
python3 - <<PY
import json
from pathlib import Path
data = {
    "orchestrator_target": "$ORCH_TARGET",
    "orchestrator_window_id": "$WINDOW_ID",
    "orchestrator_window_name": "$WINDOW_NAME",
    "orchestrator_session_name": "$SESSION",
    "task": "$TASK",
    "set_at": "$(date -Iseconds)",
}
Path("$MARKER_FILE").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY

echo "export ORCH_TARGET='${ORCH_TARGET}'"
echo "# Marker: $MARKER_FILE" >&2
echo "# Window renamed to: $WINDOW_NAME [${WINDOW_ID}] (wake-up target: ${ORCH_TARGET})" >&2

# --- Post-rename verification -------------------------------------------------
# Confirm the window-id now carries the expected name. A mismatch here is only
# cosmetic (wake-up routes by id, not name), but it signals tmux fought the
# rename — retry once, then warn loudly rather than fail.
ACTUAL_WINDOW="$(tmux display-message -p -t "$WINDOW_ID" '#{window_name}' 2>/dev/null || true)"
if [[ "$ACTUAL_WINDOW" != "$WINDOW_NAME" ]]; then
    tmux rename-window -t "$WINDOW_ID" "$WINDOW_NAME" 2>/dev/null || true
    pin_window_name
    ACTUAL_WINDOW="$(tmux display-message -p -t "$WINDOW_ID" '#{window_name}' 2>/dev/null || true)"
fi
if [[ "$ACTUAL_WINDOW" != "$WINDOW_NAME" ]]; then
    echo "WARNING: window '${WINDOW_ID}' is named '${ACTUAL_WINDOW}', expected '${WINDOW_NAME}'." >&2
    echo "         Wake-up still works (routed by id ${ORCH_TARGET}); the name is cosmetic." >&2
fi
