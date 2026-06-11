# KFP / Kubernetes dependency audit (#2450)

## Result

The root application does not declare or lock Kubeflow Pipelines or Kubernetes
Python clients.

## Direct dependency check

The following packages are absent from `pyproject.toml` direct runtime,
optional, and development dependencies:

- `kfp`
- `kfp-kubernetes`
- `kfp-pipeline-spec`
- `kfp-server-api`
- `kubernetes`

## Lockfile check

The same package names are absent from `uv.lock`, so they are not currently
pulled into the resolved root environment as transitive dependencies.

## Runtime import check

Static import scanning found no runtime imports of `kfp` or `kubernetes` under
`src/` or `telegram_bot/`.
