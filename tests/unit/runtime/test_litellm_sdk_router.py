# tests/unit/runtime/test_litellm_sdk_router.py
"""Unit tests for the LiteLLM SDK boundary (#3325).

Pins the OpenAI Structured Outputs strict-mode contract for
``json_schema_response_format``: every object in the emitted schema — root,
``$defs`` and nested/array items — must have ``additionalProperties: false``
and a ``required`` list equal to its property set. Semantic optionality is
represented with nullable unions, never by dropping properties from
``required``.
"""

from __future__ import annotations

from typing import Any

from src.models.apartment import ApartmentSearchFilters
from src.runtime.llm.router import json_schema_response_format


def _assert_strict_objects(node: Any) -> None:
    """Recursively prove every object node satisfies the strict contract."""
    if isinstance(node, dict):
        if "$ref" in node:
            return  # reference: the target definition carries the contract
        if node.get("type") == "object" or isinstance(node.get("properties"), dict):
            properties = node.get("properties") or {}
            assert node.get("additionalProperties") is False, node
            assert set(node.get("required") or []) == set(properties), node
        for value in node.values():
            _assert_strict_objects(value)
    elif isinstance(node, list):
        for item in node:
            _assert_strict_objects(item)


def test_response_format_wraps_strict_json_schema() -> None:
    response_format = json_schema_response_format(ApartmentSearchFilters)

    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "ApartmentSearchFilters"
    assert response_format["json_schema"]["strict"] is True


def test_apartment_filters_schema_satisfies_openai_strict_contract() -> None:
    """Every object (root + $defs) is strict-complete, including nesting."""
    schema = json_schema_response_format(ApartmentSearchFilters)["json_schema"]["schema"]

    _assert_strict_objects(schema)

    defs = schema.get("$defs") or {}
    assert defs, "ApartmentSearchFilters must expose its nested models in $defs"
    for definition in defs.values():
        assert definition.get("additionalProperties") is False
        assert set(definition.get("required") or []) == set(definition.get("properties") or {})


def test_optional_fields_are_nullable_unions_not_dropped() -> None:
    """Semantic optionality becomes a nullable union, not a missing required."""
    schema = json_schema_response_format(ApartmentSearchFilters)["json_schema"]["schema"]

    soft = schema["$defs"]["SoftPreferences"]
    assert "near_sea" in soft["required"]
    near_sea = soft["properties"]["near_sea"]
    variants = near_sea.get("anyOf") or near_sea.get("oneOf") or []
    assert any(v.get("type") == "null" for v in variants), near_sea


def test_array_items_of_objects_are_strict_complete() -> None:
    """An object-valued array item must itself carry the strict contract."""
    from pydantic import BaseModel

    class _Item(BaseModel):
        label: str

    class _Holder(BaseModel):
        items: list[_Item]
        maybe: _Item | None = None

    schema = json_schema_response_format(_Holder)["json_schema"]["schema"]
    _assert_strict_objects(schema)


def test_normalization_does_not_mutate_the_model_schema_cache() -> None:
    """``model_json_schema()`` output is copied, not mutated in place."""
    first = json_schema_response_format(ApartmentSearchFilters)
    model_schema = ApartmentSearchFilters.model_json_schema()
    assert model_schema.get("additionalProperties") is None
    assert "required" not in model_schema or model_schema.get("title") == "ApartmentSearchFilters"
    _ = first
