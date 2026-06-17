---
inclusion: always
---

# MCP Tools Available

Prefer these tools over shell commands (grep, find, cat, sed) for code work.

## codeindexer — semantic search + audit (local, port 8978)

Project indexed: `rag-fresh` (19k chunks, 15k symbols).

| Tool | Use for |
|---|---|
| `search_code` | Find code by meaning, symbol name, or exact pattern |
| `find_callers` | Who calls a function (blast radius) |
| `find_callees` | What a function calls |
| `find_references` | All usages of a symbol |
| `read_chunk` | Read the indexed chunk that owns a line |
| `read_file_range` | Read any line slice without shell |
| `audit_project` | Code quality + security audit |
| `file_deps` | Forward + reverse deps for a file before editing |
| `projects` | List/report indexed projects |

## codegraph — call graph navigation (npx, project: rag-fresh)

Graph: 19k nodes, 35k edges. Use **instead of Read** when exploring code.

| Tool | Use for |
|---|---|
| `codegraph_explore` | PRIMARY — verbatim source + call paths in one call |
| `codegraph_node` | One symbol or full file with line numbers + callers |
| `codegraph_callers` | Who calls this symbol |
| `codegraph_search` | Find symbol locations by name |

## context7 — library documentation

Use for: "how to use library X", SDK examples, API reference.
Call `resolve-library-id` first, then `query-docs`.

## exa — web search

Use for: current news, external resources, anything not in repo or docs.

## Decision rule

1. Code/symbols in repo → `codegraph_explore` or `search_code` first
2. Library/SDK docs → context7
3. Web → exa
4. Never use grep/find/cat for code search if codeindexer/codegraph can answer it
