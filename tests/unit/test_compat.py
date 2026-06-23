"""Unit tests for src/_compat.py compatibility helpers."""

import warnings

import pytest


class TestLoadDeprecatedPackageExport:
    def test_emits_deprecation_warning(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # Use json.loads as a real target so the import succeeds
            load_deprecated_package_export(
                module_name="old.module",
                attr_name="OldClass",
                target=("json", "loads", "json.loads"),
            )

        assert len(caught) == 1
        assert issubclass(caught[0].category, DeprecationWarning)
        msg = str(caught[0].message)
        assert "old.module.OldClass" in msg
        assert "deprecated" in msg.lower()
        assert "json.loads" in msg

    def test_returns_target_attribute(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = load_deprecated_package_export(
                module_name="old.module",
                attr_name="OldClass",
                target=("json", "dumps", "json.dumps"),
            )

        from json import dumps

        assert result is dumps

    def test_raises_attribute_error_for_nonexistent_target(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(AttributeError):
                load_deprecated_package_export(
                    module_name="old.module",
                    attr_name="OldClass",
                    target=("json", "nonexistent_attr_xyz", "json.nonexistent_attr_xyz"),
                )

    def test_raises_module_not_found_for_bad_module(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(ModuleNotFoundError):
                load_deprecated_package_export(
                    module_name="old.module",
                    attr_name="OldClass",
                    target=(
                        "nonexistent_module_xyz_123",
                        "SomeClass",
                        "nonexistent_module_xyz_123.SomeClass",
                    ),
                )

    def test_warning_includes_replacement_suggestion(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            load_deprecated_package_export(
                module_name="pkg",
                attr_name="func",
                target=("os.path", "join", "os.path.join"),
            )

        assert len(caught) == 1
        assert "import os.path.join instead" in str(caught[0].message)
