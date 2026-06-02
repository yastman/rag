# Runbook: Self-Hosted GitHub Actions Runner Policy

> **Owner:** CI / Release Engineering
> **Closes:** #1531
> **Last verified:** 2026-06-01
> **Verification command:**
> ```bash
> scripts/check_self_hosted_runner.sh
> ```

Use this runbook when PR fast-gate or nightly heavy-tier test jobs fail to start,
queue forever, or the operator needs to bring new self-hosted runners online.

## Self-Hosted Runner Policy

The repo follows a two-tier runner policy to balance security and capability:

| Tier | Runner | Scope | Examples |
|------|--------|-------|----------|
| **Light (trusted)** | `ubuntu-latest` (GitHub-hosted) | Required PR checks, lint, format | CI.yml |
| **Heavy (trusted)** | `self-hosted`, `Linux`, `X64` (WSL/Linux host) | Trusted PR fast gate, shadow contract checks, nightly, runtime, benchmarks | `trusted-heavy.yml`, `nightly-heavy.yml` |

The heavy tier uses two **custom label groups** on self-hosted runners:

| Label group | Required labels | Workflow | Purpose |
|-------------|----------------|----------|---------|
| **`pr-fast`** | `self-hosted`, `Linux`, `X64`, `pr-fast` | `trusted-heavy.yml` | PR fast-gate (`fast-tests`) and shadow contract checks (`heavy-contract-tests-shadow`) |
| **`nightly-heavy`** | `self-hosted`, `Linux`, `X64`, `nightly-heavy` | `nightly-heavy.yml` | Scheduled heavy-tier test suite (`requires_extras`, `load`, `chaos`, `e2e`, `benchmark`) |

GitHub remains the authority for runner registration and label assignment; the
WSL runner host provides compute only.

### Policy Rules

1. **GitHub-hosted for light PR checks.** All jobs in public CI workflows
   (`.github/workflows/ci.yml`) must use `runs-on: ubuntu-latest`. This
   prevents fork-based PRs from running untrusted code on self-hosted
   infrastructure.

2. **Self-hosted only for trusted heavy/runtime/nightly checks.**
   Self-hosted runners (`trusted-heavy.yml`, `nightly-heavy.yml`) are reserved
   for jobs that require large resources, real model loading
   (`requires_extras`, `e2e`, `benchmark`), or extended timeouts. Pull-request
   jobs must be restricted to same-repository branches; fork PRs must never run
   on the self-hosted runner.

3. **`permissions: contents: read` by default.** Every workflow must
   explicitly declare `permissions: contents: read` as the initial permission
   set. This is a defense-in-depth measure for the public repository -- even
   though it is the GitHub Actions default, making it explicit prevents
   silent escalation if org/repo defaults change later.

4. **No secrets for untrusted PR jobs.** Workflows triggered by
   `pull_request` events from forks cannot access repository secrets.
   Light-tier workflows (CI.yml) must never reference `secrets.*` --
   they must remain runnable without maintainer approval on every fork PR.

5. **Workspace and cache cleanup expectations.** Self-hosted runners are
   long-lived and accumulate disk pressure from `uv` caches, Docker layers,
   pytest artifacts, and model weights. Operators must:
   - Run `scripts/docker-cleanup.sh` weekly or when disk usage exceeds 70 %.
   - Configure a tmpfs or ephemeral cache mount for the runner's workspace
     (`_work/`) so PR checkout artifacts are cleaned automatically.
   - Monitor runner disk with `df -h` via the runner host's systemd timers.

## Symptoms

- The `Nightly Heavy Tests` workflow run sits in **Queued** state past its
  02:30 UTC schedule and never picks up a runner.
- A manual `workflow_dispatch` of `nightly-heavy.yml` never starts.
- `scripts/check_self_hosted_runner.sh` exits non-zero.
- GitHub Settings -> Actions -> Runners shows zero runners or all runners
  with status `Offline`.

## What Depends on the Self-Hosted Runner

| Workflow file | Job | `runs-on` | What it runs |
|---|---|---|---|
| [`.github/workflows/trusted-heavy.yml`](../../.github/workflows/trusted-heavy.yml) | `changes` | `ubuntu-latest` | Always reports a lightweight path-filter result so trusted-heavy checks can be required without disappearing on docs-only PRs |
| [`.github/workflows/trusted-heavy.yml`](../../.github/workflows/trusted-heavy.yml) | `fast-tests` | `[self-hosted, Linux, X64, pr-fast]` | `make test` for trusted same-repo PRs that touch code/runtime/test paths |
| [`.github/workflows/trusted-heavy.yml`](../../.github/workflows/trusted-heavy.yml) | `heavy-contract-tests-shadow` | `[self-hosted, Linux, X64, pr-fast]` | `make test-contract` in shadow mode for trusted same-repo PRs that touch code/runtime/test paths |
| [`.github/workflows/nightly-heavy.yml`](../../.github/workflows/nightly-heavy.yml) | `heavy-tier` | `[self-hosted, Linux, X64, nightly-heavy]` | `pytest -n auto -m "requires_extras or load or chaos or e2e or benchmark"` |

These jobs now use custom label groups so the diagnostic script (and operators)
can verify each group independently:

- **PR-label group** (`pr-fast`): required for trusted PR fast-gate jobs. Use
  `scripts/check_self_hosted_runner.sh --pr-only` to verify just this group.
- **Nightly label group** (`nightly-heavy`): required for the scheduled
  nightly heavy-tier suite. Use the default mode (no flags) to verify both
  groups.

## Resource Requirements

The `heavy-tier` job runs the full union of these pytest markers:
`requires_extras`, `load`, `chaos`, `e2e`, `benchmark`. Sizing is anchored
to what those suites actually load.

| Resource | Minimum | Recommended | Why |
|---|---|---|---|
| vCPU | 2 | **4+** | Workflow uses `pytest -n auto --dist=loadscope` |
| RAM | 4 GiB | **8 GiB+** | `e2e` and `benchmark` load BGE-M3 + ColBERT models |
| Disk | 10 GiB free | **20 GiB+ free** | `uv` cache, model weights, pytest artifacts, Docker layers |
| Network | Outbound HTTPS | Same | GitHub, PyPI, HuggingFace |
| Tools | `git`, Python 3.12 (installed via `uv`), `docker`, `jq` | Same | `e2e` markers spin up Compose stacks; `uv sync --frozen --extra all` is heavy |
| Service | Runner installed as a systemd unit (`actions.runner.*.service`) | Same | Survives host reboots without operator intervention |

These numbers come directly from the workflow source -- see the `Run heavy
tier suites` step in [`nightly-heavy.yml`](../../.github/workflows/nightly-heavy.yml).

## Fast-Path Diagnosis

Run from any checkout with `gh` authenticated against the repo:

```bash
# Default: verify both pr-fast AND nightly-heavy label groups are online
scripts/check_self_hosted_runner.sh

# PR-only: verify only the pr-fast label group (skip nightly-heavy)
scripts/check_self_hosted_runner.sh --pr-only
```

The script:
- Calls `gh api repos/$OWNER/$REPO/actions/runners` and prints
  `{name, status, os, labels, busy}` per runner.
- In default mode, requires at least one online runner with labels
  `self-hosted, Linux, X64, pr-fast` AND at least one online runner with
  labels `self-hosted, Linux, X64, nightly-heavy`.
- In `--pr-only` mode, requires only the `pr-fast` label group.
- Exits non-zero if a required label group is missing or every runner in that
  group is offline.
- Prints a checklist of resource requirements at the end.

Direct API equivalent (read-only):

```bash
gh api repos/$OWNER/$REPO/actions/runners \
  --jq '.runners[] | {name,status,os,labels:[.labels[].name],busy}'
```

If the script exits non-zero, follow **Common Failure Modes** below.

## How to Register a New Runner

GitHub publishes the canonical, token-bearing instructions at
**Settings -> Actions -> Runners -> New self-hosted runner** for the
repository. Follow that flow exactly; the registration token shown there
is short-lived and must not be committed.

For this repository, the runner needs the following labels after registration:

- **PR runner** (`pr-fast`): `self-hosted, Linux, X64, pr-fast`
- **Nightly runner** (`nightly-heavy`): `self-hosted, Linux, X64, nightly-heavy`

GitHub automatically adds built-in labels such as `self-hosted`, OS, and
architecture. Add the custom labels (`pr-fast` or `nightly-heavy`) via
**Settings -> Actions -> Runners -> select runner -> Labels** in the GitHub
UI, or pass `--labels` during `config.sh`. The final configure command from
GitHub should look like this shape (add `--labels pr-fast` or
`--labels nightly-heavy` as appropriate):

```bash
./config.sh \
  --url https://github.com/yastman/rag \
  --token "$GITHUB_ACTIONS_RUNNER_TOKEN" \
  --name "rag-heavy-$(hostname)" \
  --labels "pr-fast" \
  --work _work
```

Do not store the registration token in `.env`, shell history, docs, issue
comments, or workflow files.

### Windows host: use WSL first

On a Windows workstation, install and run the GitHub Actions runner inside WSL
Ubuntu first. The repository's heavy commands use Linux-oriented tooling
(`make`, `uv`, Docker/Compose), so WSL gives the closest match to local
development and CI without a separate Windows workflow.

Native Windows runners are possible later, but they need a separate workflow
or shell/tooling contract for PowerShell, `make`, Docker Desktop paths, and
line endings.

Verify Docker Desktop is visible from WSL before starting the runner:

```bash
docker --version
docker compose version
docker ps
```

Start the WSL runner detached from the current terminal:

```bash
cd ~/actions-runner-rag
rm -f runner.log
setsid ./run.sh > runner.log 2>&1 < /dev/null &
tail -f runner.log
```

For automatic startup when a WSL login shell opens, use the existing
`~/bin/start-github-runner-rag.sh` script (called from `~/.zprofile`):

```bash
~/bin/start-github-runner-rag.sh
```

The startup script should be updated to handle both runner directories
when both runners (a `pr-fast` and a `nightly-heavy` runner) are registered:

- exit early if `~/actions-runner-rag/run.sh` is missing;
- exit if `Runner.Listener` is already running for that directory;
- wait briefly for `docker ps` to succeed;
- for each registered runner dir (e.g., `~/actions-runner-rag` and
  `~/actions-runner-rag-nightly`), start
  `setsid ./run.sh > runner.log 2>&1 < /dev/null &`.

If only one runner is registered, the script should start that one without
error. The script is idempotent -- running it when a Runner.Listener is
already running is a no-op for that directory.

Verify GitHub sees it:

```bash
gh api repos/yastman/rag/actions/runners \
  --jq '.runners[] | {name,status,os,labels:[.labels[].name],busy}'
```

Expected labels for this rollout:

- **PR fast-gate runner** (`pr-fast`):
  ```text
  self-hosted, Linux, X64, pr-fast
  ```
- **Nightly heavy-tier runner** (`nightly-heavy`):
  ```text
  self-hosted, Linux, X64, nightly-heavy
  ```

GitHub adds built-in labels (`self-hosted`, `Linux`, `X64`) automatically. The
custom labels `pr-fast` and `nightly-heavy` must be added during registration
via the GitHub UI (Settings -> Actions -> Runners -> select runner -> Labels)
or the `--labels` flag during `config.sh`.

### Local foreground start

Use foreground mode only for first-time smoke tests or debugging:

```bash
cd ~/actions-runner-rag
./run.sh
```

Keep that terminal open. The runner is online only while this process is
running. Stop it with `Ctrl-C` after the smoke test.

### Persistent systemd start

For normal operation on Linux, install the runner as a service from inside the
runner directory:

```bash
cd ~/actions-runner-rag
sudo ./svc.sh install "$USER"
sudo ./svc.sh start
sudo ./svc.sh status
```

After host reboot, the runner should come back automatically. If it does not:

```bash
sudo ./svc.sh status
sudo ./svc.sh start
```

The runner user must be able to run the tools used by heavy workflows:

```bash
git --version
uv --version
docker ps
```

If `docker ps` fails with a permission error, add the runner user to the
`docker` group and restart the runner service.

Reference docs (paraphrased; <=30 words each):

- [About self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners)
  -- Overview of when self-hosted runners are appropriate and security tradeoffs.
- [Adding self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners)
  -- Per-OS download/configure/install steps with a per-runner registration token.
- [Configuring the self-hosted runner application as a service](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service)
  -- Install the runner as a systemd/launchd service so it auto-restarts.

> Content was rephrased for compliance with licensing restrictions.

After registration, **always** verify with `scripts/check_self_hosted_runner.sh`.
Do not consider the runner "live" until that script exits 0.

## How to Verify the Runner

1. Run the diagnostic:
   ```bash
   scripts/check_self_hosted_runner.sh
   ```
   Expect: exit 0 with both `pr-fast` and `nightly-heavy` label groups online.

   For PR-gate triage only:
   ```bash
   scripts/check_self_hosted_runner.sh --pr-only
   ```
   Expect: exit 0 with the `pr-fast` label group online.

2. Trigger a manual workflow run as a smoke test (does not wait for the
   2:30 UTC schedule):
   ```bash
   gh workflow run nightly-heavy.yml
   gh run watch
   ```

3. Confirm the run is **In progress** within a minute. If it stays
   `Queued`, the runner is not picking up jobs -- see **Common Failure Modes**.

## Common Failure Modes

| Symptom | Likely cause | Recovery |
|---|---|---|
| Runner shows `Offline` in API/UI | Host rebooted; runner service not enabled | `sudo systemctl enable --now actions.runner.<org-repo>.<name>.service` on the host |
| Runner is `online` but PR `Fast Tests` stays `Queued` | Label drift: `trusted-heavy.yml` asks for `pr-fast`, but no online runner advertises it | Run `scripts/check_self_hosted_runner.sh --pr-only`; add `pr-fast` to the PR runner |
| Runner is `online` but nightly `heavy-tier` stays `Queued` | Label drift: `nightly-heavy.yml` asks for `nightly-heavy`, but no online runner advertises it | Run `scripts/check_self_hosted_runner.sh`; add `nightly-heavy` to the nightly runner |
| Workflow run fails with `No space left on device` | Disk full from accumulated `uv` cache, Docker images, pytest artifacts | Run `scripts/docker-cleanup.sh` on the runner host; consider a tmpfs/ephemeral cache mount |
| `e2e` tests fail to start Compose stack | Docker daemon down or unprivileged user not in `docker` group | `sudo systemctl status docker`; verify the runner's user can run `docker ps` |
| `gh api` call fails with 404 in the diagnostic script | Token lacks `actions:read` scope, or operator is not a repo admin | Re-auth `gh` with a scope-bearing token, or run the script as a maintainer |
| Heavy-tier job OOM-killed | Runner host below the recommended 8 GiB RAM | Resize host to >= 8 GiB RAM; consider lowering `pytest -n auto` to `-n 2` |

## How to Mute / Disable nightly-heavy.yml During Maintenance

If the runner must be down for maintenance, prefer one of the following so
the schedule does not pile up failed/queued runs:

1. **Disable the workflow** (preferred, reversible, surfaced in the UI):
   ```bash
   gh workflow disable nightly-heavy.yml
   # ... maintenance ...
   gh workflow enable nightly-heavy.yml
   ```

2. **Comment out the schedule** (if you want to keep `workflow_dispatch`
   alive but stop scheduled runs). Edit
   [`nightly-heavy.yml`](../../.github/workflows/nightly-heavy.yml) and
   remove the `schedule:` block in a short-lived PR.

3. **Cancel any queued runs** while the runner is offline:
   ```bash
   gh run list --workflow nightly-heavy.yml --status queued --json databaseId \
     | jq -r '.[].databaseId' \
     | xargs -I{} gh run cancel {}
   ```

Re-verify with `scripts/check_self_hosted_runner.sh` after maintenance and
re-enable the workflow only once the script exits 0.

## See Also

- [`scripts/check_self_hosted_runner.sh`](../../scripts/check_self_hosted_runner.sh) -- diagnostic this runbook is the operator-facing companion of.
- [`.github/workflows/trusted-heavy.yml`](../../.github/workflows/trusted-heavy.yml) -- trusted PR self-hosted fast gate and shadow contract workflow.
- [`.github/workflows/nightly-heavy.yml`](../../.github/workflows/nightly-heavy.yml) -- nightly heavy-tier self-hosted workflow.
- [`scripts/docker-cleanup.sh`](../../scripts/docker-cleanup.sh) -- disk pressure remediation on the runner host.
- [Runbooks index](README.md)
