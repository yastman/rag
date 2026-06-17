# Nodes

## Purpose
Navigation index for the folder. Use this page to quickly find files and route into this part of the project.

## Scope
telegram_bot/graph/nodes


## Contents

| File | Status | Notes |
|---|---|---|
| `__init__.py` | active | package marker |
| `cache.py` | **ARCHIVED — dead code** | `cache_check_node` / `cache_store_node` are never called in production; all cache logic runs inside `src/runtime/pipeline/rag.py`. Retained for `PYTEST_LEGACY_GRAPH_PATHS` tests only. See #2744. |
| `classify.py` | active | classification node |
| `generate.py` | active | generation node |
| `grade.py` | active | grading node |
| `guard.py` | active | guard node |
| `rerank.py` | active | rerank node |
| `respond.py` | active | respond node |
| `retrieve.py` | active | retrieval node |
| `rewrite.py` | active | rewrite node |
| `transcribe.py` | active | transcription node |

## Parent
- [..](..)
