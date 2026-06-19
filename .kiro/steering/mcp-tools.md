---
inclusion: always
---

# Code-Navigation Tools (always prefer over grep/find/cat/sed)

Full reference: `docs/engineering/mcp-tools.md`. This file is the always-loaded
summary. graphify was evaluated and **removed** — do not look for it.

## codeindexer — semantic search + audit (MCP, local port 8978)

Project indexed: `rag-fresh`. Best for meaning-based search, full caller lists
(incl. tests), audits, type-signature search.

| Tool | Use for |
|---|---|
| `search_code` | find code by meaning / symbol / exact pattern |
| `find_callers` / `find_callees` | who calls X / what X calls (full lists incl. tests) |
| `find_references` | all usages of a symbol |
| `find_call_chain` | real call path A → B |
| `find_by_signature` | search by param/return type, arity, async |
| `find_dead_code` / `audit_project` | unused code / security+quality audit |
| `read_chunk` / `read_file_range` | read indexed code without shell |
| `file_deps` | forward+reverse deps of a file before editing |

Freshness: `search_code` self-reports staleness (`freshness` block). If it says
`behind`, run `projects(action="reindex", project="rag-fresh")`.

## codegraph — precise directed call graph (global `codegraph` CLI + 4 MCP tools)

AST graph in local SQLite (`.codegraph/`). A **daemon file-watcher auto-syncs on
every save → always fresh** (no manual reindex). Directed edges = accurate
call paths (unlike an undirected graph).

**MCP tools (use in-session, no shell):**

| Tool | Use for |
|---|---|
| `codegraph_explore` | PRIMARY — verbatim source + call paths in one call |
| `codegraph_node` | one symbol (source + caller/callee trail) OR read a file w/ dependents |
| `codegraph_callers` | direct callers of a symbol |
| `codegraph_search` | locate symbols by name |

**CLI-only (run via shell — NOT exposed as MCP in v1.0.1):**

| Command | Use for |
|---|---|
| `codegraph impact <sym> --depth N` | transitive blast radius (everything affected by a change) |
| `codegraph affected --stdin` | which test files cover changed sources (`git diff --name-only … \| codegraph affected --stdin --quiet`) |
| `codegraph callees <sym>` | what a symbol calls |
| `codegraph status [--json]` | index stats + `reindexRecommended` flag |
| `codegraph sync` / `codegraph index --force --quiet` | incremental / full rebuild |

> `codegraph context` is upstream-main only — NOT in v1.0.1. Use codeindexer
> `search_code` for task-context instead.

## Documentation (not just code) — codeindexer only

The project's `docs/` (engineering, designs, adr, runbooks), root `*.md`, and
folder READMEs are indexed as `module_type="doc"`. codegraph is **blind to
docs** (it only knows code symbols) — use codeindexer for anything doc-related.

| Task | Tool |
|---|---|
| Find something **in the docs** (semantic) | `search_code(query, module_type="doc")` |
| Pure-**code** search (skip README/docs) | `search_code(query, exclude_module_types=["doc"])` |
| Docs hygiene — stray `TODO`/`XXX`/`FIXME`, repeated paragraph openers | `find_prose_smells(checks=["leaks","anaphora"])` |
| Topic map of a **pure** doc/PDF collection | `analyze_corpus` (weak on code-dominated repos — docs are <20% of chunks here) |

> Writer-mode tools (`find_citations`, `find_tropes`, `consistency_check`) are
> for prose **books**, not technical docs — don't reach for them here.

## context7 — library docs

"How to use library X", current SDK/API. Call `resolve-library-id` first, then
`query-docs` (≤3/question). No secrets in the query.

## exa — web search

Current news / external resources not in repo or docs.

## Decision rule

1. Explore code / read a symbol or file → `codegraph_explore` / `codegraph_node` (MCP)
2. Meaning-based search, full callers incl. tests, audit → codeindexer
3. Blast radius / impact / which-tests-to-run → **codegraph CLI** (`impact`, `affected`)
4. Library/SDK docs → context7
5. Web → exa
6. Never grep/find/cat for code if codeindexer/codegraph can answer.
