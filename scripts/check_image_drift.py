#!/usr/bin/env python3
"""Detect Docker image drift between compose config and running containers.

Compares image tags and digests pinned in docker-compose files against
the images actually used by running containers. Reports mismatches that
indicate stale containers running older/different image versions.

Usage:
    python scripts/check_image_drift.py                         # Human-readable
    python scripts/check_image_drift.py --json                  # JSON output
    python scripts/check_image_drift.py -f compose.vps.yml      # Custom file
    python scripts/check_image_drift.py --fix                   # Show fix commands

Exit codes:
    0 — no drift detected and at least one running container was checked
    1 — drift detected or no running containers were checked
    2 — error (compose file not found, docker not available)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# Regex to parse image references like:
#   redis:8.6.0@sha256:abc123...
#   langfuse/langfuse:3.153.0@sha256:abc123...
#   ghcr.io/berriai/litellm:main-v1.81.3-stable@sha256:abc123...
IMAGE_RE = re.compile(
    r"^(?P<name>[^:@]+)"
    r"(?::(?P<tag>[^@]+))?"
    r"(?:@(?P<digest>sha256:[a-f0-9]+))?$"
)


@dataclass
class ImageRef:
    """Parsed image reference."""

    raw: str
    name: str
    tag: str
    digest: str

    @classmethod
    def parse(cls, raw: str) -> ImageRef:
        m = IMAGE_RE.match(raw.strip())
        if not m:
            return cls(raw=raw, name=raw, tag="", digest="")
        return cls(
            raw=raw,
            name=m.group("name") or "",
            tag=m.group("tag") or "",
            digest=m.group("digest") or "",
        )


@dataclass
class DriftResult:
    """Single service drift check result."""

    service: str
    container: str
    expected_image: str
    expected_tag: str
    expected_digest: str
    actual_image: str
    actual_digest: str
    tag_match: bool
    digest_match: bool

    @property
    def has_drift(self) -> bool:
        # If expected has digest, compare digests; otherwise compare tags
        if self.expected_digest:
            return not self.digest_match
        return not self.tag_match


@dataclass
class DriftReport:
    """Aggregated drift findings."""

    compose_file: str
    checked: list[DriftResult] = field(default_factory=list)
    skipped_build: list[str] = field(default_factory=list)
    skipped_not_running: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def drifted(self) -> list[DriftResult]:
        return [r for r in self.checked if r.has_drift]

    @property
    def ok(self) -> list[DriftResult]:
        return [r for r in self.checked if not r.has_drift]

    @property
    def has_checked_containers(self) -> bool:
        return bool(self.checked)


def _run(cmd: list[str], *, check: bool = True) -> str:
    """Run a command and return stripped stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def get_compose_services(compose_file: str) -> dict[str, dict[str, object]]:
    """Parse compose file via `docker compose config` for normalized output."""
    try:
        out = _run(
            [
                "docker",
                "compose",
                "-f",
                compose_file,
                "config",
                "--format",
                "json",
            ]
        )
        data: dict[str, object] = json.loads(out)
        services: dict[str, dict[str, object]] = data.get("services", {})  # type: ignore[assignment]
        return services
    except subprocess.CalledProcessError as exc:
        print(f"Error: cannot parse {compose_file}: {exc.stderr}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError:
        print("Error: invalid JSON from docker compose config", file=sys.stderr)
        sys.exit(2)


def get_running_containers(compose_file: str) -> dict[str, dict]:
    """Get running containers for this compose project."""
    try:
        out = _run(
            [
                "docker",
                "compose",
                "-f",
                compose_file,
                "ps",
                "--format",
                "json",
            ],
            check=False,
        )
        if not out:
            return {}
        # docker compose ps --format json can return one JSON per line or an array
        containers = {}
        if out.startswith("["):
            items = json.loads(out)
        else:
            items = [json.loads(line) for line in out.splitlines() if line.strip()]
        for c in items:
            svc = c.get("Service", "")
            if svc:
                containers[svc] = c
        return containers
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


def get_container_image_digest(container_id: str) -> tuple[str, str]:
    """Get the image name and repo digest for a running container."""
    try:
        # Get image name
        image = _run(
            [
                "docker",
                "inspect",
                container_id,
                "--format",
                "{{.Config.Image}}",
            ]
        )

        # Get image ID, then inspect the image for RepoDigests
        image_id = _run(
            [
                "docker",
                "inspect",
                container_id,
                "--format",
                "{{.Image}}",
            ]
        )
        repo_digests_raw = _run(
            [
                "docker",
                "image",
                "inspect",
                image_id,
                "--format",
                "{{json .RepoDigests}}",
            ],
            check=False,
        )

        digests: list[str] = json.loads(repo_digests_raw) if repo_digests_raw else []

        # Extract sha256 digest from RepoDigests
        digest = ""
        for d in digests:
            if "@sha256:" in d:
                digest = "sha256:" + d.split("@sha256:")[1]
                break

        return image, digest
    except subprocess.CalledProcessError:
        return "", ""


def check_drift(compose_file: str) -> DriftReport:
    """Compare compose-pinned images against running containers."""
    report = DriftReport(compose_file=compose_file)

    services = get_compose_services(compose_file)
    containers = get_running_containers(compose_file)

    for svc_name, svc_config in sorted(services.items()):
        image_str = svc_config.get("image", "")
        has_build = "build" in svc_config

        # Skip custom-built services
        if not image_str or has_build:
            report.skipped_build.append(svc_name)
            continue

        # Check if container is running
        container = containers.get(svc_name)
        if not container:
            report.skipped_not_running.append(svc_name)
            continue

        expected = ImageRef.parse(image_str)
        container_id = container.get("ID", container.get("Name", ""))

        actual_image, actual_digest = get_container_image_digest(container_id)
        actual = ImageRef.parse(actual_image)

        # Compare tag (from image name)
        tag_match = not expected.tag or expected.tag == actual.tag
        # Compare digest
        digest_match = not expected.digest or expected.digest == actual_digest

        result = DriftResult(
            service=svc_name,
            container=container_id,
            expected_image=image_str,
            expected_tag=expected.tag,
            expected_digest=expected.digest,
            actual_image=actual_image,
            actual_digest=actual_digest,
            tag_match=tag_match,
            digest_match=digest_match,
        )
        report.checked.append(result)

    return report


def print_report(report: DriftReport, *, show_fix: bool = False) -> None:
    """Print human-readable report."""
    compose = report.compose_file

    # Header
    print(f"\n{'=' * 60}")
    print(f"  Image Drift Report: {compose}")
    print(f"{'=' * 60}")

    # OK services
    if report.ok:
        print(f"\n\033[32m✓ {len(report.ok)} services match pinned images:\033[0m")
        for r in report.ok:
            tag = r.expected_tag or "latest"
            print(f"  {r.service:25s} {tag}")

    # Drifted services
    if report.drifted:
        print(f"\n\033[31m✗ {len(report.drifted)} services have image drift:\033[0m")
        for r in report.drifted:
            print(f"\n  \033[1m{r.service}\033[0m")
            print(f"    Expected: {r.expected_tag or 'latest'}")
            if r.expected_digest:
                print(f"    Pinned:   {r.expected_digest[:20]}...")
            print(f"    Running:  {r.actual_image}")
            if r.actual_digest:
                print(f"    Digest:   {r.actual_digest[:20]}...")
            else:
                print("    Digest:   (not available)")

            if not r.tag_match:
                print("    \033[31m→ Tag mismatch\033[0m")
            if r.expected_digest and not r.digest_match:
                print("    \033[31m→ Digest mismatch\033[0m")

    # Skipped
    if report.skipped_build:
        print(f"\n\033[33m⊘ {len(report.skipped_build)} custom-build services (skipped):\033[0m")
        print(f"  {', '.join(report.skipped_build)}")

    if report.skipped_not_running:
        print(
            f"\n\033[33m⊘ {len(report.skipped_not_running)} services not running (skipped):\033[0m"
        )
        print(f"  {', '.join(report.skipped_not_running)}")

    # Fix commands
    if show_fix and report.drifted:
        drifted_names = [r.service for r in report.drifted]
        names_str = " ".join(drifted_names)
        print("\n\033[36mFix commands:\033[0m")
        print("  # Pull fresh images")
        print(f"  docker compose -f {compose} pull {names_str}")
        print("  # Recreate drifted containers")
        print(f"  docker compose -f {compose} up -d --force-recreate {names_str}")
        print("  # Or recreate all:")
        print(f"  docker compose -f {compose} down --remove-orphans")
        print(f"  docker compose -f {compose} pull")
        print(f"  docker compose -f {compose} up -d")

    # Summary
    print(f"\n{'─' * 60}")
    total = len(report.checked)
    ok = len(report.ok)
    drifted = len(report.drifted)
    print(f"  Checked: {total}  OK: {ok}  Drifted: {drifted}")
    if drifted:
        print("  \033[31mResult: DRIFT DETECTED\033[0m")
    elif total:
        print("  \033[32mResult: ALL IMAGES MATCH\033[0m")
    else:
        print("  \033[33mResult: NO RUNNING CONTAINERS TO CHECK\033[0m")
    print()


def print_json(report: DriftReport) -> None:
    """Print JSON output."""
    data = {
        "compose_file": report.compose_file,
        "checked": [
            {
                "service": r.service,
                "expected_image": r.expected_image,
                "expected_tag": r.expected_tag,
                "expected_digest": r.expected_digest,
                "actual_image": r.actual_image,
                "actual_digest": r.actual_digest,
                "tag_match": r.tag_match,
                "digest_match": r.digest_match,
                "has_drift": r.has_drift,
            }
            for r in report.checked
        ],
        "skipped_build": report.skipped_build,
        "skipped_not_running": report.skipped_not_running,
        "summary": {
            "total": len(report.checked),
            "ok": len(report.ok),
            "drifted": len(report.drifted),
        },
    }
    print(json.dumps(data, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect Docker image drift between compose config and running containers.",
    )
    parser.add_argument(
        "-f",
        "--file",
        default="compose.yml",
        help="Compose file to check (default: compose.yml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Show fix commands for drifted services",
    )
    args = parser.parse_args()

    compose_path = Path(args.file)
    if not compose_path.exists():
        print(f"Error: {args.file} not found", file=sys.stderr)
        sys.exit(2)

    # Verify docker is available (lightweight check)
    try:
        _run(["docker", "version", "--format", "{{.Server.Version}}"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: docker is not available or not running", file=sys.stderr)
        sys.exit(2)

    report = check_drift(args.file)

    if args.json_output:
        print_json(report)
    else:
        print_report(report, show_fix=args.fix)

    sys.exit(1 if report.drifted or not report.has_checked_containers else 0)


if __name__ == "__main__":
    main()
