from typing import Any

def get_prompt_with_config(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = ...,
    variables: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]: ...
def get_prompt_with_object(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = ...,
    variables: dict[str, str] | None = None,
) -> tuple[str, None]: ...
def get_prompt(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = ...,
    variables: dict[str, str] | None = None,
) -> str: ...
def _reset_client() -> None: ...
def _apply_fallback_vars(fallback: str, compile_vars: dict[str, str]) -> str: ...
