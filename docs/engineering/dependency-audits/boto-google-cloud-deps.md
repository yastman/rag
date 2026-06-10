# Boto3 / Google Cloud dependency audit (DEPS-9)

## Scope

This audit covers the root and Telegram dependency surfaces for the packages
listed in #2451:

- `boto3`
- `botocore`
- `google-cloud-storage`
- `google-auth`
- `google-cloud-core`
- `google-crc32c`
- `google-resumable-media`
- `googleapis-common-protos`

## Findings

The application code does not import Boto3, Botocore, Google Cloud Storage, or
Google Auth directly from `src/` or `telegram_bot/`.

After DEPS-8 removed root `docling-serve[ui]` from the application dependency
extra, the root lockfile no longer contains these service-only packages:

- `boto3`
- `botocore`
- `google-cloud-storage`
- `google-auth`
- `google-cloud-core`
- `google-crc32c`
- `google-resumable-media`

`googleapis-common-protos` may still appear while OpenTelemetry exporter packages
remain in the root or Telegram lockfiles. Its parents are OTel exporters (`opentelemetry-exporter-otlp-proto-http` and, in the root lock, `opentelemetry-exporter-otlp-proto-grpc`), not Boto3 or Google Cloud Storage runtime code. That remaining transitive dependency
is owned by the OTel removal path (#2434 / PR #2447), not by a Boto/GCS direct
usage path.

## Guardrail

`tests/contract/test_boto_google_cloud_dependency_audit_contract.py` prevents
these packages from returning as direct dependencies or direct runtime imports,
and keeps the only temporary `googleapis-common-protos` allowance tied to OTel
exporter parents.
