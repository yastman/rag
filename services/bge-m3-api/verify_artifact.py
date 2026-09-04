"""Hash-verified artifact gate for the pinned BGE-M3 ONNX artifact (#3366).

Verifies a BGE-M3 artifact directory against its ``artifact_manifest.json``
before anything is baked into an image or loaded for inference. Missing
manifest/files and size or SHA-256 mismatches are hard failures with
actionable, non-secret diagnostics. Standard library only — this module must
stay importable from the runtime image, the Docker build, and the fetch tool.

CLI:
    python verify_artifact.py --dir DIR [--manifest PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ARTIFACT_MANIFEST_NAME = "artifact_manifest.json"

# Every manifest entry must carry these fields (files[] entries).
_REQUIRED_FILE_FIELDS = ("name", "role", "bytes", "sha256")
_REQUIRED_MANIFEST_SECTIONS = ("schema_version", "artifact", "source", "upstream_model", "files")


class ArtifactIntegrityError(RuntimeError):
    """Artifact manifest or content failed verification."""


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# The artifact contract is incomplete without every required role.
_REQUIRED_ROLES = ("model", "external_data", "tokenizer")


def load_manifest(manifest_path: str | Path) -> dict:
    """Load and schema-check an artifact manifest.

    Raises:
        FileNotFoundError: manifest file missing.
        ArtifactIntegrityError: unreadable JSON or missing required sections.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"artifact manifest not found: {manifest_path.name} "
            f"(expected a hash-verified BGE-M3 artifact; see services/bge-m3-api/README.md "
            f"for the fetch command)"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError(f"artifact manifest unreadable: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ArtifactIntegrityError("artifact manifest must be a JSON object")
    missing = [section for section in _REQUIRED_MANIFEST_SECTIONS if section not in manifest]
    if missing:
        raise ArtifactIntegrityError(
            f"artifact manifest missing required sections: {', '.join(missing)}"
        )
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise ArtifactIntegrityError("artifact manifest 'files' must be a non-empty list")
    for entry in files:
        if not isinstance(entry, dict):
            raise ArtifactIntegrityError("artifact manifest 'files' entries must be objects")
        absent = [field for field in _REQUIRED_FILE_FIELDS if field not in entry]
        if absent:
            raise ArtifactIntegrityError(
                f"artifact manifest entry missing fields: {', '.join(absent)}"
            )
    present_roles = {entry["role"] for entry in files}
    absent_roles = [role for role in _REQUIRED_ROLES if role not in present_roles]
    if absent_roles:
        raise ArtifactIntegrityError(
            f"artifact manifest incomplete: no file with role {', '.join(absent_roles)}"
        )
    return manifest


def verify_artifact_dir(artifact_dir: str | Path, manifest_path: str | Path | None = None) -> dict:
    """Verify every manifest-listed file inside ``artifact_dir``.

    Checks existence, exact byte size, and SHA-256 for each ``files[]`` entry.
    Returns the validated manifest dict so callers can inspect the pinned
    provenance (revision, ONNX contract, license).

    Raises:
        FileNotFoundError: manifest or any listed file is missing.
        ArtifactIntegrityError: size/hash mismatch or invalid manifest schema.
    """
    artifact_dir = Path(artifact_dir)
    if manifest_path is None:
        manifest_path = artifact_dir / ARTIFACT_MANIFEST_NAME
    manifest = load_manifest(manifest_path)

    seen_names: set[str] = set()
    for entry in manifest["files"]:
        name = entry["name"]
        if name in seen_names:
            raise ArtifactIntegrityError(f"artifact manifest lists duplicate file: {name}")
        seen_names.add(name)

        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ArtifactIntegrityError(f"artifact manifest entry must be relative: {name}")
        target = artifact_dir / relative
        if not target.is_file():
            raise FileNotFoundError(f"artifact file missing: {name}")

        actual_size = target.stat().st_size
        expected_size = entry["bytes"]
        if actual_size != expected_size:
            raise ArtifactIntegrityError(
                f"artifact byte size mismatch for {name}: expected {expected_size}, got {actual_size}"
            )

        actual_hash = _sha256_of(target)
        expected_hash = entry["sha256"]
        if actual_hash != expected_hash:
            raise ArtifactIntegrityError(
                f"artifact sha256 mismatch for {name}: expected {expected_hash[:12]}…, "
                f"got {actual_hash[:12]}… (refusing to run on unverified model artifacts)"
            )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a pinned BGE-M3 artifact directory")
    parser.add_argument("--dir", required=True, help="artifact directory to verify")
    parser.add_argument(
        "--manifest",
        default=None,
        help=f"manifest path (default: <dir>/{ARTIFACT_MANIFEST_NAME})",
    )
    args = parser.parse_args(argv)
    try:
        manifest = verify_artifact_dir(args.dir, args.manifest)
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        print(f"ARTIFACT VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1
    source = manifest["source"]
    print(f"revision: {source.get('revision', '?')}")
    for entry in manifest["files"]:
        print(f"  ok {entry['name']} ({entry['bytes']} bytes, sha256 {entry['sha256'][:12]}…)")
    print("ARTIFACT VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
