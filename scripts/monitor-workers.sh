#!/bin/bash
declare -A WINDOW_MAP=(
  ["worker-bge"]="W-BGE"
  ["worker-user"]="W-USER"
  ["worker-bm42"]="W-BM42"
  ["worker-bot"]="W-BOT"
  ["worker-docling"]="W-DOC"
)

while true; do
  for k in "${!WINDOW_MAP[@]}"; do
    grep -q '\[COMPLETE\]' "logs/${k}.log" 2>/dev/null && \
      tmux kill-window -t "${WINDOW_MAP[$k]}" 2>/dev/null
  done
  sleep 30
done
