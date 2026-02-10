#!/bin/bash
SESSION=$(TMUX="" tmux list-sessions -F "#{session_name}" | head -1)
declare -A WINDOW_MAP=(["worker-p1-config"]="W-P1-CONFIG" ["worker-p1-qdrant"]="W-P1-QDR")
echo "[MONITOR] Started at $(date +%H:%M:%S), watching: ${!WINDOW_MAP[*]}"
while true; do
  all_done=true
  for k in "${!WINDOW_MAP[@]}"; do
    if grep -q '\[COMPLETE\]' "logs/${k}.log" 2>/dev/null; then
      if TMUX="" tmux list-windows -t "$SESSION" -F "#{window_name}" 2>/dev/null | grep -q "^${WINDOW_MAP[$k]}$"; then
        echo "[MONITOR] $(date +%H:%M:%S) ${k} COMPLETE — closing ${WINDOW_MAP[$k]}"
        TMUX="" tmux kill-window -t "$SESSION:${WINDOW_MAP[$k]}" 2>/dev/null
      fi
    else
      all_done=false
    fi
  done
  $all_done && { echo "[MONITOR] $(date +%H:%M:%S) All workers complete!"; break; }
  sleep 30
done
