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

## Execution Model

The swarm pipeline uses **tmux** as its coordination layer (enforced by
`scripts/validate_worker_prompt.py` and contract tests):

- Workers are launched via `scripts/launch_kiro_worker.sh`
- Wake-up signals use `tmux send-keys -t "$ORCH_TARGET" -l ... C-m`
- `ORCH_TARGET` is a stable window-id target (`session:@id`) set by
  `set_orchestrator_window.sh`. The window is named once per session; wake-up
  routes by the immutable window-id, so a later rename never misdelivers `[DONE]`.

The skills in this directory are **worker-side** adaptations: they define what
a worker does _inside_ a tmux session. Orchestrator skills (`swarm-orchestrator`,
`swarm-launch`, `swarm-plan`, etc.) live in `~/.kiro/skills/` and manage the
tmux coordination layer.

The "subagent" tool (Kiro native) is an alternative model for purely in-process
parallelism (`dispatching-parallel-agents`, `subagent-driven-development`). It
does not replace tmux for the full swarm pipeline — migrating to it would
require retiring `validate_worker_prompt.py`'s tmux enforcement and the
`launch_kiro_worker.sh` launcher. That migration is tracked as an architecture
decision (card_4fe2c6504aca, card_9284e850fec6).

## Sources

Adapted from:
- `~/.kiro/skills/swarm-*/` (Kiro swarm skills)
- `~/.kiro/skills/` (dispatching + subagent-driven)
