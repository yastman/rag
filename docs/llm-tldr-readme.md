***REMOVED*** TLDR: Code Analysis for AI Agents

[![PyPI](https://img.shields.io/pypi/v/llm-tldr)](https://pypi.org/project/llm-tldr/)
[![Python](https://img.shields.io/pypi/pyversions/llm-tldr)](https://pypi.org/project/llm-tldr/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

**Give LLMs exactly the code they need. Nothing more.**

```bash
***REMOVED*** One-liner: Install, index, search
pip install llm-tldr && tldr warm . && tldr semantic "what you're looking for" .
```

Your codebase is 100K lines. Claude's context window is 200K tokens. Raw code won't fit—and even if it did, the LLM would drown in irrelevant details.

TLDR extracts *structure* instead of dumping *text*. The result: **95% fewer tokens** while preserving everything needed to understand and edit code correctly.

```bash
pip install llm-tldr
tldr warm .                    ***REMOVED*** Index your project
tldr context main --project .  ***REMOVED*** Get LLM-ready summary
```

---

***REMOVED******REMOVED*** How It Works

TLDR builds 5 analysis layers, each answering different questions:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Program Dependence  → "What affects line 42?"      │
│ Layer 4: Data Flow           → "Where does this value go?"  │
│ Layer 3: Control Flow        → "How complex is this?"       │
│ Layer 2: Call Graph          → "Who calls this function?"   │
│ Layer 1: AST                 → "What functions exist?"      │
└─────────────────────────────────────────────────────────────┘
```

**Why layers?** Different tasks need different depth:
- Browsing code? Layer 1 (structure) is enough
- Refactoring? Layer 2 (call graph) shows what breaks
- Debugging null? Layer 5 (slice) shows only relevant lines

The daemon keeps indexes in memory for **100ms queries** instead of 30-second CLI spawns.

***REMOVED******REMOVED******REMOVED*** Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         YOUR CODE                                │
│  src/*.py, lib/*.ts, pkg/*.go                                    │
└───────────────────────────┬──────────────────────────────────────┘
                            │ tree-sitter
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                     5-LAYER ANALYSIS                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│  │   AST   │→│  Calls  │→│   CFG   │→│   DFG   │→│   PDG   │     │
│  │   L1    │ │   L2    │ │   L3    │ │   L4    │ │   L5    │     │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘     │
└───────────────────────────┬──────────────────────────────────────┘
                            │ bge-large-en-v1.5
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    SEMANTIC INDEX                                │
│  1024-dim embeddings in FAISS  →  "find JWT validation"          │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                       DAEMON                                     │
│  In-memory indexes  •  100ms queries  •  Auto-lifecycle          │
└──────────────────────────────────────────────────────────────────┘
```

***REMOVED******REMOVED******REMOVED*** The Semantic Layer: Search by Behavior

The real power comes from combining all 5 layers into **searchable embeddings**.

Every function gets indexed with:
- Signature + docstring (L1)
- What it calls + who calls it (L2)
- Complexity metrics (L3)
- Data flow patterns (L4)
- Dependencies (L5)
- First ~10 lines of actual code

This gets encoded into **1024-dimensional vectors** using `bge-large-en-v1.5`. The result: search by *what code does*, not just what it says.

```bash
***REMOVED*** "validate JWT" finds verify_access_token() even without that exact text
tldr semantic "validate JWT tokens and check expiration" .
```

**Why this works:** Traditional search finds `authentication` in variable names and comments. Semantic search understands that `verify_access_token()` *performs* JWT validation because the call graph and data flow reveal its purpose.

***REMOVED******REMOVED******REMOVED*** Setting Up Semantic Search

```bash
***REMOVED*** Build the semantic index (one-time, ~2 min for typical project)
tldr warm /path/to/project

***REMOVED*** Search by behavior
tldr semantic "database connection pooling" .
```

Embedding dependencies (`sentence-transformers`, `faiss-cpu`) are included with `pip install llm-tldr`. The index is cached in `.tldr/cache/semantic.faiss`.

***REMOVED******REMOVED******REMOVED*** Keeping the Index Fresh

The daemon tracks dirty files and auto-rebuilds after 20 changes, but you need to notify it when files change:

```bash
***REMOVED*** Notify daemon of a changed file
tldr daemon notify src/auth.py --project .
```

**Integration options:**

1. **Git hook** (post-commit):
   ```bash
   git diff --name-only HEAD~1 | xargs -I{} tldr daemon notify {} --project .
   ```

2. **Editor hook** (on save):
   ```bash
   tldr daemon notify "$FILE" --project .
   ```

3. **Manual rebuild** (when needed):
   ```bash
   tldr warm .  ***REMOVED*** Full rebuild
   ```

The daemon auto-rebuilds semantic embeddings in the background once the dirty threshold (default: 20 files) is reached.

---

***REMOVED******REMOVED*** The Workflow

***REMOVED******REMOVED******REMOVED*** Before Reading Code
```bash
tldr tree src/                      ***REMOVED*** See file structure
tldr structure src/ --lang python   ***REMOVED*** See functions/classes
```

***REMOVED******REMOVED******REMOVED*** Before Editing
```bash
tldr extract src/auth.py            ***REMOVED*** Full file analysis
tldr context login --project .      ***REMOVED*** LLM-ready summary (95% savings)
```

***REMOVED******REMOVED******REMOVED*** Before Refactoring
```bash
tldr impact login .                 ***REMOVED*** Who calls this? (reverse call graph)
tldr change-impact                  ***REMOVED*** Which tests need to run?
```

***REMOVED******REMOVED******REMOVED*** Debugging
```bash
tldr slice src/auth.py login 42     ***REMOVED*** What affects line 42?
tldr dfg src/auth.py login          ***REMOVED*** Trace data flow
```

***REMOVED******REMOVED******REMOVED*** Finding Code by Behavior
```bash
tldr semantic "validate JWT tokens" .   ***REMOVED*** Natural language search
```

---

***REMOVED******REMOVED*** Quick Setup

***REMOVED******REMOVED******REMOVED*** 1. Install

```bash
pip install llm-tldr
```

***REMOVED******REMOVED******REMOVED*** 2. Index Your Project

```bash
tldr warm /path/to/project
```

This builds all analysis layers and starts the daemon. Takes 30-60 seconds for a typical project, then queries are instant.

***REMOVED******REMOVED******REMOVED*** 3. Start Using

```bash
tldr context main --project .   ***REMOVED*** Get context for a function
tldr impact helper_func .       ***REMOVED*** See who calls it
tldr semantic "error handling"  ***REMOVED*** Find by behavior
```

---

***REMOVED******REMOVED*** Real Example: Why This Matters

**Scenario:** Debug why `user` is null on line 42.

**Without TLDR:**
1. Read the 150-line function
2. Trace every variable manually
3. Miss the bug because it's hidden in control flow

**With TLDR:**
```bash
tldr slice src/auth.py login 42
```

**Output:** Only 6 lines that affect line 42:
```python
3:   user = db.get_user(username)
7:   if user is None:
12:      raise NotFound
28:  token = create_token(user)  ***REMOVED*** ← BUG: skipped null check
35:  session.token = token
42:  return session
```

The bug is obvious. Line 28 uses `user` without going through the null check path.

---

***REMOVED******REMOVED*** Command Reference

***REMOVED******REMOVED******REMOVED*** Exploration
| Command | What It Does |
|---------|--------------|
| `tldr tree [path]` | File tree |
| `tldr structure [path] --lang <lang>` | Functions, classes, methods |
| `tldr search <pattern> [path]` | Text pattern search |
| `tldr extract <file>` | Full file analysis |

***REMOVED******REMOVED******REMOVED*** Analysis
| Command | What It Does |
|---------|--------------|
| `tldr context <func> --project <path>` | LLM-ready summary (95% savings) |
| `tldr cfg <file> <function>` | Control flow graph |
| `tldr dfg <file> <function>` | Data flow graph |
| `tldr slice <file> <func> <line>` | Program slice |

***REMOVED******REMOVED******REMOVED*** Cross-File
| Command | What It Does |
|---------|--------------|
| `tldr calls [path]` | Build call graph |
| `tldr impact <func> [path]` | Find all callers (reverse call graph) |
| `tldr dead [path]` | Find unreachable code |
| `tldr arch [path]` | Detect architecture layers |
| `tldr imports <file>` | Parse imports |
| `tldr importers <module> [path]` | Find files that import a module |

***REMOVED******REMOVED******REMOVED*** Semantic
| Command | What It Does |
|---------|--------------|
| `tldr warm <path>` | Build all indexes (including embeddings) |
| `tldr semantic <query> [path]` | Natural language code search |

***REMOVED******REMOVED******REMOVED*** Diagnostics
| Command | What It Does |
|---------|--------------|
| `tldr diagnostics <file>` | Type check + lint |
| `tldr change-impact [files]` | Find tests affected by changes |
| `tldr doctor` | Check/install diagnostic tools |

***REMOVED******REMOVED******REMOVED*** Daemon
| Command | What It Does |
|---------|--------------|
| `tldr daemon start` | Start background daemon |
| `tldr daemon stop` | Stop daemon |
| `tldr daemon status` | Check status |

---

***REMOVED******REMOVED*** Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C, C++, Ruby, PHP, C***REMOVED***, Kotlin, Scala, Swift, Lua, Elixir

Language is auto-detected or specify with `--lang`.

---

***REMOVED******REMOVED*** MCP Integration

For AI tools (Claude Desktop, Claude Code):

**Claude Desktop** - Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "tldr": {
      "command": "tldr-mcp",
      "args": ["--project", "/path/to/your/project"]
    }
  }
}
```

**Claude Code** - Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "tldr": {
      "command": "tldr-mcp",
      "args": ["--project", "."]
    }
  }
}
```

---

***REMOVED******REMOVED*** Configuration

***REMOVED******REMOVED******REMOVED*** `.tldrignore` - Exclude Files

TLDR respects `.tldrignore` (gitignore syntax) for all commands including `tree`, `structure`, `search`, `calls`, and semantic indexing:

```bash
***REMOVED*** Auto-create with sensible defaults
tldr warm .  ***REMOVED*** Creates .tldrignore if missing
```

**Default exclusions:**
- `node_modules/`, `.venv/`, `__pycache__/`
- `dist/`, `build/`, `*.egg-info/`
- Binary files (`*.so`, `*.dll`, `*.whl`)
- Security files (`.env`, `*.pem`, `*.key`)

**Customize** by editing `.tldrignore`:
```gitignore
***REMOVED*** Add your patterns
large_test_fixtures/
vendor/
data/*.csv
```

**CLI Flags:**
```bash
***REMOVED*** Add patterns from command line (can be repeated)
tldr --ignore "packages/old/" --ignore "*.generated.ts" tree .

***REMOVED*** Bypass all ignore patterns
tldr --no-ignore tree .
```

***REMOVED******REMOVED******REMOVED*** Settings - Daemon Behavior

Create `.tldr/config.json` for daemon settings:

```json
{
  "semantic": {
    "enabled": true,
    "auto_reindex_threshold": 20
  }
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `true` | Enable semantic search |
| `auto_reindex_threshold` | `20` | Files changed before auto-rebuild |

***REMOVED******REMOVED******REMOVED*** Monorepo Support

For monorepos, create `.claude/workspace.json` to scope indexing:

```json
{
  "active_packages": ["packages/core", "packages/api"],
  "exclude_patterns": ["**/fixtures/**"]
}
```

---

***REMOVED******REMOVED*** Performance

| Metric | Raw Code | TLDR | Improvement |
|--------|----------|------|-------------|
| Tokens for function context | 21,000 | 175 | **99% savings** |
| Tokens for codebase overview | 104,000 | 12,000 | **89% savings** |
| Query latency (daemon) | 30s | 100ms | **300x faster** |

---

***REMOVED******REMOVED*** Deep Dive

For the full architecture explanation, benchmarks, and advanced workflows:

**[Full Documentation](./docs/TLDR.md)**

---

***REMOVED******REMOVED*** License

AGPL-3.0 - See LICENSE file.
