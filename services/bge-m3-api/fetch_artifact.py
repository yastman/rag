"""Reproducible fetcher for the pinned BGE-M3 ONNX artifact (#3366).

Downloads every manifest-listed file from the immutable Hugging Face revision
(resuming completed files from an interrupted earlier run) and verifies the
result against the committed ``artifact_manifest.json`` used as the trusted
repository pin (sizes + SHA-256 + manifest equality) BEFORE declaring
success. The manifest copy inside the download folder is input to compare —
never its own authority (#3366 audit). Tokenizer entries record their
upstream ``remote`` path because the artifact layout nests them under
``tokenizer/`` while the upstream repo stores them at its root. This command
is a build/host-side provisioning tool: it is never imported by the
application and the container runtime never downloads anything.

Usage (from ``services/bge-m3-api/``):
    uv run python fetch_artifact.py --dest ../../logs/bge_m3_onnx_int8

Standard library only.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

from verify_artifact import ARTIFACT_MANIFEST_NAME, load_manifest, verify_artifact_dir


MANIFEST_PATH = Path(__file__).with_name(ARTIFACT_MANIFEST_NAME)
DEFAULT_DEST = Path("logs") / "bge_m3_onnx_int8"
HF_RESOLVE_URL_TEMPLATE = "https://huggingface.co/{repo_id}/resolve/{revision}/{name}"


def build_url(source: dict, name: str) -> str:
    """Return the immutable-revision resolve URL for one manifest file entry."""
    return HF_RESOLVE_URL_TEMPLATE.format(
        repo_id=source["repo_id"], revision=source["revision"], name=name
    )


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "rag-fresh-bge-artifact-fetch/1"})
    temporary = target.with_name(target.name + ".part")
    with urllib.request.urlopen(request) as response, temporary.open("wb") as sink:  # nosec B310 — pinned https URL from the committed manifest
        shutil.copyfileobj(response, sink, length=1024 * 1024)
    temporary.replace(target)


def fetch_artifact(dest: str | Path, manifest_path: str | Path = MANIFEST_PATH) -> Path:
    """Download and verify the pinned artifact into ``dest``; returns ``dest``.

    Files already present with the expected byte size (an interrupted earlier
    run) are kept and still hash-verified by the final pinned verification.
    Refuses to continue when the manifest is missing or any file fails the
    size/SHA-256/manifest-equality verification against the repository pin.
    """
    manifest = load_manifest(manifest_path)
    source = manifest["source"]
    if source.get("kind") != "huggingface":
        raise ValueError(f"unsupported artifact source kind: {source.get('kind')!r}")

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    # The manifest itself is part of the verified artifact (runtime re-verifies
    # it) — copied from the repository pin, never taken from the network.
    shutil.copyfile(Path(manifest_path), dest / ARTIFACT_MANIFEST_NAME)

    for entry in manifest["files"]:
        name = entry["name"]
        target = dest / name
        url = build_url(source, entry.get("remote", name))
        if target.is_file() and target.stat().st_size == entry["bytes"]:
            print(f"keep {name} ({entry['bytes']} bytes present; hash verified below)")
            continue
        print(f"fetch {url} -> {name}")
        _download(url, target)

    # Pinned verification: the repository-committed manifest is the authority;
    # the folder copy must equal it and every file must match its entries.
    verify_artifact_dir(dest, expected_manifest=manifest_path)
    print(f"ARTIFACT FETCHED AND VERIFIED: {dest} (revision {source['revision']})")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the pinned BGE-M3 artifact")
    parser.add_argument(
        "--dest",
        default=str(DEFAULT_DEST),
        help=f"target directory (default: {DEFAULT_DEST})",
    )
    parser.add_argument("--manifest", default=str(MANIFEST_PATH), help="manifest to fetch against")
    args = parser.parse_args(argv)
    try:
        fetch_artifact(args.dest, args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FETCH FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FETCH FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
