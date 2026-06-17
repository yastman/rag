# .kiro/skills/

Kiro CLI skills for this project. Skills are auto-discovered by `kiro_default` agent and activated when your request matches the skill description. Custom agents need explicit `skill://.kiro/skills/**/SKILL.md` in `resources`.

Invoke directly with `/skill-name` slash command.

## Skills

### Agent Orchestration

| Skill | When to use |
|---|---|
| `dispatching-parallel-agents` | 2+ independent tasks with no shared state — dispatch one subagent per domain |
| `subagent-driven-development` | Execute an implementation plan task-by-task with spec + quality review after each |

### Swarm Worker Skills (subagent workers)

These are used **inside** subagent workers, not by the orchestrator directly.

| Skill | When to use |
|---|---|
| `swarm-worker-contract` | Before finishing any worker task — defines finish report schema and safety gates |
| `swarm-pr-finish` | Finishing assigned implementation work — pre-finish checks + Markdown report |
| `swarm-secretary-intake` | Bounded issue/PR/artifact intake as a research worker |
| `swarm-review-fix` | PR review (read-only) or fixing named PR blockers on the same branch |
| `swarm-bug-reporting` | Report confirmed bugs as compact Markdown findings |
| `swarm-sdk-baseline` | Read-only preflight before implementation when SDK/API/runtime uncertainty exists |

## Key Differences from Upstream Skills

These skills are adapted for Kiro CLI:

- **No tmux** — completion signals are output as final message text, not `tmux send-keys`
- **No `launch_kiro_worker.sh`** — use Kiro's `subagent` tool instead
- **No `ORCH_TARGET`/`SWARM_CONTRACT`** — orchestration via `subagent` tool stages
- **Same report formats** — Markdown-first, same field schemas as the originals

## Sources

Adapted from:
- `~/.kiro/skills/swarm-*/` (Kiro swarm skills)
- `~/.kiro/skills/swarm-*/` (Kiro swarm skills, more complete)
- `~/.kiro/skills/` (dispatching + subagent-driven)
