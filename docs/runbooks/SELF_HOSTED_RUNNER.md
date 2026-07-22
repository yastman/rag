# Self-Hosted GitHub Actions Runner

Operational runbook for the self-hosted runner that powers
`.github/workflows/nightly-heavy.yml` (heavy-tier tests). PR fast-gate
and contract-test jobs in `.github/workflows/trusted-heavy.yml` run
on GitHub-hosted `ubuntu-latest` runners.

---

## What this is

A GitHub Actions self-hosted runner instance is registered for this repo,
carrying the `nightly-heavy` label group:

| Label group | Labels | Used by |
|---|---|---|
| `nightly-heavy` | `self-hosted, Linux, X64, nightly-heavy` | `nightly-heavy.yml` (heavy-tier job) |

This runner runs the full test suite including `requires_extras`, `load`,
`chaos`, `e2e`, and `benchmark` markers — tests that need BGE-M3 and ColBERT
models loaded locally. PR fast-gate and contract-test jobs no longer depend
on self-hosted runners; they run on GitHub-hosted `ubuntu-latest`.

---

## Resource requirements

The `nightly-heavy` workflow uses `pytest -n auto` and loads BGE-M3 + ColBERT
models, so the runner needs more RAM and disk than typical GitHub-hosted runners.

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

The `nightly-heavy` runner requires a single registration. Use the GitHub web UI
or `gh` CLI:

1. Go to **Settings → Actions → Runners → New self-hosted runner** in the repo.
2. Select **Linux / x64**.
3. Follow the download and configure steps GitHub shows.
4. When prompted for labels, enter: `nightly-heavy`
   (The `self-hosted`, `Linux`, `X64` labels are added automatically.)

The runner lives in its own directory (e.g. `~/actions-runner-nightly-heavy/`).

---

## WSL autostart

The runner must survive host or WSL restarts. An autostart script exists at
`~/bin/start-github-runner-rag.sh`. Example content:

```bash
#!/usr/bin/env bash
# ~/bin/start-github-runner-rag.sh
# Starts the nightly-heavy runner in the background.
nohup ~/actions-runner-nightly-heavy/run.sh &
```

Wire it into your WSL profile (`.bashrc`, `.profile`, or `/etc/wsl.conf`
`[boot] command`) so it runs on session start.

---

## Verifying runner health

Use the diagnostic script:

```bash
scripts/check_self_hosted_runner.sh               # check nightly-heavy label group
```

The script calls the GitHub Actions runners API via `gh` and prints runner
status, labels, and busy state. Exit codes:

- `0` — the required label group has at least one online runner.
- `1` — runner is missing, offline, or the label group is absent.
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

## Temporary disable (maintenance)

To mute `nightly-heavy.yml` while the runner is down:

1. **Disable the workflow** in the GitHub UI: **Settings → Actions → Workflows
   → Nightly Heavy Tests → Disable workflow**. Re-enable when the runner is
   back.
2. Alternatively, `workflow_dispatch` can be left as the only trigger — remove
   the `schedule:` entry temporarily to stop automatic runs.

---

## See also

- `scripts/check_self_hosted_runner.sh` — diagnostic script
- `.github/workflows/nightly-heavy.yml` — heavy-tier workflow that depends on this runner
- `.github/workflows/trusted-heavy.yml` — PR fast-gate workflow (uses GitHub-hosted runners)
