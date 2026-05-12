import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[3]
PACKAGE_JSON = ROOT / "mini_app/frontend/package.json"
PACKAGE_LOCK = ROOT / "mini_app/frontend/package-lock.json"
DOCKERFILE = ROOT / "mini_app/frontend/Dockerfile"
DOCKERIGNORE = ROOT / "mini_app/frontend/.dockerignore"
NGINX_CONF = ROOT / "mini_app/frontend/nginx.conf"
NODE_FLOOR = "^20.19.0 || >=22.12.0"


def test_frontend_package_declares_supported_node_floor() -> None:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    assert data["engines"]["node"] == NODE_FLOOR


def test_frontend_lockfile_records_supported_node_floor() -> None:
    data = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    assert data["packages"][""]["engines"]["node"] == NODE_FLOOR


def test_frontend_builder_pins_supported_node_floor() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(
        r"FROM node:20\.19\.0-slim(?:@sha256:[a-f0-9]{64})? AS builder",
        text,
    ), "Dockerfile must use supported Node floor (20.19.0-slim) with builder stage"


def test_frontend_build_context_ignores_local_dependency_and_build_artifacts() -> None:
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    entries = {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "node_modules/" in entries
    assert "dist/" in entries
    assert ".env" in entries


def test_frontend_nginx_temp_paths_use_tmp_root_dirs() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")
    directives = (
        "client_body_temp_path",
        "proxy_temp_path",
        "fastcgi_temp_path",
        "uwsgi_temp_path",
        "scgi_temp_path",
    )
    for directive in directives:
        pattern = rf"{directive}\s+/tmp/[a-z_]+;"
        assert re.search(pattern, text), (
            f"{directive} must use a direct /tmp/<dir> path so nginx can create it on tmpfs"
        )


def test_frontend_nginx_temp_dirs_are_created_for_unprivileged_runtime() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    nginx_conf = NGINX_CONF.read_text(encoding="utf-8")
    for path in [
        "/tmp/client_temp",
        "/tmp/proxy_temp",
        "/tmp/fastcgi_temp",
        "/tmp/uwsgi_temp",
        "/tmp/scgi_temp",
    ]:
        assert path in nginx_conf
        assert path in dockerfile
    assert "chown -R 101:101" in dockerfile
    assert "USER 101:101" in dockerfile
