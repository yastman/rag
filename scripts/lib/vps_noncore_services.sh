# shellcheck shell=bash
# scripts/lib/vps_noncore_services.sh
#
# Single source of truth for the VPS non-core service list.
#
# These services declare the `vps-noncore` profile in compose.vps.yml and are
# stopped/removed on the minimal-runtime VPS. The list is sourced by:
#   - scripts/test_release_health_vps.sh        (release smoke)
#   - scripts/vps_cleanup_removed_services.sh   (cleanup, dry-run + apply)
#
# This file is meant to be `source`d, not executed. Do not add a shebang or
# `set -e`: that would alter the caller's shell options.
#
# Drift between this list and compose.vps.yml is enforced by the contract
# test tests/contract/test_vps_noncore_list_single_source_contract.py.
#
# Closes #1611.

# shellcheck disable=SC2034  # consumed by sourcing scripts
VPS_NONCORE_SERVICES=(
  mini-app-api
  mini-app-frontend
  docling
  ingestion
  langfuse
  langfuse-worker
  clickhouse
  minio
  redis-langfuse
)
