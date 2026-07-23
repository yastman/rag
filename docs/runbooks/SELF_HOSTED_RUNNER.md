# Self-Hosted GitHub Actions Runner

Operational runbook for the self-hosted runner that powers
`.github/workflows/nightly-heavy.yml` (heavy-tier tests).

---

## What this is

One self-hosted runner is registered with the label group
`self-hosted, Linux, X64, nightly-heavy`. It runs the scheduled heavy-tier
suite: `requires_extras`, `load`, `chaos`, `e2e`, and `benchmark` markers.
Pull-request jobs remain on GitHub-hosted runners.

---

## Resource requirements

The `nightly-heavy` job uses `pytest -n auto` and loads BGE-M3 + ColBERT
models, so it needs more RAM and disk.

| Resource | Minimum |
|---|---|
| CPU | 4 vCPU |
| RAM | 8 GiB |
| Disk | 20 GiB free (uv cache + model weights + pytest artifacts) |
| Network | Outbound HTTPS to GitHub, PyPI, HuggingFace |
| Tools | `docker` (for Compose-backed e2e), Python 3.12 via `uv`, `git`, `jq` |
| Runner version | Actions Runner v2.329.0+ (Node 24 runtime required by actions/checkout@v6 and setup-uv@v8) |

---

## Registration

Register one runner:

1. Go to **Settings → Actions → Runners → New self-hosted runner** in the repo.
2. Select **Linux / x64**.
3. Follow the download and configure steps GitHub shows.
4. When prompted for labels, enter `nightly-heavy`.
   (The `self-hosted`, `Linux`, `X64` labels are added automatically.)

Keep it in its own directory, for example `~/actions-runner-nightly-heavy/`.

---

## WSL autostart

The runner must survive host or WSL restarts. Put this in
`~/bin/start-github-runner-rag.sh`:

```bash
#!/usr/bin/env bash
nohup ~/actions-runner-nightly-heavy/run.sh &
```

Wire it into your WSL profile (`.bashrc`, `.profile`, or `/etc/wsl.conf`
`[boot] command`) so it runs on session start.

---

## Verifying runner health

Use the diagnostic script:

```bash
scripts/check_self_hosted_runner.sh
```

The script calls the GitHub Actions runners API via `gh` and prints runner
status, labels, and busy state. Exit codes:

- `0` — the required label group has at least one online runner.
- `1` — the runner is missing, offline, or the label group is absent.
- `2` — bad arguments or missing prerequisites (`gh`, `jq`).

Prerequisites: `gh` authenticated with `repo` + `actions:read` scopes, `jq`.

---

## Troubleshooting

**Job queues forever (never starts):** No online runner with the required
labels. Run `scripts/check_self_hosted_runner.sh` to see what is registered.
Possible causes: runner process exited, WSL was restarted without the autostart
script running, runner deregistered itself after downtime.

**Runner shows offline in GitHub UI:** The `run.sh` process is not running.
SSH into the host and start it, or trigger `start-github-runner-rag.sh`.

**Node 24 / runtime error on first step:** Runner version is below v2.329.0.
Update the runner: stop it, download the latest archive from
`https://github.com/actions/runner/releases`, extract over the runner dir,
and restart.

**Label mismatch:** The workflow `runs-on` list must match the runner's labels
exactly. If you re-register a runner, verify labels with
`scripts/check_self_hosted_runner.sh`.

---

## Temporary disable (maintenance)

To mute `nightly-heavy.yml` while the runner is down:

1. **Disable the workflow** in the GitHub UI: **Settings → Actions → Workflows
   → Nightly Heavy Tests → Disable workflow**. Re-enable when the runner is
   back.
2. Alternatively, `workflow_dispatch` can be left as the only trigger — remove
   the `schedule:` entry temporarily to stop automatic runs.
3. **Comment out** the `runs-on: [self-hosted, …]` line in the workflow and
   replace it with `runs-on: ubuntu-latest` if the job must run on hosted
   runners during the outage.

---

## See also

- `scripts/check_self_hosted_runner.sh` — diagnostic script
- `.github/workflows/nightly-heavy.yml` — the only workflow that depends on this runner
