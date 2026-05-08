#!/usr/bin/env python3
"""Check Markdown relative links and exit nonzero on missing targets.

Checks at least README.md, DOCKER.md, AGENTS.md, all docs/**/*.md,
and folder README.md files. Skips external URLs, anchors-only links,
mailto links, and generated/cache/vendor directories.
"""

import re
import sys
from pathlib import Path


# Directories to skip
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".terraform",
    "vendor",
    "generated",
    "cache",
    "dist",
    "build",
    "site",
    ".claude",
}

# Markdown link regex: [text](url)
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def should_skip_dir(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def is_skipped_link(url: str) -> bool:
    """Skip external URLs, anchors-only, mailto, and empty links."""
    if not url:
        return True
    if url.startswith(("http://", "https://", "ftp://", "mailto:")):
        return True
    return bool(url.startswith("#"))


def resolve_link(source_file: Path, url: str) -> Path:
    """Resolve a relative URL against its source file, stripping any fragment."""
    # Strip fragment
    if "#" in url:
        url = url.split("#", 1)[0]
    # Strip query string (rare in md but possible)
    if "?" in url:
        url = url.split("?", 1)[0]
    if not url:
        return source_file
    target = source_file.parent / url
    return target.resolve()


def collect_markdown_files(root: Path) -> list[Path]:
    """Collect markdown files to check."""
    files = set()

    # Always include these root files if they exist
    for name in ("README.md", "DOCKER.md", "AGENTS.md"):
        p = root / name
        if p.exists():
            files.add(p.resolve())

    # All docs/**/*.md
    for p in (root / "docs").rglob("*.md"):
        if not should_skip_dir(p):
            files.add(p.resolve())

    # Folder README.md files
    for p in root.rglob("README.md"):
        if not should_skip_dir(p):
            files.add(p.resolve())

    return sorted(files)


INLINE_CODE_RE = re.compile(r"`[^`]+`")


def strip_inline_code(line: str) -> str:
    """Remove inline code spans so links inside backticks are not matched."""
    return INLINE_CODE_RE.sub("", line)


def check_links(root: Path) -> list[tuple[Path, int, str, Path]]:
    """Return list of (source_file, line_number, url, missing_target)."""
    broken = []
    md_files = collect_markdown_files(root)

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        in_fenced_code = False
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # Toggle fenced code block state
            if stripped.startswith("```"):
                in_fenced_code = not in_fenced_code
                continue
            if in_fenced_code:
                continue
            # Remove inline code before matching links
            clean_line = strip_inline_code(line)
            for match in LINK_RE.finditer(clean_line):
                url = match.group(2).strip()
                if is_skipped_link(url):
                    continue
                target = resolve_link(md_file, url)
                if not target.exists():
                    broken.append((md_file, line_no, url, target))

    return broken


def main() -> int:
    root = Path.cwd()
    broken = check_links(root)

    if not broken:
        print("All relative Markdown links OK.")
        return 0

    print(f"Broken links found: {len(broken)}")
    for source, line_no, url, target in broken:
        rel_source = source.relative_to(root)
        try:
            rel_target = target.relative_to(root)
        except ValueError:
            rel_target = target
        print(f"  {rel_source}:{line_no} -> '{url}' (missing: {rel_target})")

    return 1


if __name__ == "__main__":
    sys.exit(main())
