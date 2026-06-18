# MCP Tools for Development

Two code-navigation MCP servers plus Context7 for library docs. Use them in
combination — they answer different questions.

> Note: graphify was evaluated and removed. Its knowledge-graph links are
> LLM-inferred (fuzzy) and its NL query is token-based; for this codebase
> codegraph (precise AST graph) and codeindexer (semantic search) cover every
> navigation need. graphify's only unique angles (Neo4j/Obsidian export,
> cross-repo graph, PR-triage) were not part of day-to-day work here.

---

## 1. codeindexer MCP

**Purpose:** semantic search, symbol lookup, references, audit, dead code.

**When to use:** finding where something happens by meaning, auditing security
patterns, finding unused code, searching by type signature.

| Tool | Example |
|---|---|
| `search_code` | `search_code(query="semantic cache before retrieval", project="rag-fresh")` |
| `find_callers` | `find_callers(function="guard_node", project="rag-fresh")` |
| `find_references` | `find_references(symbol="route_cache", project="rag-fresh")` |
| `find_callees` | `find_callees(function="handle_query", project="rag-fresh")` |
| `find_call_chain` | `find_call_chain(start="handle_query", end="guard_node", project="rag-fresh")` |
| `find_by_signature` | search by param/return types, arity, async |
| `find_dead_code` | unused functions |
| `audit_project` | security / complexity / dead-code report |
| `read_chunk` / `read_file_range` | fetch indexed code without grep |

Endpoint: `http://127.0.0.1:8978/mcp` (in `~/.kiro/settings/mcp.json`).

**Freshness:** self-reports staleness in `search_code` results (`freshness`
block: indexed_commit vs HEAD, commits_behind). Reindex with
`projects(action="reindex", project="rag-fresh")` when it reports `behind`.
`find_callers` returns full caller lists including tests (more complete than
codegraph's direct-edge view).

---

## 2. codegraph MCP + CLI

**Purpose:** precise directed call graph — verbatim source, blast radius,
caller/callee trails. AST-based, 100% local SQLite (`.codegraph/codegraph.db`).

Installed globally: `@colbymchenry/codegraph` v1.0.1 (`codegraph` on PATH).
A **background daemon with a file watcher auto-syncs the graph on every save**
— the index stays fresh without manual reindex (unlike codeindexer).

### MCP tools (4 — the v1.0.1 server ceiling)

| Tool | Example |
|---|---|
| `codegraph_explore` | `codegraph_explore(query="guard_node route_cache edges")` |
| `codegraph_callers` | `codegraph_callers(symbol="guard_node")` |
| `codegraph_search` | `codegraph_search(query="build_graph", kind="function")` |
| `codegraph_node` | `codegraph_node(file="src/runtime/graph/edges.py")` |

Returns verbatim on-disk source (line-numbered, identical to `Read`). Treat the
returned source as already read — do not re-open the file.

### CLI — the rest (not exposed over MCP in v1.0.1, all verified working)

| Command | What it does |
|---|---|
| `codegraph status [--json]` | index stats; `reindexRecommended` flag |
| `codegraph callees <symbol>` | what a symbol calls (forward edges) |
| `codegraph impact <symbol> --depth N` | transitive blast radius — every affected symbol |
| `codegraph affected <files...>` / `--stdin` | test files affected by changed sources |
| `codegraph files --filter <dir> --format grouped` | indexed file structure |
| `codegraph query <s> --kind function` | symbol search with signatures |
| `codegraph node <name> --symbols-only` | file symbol map + dependents |
| `codegraph node <path> --offset N --limit M` | read a file like `Read` + dependents |
| `codegraph sync` | incremental update (run after a branch switch) |
| `codegraph index --force` | full rebuild (use `--quiet` to suppress the progress bar) |
| `codegraph daemon` | manage the background auto-sync daemon |

> `codegraph context` exists in upstream docs but is **main-branch only** — not
> in published v1.0.1. Use codeindexer `search_code` for task-context.

MCP config (`~/.kiro/settings/mcp.json`):
```json
"codegraph": {
  "command": "codegraph",
  "args": ["serve", "--mcp", "--path", "/home/user/projects/rag-fresh"]
}
```

### Killer feature for this repo — test selection

```bash
git diff --name-only HEAD~5 | codegraph affected --stdin --quiet
```
Returns the test files covering the changed sources — run only those in
pre-commit / CI instead of the whole suite.

---

## 3. Context7

**Purpose:** up-to-date documentation for external libraries (LangGraph,
aiogram, Qdrant, Pydantic, …). Not codebase navigation.

Two tools, always paired:
- `resolve-library-id` — name → ranked Context7 IDs with coverage/score
- `query-docs` — ID + question → code snippets from official docs

Limits: ≤3 `query-docs` calls per question; call `resolve-library-id` first.
Do not put secrets in the query.

---

## When to use which

| Question | Tool |
|---|---|
| Where is X defined / called (by meaning)? | codeindexer `search_code` |
| Verbatim source + who calls X (precise)? | codegraph `codegraph_explore` / `codegraph_node` |
| What breaks if I change X (transitive)? | codegraph CLI `impact` |
| Which tests cover my changed files? | codegraph CLI `affected --stdin` |
| All callers incl. tests? | codeindexer `find_callers` |
| Real call path A → B? | codegraph CLI `trace` (main) / codeindexer `find_call_chain` |
| Security / dead-code audit? | codeindexer `audit_project` / `find_dead_code` |
| How to use library Y (current API)? | Context7 |

**Default for code navigation:** codegraph (precise, directed, auto-fresh).
codeindexer for semantic search, full caller lists, and audits.
