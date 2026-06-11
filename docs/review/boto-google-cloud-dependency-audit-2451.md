# Boto3 / Google Cloud dependency audit (#2451)

## Result

The root app does not directly depend on AWS or Google Cloud storage SDKs.

## Direct dependency check

The following packages are absent from `pyproject.toml` direct runtime,
optional, and development dependencies:

- `boto3`
- `botocore`
- `google-cloud-storage`
- `google-auth`
- `google-cloud-core`
- `google-crc32c`
- `google-resumable-media`

## Lockfile check

`uv.lock` does not contain `boto3`, `botocore`, `google-cloud-storage`,
`google-auth`, `google-cloud-core`, `google-crc32c`, or
`google-resumable-media`.

`googleapis-common-protos` is still present as a transitive dependency of the
OpenTelemetry OTLP exporters used by optional/dev observability tooling:

- `opentelemetry-exporter-otlp-proto-grpc`
- `opentelemetry-exporter-otlp-proto-http`

That package is protobuf definitions, not a cloud storage client, and should be
removed only if the OTLP exporter dependency is removed.

## Runtime import check

Static import scanning found no runtime imports of `boto3`, `botocore`,
`google.cloud`, or Google auth/storage transport packages under `src/` or
`telegram_bot/`.
