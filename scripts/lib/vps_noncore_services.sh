***REMOVED*** shellcheck shell=bash
***REMOVED*** scripts/lib/vps_noncore_services.sh
***REMOVED***
***REMOVED*** Single source of truth for the VPS non-core service list.
***REMOVED***
***REMOVED*** These services declare the `vps-noncore` profile in compose.vps.yml and are
***REMOVED*** stopped/removed on the minimal-runtime VPS. The list is sourced by:
***REMOVED***   - scripts/test_release_health_vps.sh        (release smoke)
***REMOVED***   - scripts/vps_cleanup_removed_services.sh   (cleanup, dry-run + apply)
***REMOVED***
***REMOVED*** This file is meant to be `source`d, not executed. Do not add a shebang or
***REMOVED*** `set -e`: that would alter the caller's shell options.
***REMOVED***
***REMOVED*** Drift between this list and compose.vps.yml is enforced by the contract
***REMOVED*** test tests/contract/test_vps_noncore_list_single_source_contract.py.
***REMOVED***
***REMOVED*** Closes ***REMOVED***1611.

***REMOVED*** shellcheck disable=SC2034  ***REMOVED*** consumed by sourcing scripts
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
