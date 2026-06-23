"""Bidirectional compose-observe coverage contract (#2219).

Closes the Epic A class of bug from #2210 / #2229. The pattern was:

* a new micro-service in ``services/<X>/`` declared ``@observe(...)``
  decorators in its FastAPI app;
* the corresponding compose service in ``compose.yml`` and
  ``compose.dev.yml`` did NOT receive ``LANGFUSE_PUBLIC_KEY``,
  ``LANGFUSE_SECRET_KEY``, ``LANGFUSE_HOST``, ``OTEL_SERVICE_NAME``;
* the Langfuse SDK silently no-op'd at startup;
* every ``@observe`` span landed in the void with zero log signal.

The pre-existing ``tests/unit/test_compose_langfuse.py`` parametrises a
hardcoded ``TRACED_SERVICES`` list. That keeps the existing services
honest, but a *new* micro-service can be added with ``@observe`` and
zero compose env, and the test will pass because the new service is
not in the list. This contract closes the gap by walking the actual
source tree.

Two assertions:

1. **Source -> compose**: every directory listed in
   ``services_with_observe`` of ``trace_contract.yaml`` must have
   ``@observe`` decorators in production code (sanity — keeps the
   YAML honest).
2. **Compose -> source**: every directory under ``services/`` that
   contains ``@observe`` decorators must be listed in
   ``services_with_observe``, and the listed compose service must
   carry the four required env vars in **both** ``compose.yml`` and
   ``compose.dev.yml``.

Together, they make Epic A class regressions structurally impossible:
adding ``@observe`` to a new service without compose env will fail
this test on CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "tests" / "observability" / "trace_contract.yaml"
BASE_COMPOSE = REPO_ROOT / "compose.yml"
DEV_COMPOSE = REPO_ROOT / "compose.dev.yml"


REQUIRED_LANGFUSE_VARS = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "OTEL_SERVICE_NAME",
)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _get_service_env(compose: dict, service: str) -> dict[str, str]:
    """Extract environment dict from a compose service.

    Compose ``environment`` may be a mapping or a list of ``"VAR=value"``
    entries. Normalize both shapes to a mapping.
    """
    svc = compose["services"].get(service) or {}
    env = svc.get("environment", {})
    if isinstance(env, list):
        return {
            item.split("=", 1)[0]: (item.split("=", 1)[1] if "=" in item else "") for item in env
        }
    return env or {}


def _has_observe_decorator_anywhere(root: Path) -> bool:
    """Return True if ``root`` contains any ``@observe(...)`` decorator
    in production code (excluding tests, archives, and venv).

    Uses AST walk so commented-out decorators are not counted.
    """
    if not root.exists():
        return False

    for py_file in root.rglob("*.py"):
        # Skip test fixtures and venv
        path_str = str(py_file)
        if any(skip in path_str for skip in ("/tests/", "/.venv/", "/__pycache__/", "/archive/")):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for dec in node.decorator_list:
                    name = _decorator_name(dec)
                    if name == "observe":
                        return True
    return False


def _decorator_name(dec: ast.expr) -> str | None:
    """Return the simple name of a decorator (``observe`` for both
    ``@observe`` and ``@observe(name="...")``)."""
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return None


@pytest.fixture(scope="module")
def contract() -> dict:
    return _load_yaml(CONTRACT_PATH)


@pytest.fixture(scope="module")
def services_with_observe(contract: dict) -> dict[str, dict[str, str]]:
    section = contract.get("services_with_observe")
    assert section, (
        "trace_contract.yaml must declare a non-empty `services_with_observe` "
        "section. See #2219 for the schema."
    )
    return section


@pytest.fixture(scope="module")
def compose_base() -> dict:
    return _load_yaml(BASE_COMPOSE)


@pytest.fixture(scope="module")
def compose_dev() -> dict:
    return _load_yaml(DEV_COMPOSE)


# ---------------------------------------------------------------------------
# Direction 1: every YAML entry actually contains @observe in source
# ---------------------------------------------------------------------------


class TestServicesWithObserveYamlIsHonest:
    def test_each_listed_source_root_has_observe_decorators(
        self, services_with_observe: dict[str, dict[str, str]]
    ) -> None:
        missing: list[tuple[str, str]] = []
        for entry, meta in services_with_observe.items():
            root = REPO_ROOT / meta["source_root"]
            if not _has_observe_decorator_anywhere(root):
                missing.append((entry, meta["source_root"]))

        assert not missing, (
            "trace_contract.yaml::services_with_observe lists source roots "
            "that no longer contain @observe decorators (stale entry?):\n"
            + "\n".join(f"  - {entry} -> {root}" for entry, root in missing)
        )

    @pytest.mark.parametrize(
        "var",
        REQUIRED_LANGFUSE_VARS,
    )
    def test_each_listed_compose_service_has_required_env_in_base(
        self,
        services_with_observe: dict[str, dict[str, str]],
        compose_base: dict,
        var: str,
    ) -> None:
        """Bidirectional check: every entry in services_with_observe must
        receive each LANGFUSE_* + OTEL_SERVICE_NAME var in compose.yml."""
        missing: list[str] = []
        for entry, meta in services_with_observe.items():
            compose_service = meta["compose_service"]
            env = _get_service_env(compose_base, compose_service)
            if var not in env:
                missing.append(f"{compose_service} (entry {entry!r})")

        assert not missing, (
            f"compose.yml: services with @observe decorators missing {var}:\n"
            + "\n".join(f"  - {svc}" for svc in missing)
            + f"\n\nWithout {var} the Langfuse v4 SDK no-ops at startup and "
            "every @observe span drops silently. Mirror the pattern from "
            "the bge-m3 service (#2229 commit 15a95e7)."
        )

    @pytest.mark.parametrize(
        "var",
        ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "OTEL_SERVICE_NAME"),
    )
    def test_each_listed_compose_service_has_required_env_in_dev(
        self,
        services_with_observe: dict[str, dict[str, str]],
        compose_dev: dict,
        var: str,
    ) -> None:
        """compose.dev.yml may inherit LANGFUSE_HOST from base but must
        explicitly carry public/secret/service-name dev defaults."""
        missing: list[str] = []
        for entry, meta in services_with_observe.items():
            compose_service = meta["compose_service"]
            env = _get_service_env(compose_dev, compose_service)
            if var not in env:
                missing.append(f"{compose_service} (entry {entry!r})")

        assert not missing, (
            f"compose.dev.yml: services with @observe decorators missing {var}:\n"
            + "\n".join(f"  - {svc}" for svc in missing)
        )

    def test_each_listed_compose_service_has_resource_attributes(
        self,
        services_with_observe: dict[str, dict[str, str]],
        compose_base: dict,
    ) -> None:
        """Every traced service must carry OTEL_RESOURCE_ATTRIBUTES so spans
        get service.version / service.namespace / deployment.environment for
        Langfuse "Aggregate by version" + multi-instance triage (#2227).

        Closes the contract drift where
        test_env_example_completeness_contract.py claimed the var was "set
        per-service in compose" but no compose service actually carried it.
        """
        missing: list[str] = []
        for entry, meta in services_with_observe.items():
            compose_service = meta["compose_service"]
            env = _get_service_env(compose_base, compose_service)
            if "OTEL_RESOURCE_ATTRIBUTES" not in env:
                missing.append(f"{compose_service} (entry {entry!r})")

        assert not missing, (
            "compose.yml: services with @observe decorators missing "
            "OTEL_RESOURCE_ATTRIBUTES:\n"
            + "\n".join(f"  - {svc}" for svc in missing)
            + "\n\nAdd OTEL_RESOURCE_ATTRIBUTES so every span carries "
            "service.version / service.namespace / deployment.environment "
            "(#2227). The OTEL SDK reads this env var natively."
        )


# ---------------------------------------------------------------------------
# Direction 2: every services/<X>/ with @observe is listed in YAML
# ---------------------------------------------------------------------------


class TestNoUntrackedObserveServices:
    def test_every_services_subdir_with_observe_is_listed(
        self, services_with_observe: dict[str, dict[str, str]]
    ) -> None:
        services_root = REPO_ROOT / "services"
        if not services_root.exists():
            pytest.skip("services/ directory not present")

        listed_roots = {meta["source_root"] for meta in services_with_observe.values()}

        untracked: list[str] = []
        for sub in services_root.iterdir():
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            relative = sub.relative_to(REPO_ROOT).as_posix()
            if not _has_observe_decorator_anywhere(sub):
                continue
            if relative not in listed_roots:
                untracked.append(relative)

        assert not untracked, (
            "Found services/ subdirectories with @observe decorators that "
            "are NOT listed in trace_contract.yaml::services_with_observe:\n"
            + "\n".join(f"  - {p}" for p in untracked)
            + "\n\nA new micro-service with @observe must:\n"
            "  1. add an entry in trace_contract.yaml::services_with_observe;\n"
            "  2. wire LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST + OTEL_SERVICE_NAME\n"
            "     in both compose.yml and compose.dev.yml (mirror bge-m3 from\n"
            "     #2229 commit 15a95e7)."
        )
