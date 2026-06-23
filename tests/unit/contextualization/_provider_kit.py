"""Provider test kit for shared contextualization scenarios (#2068).

Each provider (Claude, OpenAI, Groq) exposes the same async ``contextualize``
contract on top of a different vendor SDK. The kit captures the bits that
diverge — module path, settings keys, mocked client patches, mock-response
shape — so the parametrized scenarios in
``test_providers_parametrized.py`` can drive all three providers without
duplicating fixtures.

Provider-specific edge cases (Claude prompt caching, OpenAI Langfuse drop-in
and SDK retry contract, Groq free-tier stats and temperature handling) stay
in their respective ``test_<provider>.py`` files.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


def _claude_response(text: str, *, input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


def _chat_completion_response(
    text: str, *, prompt_tokens: int = 100, completion_tokens: int = 50
) -> MagicMock:
    """Shape used by both OpenAI and Groq (chat.completions API)."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    resp.usage.total_tokens = prompt_tokens + completion_tokens
    return resp


@dataclass(frozen=True)
class ProviderSpec:
    """Static description of one contextualization provider."""

    name: str  # context_method label and parametrization id
    module_path: str  # e.g. "src.contextualization.claude"
    class_name: str  # e.g. "ClaudeContextualizer"
    api_key_attr: str  # settings attribute holding the API key
    model_name: str
    client_patch_paths: tuple[str, ...]  # SDK constructors to patch on init
    create_attr_path: tuple[str, ...]  # how to reach the create() coro on the client
    response_factory: Callable[..., MagicMock]

    def settings_mock(self) -> MagicMock:
        """Build a mock Settings object accepted by the contextualizer."""
        settings = MagicMock()
        setattr(settings, self.api_key_attr, "test-key")
        settings.model_name = self.model_name
        settings.temperature = 0.0
        # Groq currently reads its own attribute name; harmless on others.
        settings.groq_api_key = getattr(settings, "groq_api_key", "test-key")
        return settings


def _resolve_create(client: Any, attr_path: tuple[str, ...]) -> Any:
    target = client
    for part in attr_path[:-1]:
        target = getattr(target, part)
    return getattr(target, attr_path[-1]), target, attr_path[-1]


def _set_create(client: Any, attr_path: tuple[str, ...], value: Any) -> None:
    target = client
    for part in attr_path[:-1]:
        target = getattr(target, part)
    setattr(target, attr_path[-1], value)


def make_contextualizer(spec: ProviderSpec):
    """Construct a contextualizer with mocked vendor clients.

    Returns the instantiated contextualizer with ``ctx.client`` already an
    ``AsyncMock`` so tests can attach create() side-effects directly.
    """
    module = __import__(spec.module_path, fromlist=[spec.class_name])
    contextualizer_cls = getattr(module, spec.class_name)

    settings = spec.settings_mock()
    with ExitStack() as stack:
        for path in spec.client_patch_paths:
            stack.enter_context(patch(path))
        # Settings patch is required for providers that build a default Settings()
        stack.enter_context(patch(f"{spec.module_path}.Settings", return_value=settings))
        ctx = contextualizer_cls(settings=settings)
    ctx.client = AsyncMock()
    return ctx


CLAUDE_SPEC = ProviderSpec(
    name="claude",
    module_path="src.contextualization.claude",
    class_name="ClaudeContextualizer",
    api_key_attr="anthropic_api_key",
    model_name="claude-3-sonnet",
    client_patch_paths=(
        "src.contextualization.claude.AsyncAnthropic",
        "src.contextualization.claude.Anthropic",
    ),
    create_attr_path=("messages", "create"),
    response_factory=_claude_response,
)


OPENAI_SPEC = ProviderSpec(
    name="openai",
    module_path="src.contextualization.openai",
    class_name="OpenAIContextualizer",
    api_key_attr="openai_api_key",
    model_name="gpt-4",
    client_patch_paths=(
        "src.contextualization.openai.AsyncOpenAI",
        "src.contextualization.openai.OpenAI",
    ),
    create_attr_path=("chat", "completions", "create"),
    response_factory=_chat_completion_response,
)


GROQ_SPEC = ProviderSpec(
    name="groq",
    module_path="src.contextualization.groq",
    class_name="GroqContextualizer",
    api_key_attr="groq_api_key",
    model_name="llama-3.3-70b-versatile",
    client_patch_paths=(
        "src.contextualization.groq.AsyncGroq",
        "src.contextualization.groq.Groq",
    ),
    create_attr_path=("chat", "completions", "create"),
    response_factory=_chat_completion_response,
)


ALL_PROVIDERS: tuple[ProviderSpec, ...] = (CLAUDE_SPEC, OPENAI_SPEC, GROQ_SPEC)


def patch_create(ctx: Any, spec: ProviderSpec, **kwargs: Any) -> AsyncMock:
    """Replace the provider create() coro with an ``AsyncMock``.

    Accepts the same kwargs as ``AsyncMock`` (``return_value=`` /
    ``side_effect=``). Returns the mock so tests can assert on calls.
    """
    create_mock = AsyncMock(**kwargs)
    _set_create(ctx.client, spec.create_attr_path, create_mock)
    return create_mock
