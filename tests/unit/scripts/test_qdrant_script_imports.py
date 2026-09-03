"""Import-mode characterization for the Qdrant maintenance scripts (#3249).

Each Qdrant script must bind its helper names in both invocation modes:

- package mode: ``import scripts.<module>``
- direct-script mode: ``python scripts/<module>.py`` (bare sibling imports)

The direct-script mode is exercised by blocking every ``scripts``/``scripts.*``
import via a meta-path finder and loading each script file from disk, so its
``except ModuleNotFoundError`` fallback branch is the only way names can bind.
"""

import importlib
import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType


SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"

# Names each script binds through the dual-mode import block.
EXPECTED_SCRIPT_NAMES: dict[str, tuple[str, ...]] = {
    "setup_scalar_collection": (
        "collection_exists",
        "delete_collection",
        "get_qdrant_client",
        "_create_payload_indexes",
    ),
    "setup_qdrant_collection": (
        "collection_exists",
        "delete_collection",
        "get_qdrant_client",
        "_create_payload_indexes",
    ),
    "setup_binary_collection": (
        "collection_exists",
        "delete_collection",
        "get_qdrant_client",
        "payload_index_types",
        "_create_payload_indexes",
    ),
    "qdrant_ensure_indexes": (
        "GDRIVE_PAYLOAD_INDEX_FIELDS",
        "create_payload_indexes",
        "_get_qdrant_client",
    ),
    "reindex_to_binary": (
        "_get_qdrant_client",
        "collection_exists",
        "create_binary_collection",
        "create_payload_indexes",
        "get_binary_collection_name",
        "print_collection_info",
    ),
    "qdrant_audit_indexes": (
        "PAYLOAD_INDEX_FIELDS_BY_COLLECTION",
        "get_qdrant_client",
        "payload_index_types",
        "PAYLOAD_INDEX_FIELDS",
    ),
}


class _ScriptsImportBlocker:
    """Meta-path finder that makes every ``scripts`` / ``scripts.*`` import fail."""

    def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:
        if fullname == "scripts" or fullname.startswith("scripts."):
            raise ModuleNotFoundError(f"blocked for import-mode test: {fullname!r}", name=fullname)
        return


def _load_script_from_path(name: str) -> ModuleType:
    """Execute ``scripts/<name>.py`` from disk under a synthetic top-level name."""
    spec = importlib.util.spec_from_file_location(
        f"_qdrant_import_mode_{name}", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _assert_names(module: ModuleType, names: Iterable[str]) -> None:
    for attr in names:
        assert getattr(module, attr, None) is not None, f"{module.__name__} lacks {attr!r}"


def test_scripts_bind_helpers_as_package_modules() -> None:
    for name, expected in EXPECTED_SCRIPT_NAMES.items():
        module = importlib.import_module(f"scripts.{name}")
        _assert_names(module, expected)


def test_scripts_bind_helpers_through_direct_script_fallback(monkeypatch) -> None:
    monkeypatch.setattr(sys, "meta_path", [_ScriptsImportBlocker(), *sys.meta_path])
    monkeypatch.syspath_prepend(str(SCRIPTS_DIR))

    saved = {
        key: sys.modules.pop(key)
        for key in [k for k in sys.modules if k == "scripts" or k.startswith("scripts.")]
    }
    added: set[str] = set(sys.modules)
    try:
        for name, expected in EXPECTED_SCRIPT_NAMES.items():
            module = _load_script_from_path(name)
            _assert_names(module, expected)
    finally:
        sys.modules.update(saved)
        for key in set(sys.modules) - added:
            if not key.startswith("scripts"):
                del sys.modules[key]
