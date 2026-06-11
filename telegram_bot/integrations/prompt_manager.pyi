from typing import Any

DEFAULT_CACHE_TTL: int

def get_prompt_with_config(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]: ...
def get_prompt_with_object(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> tuple[str, Any | None]: ...
def get_prompt(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> str: ...
def _reset_client() -> None: ...
