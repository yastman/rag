# tests/contract/test_manifest_no_content_hash_collapse_contract.py
"""Contract test: get_or_create_id must use copy-vs-rename detection (#1603).

AST-based check that the implementation of ``GDriveManifest.get_or_create_id``
in ``manifest.py``:
1. References ``_path_to_hash`` (or ``path_to_hash``) when deciding whether to
   reuse a file_id — i.e., the active-paths set is consulted (Option B
   copy-detection).
2. Does NOT unconditionally reuse ``hash_to_id[content_hash]`` when the hash
   was seen before (the pre-#1603 bug was a bare ``elif content_hash in
   self._hash_to_id`` that always returned the stored id without checking
   active paths).

This contract prevents regression to the old behaviour where two files with
identical bytes collapsed to the same file_id regardless of whether the
original path was still active.
"""

import ast
import textwrap
from pathlib import Path


MANIFEST_PATH = Path(__file__).parents[2] / "src" / "ingestion" / "unified" / "manifest.py"

_FUNCTION_NAME = "get_or_create_id"


def _get_function_source() -> str:
    """Return the source of GDriveManifest.get_or_create_id."""
    source = MANIFEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "GDriveManifest":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == _FUNCTION_NAME:
                    return ast.get_source_segment(source, item) or ""

    return ""


def _get_function_ast() -> ast.FunctionDef | None:
    source = MANIFEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "GDriveManifest":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == _FUNCTION_NAME:
                    return item

    return None


class TestManifestNoCopyCollapse:
    """Contract: get_or_create_id implements copy-detection, not hash-only dedup."""

    def test_manifest_file_exists(self) -> None:
        """manifest.py exists at the expected path."""
        assert MANIFEST_PATH.exists(), f"manifest.py not found at {MANIFEST_PATH}"

    def test_get_or_create_id_exists(self) -> None:
        """GDriveManifest.get_or_create_id method must exist."""
        fn = _get_function_ast()
        assert fn is not None, (
            f"Method '{_FUNCTION_NAME}' not found in GDriveManifest "
            f"in {MANIFEST_PATH}"
        )

    def test_function_references_path_to_hash(self) -> None:
        """get_or_create_id must reference _path_to_hash for active-path lookup.

        Option B copy-detection requires checking whether the original path is
        still active.  This is done via ``_path_to_hash``.
        """
        source = _get_function_source()
        assert source, f"Could not extract source for '{_FUNCTION_NAME}'"
        assert "_path_to_hash" in source, (
            f"'{_FUNCTION_NAME}' does not reference '_path_to_hash'. "
            "The function must consult active paths to distinguish copies from "
            "renames (Option B, #1603).  If the implementation changed the "
            "attribute name, update this contract."
        )

    def test_copy_detection_uses_active_path_set(self) -> None:
        """get_or_create_id must check active paths before reusing hash identity.

        The function must NOT blindly return ``hash_to_id[content_hash]`` when
        the hash was seen before.  It must first verify that no active path
        still holds that hash (i.e., build the set of active_paths_for_hash or
        equivalent) before deciding rename vs copy.
        """
        fn = _get_function_ast()
        assert fn is not None

        # Walk the AST looking for any reference to _path_to_hash inside the
        # branch that handles the elif-content_hash-in-_hash_to_id case.
        # A simpler proxy: verify the function body contains at least one
        # comprehension or loop that iterates _path_to_hash items/values.

        source = _get_function_source()
        assert source

        # The implementation must iterate _path_to_hash to find active paths.
        # Accept any of the common patterns:
        #   {p for p, h in self._path_to_hash.items() if h == content_hash}
        #   for p, h in self._path_to_hash.items(): ...
        #   self._path_to_hash.values() / .items()
        iteration_patterns = [
            "_path_to_hash.items()",
            "_path_to_hash.values()",
            "_path_to_hash.keys()",
        ]
        assert any(pat in source for pat in iteration_patterns), (
            f"'{_FUNCTION_NAME}' does not iterate _path_to_hash to determine "
            "active paths for a given hash.  Copy-detection (Option B, #1603) "
            "requires building the set of currently active paths for the hash "
            "before deciding whether to reuse or generate a new file_id."
        )

    def test_no_unconditional_hash_reuse(self) -> None:
        """get_or_create_id must not unconditionally reuse hash_to_id.

        The pre-#1603 bug was:
            elif content_hash in self._hash_to_id:
                file_id = self._hash_to_id[content_hash]   # ← always returned old id
                self._key_to_id[composite_key] = file_id

        The fix adds a conditional: only reuse if active_paths_for_hash is
        empty.  We verify this by checking that the function does NOT immediately
        assign ``file_id = self._hash_to_id[content_hash]`` right after the
        ``elif`` without first checking active paths.

        We do this by looking at the AST: the elif branch must NOT have
        ``file_id = self._hash_to_id[content_hash]`` as its first statement
        (it should instead compute active_paths_for_hash first).
        """
        fn = _get_function_ast()
        assert fn is not None

        # Find the elif branch body (IfExp or If node with content_hash test)
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue

            # Look for: if/elif ... content_hash in self._hash_to_id ...
            test_src = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
            if "_hash_to_id" not in test_src:
                continue

            # This is the elif content_hash in self._hash_to_id branch.
            # Its body must NOT start with a simple assignment
            # file_id = self._hash_to_id[content_hash].
            body = node.body
            if not body:
                continue

            first_stmt = body[0]
            if isinstance(first_stmt, ast.Assign):
                # Check if it's file_id = self._hash_to_id[...]
                rhs = first_stmt.value
                if (
                    isinstance(rhs, ast.Subscript)
                    and isinstance(rhs.value, ast.Attribute)
                    and rhs.value.attr == "_hash_to_id"
                ):
                    raise AssertionError(
                        "Regression detected: the elif-content_hash branch "
                        "immediately assigns file_id = self._hash_to_id[...] "
                        "without first checking active paths. "
                        "This is the pre-#1603 bug pattern.  Add copy-detection "
                        "logic (active_paths_for_hash check) before the assignment."
                    )
            # Branch body starts with something else → OK
            break
