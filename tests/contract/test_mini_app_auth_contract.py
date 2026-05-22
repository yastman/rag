"""AST-level contract tests for Mini App initData enforcement (#1595).

Locks four structural invariants that must never regress:

  1. ``mini_app/api.py`` does NOT contain ``allow_origins=["*"]`` literal.
  2. ``mini_app/api.py`` imports the auth dependency module and both mutation
     handlers (``start_expert`` and ``phone``) reference
     ``get_validated_init_data`` via ``Depends(...)``.
  3. ``mini_app/api.py`` reaches the canonical ``validate_init_data`` symbol
     (directly or via the shared dependency module).
  4. SDK-audited path: ``mini_app/auth.py`` imports from
     ``aiogram.utils.web_app`` (Context7 SDK research, #1595).

These tests are pure file/AST inspection — no live FastAPI app is required,
so they run cleanly in collection-only contexts.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
API_FILE = REPO_ROOT / "mini_app" / "api.py"
AUTH_FILE = REPO_ROOT / "mini_app" / "auth.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
# 1. No wildcard CORS in api.py source
# ---------------------------------------------------------------------------


def test_api_does_not_contain_wildcard_cors() -> None:
    source = API_FILE.read_text(encoding="utf-8")
    wildcard_pattern = re.compile(r'allow_origins\s*=\s*\[\s*["\']\*["\']\s*\]')
    assert not wildcard_pattern.search(source), (
        "mini_app/api.py still contains allow_origins=['*']. "
        "Read MINI_APP_ALLOWED_ORIGIN from env (default 'https://t.me') instead (#1595)."
    )


# ---------------------------------------------------------------------------
# 2. Both mutation handlers wire the auth dependency
# ---------------------------------------------------------------------------


def test_start_expert_handler_uses_get_validated_init_data() -> None:
    tree = _parse(API_FILE)
    func = _find_func(tree, "start_expert")
    assert func is not None, "start_expert handler must exist in mini_app/api.py"

    body_text = ast.unparse(func)
    assert "get_validated_init_data" in body_text, (
        "start_expert must inject get_validated_init_data via Depends(...) (#1595). "
        f"Found:\n{body_text[:400]}"
    )


def test_phone_handler_uses_get_validated_init_data() -> None:
    tree = _parse(API_FILE)
    func = _find_func(tree, "phone")
    assert func is not None, "phone handler must exist in mini_app/api.py"

    body_text = ast.unparse(func)
    assert "get_validated_init_data" in body_text, (
        "phone must inject get_validated_init_data via Depends(...) (#1595). "
        f"Found:\n{body_text[:400]}"
    )


# ---------------------------------------------------------------------------
# 3. validate_init_data is reachable from api.py
# ---------------------------------------------------------------------------


def test_api_reaches_validate_init_data() -> None:
    """api.py must reference validate_init_data either directly or via auth dependency."""
    source = API_FILE.read_text(encoding="utf-8")
    has_direct_import = bool(
        re.search(r"from\s+mini_app\.auth\s+import\s+[^#\n]*validate_init_data", source)
    )
    has_dependency_helper = "get_validated_init_data" in source
    assert has_direct_import or has_dependency_helper, (
        "mini_app/api.py must expose validate_init_data — either by direct import "
        "or via a get_validated_init_data dependency (#1595)."
    )


# ---------------------------------------------------------------------------
# 4. SDK-audited path: auth.py uses aiogram.utils.web_app
# ---------------------------------------------------------------------------


def test_auth_module_uses_aiogram_sdk() -> None:
    """mini_app/auth.py must delegate to aiogram.utils.web_app (Context7 SDK audit)."""
    source = AUTH_FILE.read_text(encoding="utf-8")
    sdk_import_pattern = re.compile(
        r"from\s+aiogram\.utils\.web_app\s+import\s+[\w,\s]*"
        r"(safe_parse_webapp_init_data|check_webapp_signature|parse_webapp_init_data)",
    )
    assert sdk_import_pattern.search(source), (
        "mini_app/auth.py must import from aiogram.utils.web_app — the SDK ships a "
        "vetted HMAC-SHA256 validator with hmac.compare_digest, so the custom "
        "implementation should delegate to it (#1595, Context7 audit)."
    )

    # And the custom HMAC computation should be gone (no more raw secret derivation).
    assert 'b"WebAppData"' not in source and "b'WebAppData'" not in source, (
        "mini_app/auth.py still contains raw HMAC secret derivation (b'WebAppData'); "
        "the SDK helper should own that detail now (#1595)."
    )
