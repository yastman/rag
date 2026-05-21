#!/usr/bin/env bash
set -euo pipefail

if ! command -v opencode >/dev/null 2>&1; then
    echo "ERROR: 'opencode' is not installed or not in PATH." >&2
    echo "Install opencode and ensure it is available on your PATH before running this script." >&2
    exit 127
fi

if [[ -z "${OPENCODE_CONFIG:-}" && -z "${OPENCODE_CONFIG_CONTENT:-}" ]]; then
    # NOTE: permission=allow grants full tool access; intended for trusted automation only.
    export OPENCODE_CONFIG_CONTENT='{"permission":"allow"}'
fi

exec opencode "$@"
