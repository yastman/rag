"""Docker compose profile/port validation tests (#555)."""

from __future__ import annotations

from pathlib import Path

import yaml


_BASE_COMPOSE_PATH = Path("compose.yml")
_DEV_OVERRIDE_PATH = Path("compose.dev.yml")


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _effective_services() -> dict[str, dict]:
    """Build lightweight effective service view for dev (base + dev override)."""
    base = _load_compose(_BASE_COMPOSE_PATH)
    override = _load_compose(_DEV_OVERRIDE_PATH)

    services = {name: dict(cfg) for name, cfg in base.get("services", {}).items()}
    for service_name, override_cfg in override.get("services", {}).items():
        merged = dict(services.get(service_name, {}))
        merged.update(override_cfg)
        services[service_name] = merged
    return services


def _extract_host_port(port_mapping: str) -> str | None:
    """Extract host port from docker compose short syntax."""
    # Examples:
    # - "6333:6333"
    # - "127.0.0.1:6333:6333"
    # - "6333:6333/tcp"
    port_mapping = str(port_mapping).strip().strip('"').strip("'")
    if not port_mapping:
        return None

    left = port_mapping.split("/")[0]
    parts = left.split(":")
    if len(parts) == 2:
        return parts[0]
    if len(parts) == 3:
        return parts[1]
    return None


def test_compose_includes_expected_profile_groups():
    """All required optional profile groups should be present."""
    services = _effective_services()

    explicit_profiles: set[str] = set()
    for service in services.values():
        for p in service.get("profiles", []) or []:
            explicit_profiles.add(str(p))

    required = {"bot", "ml", "obs", "eval", "ingest", "voice", "full"}
    assert required.issubset(explicit_profiles)


def test_core_services_are_always_enabled():
    """Core services should have no profile restriction (default compose up)."""
    services = _effective_services()

    core_services = {"redis", "qdrant", "bge-m3", "docling"}
    missing = [name for name in core_services if name not in services]
    assert not missing, f"Missing expected core services: {missing}"

    profiled_core = [name for name in core_services if services[name].get("profiles")]
    assert not profiled_core, f"Core services must be profile-free: {profiled_core}"


def test_compose_has_no_duplicate_host_ports():
    """No two services should bind the same host port in short syntax."""
    services = _effective_services()

    seen: dict[str, str] = {}
    collisions: list[str] = []

    for service_name, service in services.items():
        for port in service.get("ports", []) or []:
            # Ignore long syntax dict mappings in this lightweight validator.
            if isinstance(port, dict):
                host = port.get("published")
                if host is None:
                    continue
                host_port = str(host)
            else:
                host_port = _extract_host_port(str(port))
                if host_port is None:
                    continue

            prev = seen.get(host_port)
            if prev and prev != service_name:
                collisions.append(f"{host_port}: {prev} vs {service_name}")
            else:
                seen[host_port] = service_name

    assert not collisions, "Duplicate host ports detected:\n" + "\n".join(collisions)
