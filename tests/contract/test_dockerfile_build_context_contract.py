"""Contract: every Dockerfile ``COPY`` source must exist in its build context (#1993).

Issue #1993 reported a hard build break: ``services/docling/Dockerfile``
declares ``COPY pyproject.toml uv.lock ./`` but ``services/docling/`` did
not contain those files, while both ``compose.yml`` and the publish-
internal-images workflow build the docling image with
``./services/docling`` as the build context. The build fails with
``failed to compute cache key: ... not found``.

This contract enumerates every ``(build_context, dockerfile)`` pair that
appears in:

- ``compose.yml`` ``build:`` blocks, and
- ``.github/workflows/publish-internal-images.yml`` matrix entries

then parses each Dockerfile and verifies that every ``COPY <src> <dst>``
source is reachable from the declared build context. Sources that come
from another build stage (``COPY --from=<stage>``) are excluded — those
are virtual filesystems built earlier in the same Dockerfile and do not
have on-disk paths.

If a future change introduces a new (Dockerfile, context) pair where the
declared sources are missing, this contract fails with the exact
offending pair, file, and line so the build break surfaces in CI rather
than at production image-build time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "compose.yml"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-internal-images.yml"


# ---------------------------------------------------------------------------
# (context, dockerfile) discovery
# ---------------------------------------------------------------------------


def _normalise_context(context: str | None) -> Path:
    """Resolve a Compose / workflow ``context`` string against the repo root."""
    if context is None or context in {"", "."}:
        return REPO_ROOT
    return (REPO_ROOT / context).resolve()


def _parse_compose_pairs() -> list[tuple[Path, Path, str]]:
    """Return ``(context_dir, dockerfile_abs_path, service_name)`` from compose.yml."""
    if not COMPOSE_FILE.exists():
        return []
    with COMPOSE_FILE.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    pairs: list[tuple[Path, Path, str]] = []
    services = data.get("services", {}) if isinstance(data, dict) else {}
    for service_name, service in services.items():
        if not isinstance(service, dict):
            continue
        build = service.get("build")
        if not isinstance(build, dict):
            # Inline string contexts ("build: ./foo") fall back to "Dockerfile" inside that dir.
            if isinstance(build, str):
                ctx = _normalise_context(build)
                df = ctx / "Dockerfile"
                pairs.append((ctx, df, service_name))
            continue
        ctx = _normalise_context(build.get("context"))
        dockerfile_attr = build.get("dockerfile") or "Dockerfile"
        df_path = (ctx / dockerfile_attr).resolve()
        pairs.append((ctx, df_path, f"compose:{service_name}"))
    return pairs


def _parse_publish_workflow_pairs() -> list[tuple[Path, Path, str]]:
    """Return ``(context_dir, dockerfile_abs_path, image_name)`` from publish workflow."""
    if not PUBLISH_WORKFLOW.exists():
        return []
    with PUBLISH_WORKFLOW.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    pairs: list[tuple[Path, Path, str]] = []
    if not isinstance(data, dict):
        return pairs
    jobs = data.get("jobs", {}) or {}
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        strategy = job.get("strategy", {}) or {}
        matrix = strategy.get("matrix", {}) or {}
        includes = matrix.get("include", []) or []
        if not isinstance(includes, list):
            continue
        for entry in includes:
            if not isinstance(entry, dict):
                continue
            ctx = _normalise_context(entry.get("build_context"))
            dockerfile_attr = entry.get("dockerfile")
            if not dockerfile_attr:
                continue
            # Workflow paths are repo-relative regardless of the build context.
            df_path = (REPO_ROOT / dockerfile_attr).resolve()
            image_name = entry.get("image_name", "<unknown>")
            pairs.append((ctx, df_path, f"workflow:{image_name}"))
    return pairs


def _all_pairs() -> list[tuple[Path, Path, str]]:
    """Deduplicate (context, dockerfile) pairs across compose + workflow."""
    seen: dict[tuple[Path, Path], str] = {}
    for ctx, df, owner in _parse_compose_pairs() + _parse_publish_workflow_pairs():
        key = (ctx, df)
        if key in seen:
            seen[key] = f"{seen[key]},{owner}"
        else:
            seen[key] = owner
    return [(ctx, df, owner) for (ctx, df), owner in seen.items()]


# ---------------------------------------------------------------------------
# Dockerfile COPY parser
# ---------------------------------------------------------------------------


# Match COPY <src1> [src2 ...] <dst>, but skip COPY --from=<stage>
# Also tolerates leading flags like --chown=...
_COPY_LINE = re.compile(r"^\s*COPY\s+(?P<rest>.+)$", re.IGNORECASE)


def _extract_copy_sources(dockerfile: Path) -> list[tuple[int, list[str]]]:
    """Return ``(line_no, [sources...])`` for every host-filesystem COPY in the file."""
    out: list[tuple[int, list[str]]] = []
    text = dockerfile.read_text(encoding="utf-8")
    # Join continuation lines
    logical_lines: list[tuple[int, str]] = []
    buf = ""
    start_line = 0
    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            if not buf:
                start_line = line_no
            buf += stripped[:-1] + " "
            continue
        if buf:
            logical_lines.append((start_line, buf + stripped))
            buf = ""
            start_line = 0
        else:
            logical_lines.append((line_no, stripped))
    if buf:
        logical_lines.append((start_line, buf))

    for line_no, line in logical_lines:
        m = _COPY_LINE.match(line)
        if not m:
            continue
        rest = m.group("rest").strip()
        # Drop trailing inline comments
        if "#" in rest:
            rest = rest.split("#", 1)[0].strip()
        if not rest:
            continue
        # Tokenise: handle simple whitespace splits (no quoted-arg support — none used today)
        parts = rest.split()
        # Skip flag tokens (--chown, --chmod, --link, etc.)
        non_flags = [p for p in parts if not p.startswith("--")]
        # COPY --from=<stage> ... — those tokens come from a build stage, not host fs
        is_stage_copy = any(p.startswith("--from=") for p in parts)
        if is_stage_copy:
            continue
        if len(non_flags) < 2:
            # Malformed COPY, skip silently — actionlint/hadolint will catch it
            continue
        # Last token = destination, the rest are sources
        sources = non_flags[:-1]
        out.append((line_no, sources))
    return out


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


PAIRS = _all_pairs()
# Skip pairs whose Dockerfile is missing entirely; that's a separate contract failure
# but not the one this test guards against. Other Dockerfile-existence checks live
# in test_dockerfile_runtime_policy_contract.py.
PAIRS_WITH_DOCKERFILE = [(c, d, o) for c, d, o in PAIRS if d.exists()]


@pytest.mark.parametrize(
    ("context_dir", "dockerfile", "owner"),
    PAIRS_WITH_DOCKERFILE,
    ids=lambda p: str(p).replace(str(REPO_ROOT) + "/", "") if isinstance(p, Path) else str(p),
)
def test_dockerfile_copy_sources_exist_in_build_context(
    context_dir: Path, dockerfile: Path, owner: str
) -> None:
    """Each ``COPY`` source must resolve under the declared build context.

    A failure indicates that the Dockerfile and its declared build
    context (compose.yml or publish workflow) disagree about where the
    source files live. Choose one of:

    1. Add the missing files to the build context (e.g. service-local
       ``pyproject.toml`` / ``uv.lock``), or
    2. Change the build context (e.g. to repo root) and update both
       compose.yml and the publish workflow to agree, then update the
       Dockerfile ``COPY`` paths.
    """
    rel_dockerfile = dockerfile.relative_to(REPO_ROOT)
    rel_context = context_dir.relative_to(REPO_ROOT) if context_dir != REPO_ROOT else Path(".")
    copies = _extract_copy_sources(dockerfile)

    missing: list[str] = []
    for line_no, sources in copies:
        for src in sources:
            # Strip any leading ``./`` for cleaner messages.
            cleaned = src.lstrip("./") or "."
            # Globs are valid; treat as present if at least one match exists
            if any(ch in src for ch in ("*", "?", "[")):
                matches = list(context_dir.glob(cleaned))
                if not matches:
                    missing.append(
                        f"line {line_no}: glob {src!r} matches nothing in {rel_context}/"
                    )
                continue
            target = context_dir / cleaned
            if not target.exists():
                missing.append(f"line {line_no}: {src!r} not found at {rel_context}/{cleaned}")

    assert not missing, (
        f"Dockerfile/build-context mismatch (#1993) in {rel_dockerfile} "
        f"(context={rel_context}, owner={owner}):\n  - "
        + "\n  - ".join(missing)
        + "\n\nFix options: add the missing files to the build context, "
        "or change the build context (compose.yml + publish workflow) and "
        "update the Dockerfile COPY paths to match."
    )


def test_at_least_one_dockerfile_pair_was_discovered() -> None:
    """Sanity check: the discovery did not silently return nothing.

    If this fails, the Compose / workflow parsing logic is broken (or
    those files moved) and the parametrized contract above is not
    actually checking anything.
    """
    assert PAIRS_WITH_DOCKERFILE, (
        "No (build_context, dockerfile) pairs discovered from compose.yml "
        "or .github/workflows/publish-internal-images.yml. The contract "
        "above is a no-op until this is fixed."
    )
