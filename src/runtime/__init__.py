"""Shared runtime engine — the transport-neutral execution kernel.

``src.runtime`` hosts the engine consumed by the assistant core
(``src.core.assistant``) and the adapters: request execution
(``runtime.pipeline``), generation, grounding, retrieval, and Qdrant
services, provider-client routing (``runtime.llm``), routing and safety
decisions, shared integrations, and runtime configuration
(``runtime.config``, ``GraphConfig``). The start-point map lives in
``src/runtime/README.md``; the canonical dependency-direction map is
``docs/architecture/STRUCTURE.md``.

This package is the finished destination of the reverse-layering migration
(#1948 and the related slice in #1265): the shared kernel modules moved out
of ``telegram_bot/`` now live here, and the ratchet allowlist
(``tests/data/known_layering_violations.json``) is empty. The standing
invariant is enforced by contract tests: ``runtime`` must not import
``telegram_bot``.
"""
