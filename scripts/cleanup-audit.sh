#!/bin/bash
set -e
cd /home/user/projects/rag-fresh
echo "[cleanup] Removing dev artifacts..."
rm -rf tmp reports .cache .mypy_cache .ruff_cache .pytest_cache .import_linter_cache .venv-py312 .bg-shell .mimocode data opencode.json
rm .coverage 2>/dev/null || true
rmdir .opencode 2>/dev/null || true
git worktree prune
rm -rf .worktrees
echo "[cleanup] Complete. Reclaimed space. Run: make check"
