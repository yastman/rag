# Sidecar services

Applies to services/**; extends [root AGENTS](../AGENTS.md).

- A sidecar owns its Dockerfile and service-local dependency manifest/lock.
- Use HTTP contracts between sidecars; do not share Python imports or mutable process state.
- Keep endpoint/port/health contracts stable. Changes require all Compose files, consumers,
  and [service documentation](README.md) to agree.
- Read the nearest service override before editing it.

## Checks

Run focused service tests using the dependency selection in [Tests](../tests/README.md).
Dockerfile/Compose changes require `make verify-compose-images` and relevant static checks.
With a configured stack, use `uv run --no-sync pytest tests/smoke/test_zoo_smoke.py -q`.
A skipped live test is not image/runtime proof. Root delivery gates remain required.

[DOCKER.md](../DOCKER.md) owns deployment wiring.
