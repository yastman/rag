# Cross-domain SDK audit — new issue drafts (2026-05-19)

Three SDK-native gaps surfaced during the 2026-05-19 audit (see context: closed PR #1657, full report
in `.github/issue-drafts/2026-05-19-langfuse-trace-coverage/AUDIT_REPORT.md` if that branch is restored,
or in the audit comments on #1538).

## Files

| File | Type | Priority | Title |
|------|------|----------|-------|
| `01-langgraph-send-parallel-fanout.md` | refactor | P3-backlog | LangGraph `Send` for parallel fan-out (HyDE multi-doc, multi-language) |
| `02-langgraph-streamwriter-custom-mode.md` | refactor | P2-backlog | LangGraph `StreamWriter` + `stream_mode="custom"` replacing `DraftStreamer` |
| `03-instructor-streaming-partial.md` | research | P3-backlog | Evaluate `instructor.create_partial` for voice-path live filter streaming |

## How to file

**Automated (recommended):**

```bash
GITHUB_TOKEN=ghp_xxx bash .github/issue-drafts/2026-05-19-audit-newgaps/create_issues.sh
```

Or with `gh` CLI:

```bash
bash .github/issue-drafts/2026-05-19-audit-newgaps/create_issues.sh --gh
```

The script reads each `*.md`, extracts the title from the first H1, and creates the issue with
the labels listed in the script (matching repo convention from #1647–#1666).

**Manual:** open new GitHub issues, copy the H1 as title, paste the rest as body, apply the labels
from `create_issues.sh:FILES`.

## Why drafts and not direct issue creation

The provider gateway used by this repo's agent does not expose a `create_issue` tool — only
`create_pull_request`. The script approach mirrors the pattern from PR #1657's `post_comments.sh`.

## Cross-references

- #1538 — broader SDK-vs-custom audit; these 3 issues are concrete next items extending it.
- #1535 — voice path migration to `create_agent`. Issue 02 (StreamWriter) is synergistic.
- #1652 — research issue for LangChain-native HyDE replacement. Issue 01 (Send) cross-links.
