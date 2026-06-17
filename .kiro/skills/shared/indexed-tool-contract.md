# Shared: Indexed-tool discovery contract

> Single source of truth for repo/code discovery in swarm workers. Referenced by
> the swarm phase skills instead of being restated in each (#2305 P2).

## Order of tools

1. **Code Indexer (MCP) first** for broad/semantic discovery and compact symbol
   tracing:
   - `projects(action="list", query="<repo>")` to resolve the indexed project,
   - `search_code(project="<project>", mode="cascade", compact=true)`,
   - compact `find_references` / `find_callers` / `find_callees`.
2. **CodeGraph** as the source-backed companion for exact symbol bodies and
   quick graph checks: `codegraph_search`, `codegraph_node(includeCode=true)`,
   `codegraph_explore`, `codegraph_callers` / `codegraph_callees` /
   `codegraph_impact`.
3. **`rg` / `find` only** for exact bytes, unindexed files, generated files, or
   paths outside the indexed project.

## Freshness (native, no git hooks)

Code Indexer uses native `auto_reindex`, not custom git hooks. After a fresh
`codeindexer serve` start, allow the watcher startup grace period (~180s). When
indexed results look stale, check `codeindexer jobs` / `codeindexer doctor` and
repair with `codeindexer doctor --fix` or a focused
`codeindexer reindex <project>` before trusting output. Do not install custom
git hooks for freshness.
