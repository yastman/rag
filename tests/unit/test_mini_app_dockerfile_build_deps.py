"""Regression test for mini app API build dependencies."""

from pathlib import Path


def test_mini_app_dockerfile_installs_build_essential_before_uv_sync() -> None:
    text = Path("mini_app/Dockerfile").read_text(encoding="utf-8")

    toolchain_install = "apt-get install -y --no-install-recommends build-essential"
    first_sync = "uv sync --frozen --no-dev --no-install-project --extra mini-app"

    assert toolchain_install in text, (
        "mini_app/Dockerfile builder must install build-essential for source builds"
    )
    assert text.index(toolchain_install) < text.index(first_sync), (
        "mini_app/Dockerfile must install build-essential before uv sync resolves mini-app dependencies"
    )
