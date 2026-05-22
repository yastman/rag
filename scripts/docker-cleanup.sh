#!/bin/bash
# Safe Docker cleanup — does NOT touch volumes
set -e
echo "$(date) — Docker cleanup starting"
docker builder prune -f --filter 'until=168h'
docker image prune -f
echo "$(date) — Docker cleanup complete"
