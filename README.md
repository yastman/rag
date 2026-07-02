The core pipeline (`src/core/` + `src/runtime/`) is healthy and well-tested. The following surfaces are physically in-tree but are **archived/reference** — not part of the active production path, and being trimmed in open issues:

- **LangGraph dead nodes** — some graph nodes are no longer on the live execution path but remain in the file tree.

**Langfuse status**: The SDK has been mostly removed from the live production path. However, some test files and compatibility shims still reference it. Full cleanup is tracked in #3097 and #3098.

Observability is currently done via structured logging.