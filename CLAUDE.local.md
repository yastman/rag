# Local Settings (gitignored)

## Long-Running Commands (> 30 sec)

**Use tmux + logs** for docker build, large tests, deployments.

### Pattern

```bash
# 1. Create window and run command with logging
tmux new-window -n "W-{NAME}" -c /repo
tmux send-keys -t "W-{NAME}" "{command} 2>&1 | tee logs/{name}.log; echo '[COMPLETE]'" Enter

# 2. Read logs when needed
tail -50 logs/{name}.log
grep -q '\[COMPLETE\]' logs/{name}.log && echo "Done"
```

### Example: Docker Build

```bash
mkdir -p logs
tmux new-window -n "W-BUILD" -c /repo
tmux send-keys -t "W-BUILD" "docker compose -f docker-compose.dev.yml --profile ingest build --no-cache ingestion 2>&1 | tee logs/docker-build.log; echo '[COMPLETE]'" Enter
```

Check progress: `tail -f logs/docker-build.log`
Check done: `grep '\[COMPLETE\]' logs/docker-build.log`

### Benefits

- User sees output in real-time (switch to tmux window)
- Claude reads logs when needed
- `[COMPLETE]` marker for automation
- No blocking, no timeouts

**Never run directly:** docker build, npm install, pytest (full suite), deployments.

## Parallel Agent Work

**Agent Teams (`/agent-teams`):** For 2+ agents working on different PRs/branches:
- Each agent MUST use its own git worktree (see `.claude/rules/git-workflow.md`)
- Without worktrees, agents switch branches under each other → lost edits, false test failures

**tmux Swarm (`/tmux-swarm-orchestration`):** For 3+ independent tasks:
- Spawns Claude workers in tmux windows
- Each worker has own worktree
- Auto-monitor closes on [COMPLETE]

## Preferences

- Russian for comments in plans
- Short answers, no fluff
- Tables over paragraphs
