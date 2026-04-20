#!/usr/bin/env bash
set -euo pipefail

exec uv run python -m scripts.test_bot_health
