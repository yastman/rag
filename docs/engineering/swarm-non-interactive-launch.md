# Swarm Non-Interactive Launch

## Problem

OpenCode worker processes launched by the swarm orchestrator prompt for permission on repo-local reads/writes/commands, blocking automated pipelines. Workers hang indefinitely waiting for interactive confirmation that will never arrive.

## Root Cause

The `OPENCODE_PERMISSION` environment variable is silently ignored by OpenCode. It has no effect on runtime behavior. Setting it does not suppress permission prompts.

## Canonical Mechanism

OpenCode reads the `permission` field from `opencode.json`. At runtime, this config can be supplied via:

1. **Project-local `./opencode.json`** (highest precedence) - a file in the working directory
2. **`OPENCODE_CONFIG=/path/to/file.json`** - explicit config file path pointing to a JSON file containing the permission field
3. **`OPENCODE_CONFIG_CONTENT='{"permission":"allow"}'`** - inline JSON (no file needed), suitable for ephemeral environments

When `permission` is set to `"allow"`, OpenCode grants all read/write/command operations without interactive prompts.

## Recommended Launcher Pattern

Use the repository wrapper script `scripts/swarm_opencode_run_unattended.sh`:

```bash
scripts/swarm_opencode_run_unattended.sh --model gpt-4 --prompt "Implement feature X"
```

The wrapper script performs the following steps:

1. Checks that `opencode` is available on PATH (exits 127 with a diagnostic if missing)
2. If neither `OPENCODE_CONFIG` nor `OPENCODE_CONFIG_CONTENT` is already set, exports `OPENCODE_CONFIG_CONTENT='{"permission":"allow"}'`
3. If either variable is already set, leaves them untouched (respects caller policy)
4. Executes `opencode` with all arguments passed through

This ensures workers always launch in non-interactive mode without overriding explicit policy set by the caller.

## Verification Checklist

1. Confirm the script is executable: `test -x scripts/swarm_opencode_run_unattended.sh`
2. Verify syntax: `bash -n scripts/swarm_opencode_run_unattended.sh`
3. Test with a stub opencode that prints its environment to confirm `OPENCODE_CONFIG_CONTENT` is set:
   ```bash
   mkdir -p /tmp/stub && echo '#!/bin/bash
   echo "OPENCODE_CONFIG_CONTENT=$OPENCODE_CONFIG_CONTENT"' > /tmp/stub/opencode && chmod +x /tmp/stub/opencode
   PATH=/tmp/stub:$PATH scripts/swarm_opencode_run_unattended.sh
   ```
4. Confirm the output contains `OPENCODE_CONFIG_CONTENT={"permission":"allow"}`
5. Test that pre-set `OPENCODE_CONFIG` is not overridden:
   ```bash
   OPENCODE_CONFIG=/my/config.json PATH=/tmp/stub:$PATH scripts/swarm_opencode_run_unattended.sh
   ```
6. Confirm the output shows `OPENCODE_CONFIG_CONTENT=` (empty, not injected)

## Per-Worker Policy Overrides

To set custom policies for specific workers, export `OPENCODE_CONFIG` or `OPENCODE_CONFIG_CONTENT` before invoking the wrapper:

```bash
# Use a custom config file for a specific worker
export OPENCODE_CONFIG="/etc/opencode/restricted-worker.json"
scripts/swarm_opencode_run_unattended.sh --prompt "Run analysis"

# Use inline JSON with a different permission level
export OPENCODE_CONFIG_CONTENT='{"permission":"deny","allowedCommands":["git status","git diff"]}'
scripts/swarm_opencode_run_unattended.sh --prompt "Read-only check"
```

The wrapper script detects these pre-set variables and does not override them, allowing fine-grained control per worker without modifying the launcher.

## References

- OpenCode permissions documentation (permissions.mdx)
- OpenCode configuration documentation (config.mdx)
- GitHub issue #1306
