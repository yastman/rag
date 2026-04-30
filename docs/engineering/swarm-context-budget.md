# Swarm Context Budget Improvements

## Problem

The tmux/OpenCode swarm flow can waste large amounts of orchestrator context on diagnostic output that is not authoritative. In the #1090 session, the biggest avoidable costs came from reading OpenCode TUI logs and process arguments that included the full worker prompt.

## Principle

After a worker creates a PR or writes a valid DONE JSON, the orchestrator should review artifacts, not transcripts.

Authoritative evidence:
- worker `SIGNAL_FILE` JSON
- PR metadata and PR file list
- `git diff --name-only` / `git diff --stat`
- focused verification commands run fresh by the orchestrator when needed
- GitHub CI checks only when they are available and relevant; local verification is the gate in local-first workflows

Diagnostic-only evidence:
- OpenCode TUI logs
- pane output
- long process command lines
- model reasoning text

## Proposed Rules

1. Do not read worker TUI logs after valid DONE JSON.
   Logs are allowed only when JSON is missing, invalid, contradictory, or the worker is stalled.

2. Cap any diagnostic log read.
   Use a sanitized tail, for example 80 lines maximum and 180 characters per line. Never read raw full TUI logs.

3. Never inspect OpenCode process `args`.
   Use process views without command arguments:
   `ps -o pid,ppid,etime,stat,pcpu,comm -p <pid>`.

4. Make PR scope check a hard gate.
   Compare `gh pr view --json files` against reserved files. Extra files fail review, even if tests passed.

5. Validate against the real PR base.
   Use `origin/<base>` or PR metadata, not only local `dev`, because local branches may be ahead or dirty.

6. Prefer structured progress over logs.
   Workers should write small JSON artifacts such as:
   - `.signals/worker.json`
   - `.signals/progress.json`
   - `.signals/commands.jsonl`
   - `.signals/diff-files.txt`
   - `.signals/pr-files.txt`

7. Keep GitHub issue reads narrow.
   Use `--jq` and label names only. Read one issue body at a time after choosing a candidate.

8. Keep SDK registry reads section-scoped.
   For a matched SDK, read only that SDK section plus nearby project usage notes.

9. Review diffs in stages.
   First read file list and stat. Read full diffs only for bounded changed files that need semantic review.

10. Prefer prompt files over prompt-in-argv launch modes.
    The launcher should avoid putting the full prompt in process arguments whenever OpenCode supports it.

11. For visible TUI workers, pass only a short file handoff prompt.
    If the TUI supports only `--prompt <string>`, keep that string tiny:
    `Read and execute /path/to/worker-prompt.md. Write DONE JSON when finished.`
    The full task lives in the prompt file, not in process arguments or pane paste history.

## Suggested DONE JSON Requirements

For code workers that create PRs, DONE JSON should include:

```json
{
  "status": "done",
  "worker": "W-NAME",
  "issue": 1090,
  "branch": "fix/example",
  "pr": "https://github.com/org/repo/pull/123",
  "base": "dev",
  "changed_files": [],
  "pr_files": [],
  "commands": [
    {"cmd": "uv run pytest ...", "exit": 0, "summary": "focused tests ok"},
    {"cmd": "make check", "exit": 0, "summary": "ruff+mypy ok"}
  ],
  "ci": [
    {"name": "Lint & Type Check", "status": "COMPLETED", "conclusion": "SUCCESS"}
  ],
  "summary": "short summary",
  "next_action": "review",
  "ts": "ISO-8601"
}
```

## Orchestrator Review Order

1. Read DONE JSON.
2. Confirm PR exists and targets expected base.
3. Compare PR files with reserved files.
4. Compare local diff files with PR files.
5. Run focused checks if needed.
6. Check CI only when available and relevant; do not block on broken or lint-only CI in local-first workflows.
7. Read worker logs only if one of the previous steps is missing or contradictory.

## Prompt File Handoff

The worker prompt should be materialized as a real file before launch. The worker window should receive only a short pointer to that file.

Preferred headless mode:

```bash
opencode run \
  --dir "$WT_PATH" \
  --file "$PROMPT_FILE" \
  --title "W-1090-final" \
  "Execute the attached worker prompt completely. Do not stop until DONE JSON is written."
```

Preferred visible TUI mode when there is no `--prompt-file` flag:

```bash
opencode "$WT_PATH" \
  --prompt "Read and execute $PROMPT_FILE. Write DONE JSON when finished."
```

Why this helps:
- `ps` no longer exposes the full prompt.
- Tmux logs contain only a short file reference.
- The prompt can be reviewed, versioned, copied into a worktree, or attached to DONE JSON evidence.
- Restarting a worker uses the same immutable prompt file instead of reconstructing a long inline prompt.

Prompt file rules:
- Store the prompt inside the worker worktree when possible, for example `.codex/prompts/worker-name.md`.
- If the prompt lives in the main checkout, copy it into the worktree before launch.
- Include a checksum in launch logs if reproducibility matters:
  `sha256sum "$PROMPT_FILE"`.
- The short launcher prompt should never contain implementation details, code snippets, or large context blocks.

## OpenCode Role Policy

- Implementation workers use `pr-worker` on `opencode-go/kimi-k2.6`.
- PR review-fix workers use `pr-review-fix` on `opencode-go/deepseek-v4-pro`.
- Model selection belongs in launcher flags or OpenCode agent config, not natural-language prompt text.
- DONE JSON records `agent`, `model`, `review_decision`, and `autofix_commits`.
- Merge remains orchestrator-owned after scope gate, local verification, and review gate. CI is an optional signal when it is available and meaningful.

## Rule To Add To Swarm Skill

Worker logs are diagnostic-only. After DONE JSON or PR creation, the orchestrator must not read TUI logs. The review source of truth is SIGNAL JSON, PR metadata/files, git diff, fresh verification commands, and CI only when available and relevant. Logs may be read only after missing or invalid JSON, contradictory artifacts, or a stalled worker, capped to 80 sanitized lines.
