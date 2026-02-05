#!/bin/bash
# Monitor tmux workers and auto-close completed ones

declare -A WINDOW_MAP=(
    ["worker-bge"]="W-BGE"
    ["worker-user"]="W-USER"
    ["worker-bot"]="W-BOT"
    ["worker-ing"]="W-ING"
    ["worker-dock"]="W-DOCK"
)

LOGS_DIR="/repo/logs"

echo "[$(date)] Monitor started"

while true; do
    all_complete=true
    for k in "${!WINDOW_MAP[@]}"; do
        log_file="${LOGS_DIR}/${k}.log"
        window_name="${WINDOW_MAP[$k]}"

        if grep -q '\[COMPLETE\]' "$log_file" 2>/dev/null; then
            echo "[$(date)] $k completed, killing window $window_name"
            tmux kill-window -t "$window_name" 2>/dev/null
            unset "WINDOW_MAP[$k]"
        else
            all_complete=false
        fi
    done

    if [ ${#WINDOW_MAP[@]} -eq 0 ]; then
        echo "[$(date)] All workers complete!"
        break
    fi

    sleep 30
done
