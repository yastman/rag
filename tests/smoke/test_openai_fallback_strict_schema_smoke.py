# tests/smoke/test_openai_fallback_strict_schema_smoke.py
"""Opt-in credentialed smoke: the OpenAI fallback accepts the strict schema (#3325).

Submits the exact production ``response_format`` built by
``json_schema_response_format(ApartmentSearchFilters)`` (normalized for OpenAI
Structured Outputs strict mode) through the real OpenAI fallback model of the
LiteLLM Router and asserts a validated ``ApartmentSearchFilters`` instance
comes back.

Opt-in by credential: the test resolves ``OPENAI_API_KEY`` from the
operator's own ``.env`` (``find_dotenv(usecwd=True)`` — worktrees resolve the
main checkout) and skips when it is absent, so hosted/deterministic lanes
never run it. ``dotenv_values`` is used directly because the pytest
bootstrap sets ``PYTHON_DOTENV_DISABLED`` (#3447), which makes
``load_dotenv`` a no-op. Provider rejection stays observable (the smoke
fails loudly on a provider error) and never prints prompt or credential
material.
"""

from __future__ import annotations

import os

import pytest
from dotenv import dotenv_values, find_dotenv

from src.models.apartment import ApartmentSearchFilters
from src.runtime.llm.router import create_llm_client, json_schema_response_format


pytestmark = pytest.mark.smoke


def _resolve_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    found = find_dotenv(usecwd=True)
    values = dotenv_values(found) if found else {}
    key = str((values or {}).get("OPENAI_API_KEY") or "").strip()
    if key:
        os.environ["OPENAI_API_KEY"] = key
    return key


@pytest.mark.requires_services
async def test_openai_fallback_accepts_production_strict_schema() -> None:
    if not _resolve_openai_key():
        pytest.skip("OPENAI_API_KEY is not configured — opt-in smoke only (#3325)")

    client = create_llm_client()

    messages = [
        {
            "role": "system",
            "content": (
                "Ты извлекаешь фильтры поиска недвижимости из запроса клиента. "
                "Заполни только те поля, которые явно следуют из запроса."
            ),
        },
        {"role": "user", "content": "Двухкомнатная квартира у моря до 150 000 евро"},
    ]

    response_format = json_schema_response_format(ApartmentSearchFilters)
    assert response_format["json_schema"]["strict"] is True

    result = await client.structured(
        messages=messages,
        response_model=ApartmentSearchFilters,
        model="gpt-4o-mini-openai",
        response_format=response_format,
        observation_name="smoke-i3325-strict-schema",
    )

    assert isinstance(result, ApartmentSearchFilters)
