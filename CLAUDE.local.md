***REMOVED*** Local Settings (gitignored)

***REMOVED******REMOVED*** Long-Running Commands (> 30 sec)

**Use tmux + logs** for docker build, large tests, deployments.

***REMOVED******REMOVED******REMOVED*** Pattern

```bash
***REMOVED*** 1. Create window and run command with logging
tmux new-window -n "W-{NAME}" -c /repo
tmux send-keys -t "W-{NAME}" "{command} 2>&1 | tee logs/{name}.log; echo '[COMPLETE]'" Enter

***REMOVED*** 2. Read logs when needed
tail -50 logs/{name}.log
grep -q '\[COMPLETE\]' logs/{name}.log && echo "Done"
```

***REMOVED******REMOVED******REMOVED*** Example: Docker Build

```bash
mkdir -p logs
tmux new-window -n "W-BUILD" -c /repo
tmux send-keys -t "W-BUILD" "docker compose -f docker-compose.dev.yml --profile ingest build --no-cache ingestion 2>&1 | tee logs/docker-build.log; echo '[COMPLETE]'" Enter
```

Check progress: `tail -f logs/docker-build.log`
Check done: `grep '\[COMPLETE\]' logs/docker-build.log`

***REMOVED******REMOVED******REMOVED*** Benefits

- User sees output in real-time (switch to tmux window)
- Claude reads logs when needed
- `[COMPLETE]` marker for automation
- No blocking, no timeouts

**Never run directly:** docker build, npm install, pytest (full suite), deployments.

***REMOVED******REMOVED*** tmux for Parallel Claude Workers

For 3+ independent tasks, use `/tmux-swarm-orchestration` skill:
- Spawns Claude workers in tmux windows
- Each worker has own worktree
- Auto-monitor closes on [COMPLETE]

***REMOVED******REMOVED*** Preferences

- Russian for comments in plans
- Short answers, no fluff
- Tables over paragraphs
