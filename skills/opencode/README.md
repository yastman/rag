# OpenCode Skills

Skills for AI-assisted development workflow. Used by OpenCode, Codex Web, and other AI coding agents.

## Skills

### PR Review & Workflow
- `gh-pr-review.md` — Solo dev PR review workflow: analyze → auto-fix → test → validate → merge

### Development Process (from obra/superpowers)
- `brainstorming/` — Required before any creative work
- `test-driven-development/` — TDD cycle
- `systematic-debugging/` — Systematic bug debugging
- `writing-plans/` — Writing implementation plans
- `executing-plans/` — Executing plans with checkpoints
- `verification-before-completion/` — Verify before claiming done

### Git & Collaboration
- `using-git-worktrees/` — Isolated git worktrees
- `finishing-a-development-branch/` — Branch completion: merge/PR/cleanup
- `requesting-code-review/` — Request code review
- `receiving-code-review/` — Handle code review feedback

### Agent Coordination
- `using-superpowers/` — How to use skills (base skill)
- `dispatching-parallel-agents/` — Parallel independent tasks
- `subagent-driven-development/` — Execute plans with subagents
- `writing-skills/` — Create new skills

## Usage

Skills are auto-discovered by OpenCode from `~/.config/opencode/skills/`.

To use a skill locally:
```bash
# Copy to OpenCode skills directory
cp -r skills/opencode/* ~/.config/opencode/skills/
```

## Sources

- Superpowers: https://github.com/obra/superpowers
- gh-pr-review: custom for rag-fresh project
