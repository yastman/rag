# Compose source cleanup

Use one checkout's canonical `compose.yml` and `compose.dev.yml` for local project `dev`. Compose records every source file used to create a project; temporary `/tmp/compose.*.yml` files or files from another worktree can leave stale overrides active.

## Inspect

```bash
docker compose ls --all --format json
```

Find project `dev` and inspect `ConfigFiles`. Every non-temporary path must have the same checkout root. No path should begin with `/tmp/compose`.

## Recreate from one checkout

From the checkout that owns the local stack:

```bash
docker compose -p dev down --remove-orphans
docker compose -p dev -f compose.yml -f compose.dev.yml up -d
```

If credentials live in `.env`, keep that file in the same checkout. To use the repository's non-secret CI defaults instead, pass `--env-file tests/fixtures/compose.ci.env` to both commands.

Run `docker compose ls --all --format json` again. Project `dev` should list only this checkout's `compose.yml` and `compose.dev.yml`.
