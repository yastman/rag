"""Shared runtime kernel — destination package for the reverse-layering fix.

This package is the migration target for #1948 (and the related slice in
#1265). The repository's stated layering is::

    src/*           — reusable RAG library, no application coupling
    telegram_bot/*  — bot application, consumer of src/*
    mini_app/*      — Mini App backend, consumer of src/*

Reality on `dev` still has ``src/api/main.py`` importing
``telegram_bot.graph.*``, ``telegram_bot.integrations.cache``,
``telegram_bot.services.qdrant``, and ``telegram_bot.scoring`` — see
``tests/data/known_layering_violations.json`` for the explicit ratchet
allowlist.

The intent of ``src.runtime`` is to host the truly shared kernel
modules that today live under ``telegram_bot/``::

    src/runtime/graph/             ← from telegram_bot/graph/
    src/runtime/integrations/cache  ← from telegram_bot/integrations/cache.py
    src/runtime/services/qdrant     ← from telegram_bot/services/qdrant.py
    src/runtime/observability/      ← from telegram_bot/observability.py
    src/runtime/services/content_loader  ← ...
    src/runtime/services/kommo_client     ← ...
    src/runtime/phone_utils.py            ← ...
    src/runtime/scoring/                  ← ...

After each migration slice:

* ``telegram_bot/`` re-exports the moved symbol from ``src.runtime`` for
  backward compatibility, then is itself updated to import from the new
  location;
* ``src/api/main.py`` and ``mini_app/*`` are switched to
  ``from src.runtime.* import ...`` for the same symbol;
* the corresponding row in ``tests/data/known_layering_violations.json``
  is removed.

The migration slices are tracked as #2045 (phase 1: pure modules),
#2047 (phase 3: coupled modules), and #2049 (cleanup: drop the
allowlist and verify Mini App separability). #2046 / #2048 cover the
parallel ``telegram_bot/bot.py`` decomposition (#1265).

Until those slices land, this package exposes nothing — importing it
just makes the destination directory exist as a Python package so
future ``git mv`` operations can land without dance. See
``src/runtime/README.md`` for the migration runbook.
"""
