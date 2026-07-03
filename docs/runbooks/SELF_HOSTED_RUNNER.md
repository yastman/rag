# Self-Hosted GitHub Actions Runner

Operational runbook for the self-hosted runners that power
`.github/workflows/nightly-heavy.yml` (heavy-tier tests) and
`.github/workflows/trusted-heavy.yml` (PR fast-gate and heavy contract tests).

---

## What this is

Two GitHub Actions self-hosted runner instances are registered for this repo,
each carrying a distinct label group:

| Label group | Labels | Used by |
|---|---|---|
| `pr-fast` | `self-hosted, Linux, X64, pr-fast` | `trusted-heavy.yml` (fast-tests, heavy-contract-tests jobs) |
| `nightly-heavy` | `self-hosted, Linux, X64, nightly-heavy` | `nightly-heavy.yml` (heavy-tier job) |

The `pr-fast` runner gates pull-request CI. The `nightly-heavy` runner runs
the full test suite including `requires_extras`, `load`, `chaos`, `e2e`, and
`benchmark` markers — tests that need BGE-M3 and ColBERT models loaded locally.

---

## Resource requirements

Both workflows use `pytest -n auto`. The `nightly-heavy` job additionally loads
BGE-M3 + ColBERT models, so it needs more RAM and disk.

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

Each label group requires a separate runner registration. Use the GitHub web UI
or `gh` CLI:

1. Go to **Settings → Actions → Runners → New self-hosted runner** in the repo.
2. Select **Linux / x64**.
3. Follow the download and configure steps GitHub shows.
4. When prompted for labels, enter the appropriate group:
   - `pr-fast` runner: `pr-fast`
   - `nightly-heavy` runner: `nightly-heavy`
   (The `self-hosted`, `Linux`, `X64` labels are added automatically.)

Each runner lives in its own directory (e.g. `~/actions-runner-pr-fast/` and
`~/actions-runner-nightly-heavy/`).

---

## WSL autostart

The runners must survive host or WSL restarts. An autostart script already
exists at `~/bin/start-github-runner-rag.sh`. Update it to start **both runner
dirs** when both are registered:

```bash
#!/usr/bin/env bash
# ~/bin/start-github-runner-rag.sh
# Starts both runners in the background.
nohup ~/actions-runner-pr-fast/run.sh &
nohup ~/actions-runner-nightly-heavy/run.sh &
```

Wire it into your WSL profile (`.bashrc`, `.profile`, or `/etc/wsl.conf`
`[boot] command`) so it runs on session start.

---

## Verifying runner health

Use the diagnostic script:

```bash
scripts/check_self_hosted_runner.sh               # check both label groups
scripts/check_self_hosted_runner.sh --pr-only     # check only pr-fast
```

The script calls the GitHub Actions runners API via `gh` and prints runner
status, labels, and busy state. Exit codes:

- `0` — all required label groups have at least one online runner.
- `1` — a runner is missing, offline, or a label group is absent.
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
- `.github/workflows/nightly-heavy.yml` — heavy-tier workflow that depends on this runner
- `.github/workflows/trusted-heavy.yml` — PR fast-gate workflow (`pr-fast` label)
