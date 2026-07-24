# Solo-Local Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all pytest verification local and authoritative while reducing GitHub to reproducible static, security, dependency, and image-publishing checks.

**Architecture:** Remove every hosted pytest workflow and its self-hosted-runner scaffolding. Strengthen the local hook/candidate ladder, then make the remaining GitHub CI deterministic across all shipped projects and make image publishing scan the exact image before push.

**Tech Stack:** Git hooks via pre-commit, GNU Make local gates, uv/pytest, GitHub Actions, Gitleaks, Bandit, pip-audit/OSV, Docker Buildx, Trivy.

## Global Constraints

- GitHub runs zero pytest jobs.
- `test-core`, `test`, `test-contract`, and `test-full` run locally.
- No mandatory reviewer or PR-only workflow for the one-person repository.
- Existing user WIP in the canonical checkout remains untouched.
- No new Python runtime dependency; use locked tools or exact immutable pins.
- Actions remain pinned to full commit SHAs.

---

### Task 1: Remove hosted test infrastructure and stale contracts

**Files:**
- Delete: `.github/workflows/core-tests.yml`
- Delete: `.github/workflows/trusted-heavy.yml`
- Delete: `.github/workflows/nightly-heavy.yml`
- Delete: `tests/unit/test_trusted_heavy_workflow.py`
- Delete: `tests/contract/test_self_hosted_runner_workflow_contract.py`
- Delete: `tests/unit/test_ci_workflow_guardrails.py`
- Delete: `docs/runbooks/SELF_HOSTED_RUNNER.md`
- Delete: `scripts/check_self_hosted_runner.sh`
- Modify: `.github/actionlint.yaml`
- Modify: `tests/unit/test_ci_deploy_workflow.py`
- Modify: `tests/contract/test_makefile_lint_scope_contract.py`
- Modify: `scripts/ci/validate_pr_guardrails.py`
- Modify: `tests/unit/scripts/test_validate_pr_guardrails.py`
- Test: `tests/unit/test_ci_deploy_workflow.py`
- Test: `tests/contract/test_github_local_test_policy_contract.py`

**Interfaces:**
- Consumes: approved design requirement that GitHub runs no pytest.
- Produces: a static-only `.github/workflows/ci.yml` policy and absence contracts for hosted test workflows.

- [ ] **Step 1: Add the failing repository policy contract**

Create `tests/contract/test_github_local_test_policy_contract.py` to assert that `core-tests.yml`, `trusted-heavy.yml`, and `nightly-heavy.yml` are absent and that every remaining workflow contains neither `pytest` nor `make test`.

- [ ] **Step 2: Run the new contract and confirm red**

Run: `uv run --no-sync pytest tests/contract/test_github_local_test_policy_contract.py -q`
Expected: FAIL because all three workflows still exist.

- [ ] **Step 3: Delete hosted workflows and their single-purpose scaffolding**

Remove the listed workflows, self-hosted diagnostic script/runbook, self-hosted actionlint labels, and tests whose only contract is that deleted infrastructure exists.

- [ ] **Step 4: Repair retained CI policy tests and registry**

Keep static/security/release-isolation assertions in `test_ci_deploy_workflow.py`; remove nightly/core/self-hosted sections. Remove deleted policy-test paths from `validate_pr_guardrails.py` and its fixtures. Remove stale `mini_app` CI-scope assertion.

- [ ] **Step 5: Run focused policy tests**

Run: `uv run --no-sync pytest tests/contract/test_github_local_test_policy_contract.py tests/unit/test_ci_deploy_workflow.py tests/unit/scripts/test_validate_pr_guardrails.py tests/contract/test_makefile_lint_scope_contract.py -q`
Expected: PASS.

### Task 2: Make the local gate ladder authoritative and cross-platform

**Files:**
- Modify: `Makefile`
- Modify: `.pre-commit-config.yaml`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/LOCAL-DEVELOPMENT.md`
- Modify: `tests/README.md`
- Modify: `tests/unit/test_ci_deploy_workflow.py`
- Modify: `tests/unit/test_makefile_contract.py`
- Modify: `tests/contract/test_makefile_review_gate_no_autosync_contract.py`
- Test: `tests/contract/test_local_gate_policy_contract.py`

**Interfaces:**
- Consumes: existing `test-core`, `test`, `test-contract`, and `check-frozen` targets.
- Produces: automatic hook installation, a Windows-compatible pre-push core gate, and `candidate-check: check-frozen test test-contract`.

- [ ] **Step 1: Add failing local-gate contracts**

Assert: `mini_app/` is absent from `LINT_PATHS`; `dev-setup` installs hooks; `candidate-check` depends on `check-frozen test test-contract`; pre-commit defines a local pre-push core pytest hook using `uv run --no-sync`; docs name `candidate-check` as the delivery gate.

- [ ] **Step 2: Confirm focused red state**

Run: `uv run --no-sync pytest tests/contract/test_local_gate_policy_contract.py tests/unit/test_makefile_contract.py tests/unit/test_ci_deploy_workflow.py -q`
Expected: FAIL on stale lint path, missing hook wiring, and candidate dependencies.

- [ ] **Step 3: Implement the minimum local ladder**

Remove `mini_app/` from `LINT_PATHS`; add `setup-hooks` to `dev-setup`; set `candidate-check: check-frozen test test-contract`; keep `pre-push: lint format-check test-core` for POSIX users. Add a `language: system`, `pass_filenames: false`, `always_run: true`, `stages: [pre-push]` hook whose entry directly runs the same core pytest selectors through `uv run --no-sync`, avoiding a Windows dependency on `make`.

- [ ] **Step 4: Align developer documentation**

Document commit, push, scope-specific, candidate, and major-candidate levels. State that GitHub runs no pytest and that Linux portability/release verification is local through WSL/container execution.

- [ ] **Step 5: Run focused local policy tests**

Run the Step 2 command again.
Expected: PASS.

### Task 3: Close secret, static-analysis, and multi-lock gaps

**Files:**
- Modify: `.gitleaks.toml`
- Modify: `pyproject.toml`
- Modify: `.github/dependabot.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/cve_gate.py`
- Modify: `tests/unit/ci/test_cve_gate.py`
- Test: `tests/contract/test_security_gate_scope_contract.py`

**Interfaces:**
- Consumes: root, `telegram_bot`, and `services/bge-m3-api` pyprojects/lockfiles.
- Produces: exact-project lock/CVE matrix and broad-path-free Gitleaks/Bandit policies.

- [ ] **Step 1: Add failing security scope contracts**

Assert no whole-tree Gitleaks allowlists for `tests`, `scripts`, `docs`, or `.env.example`; Bandit does not exclude `scripts`; Dependabot has no `services/docling` and covers pip projects, GitHub Actions, and Dockerfiles; CI matrices contain all three Python projects; CI Ruff uses locked `uv run --frozen`.

- [ ] **Step 2: Extend CVE gate tests first**

Add a unit test proving `--project telegram_bot` produces an exact-version invocation of `uvx --from pip-audit==2.10.1 pip-audit ... telegram_bot`.

- [ ] **Step 3: Confirm red state**

Run: `uv run --no-sync pytest tests/unit/ci/test_cve_gate.py tests/contract/test_security_gate_scope_contract.py -q`
Expected: FAIL on missing project argument and stale scopes.

- [ ] **Step 4: Implement deterministic security gates**

Add `--project` to `cve_gate.py`, pin pip-audit, matrix the lock/CVE jobs over `.`, `telegram_bot`, and `services/bge-m3-api`, and use locked Ruff. Remove broad Gitleaks/Bandit exclusions; add only concrete fake-secret allowlist entries discovered by a full scan. Add Dependabot entries for GitHub Actions and the three Dockerfile directories.

- [ ] **Step 5: Run focused tests and real scanners**

Run: `uv run --no-sync pytest tests/unit/ci/test_cve_gate.py tests/contract/test_security_gate_scope_contract.py -q`

Run: `uv run --no-sync bandit -r src telegram_bot services scripts -c pyproject.toml`

Run: `uv run --no-sync pre-commit run gitleaks --all-files`

Expected: all commands exit 0 without whole-tree exclusions.

### Task 4: Make image inputs immutable and scan before publish

**Files:**
- Modify: `Dockerfile.ingestion`
- Modify: `.github/workflows/publish-internal-images.yml`
- Modify: `tests/unit/test_publish_internal_images_workflow.py`
- Modify: `tests/contract/test_docling_native_authority_contract.py`
- Test: `tests/contract/test_image_supply_chain_contract.py`

**Interfaces:**
- Consumes: locked `docling==2.110.0`, BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`, Trivy action commit `ed142fd0673e97e23eac54620cfb913e5ce36c25`.
- Produces: fail-fast model prewarm and build-load-scan-login-push publishing order.

- [ ] **Step 1: Add failing image supply-chain contracts**

Assert no `pip install docling-tools`, no ignored model-download failure, exact BGE revision, Trivy full SHA, `load: true` before scan, registry login after scan, and explicit push after scan.

- [ ] **Step 2: Confirm red state**

Run: `uv run --no-sync pytest tests/contract/test_image_supply_chain_contract.py tests/unit/test_publish_internal_images_workflow.py tests/contract/test_docling_native_authority_contract.py -q`
Expected: FAIL on mutable inputs and push-before-scan.

- [ ] **Step 3: Fix ingestion prewarm**

Invoke `.venv/bin/docling-tools models download layout tableformer code_formula picture_classifier rapidocr --output-dir /opt/docling/models` from the locked environment. Add the exact BGE commit to `snapshot_download(revision=...)`. Remove every `|| true`/warning fallback around required model downloads.

- [ ] **Step 4: Add scan-before-push workflow**

Build a deterministic local image with `push: false` and `load: true`; scan High/Critical OS/library vulnerabilities with the pinned Trivy action; only then log in, tag each metadata tag, and push. Preserve cache, labels, provenance, and SBOM semantics where compatible with the local exporter.

- [ ] **Step 5: Run focused image policy tests and actionlint**

Run the Step 2 pytest command again.

Run: `uv run --no-sync pre-commit run actionlint --all-files --hook-stage pre-push`

Expected: PASS.

### Task 5: Integration review and delivery

**Files:**
- Modify: `docs/superpowers/specs/2026-07-24-solo-local-quality-gates-design.md`
- Create: `docs/superpowers/plans/2026-07-24-solo-local-quality-gates.md`
- Verify: complete branch diff against `origin/dev`.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: one reviewed, tested candidate ready for `dev`.

- [ ] **Step 1: Run focused changed-policy tests**

Run all test files named in Tasks 1-4; require zero failures.

- [ ] **Step 2: Run repository gates**

Run `git diff --check`, `uv run --no-sync pre-commit run --all-files`, Ruff, MyPy, Bandit, `test-core`, `test`, `test-contract`, and the complete local `test-full` selection using direct uv commands on Windows or Make targets in WSL.

- [ ] **Step 3: Review complete diff**

Confirm no pytest remains under `.github/workflows`, all action uses are full-SHA pinned, no stale workflow/self-hosted references remain, and only planned files changed.

- [ ] **Step 4: Commit and integrate exact candidate**

Commit the reviewed branch, fetch `origin/dev`, merge fresh `origin/dev` without rebasing, repeat affected verification if it moved, then push the exact candidate to `origin/dev`.

- [ ] **Step 5: Prove delivery**

Fetch origin and verify candidate SHA is an ancestor of `origin/dev`; report final SHAs and gate outputs.
