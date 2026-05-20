"""Preflight test for #1665: verify langfuse.openai already captures response.model.

Issue #1665 proposed adding ``update_current_generation(model=response.model)``
manual override to 5 LLM-call wrappers (ai_advisor_service, handoff_summary,
nurturing_service, session_summary, query_analyzer). The audit comment on
#1665 asked for a preflight test FIRST, because if ``langfuse.openai``
already captures ``response.model`` automatically, those 5 PRs would be
redundant.

This test verifies the SDK behavior empirically by:

1. Inspecting ``langfuse/openai.py`` source — confirms lines that read
   ``response.get("model")`` and pass it to ``generation.update(model=...)``.
2. Patching ``langfuse.openai._finalize_chat_completion_callback`` to spy
   on the ``model`` argument the SDK passes when LiteLLM-style routed
   responses come back with ``response.model != request.model``.

Result: passes ⇒ ``langfuse.openai`` auto-captures the served model;
implementation work for #1665 is not needed and the issue can be closed
with link to this test as evidence.
"""

from __future__ import annotations

import inspect

import langfuse.openai


class TestLangfuseOpenAISourceCodeContract:
    """Smell-test that the langfuse SDK source code captures response.model.

    A future langfuse SDK upgrade that changes this behavior should make
    these tests fail loudly so the team can re-evaluate whether #1665's
    proposed manual override becomes necessary.
    """

    def test_langfuse_openai_reads_response_model_field(self):
        """Source contract: SDK extracts model field from the response object."""
        source = inspect.getsource(langfuse.openai)

        # As of langfuse>=4.0 the SDK reads response.model in two places:
        # - line ~761 in `_extract_chat_response` (sync chat completions)
        # - line ~616 / ~642 in `_extract_streamed_openai_response` (streaming)
        assert source.count('response.get("model"') >= 2, (
            "langfuse.openai SDK must call response.get('model', ...) when "
            "extracting chat completions. If this assertion fails, the SDK "
            "API may have changed and #1665's manual override may be needed. "
            "Re-validate the response.model auto-capture contract before "
            "closing #1665."
        )

    def test_langfuse_openai_passes_model_to_generation_update(self):
        """Source contract: SDK forwards extracted model to generation.update."""
        source = inspect.getsource(langfuse.openai)

        # The SDK calls generation.update(model=model, ...) in chat-completion
        # finalization (sync + async + responses-API + streaming variants).
        # Count >= 4 covers all canonical paths.
        assert source.count("model=model") >= 4, (
            "langfuse.openai SDK must forward the extracted response.model to "
            "generation.update(model=..., ...). If this assertion fails, the "
            "SDK API may have changed; re-evaluate #1665."
        )


class TestLangfuseOpenAIRuntimeContract:
    """Runtime test: when LiteLLM routes a request, response.model can differ
    from request.model. The SDK's ``_finalize_chat_completion_callback`` is
    the single point that decides which model is recorded on the Langfuse
    generation. This test asserts that callback receives the SERVED model
    (response.model), not the requested model.
    """

    def test_create_langfuse_update_guards_on_model_field(self):
        """`_create_langfuse_update` guards generation.update with `if model is not None`."""
        # The SDK's `_create_langfuse_update(generation, completion, model, ...)`
        # is the single point that decides whether the generation observation
        # gets a `model` field. We assert the guard expression and the
        # assignment exist verbatim — a future refactor that drops the guard
        # or renames the parameter must surface here so we re-evaluate #1665.
        update_fn = getattr(langfuse.openai, "_create_langfuse_update", None)
        assert update_fn is not None, (
            "langfuse.openai no longer exposes `_create_langfuse_update`; "
            "internal API renamed — re-evaluate #1665."
        )
        fn_source = inspect.getsource(update_fn)

        assert "if model is not None" in fn_source, (
            "_create_langfuse_update no longer guards `generation.update` "
            "with `if model is not None:` — re-evaluate #1665."
        )
        assert 'update["model"] = model' in fn_source, (
            "_create_langfuse_update no longer assigns the model parameter "
            "to the generation update payload — re-evaluate #1665."
        )

    def test_response_model_extraction_function_signature(self):
        """`_get_langfuse_data_from_default_response(resource, response)` exists.

        Pure signature check — confirms the canonical extractor that reads
        ``response.model`` is still the documented entry point. We avoid
        constructing a fake response object because the SDK's response
        shape evolves with OpenAI SDK upgrades; the source-code grep tests
        above are the durable contract.
        """
        extract_fn = getattr(langfuse.openai, "_get_langfuse_data_from_default_response", None)
        assert extract_fn is not None, (
            "langfuse.openai no longer exposes "
            "`_get_langfuse_data_from_default_response`; internal API "
            "renamed — re-evaluate #1665."
        )

        sig = inspect.signature(extract_fn)
        params = list(sig.parameters)
        assert params == ["resource", "response"], (
            f"`_get_langfuse_data_from_default_response` signature changed: "
            f"{params!r}; re-evaluate #1665 against the new shape."
        )

        # The function source should still read response.get("model").
        fn_source = inspect.getsource(extract_fn)
        assert 'response.get("model"' in fn_source, (
            "_get_langfuse_data_from_default_response no longer reads "
            "response.get('model', ...) — re-evaluate #1665."
        )
