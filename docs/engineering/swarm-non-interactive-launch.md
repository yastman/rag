# Non-Interactive OpenCode Launches for Swarm Workers

Reference for swarm worker launchers (e.g.
`~/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_*.sh`) so
unattended workers do not block on permission prompts. Tracks issue
[#1306](https://github.com/yastman/rag/issues/1306).

## Root Cause

The legacy launcher exported

```bash
OPENCODE_PERMISSION='{"*":"allow"}'
```

before invoking OpenCode. **OpenCode does not recognise the
`OPENCODE_PERMISSION` environment variable.** It is silently ignored and the
TUI continues to prompt for approval on the first tool call, deadlocking
the worker.

## Canonical Mechanism

OpenCode's permission policy is defined by the `permission` field in an
`opencode.json` config file. From the upstream docs (Context7 source IDs
listed below), the policy can be set globally or per-tool:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": "allow"
}
```

Granular form for stricter sandboxes:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "*": "ask",
    "edit": "deny",
    "bash": { "git *": "allow", "rm *": "deny", "*": "ask" },
    "external_directory": { "~/secrets/**": "deny", "*": "allow" }
  }
}
```

### Loading the policy at runtime

OpenCode discovers the policy via three mechanisms, in precedence order:

1. **Project-local config** — `./opencode.json` in the current working
   directory. Highest precedence.
2. **Explicit config path** — `OPENCODE_CONFIG=/abs/path/to/file.json`.
   Loaded between project and global config.
3. **Inline injection** — `OPENCODE_CONFIG_CONTENT='<JSON>'`. The JSON
   document is parsed in place; useful for ephemeral worker sessions
   where writing a file would be unnecessary noise.

Escape hatches (rarely needed):

- `OPENCODE_DISABLE_PROJECT_CONFIG=1` — skip `./opencode.json`.
- `OPENCODE_CONFIG_DIR=/path` — override the directory used to load
  agents, commands, modes, and plugins.

Sources (Context7 `/anomalyco/opencode`):

- `dev/packages/web/src/content/docs/permissions.mdx`
- `dev/packages/web/src/content/docs/config.mdx`
- `dev/packages/opencode/src/skill/prompt/customize-opencode.md`

## Recommended Launcher Pattern

Use the repo-tracked wrapper
[`scripts/swarm_opencode_run_unattended.sh`](../../scripts/swarm_opencode_run_unattended.sh)
in place of bare `opencode`. It injects a permissive policy via
`OPENCODE_CONFIG_CONTENT` only when the caller has not already set a
policy of their own, then `exec`s `opencode` with every argument passed
through:

```bash
# In ~/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh:
RAG_REPO=/path/to/rag
WRAPPER="$RAG_REPO/scripts/swarm_opencode_run_unattended.sh"

OPENCODE_AGENT=pr-worker \
OPENCODE_MODEL=opencode-go/kimi-k2.6 \
  bash "$WRAPPER" run "Implement issue #1234 ..."
```

`OPENCODE_PERMISSION` should be **removed** from any launcher that still
exports it; the variable does nothing.

### Per-worker overrides

If a worker should run with a stricter policy than `"allow"`, set
`OPENCODE_CONFIG_CONTENT` (or `OPENCODE_CONFIG`) before invoking the
wrapper. The wrapper detects an existing value and leaves it untouched:

```bash
OPENCODE_CONFIG_CONTENT='{"permission":{"bash":"ask","edit":"allow","*":"deny"}}' \
  bash "$WRAPPER" run "Read-only audit ..."
```

## Verification Checklist

When updating a launcher:

- [ ] Remove every reference to `OPENCODE_PERMISSION` (no real var).
- [ ] Set `OPENCODE_CONFIG_CONTENT` *or* delegate to
      `swarm_opencode_run_unattended.sh`.
- [ ] In an isolated test worktree, run a small worker prompt and
      observe that no permission prompt appears in the tmux pane.
- [ ] Confirm `.signals/launch-W-name.json` records the chosen
      permission mode (e.g. `"permission_mode": "allow"` or
      `"opencode_config_content_set": true`).
- [ ] Update the swarm skill docs (in `~/.codex/skills/`) to point at
      this runbook.

## Tests

The wrapper contract is pinned by
[`tests/unit/scripts/test_swarm_opencode_run_unattended.py`](../../tests/unit/scripts/test_swarm_opencode_run_unattended.py)
(9 tests). Run from the repo root:

```bash
uv run pytest tests/unit/scripts/test_swarm_opencode_run_unattended.py -q
```
