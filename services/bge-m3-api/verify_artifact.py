"""Hash-verified artifact gate for the pinned BGE-M3 ONNX artifact (#3366).

Verifies a BGE-M3 artifact directory against its ``artifact_manifest.json``
before anything is baked into an image or loaded for inference. Missing
manifest/files and size or SHA-256 mismatches are hard failures with
actionable, non-secret diagnostics. Standard library only — this module must
stay importable from the runtime image, the Docker build, and the fetch tool.

Integrity is anchored to the repository pin (#3366 audit): in pinned mode the
caller supplies the trusted repository-committed manifest as the *expected*
artifact identity. The manifest found next to the downloaded bytes is treated
as input to compare — never as its own authority — so replacing model bytes
together with their folder manifest still fails against the unchanged pin.

CLI:
    python verify_artifact.py --dir DIR [--manifest PATH]
    python verify_artifact.py --dir DIR --expected-manifest REPO_PIN.json
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

# The pinned artifact contract is incomplete without all three vector outputs.
_PINNED_OUTPUTS = ("dense_vecs", "sparse_vecs", "colbert_vecs")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


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


def validate_pin_contract(manifest: dict) -> None:
    """Validate the format contract the repository pin must record.

    The trusted pin is only a pin if it names an immutable source revision and
    the approved three-output ONNX contract; anything less cannot anchor the
    artifact identity.

    Raises:
        ArtifactIntegrityError: revision missing/not a 40-hex sha, or the
            recorded outputs do not include every pinned vector family.
    """
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ArtifactIntegrityError("pinned manifest 'source' must be an object")
    revision = source.get("revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(char not in _HEX_DIGITS for char in revision)
    ):
        raise ArtifactIntegrityError(
            f"pinned manifest source.revision must be an immutable 40-hex sha, got {revision!r}"
        )
    artifact = manifest.get("artifact")
    outputs = artifact.get("outputs") if isinstance(artifact, dict) else None
    if not isinstance(outputs, list) or not all(name in outputs for name in _PINNED_OUTPUTS):
        raise ArtifactIntegrityError(
            "pinned manifest artifact.outputs must include all of: " + ", ".join(_PINNED_OUTPUTS)
        )


def _describe_manifest_diff(expected: dict, actual: dict) -> str:
    """Return a short, actionable summary of where two manifests differ."""
    parts: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        if key == "files":
            continue
        if expected.get(key) != actual.get(key):
            parts.append(f"{key} section differs")

    def _files_by_name(manifest: dict) -> dict[str, dict]:
        files: dict[str, dict] = {}
        for entry in manifest.get("files", []):
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                files[entry["name"]] = entry
        return files

    expected_files = _files_by_name(expected)
    actual_files = _files_by_name(actual)
    for name in sorted(set(expected_files) - set(actual_files)):
        parts.append(f"pin lists {name} but artifact manifest does not")
    for name in sorted(set(actual_files) - set(expected_files)):
        parts.append(f"artifact manifest lists unexpected file {name}")
    for name in sorted(set(expected_files) & set(actual_files)):
        changed = [
            field
            for field in sorted(set(expected_files[name]) | set(actual_files[name]))
            if expected_files[name].get(field) != actual_files[name].get(field)
        ]
        if changed:
            parts.append(f"{name}: changed {', '.join(changed)}")
    return "; ".join(parts) if parts else "content differs"


def _verify_files(artifact_dir: Path, manifest: dict) -> None:
    """Verify existence, byte size, and SHA-256 of every manifest-listed file."""
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


def _reject_extra_files(artifact_dir: Path, manifest: dict) -> None:
    """Reject any file in the artifact directory outside the pinned file set."""
    expected_names = {entry["name"] for entry in manifest["files"]}
    expected_names.add(ARTIFACT_MANIFEST_NAME)
    extras = []
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(artifact_dir).as_posix()
        if relative not in expected_names:
            extras.append(relative)
    if extras:
        shown = ", ".join(extras[:8]) + ("…" if len(extras) > 8 else "")
        raise ArtifactIntegrityError(
            f"unexpected extra file(s) in artifact directory: {shown}; "
            "the artifact directory must contain exactly the pinned file set"
        )


def _verify_pinned(artifact_dir: Path, pin_path: Path) -> dict:
    """Verify the artifact directory against the trusted repository pin.

    The pin manifest is the authority: the folder's own manifest must be
    semantically identical to it, files are verified against the pin's entries,
    and any extra file in the directory fails verification.
    """
    trusted = load_manifest(pin_path)
    validate_pin_contract(trusted)

    supplied = load_manifest(artifact_dir / ARTIFACT_MANIFEST_NAME)
    expected_revision = trusted["source"]["revision"]
    supplied_source = supplied.get("source")
    supplied_revision = (
        supplied_source.get("revision") if isinstance(supplied_source, dict) else None
    )
    if supplied_revision != expected_revision:
        raise ArtifactIntegrityError(
            f"artifact revision {supplied_revision!r} does not match the repository pin "
            f"revision {expected_revision!r}: refusing to bake or run unapproved model artifacts"
        )
    if supplied != trusted:
        raise ArtifactIntegrityError(
            "artifact manifest differs from the repository pin ("
            f"{_describe_manifest_diff(trusted, supplied)}): the manifest next to the "
            "downloaded bytes is input to compare, not its own authority; refusing to "
            "bake or run unapproved model artifacts"
        )

    _verify_files(artifact_dir, trusted)
    _reject_extra_files(artifact_dir, trusted)
    return trusted


def verify_artifact_dir(
    artifact_dir: str | Path,
    manifest_path: str | Path | None = None,
    *,
    expected_manifest: str | Path | None = None,
) -> dict:
    """Verify every manifest-listed file inside ``artifact_dir``.

    Without ``expected_manifest`` the manifest in (or next to) the artifact is
    the verification reference — plain self-consistency, used for fixture-level
    gates. Pass ``expected_manifest`` (the repository-committed pin) for the
    pinned boundary used by the Docker build, the fetch tool, and runtime:
    the folder manifest must then equal the pin, files must match the pin's
    sizes/hashes, and no extra file may exist. Returns the validated manifest
    dict so callers can inspect the pinned provenance (revision, ONNX
    contract, license).

    Raises:
        FileNotFoundError: manifest or any listed file is missing.
        ArtifactIntegrityError: size/hash mismatch, invalid manifest schema,
            pin/contract violation, or unexpected extra files.
    """
    artifact_dir = Path(artifact_dir)
    if expected_manifest is not None:
        return _verify_pinned(artifact_dir, Path(expected_manifest))
    if manifest_path is None:
        manifest_path = artifact_dir / ARTIFACT_MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    _verify_files(artifact_dir, manifest)
    return manifest


def verify_pinned_artifact(artifact_dir: str | Path, expected_manifest: str | Path) -> dict:
    """Verify ``artifact_dir`` against the trusted repository pin manifest.

    Named boundary for the Docker build, the fetch tool, and runtime startup:
    the artifact-folder manifest is compared against — never trusted as — the
    approved artifact identity (#3366).
    """
    return verify_artifact_dir(artifact_dir, expected_manifest=expected_manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a pinned BGE-M3 artifact directory")
    parser.add_argument("--dir", required=True, help="artifact directory to verify")
    parser.add_argument(
        "--manifest",
        default=None,
        help=f"manifest path (default: <dir>/{ARTIFACT_MANIFEST_NAME})",
    )
    parser.add_argument(
        "--expected-manifest",
        default=None,
        help=(
            "trusted repository pin manifest; the artifact folder's own manifest "
            "must equal it and files are verified against it (#3366)"
        ),
    )
    args = parser.parse_args(argv)
    try:
        if args.expected_manifest is not None:
            manifest = verify_artifact_dir(args.dir, expected_manifest=args.expected_manifest)
        else:
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
