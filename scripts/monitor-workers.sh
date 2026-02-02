#!/bin/bash
# Auto-monitor workers: read logs, close completed, notify when all done

LOGS_DIR="/home/user/projects/rag-fresh/logs"
POLL_INTERVAL=30

declare -A WINDOW_MAP=(
    ["worker-j"]="W-J"
)

echo "=== Worker Monitor Started $(date) ==="
echo "Polling every ${POLL_INTERVAL}s"
echo

while true; do
    completed=0
    total=${#WINDOW_MAP[@]}

    for log_name in "${!WINDOW_MAP[@]}"; do
        log_file="$LOGS_DIR/${log_name}.log"
        window="${WINDOW_MAP[$log_name]}"

        if [[ -f "$log_file" ]]; then
            if grep -q '\[COMPLETE\]' "$log_file" 2>/dev/null; then
                # Check if window still exists
                if tmux list-windows -F '#{window_name}' | grep -q "^${window}$"; then
                    echo "[$(date +%H:%M:%S)] ✅ $window COMPLETE - closing window"
                    tmux kill-window -t "$window" 2>/dev/null
                fi
                ((completed++))
            elif grep -q '\[FAIL\]' "$log_file" 2>/dev/null; then
                echo "[$(date +%H:%M:%S)] ❌ $window has FAILURES - check logs"
            fi
        fi
    done

    echo "[$(date +%H:%M:%S)] Progress: $completed/$total complete"

    if [[ "$completed" -eq "$total" ]]; then
        echo
        echo "🎉 ALL WORKERS COMPLETE! $(date)"
        echo "Run: /verification-before-completion"
        break
    fi

    sleep $POLL_INTERVAL
done
