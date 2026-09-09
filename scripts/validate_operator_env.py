"""Explicit operator environment gate for real full-stack commands (#3367).

Validates the operator env file *before* Compose runs so a failing stack can
never look like a successful start:

1. The env file exists (real build/up commands never fall back to the CI
   fixture ``tests/fixtures/compose.ci.env`` — that file carries dummy
   credentials and an intentionally invalid 41-byte BGE context).
2. Required secrets are present with a plausible shape — checked by name and
   pattern only: secret values are never printed.
3. Host paths (``BGE_M3_ONNX_MODEL_HOST_DIR``, ``GDRIVE_SYNC_DIR``) use native
   path semantics for the host running Docker: WSL/POSIX paths on native
   Windows and Windows drive-letter paths on POSIX hosts are rejected.
4. The BGE-M3 ONNX artifact directory is verified against the repository pin
   manifest (``services/bge-m3-api/artifact_manifest.json``) via the #3366
   hash verifier, so an invalid or substituted model fails before an image
   build can consume it.

Every failure is reported as an actionable ``- KEY: reason`` line and the
process exits nonzero. Standard library only.

CLI::

    python scripts/validate_operator_env.py --env-file .env
    python scripts/validate_operator_env.py --env-file .env \\
        --pin-manifest /path/to/artifact_manifest.json   # tests only; the
        # Makefile gate always uses the repository pin (default)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "services" / "bge-m3-api" / "verify_artifact.py"
DEFAULT_PIN_MANIFEST = REPO_ROOT / "services" / "bge-m3-api" / "artifact_manifest.json"

# sha256 of the dummy Telegram token carried by tests/fixtures/compose.ci.env
# ("123456789:ABC..."). Stored as a digest so no dummy credential is embedded
# in source, and the value is never printable in diagnostics.
KNOWN_CI_DUMMY_TOKEN_SHA256 = "14dce256a2d15778e073c0155363a40dabc05c4d9f0e138724518da142a9b524"

REQUIRED_KEYS: tuple[str, ...] = (
    "TELEGRAM_BOT_TOKEN",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "ENCRYPTION_KEY",
    "SALT",
    "NEXTAUTH_SECRET",
    "BGE_M3_ONNX_MODEL_HOST_DIR",
)
LLM_KEY_CHOICES: tuple[str, ...] = (
    "CEREBRAS_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "LLM_API_KEY",
)
OPTIONAL_PATH_KEYS: tuple[str, ...] = ("GDRIVE_SYNC_DIR",)

TELEGRAM_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
# A Windows drive-letter absolute path accepts either slash style (Docker
# Desktop handles both; .env.example documents the forward-slash form).
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
# A WSL bind path (/mnt/c/...) — valid inside WSL, unusable by Docker Desktop
# running natively on Windows.
WSL_MNT_RE = re.compile(r"^/mnt/[A-Za-z]/")

# Substrings that mark a value as a CI fixture / template placeholder rather
# than a real operator credential.
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "change-me",
    "placeholder",
    "ci-only",
    "dummy",
    "example-key",
)
# compose.ci.env's POSTGRES_PASSWORD value.
CI_DUMMY_POSTGRES_PASSWORD = "postgres"

WINDOWS_PATH_EXAMPLE = "C:/models/bge_m3_onnx_int8"
POSIX_PATH_EXAMPLE = "/srv/models/bge_m3_onnx_int8"


def parse_env_file(env_path: Path) -> tuple[dict[str, str], list[str]]:
    """Parse a dotenv file into KEY/VALUE pairs.

    Mirrors the Compose dotenv conventions that matter here: full-line
    ``#`` comments, inline `` #`` comments on unquoted values, and optional
    single/double quoting. Never includes values in parse-error text.
    """
    values: dict[str, str] = {}
    problems: list[str] = []
    for number, raw in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            problems.append(
                f"  - line {number}: malformed entry (expected KEY=VALUE; "
                "the line content is not shown because it may hold a secret)"
            )
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            problems.append(f"  - line {number}: empty variable name")
            continue
        # Inline comment on an unquoted value (Compose dotenv behavior).
        if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
            value = value[1:-1]
        else:
            hash_index = value.find(" #")
            if hash_index != -1:
                value = value[:hash_index]
            value = value.strip()
        values[key] = value
    return values, problems


def _is_known_dummy(key: str, value: str) -> bool:
    """Return True when the value is a documented CI fixture credential."""
    if key == "TELEGRAM_BOT_TOKEN":
        return hashlib.sha256(value.encode("utf-8")).hexdigest() == (KNOWN_CI_DUMMY_TOKEN_SHA256)
    if key == "POSTGRES_PASSWORD":
        return value == CI_DUMMY_POSTGRES_PASSWORD
    if key == "ENCRYPTION_KEY":
        return set(value) == {"0"}
    return False


def _placeholder_reason(value: str) -> str | None:
    lowered = value.lower()
    if lowered.startswith("test-"):
        return "looks like a CI fixture value (starts with 'test-')"
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            return f"looks like a template placeholder (contains '{marker}')"
    return None


def _shape_problems(key: str, value: str) -> list[str]:
    problems: list[str] = []
    if not value:
        return [f"  - {key}: is empty (set a real operator value)"]
    if reason := _placeholder_reason(value):
        return [f"  - {key}: {reason}"]
    if _is_known_dummy(key, value):
        return [
            f"  - {key}: matches the known CI dummy credential; real operator "
            "credentials are required (#3367)"
        ]
    if key == "TELEGRAM_BOT_TOKEN" and not TELEGRAM_TOKEN_RE.match(value):
        problems.append(
            f"  - {key}: expected shape '<digits>:<>=30 token characters' "
            "(Telegram bot token format); value not shown"
        )
    if key == "ENCRYPTION_KEY" and not HEX64_RE.match(value):
        problems.append(
            f"  - {key}: must be 64 hex characters (generate with: openssl rand -hex 32)"
        )
    if key in {"SALT", "NEXTAUTH_SECRET"} and len(value) < 16:
        problems.append(
            f"  - {key}: too short (minimum 16 characters; generate with: openssl rand -base64 32)"
        )
    if key in {"POSTGRES_PASSWORD", "REDIS_PASSWORD"}:
        if len(value) < 8:
            problems.append(f"  - {key}: too short (minimum 8 characters)")
        elif any(char.isspace() for char in value):
            problems.append(f"  - {key}: must not contain whitespace")
    if key in LLM_KEY_CHOICES and len(value) < 8:
        problems.append(f"  - {key}: too short to be a provider API key")
    return problems


def _native_path_problem(key: str, raw: str) -> str | None:
    """Return a problem line when the path form is not native to this host."""
    is_windows_host = os_name() == "nt"
    if raw.startswith("~"):
        return (
            f"  - {key}: '~' paths are not expanded by Compose; use an explicit "
            f"path (POSIX example: {POSIX_PATH_EXAMPLE}, Windows example: "
            f"{WINDOWS_PATH_EXAMPLE})"
        )
    if WINDOWS_DRIVE_RE.match(raw):
        if is_windows_host:
            return None
        return (
            f"  - {key}: Windows drive-letter path '{raw}' is not native on this "
            f"POSIX host; use an absolute POSIX path (example: {POSIX_PATH_EXAMPLE})"
        )
    if raw.startswith("/"):
        if not is_windows_host:
            return None
        if WSL_MNT_RE.match(raw):
            return (
                f"  - {key}: WSL path '{raw}' is not native on Windows Docker "
                "Desktop; use the Windows path form (example: "
                f"{WINDOWS_PATH_EXAMPLE})"
            )
        return (
            f"  - {key}: POSIX-absolute path '{raw}' is not a native Windows "
            "path; use a drive-letter path (example: "
            f"{WINDOWS_PATH_EXAMPLE})"
        )
    return None  # Repo-relative paths are resolved against the repo root.


def os_name() -> str:
    """Platform selector (separated for testability)."""
    return os.name


def _resolve_repo_relative(raw: str) -> Path:
    """Resolve a repo-relative path the way Compose resolves bind sources.

    Compose resolves relative paths against the project directory (the repo
    root), which is also where ``make`` invokes this validator from.
    """
    return (REPO_ROOT / raw).resolve()


def _resolve_host_path(raw: str) -> Path:
    """Resolve an operator path to its host location (native or repo-relative)."""
    if WINDOWS_DRIVE_RE.match(raw) or raw.startswith("/"):
        return Path(raw)
    return _resolve_repo_relative(raw)


def _path_problems(key: str, raw: str, label: str) -> list[str]:
    """Native-semantics + existence checks for one operator host path."""
    native_problem = _native_path_problem(key, raw)
    if native_problem is not None:
        return [native_problem]
    resolved = _resolve_host_path(raw)
    if not resolved.is_dir():
        return [f"  - {key}: {label} directory does not exist: {resolved}"]
    return []


def _bge_artifact_problems(bge_dir: Path, pin_manifest: Path) -> list[str]:
    """Verify the artifact against the pin via the #3366 hash verifier."""
    print(
        "Verifying the BGE-M3 artifact against the repository pin "
        "(hashes the model files; the pinned artifact is ~6.8 GB)...",
        flush=True,
    )
    if not pin_manifest.is_file():
        return [f"  - BGE_M3_ONNX_MODEL_HOST_DIR: repository pin manifest missing: {pin_manifest}"]
    proc = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--dir",
            str(bge_dir),
            "--expected-manifest",
            str(pin_manifest),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        detail = (proc.stderr.strip() or proc.stdout.strip() or "unknown error").splitlines()
        shown = detail[0] if detail else "unknown error"
        return [
            "  - BGE_M3_ONNX_MODEL_HOST_DIR: pinned-artifact verification failed: "
            f"{shown} (fetch the pinned artifact with "
            "services/bge-m3-api/fetch_artifact.py; see services/bge-m3-api/README.md)"
        ]
    print(proc.stdout.strip(), flush=True)
    return []


def validate(
    env_path: Path,
    pin_manifest: Path = DEFAULT_PIN_MANIFEST,
) -> list[str]:
    """Return the list of problem lines for the operator env file."""
    problems: list[str] = []
    if not env_path.is_file():
        return [
            f"operator env file not found: {env_path}",
            "  Real build/up commands never fall back to CI fixtures (#3367).",
            "  Fix: cp .env.example .env, fill in the required values,",
            "  then re-run this command (or pass OPERATOR_ENV=/path/to/env).",
        ]

    values, parse_problems = parse_env_file(env_path)
    problems.extend(parse_problems)

    missing = [key for key in REQUIRED_KEYS if key not in values]
    for key in missing:
        problems.append(f"  - {key}: missing (required for the full operator stack)")

    if not any(key in values and values[key].strip() for key in LLM_KEY_CHOICES):
        problems.append(
            "  - LLM provider key: missing; set at least one of " + ", ".join(LLM_KEY_CHOICES)
        )

    for key in REQUIRED_KEYS:
        if key in values:
            problems.extend(_shape_problems(key, values[key]))
    for key in LLM_KEY_CHOICES:
        if key in values:
            problems.extend(_shape_problems(key, values[key]))

    bge_dir: Path | None = None
    bge_raw = values.get("BGE_M3_ONNX_MODEL_HOST_DIR", "").strip()
    if bge_raw:
        bge_problems = _path_problems("BGE_M3_ONNX_MODEL_HOST_DIR", bge_raw, "BGE-M3 artifact")
        problems.extend(bge_problems)
        if not bge_problems:
            bge_dir = _resolve_host_path(bge_raw)

    for key in OPTIONAL_PATH_KEYS:
        raw = values.get(key, "").strip()
        if raw:
            problems.extend(_path_problems(key, raw, "Google Drive sync"))

    if bge_dir is not None:
        problems.extend(_bge_artifact_problems(bge_dir, pin_manifest))

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the explicit operator env file before Compose build/up "
            "(#3367): existence, required secret shape (values are never "
            "printed), native host path semantics, and the pinned BGE-M3 "
            "artifact hash."
        )
    )
    parser.add_argument(
        "--env-file",
        required=True,
        help="operator env file to validate (Makefile default: .env via OPERATOR_ENV)",
    )
    parser.add_argument(
        "--pin-manifest",
        default=str(DEFAULT_PIN_MANIFEST),
        help=(
            "trusted repository pin manifest for the BGE-M3 artifact; the "
            "Makefile gate always uses the repository default"
        ),
    )
    args = parser.parse_args(argv)

    env_path = Path(args.env_file)
    print(f"Validating operator env: {env_path}")
    problems = validate(env_path, Path(args.pin_manifest))
    if problems:
        print("OPERATOR ENV INVALID — fix the following before build/up:", file=sys.stderr)
        for line in problems:
            print(line, file=sys.stderr)
        print(
            f"Exiting nonzero: {len(problems)} problem(s) in {env_path}. "
            "Secret values are never printed.",
            file=sys.stderr,
        )
        return 1
    print(f"OPERATOR ENV OK: {env_path}")
    print(
        "Required secrets present with a valid shape, host paths are native "
        "and exist, and the BGE-M3 artifact matches the repository pin."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
