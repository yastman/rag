# Issue #3248 Native Windows POSIX Make Test Boundary Specification

## Outcome

The native Windows test gate does not execute a repository Make target that is explicitly supported only on POSIX, while Linux/WSL retains the real dynamic cleanup proof.

## Evidence

Chocolatey GNU Make is present on Windows, so the current availability-only skip allows `test_force_cleanup_deletes_branch_merged_into_base_from_other_head` to execute. Make then uses `cmd.exe` and fails on `sed`, `[`, and `MAIN_BRANCH=...`. Repository documentation already declares these Make commands POSIX-only.

## Contract

- Add the established `sys.platform == "win32"` skip to the one dynamic Make execution test.
- Keep the existing make-unavailable skip.
- Keep all cross-platform static assertions active on Windows.
- Do not edit the Makefile or cleanup implementation.

## Acceptance

Native Windows reports one explicit `requires a POSIX shell` skip and no failure; Linux/WSL continues executing the unchanged test body.

## Rollback

Revert the one-file test marker/import change.
