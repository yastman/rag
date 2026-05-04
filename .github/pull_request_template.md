## Summary

What does this PR do and why?

## Scope

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Documentation / portfolio cleanup
- [ ] Infrastructure / deploy

## Files touched

List the main files or modules changed (one per line):
- `...`

## Validation

What did you run to verify this change?

- [ ] `make check`
- [ ] `make test-unit`
- [ ] `make test`
- [ ] Focused pytest on touched files (`uv run pytest <path> -q`)
- [ ] Other: ___________

If any check above was skipped, state the reason explicitly:
> ___________

## Runtime Impact

Does this change affect Docker Compose, k8s manifests, service startup, or production deploy?

- [ ] No runtime impact
- [ ] Compose file change (`compose.yml`, `compose.dev.yml`, `compose.vps.yml`)
- [ ] Dockerfile or build change
- [ ] k8s manifest change
- [ ] Environment variable or secret contract change
- [ ] Database migration or collection schema change

If runtime-impacting, note the verification you ran (e.g., `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services`):
> ___________

## Screenshots / Demo

If this PR changes UI, Telegram flows, or visual output, attach screenshots or a short demo.

## Reviewer Notes

- Anything non-obvious about the implementation?
- Any trade-offs or follow-up work?
- Relevant docs: [`docs/review/ACCESS_FOR_REVIEWERS.md`](docs/review/ACCESS_FOR_REVIEWERS.md), [`docs/engineering/test-writing-guide.md`](docs/engineering/test-writing-guide.md), [`DOCKER.md`](DOCKER.md), [`tests/README.md`](tests/README.md)
