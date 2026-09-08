"""Contract: Python runtime version matrix — guards intentional drift (#2623).

Supported Python matrix
-----------------------
| Component            | requires-python | Docker runtime | Justification                         |
|----------------------|-----------------|----------------|---------------------------------------|
| root / core / ingest | >=3.12          | 3.13           | Langfuse/pydantic.v1 compat; uv floor |
| telegram_bot         | (root >=3.12 — no own manifest, #3210) | 3.13 | Resolves from the root lock (--extra telegram) |
| services/bge-m3-api  | (no pyproject)  | 3.14           | Independent ML service; no Langfuse   |

This contract fails on:
- root requires-python below 3.12 (evaluated with PEP 440 semantics, #3446)
- a dev ``.python-version`` outside the 3.12 release line

The Langfuse-importing Docker runtime constraint (>=3.13) is enforced by
``test_dockerfile_runtime_policy_contract.py``. This contract covers the
pyproject-level floor only. ``telegram_bot`` has no manifest since #3210
(root lock is the single Telegram authority), so only the root floor and
the ``.python-version`` dev floor are asserted here.

Note: services/docling was removed in the Docling migration (phase_6508bc74ca4a);
its pyproject.toml row has been dropped from this matrix.

Validation semantics (#3446): specifier and version strings are parsed with the
toolchain-standard ``packaging`` implementation (PEP 440). The floor check never
compares version strings: the previous lexicographic check accepted ``>=3.9``
against a 3.12 floor because ``'3.9' >= '3.12'`` is ``True`` as a string
comparison. The semantic rule is: 3.12 must be inside the specifier set and
every 3.11.x probe must stay outside it; malformed or empty specifiers never
satisfy the floor.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


REPO_ROOT = Path(__file__).resolve().parents[2]

# Documented minimum Python floor per the matrix above
ROOT_REQUIRES_PYTHON_FLOOR = Version("3.12")

# Semantic floor probes (#3446): the floor release itself must be admitted, and
# probes from the release line immediately below the floor must be excluded.
_FLOOR_PROBE = Version("3.12")
_BELOW_FLOOR_PROBES = (Version("3.11"), Version("3.11.9"))


def _load_toml(rel: str) -> dict:
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} not found at {path}"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _satisfies_floor(requires_python: str) -> bool:
    """PEP 440 check: does the specifier set admit 3.12 while excluding 3.11.x?

    Uses the standard ``packaging`` implementation — no string comparison, no
    custom parser. Malformed or ambiguous specifiers never satisfy the floor.
    """
    try:
        spec = SpecifierSet(requires_python)
    except InvalidSpecifier:
        return False
    return _FLOOR_PROBE in spec and all(probe not in spec for probe in _BELOW_FLOOR_PROBES)


def test_root_requires_python_floor() -> None:
    """Root pyproject.toml requires-python must be >= 3.12 under PEP 440 (#2623)."""
    data = _load_toml("pyproject.toml")
    requires = data["project"]["requires-python"]
    assert _satisfies_floor(requires), (
        f"root pyproject.toml requires-python={requires!r}; "
        f"must be >={ROOT_REQUIRES_PYTHON_FLOOR} (#2623, #3446)"
    )


def test_python_version_file() -> None:
    """.python-version must be a 3.12.x release (local dev floor matches matrix)."""
    path = REPO_ROOT / ".python-version"
    assert path.is_file(), ".python-version not found"
    version = path.read_text(encoding="utf-8").strip()
    try:
        parsed = Version(version)
    except InvalidVersion:
        parsed = None
    assert parsed is not None and (parsed.major, parsed.minor) == (
        ROOT_REQUIRES_PYTHON_FLOOR.major,
        ROOT_REQUIRES_PYTHON_FLOOR.minor,
    ), f".python-version={version!r}; must be a 3.12.x release to match matrix floor (#2623, #3446)"


@pytest.mark.parametrize(
    ("specifier", "expected"),
    [
        (">=3.12", True),  # documented floor
        (">=3.12.0", True),  # zero-padded floor
        (">=3.12,<3.14", True),  # bounded equivalent of the floor
        (">=3.9", False),  # lexicographic false green (#3446)
        (">=3.11", False),  # 3.11 line is outside the floor
        (">3.11", False),  # still admits 3.11.x
        ("==3.9", False),  # pinned below the floor
        (">=3.9,<3.12", False),  # bounded below the floor
        ("", False),  # ambiguous: admits everything
        ("not-a-specifier", False),  # malformed
        (">=banana", False),  # malformed version inside a specifier
    ],
)
def test_floor_check_semantics(specifier: str, expected: bool) -> None:
    """The floor check must follow PEP 440 semantics, never string order."""
    assert _satisfies_floor(specifier) is expected, specifier


@pytest.mark.parametrize("requires", [">=3.9", ">=3.11", ">3.11", "==3.9", ">=3.9,<3.12"])
def test_contract_rejects_below_floor_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requires: str
) -> None:
    """False-green guard (#3446): a manifest below the floor must fail this contract.

    The previous lexicographic implementation accepted such manifests.
    """
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "probe"\nrequires-python = "{requires}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    with pytest.raises(AssertionError):
        test_root_requires_python_floor()


@pytest.mark.parametrize("requires", [">=3.12", ">=3.12,<3.14"])
def test_contract_accepts_floor_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requires: str
) -> None:
    """The contract must keep admitting the documented floor and its equivalents."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "probe"\nrequires-python = "{requires}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    test_root_requires_python_floor()  # must not raise
