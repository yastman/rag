"""Canonical Qdrant collection contracts: schema, identity, filters (#3333).

One pure-data owner for everything every Qdrant consumer shares:

* named-vector names and the canonical embedding width,
* the payload-index map of each product collection (knowledge, apartments),
* the deterministic apartment point-id function (ingestion == readiness),
* the payload filter builder (production search == readiness probes),
* strict-mode guardrails applied by explicit bootstrap, never by reads,
* the filtered-field registries consumer parity tests assert against.

Transport-neutral (stdlib + ``qdrant_client.models`` only). Never imports
``telegram_bot`` (#1948 layering ratchet) and never performs I/O: validation
and setup code consume these definitions instead of restating them.

Issue: #3333 — establish one schema/filter/identity authority.
"""

from __future__ import annotations

import uuid

from qdrant_client import models


#: BGE-M3 dense dimensionality — the canonical embedding width for both roles.
BGEM3_DENSE_DIM = 1024

#: Named vectors shared by both product collections.
DENSE_VECTOR = "dense"
COLBERT_VECTOR = "colbert"
SPARSE_VECTOR = "bm42"

#: Hard-coded apartments collection name (setup, ingestion, readiness agree).
APARTMENTS_COLLECTION = "apartments"

# ---------------------------------------------------------------------------
# Payload-index maps — the one schema authority per collection
# ---------------------------------------------------------------------------

#: Keyword payload indexes of the knowledge collection. Superset of the
#: historical audited set: ``metadata.source_type``/``jurisdiction``/
#: ``audience``/``language`` are written by the unified writer and reachable
#: through the runtime metadata filter mapping, so they must stay declared.
KNOWLEDGE_KEYWORD_INDEXES = (
    "file_id",
    "metadata.file_id",
    "metadata.doc_id",
    "metadata.source",
    "metadata.file_name",
    "metadata.mime_type",
    "metadata.source_type",
    "metadata.topic",
    "metadata.doc_type",
    "metadata.jurisdiction",
    "metadata.audience",
    "metadata.language",
)
KNOWLEDGE_INTEGER_INDEXES = ("metadata.order", "metadata.chunk_id")

#: Canonical knowledge payload-index map: ``(schema_type, fields)`` pairs.
#: ``metadata.doc_id`` is the product knowledge identifier — written by the
#: unified writer, used for grouping (small-to-big) and doc addressing.
KNOWLEDGE_PAYLOAD_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("keyword", KNOWLEDGE_KEYWORD_INDEXES),
    ("integer", KNOWLEDGE_INTEGER_INDEXES),
)

APARTMENTS_KEYWORD_INDEXES = (
    "complex_name",
    "city",
    "section",
    "apartment_number",
    "view_primary",
    "view_tags",
)
APARTMENTS_INTEGER_INDEXES = ("rooms", "floor")
APARTMENTS_FLOAT_INDEXES = ("price_eur", "area_m2")
APARTMENTS_BOOL_INDEXES = ("is_furnished", "is_promotion")

#: Canonical apartments payload-index map: ``(schema_type, fields)`` pairs.
APARTMENTS_PAYLOAD_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("keyword", APARTMENTS_KEYWORD_INDEXES),
    ("integer", APARTMENTS_INTEGER_INDEXES),
    ("float", APARTMENTS_FLOAT_INDEXES),
    ("bool", APARTMENTS_BOOL_INDEXES),
)


def flat_payload_indexes(
    index_map: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[str, str], ...]:
    """Flatten an index map into ``(field_name, schema_type)`` pairs."""
    return tuple(
        (field_name, schema_type) for schema_type, fields in index_map for field_name in fields
    )


# ---------------------------------------------------------------------------
# Filtered-field registries — consumer parity assertions
# ---------------------------------------------------------------------------

#: Payload fields the apartment product filters and demo probes constrain
#: (the HardFilters extraction surface plus probe shapes). Every entry must
#: keep a declared index in :data:`APARTMENTS_PAYLOAD_INDEXES`.
APARTMENT_FILTER_FIELDS = (
    "city",
    "complex_name",
    "rooms",
    "price_eur",
    "area_m2",
    "floor",
    "section",
    "view_tags",
    "is_furnished",
    "is_promotion",
)

#: Payload fields knowledge product filters and demo probes constrain (the
#: runtime metadata filter mapping). Every entry must keep a declared index
#: in :data:`KNOWLEDGE_PAYLOAD_INDEXES` — ``metadata.doc_id`` is the canonical
#: knowledge identifier and must never lose its declaration.
KNOWLEDGE_FILTER_FIELDS = (
    "metadata.doc_id",
    "metadata.topic",
    "metadata.doc_type",
    "metadata.jurisdiction",
    "metadata.audience",
    "metadata.source_type",
    "metadata.language",
)


def missing_filter_indexes(
    filter_fields: tuple[str, ...],
    index_map: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    """Return filtered fields lacking a declared index in ``index_map``.

    The negative-parity harness (#3333): when a filtered field loses its
    index declaration, parity tests fail with the offending field name.
    """
    declared = {field for _, fields in index_map for field in fields}
    return tuple(field for field in filter_fields if field not in declared)


# ---------------------------------------------------------------------------
# Apartment point identity
# ---------------------------------------------------------------------------

#: Namespace so apartment point ids are deterministic across writers.
_APARTMENT_POINT_NAMESPACE = uuid.UUID("7ba7b810-9dad-11d1-80b4-00c04fd430c8")


def apartment_point_id(complex_name: str, section: str, apartment_number: str) -> str:
    """Deterministic UUID5 from complex + section + apartment number.

    The one apartment point-id function: incremental ingestion, the shipped
    demo catalog, and readiness all address the same point through it.
    """
    return str(
        uuid.uuid5(_APARTMENT_POINT_NAMESPACE, f"{complex_name}::{section}::{apartment_number}")
    )


# ---------------------------------------------------------------------------
# Payload filter builder
# ---------------------------------------------------------------------------


def build_payload_filter(filters: dict | None) -> models.Filter | None:
    """Build a Qdrant filter from the production filter-dict shape.

    The one filter builder for top-level apartment filters and metadata-path
    knowledge probes alike: exact match via MatchValue, ``{"gte": .., "lte": ..}``
    dicts via Range, lists via MatchAny, bools via MatchValue (checked before
    dict/int — ``isinstance(True, int)`` is true in Python).
    """
    if not filters:
        return None
    conditions: list[models.Condition] = []
    for key, value in filters.items():
        if isinstance(value, list):
            conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=value)))
        elif isinstance(value, bool):
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        elif isinstance(value, dict):
            range_params = {op: value[op] for op in ("lt", "lte", "gt", "gte") if op in value}
            if range_params:
                conditions.append(
                    models.FieldCondition(key=key, range=models.Range(**range_params))
                )
        else:
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=conditions) if conditions else None


# ---------------------------------------------------------------------------
# Strict-mode guardrails — explicit bootstrap applies them, reads never do
# ---------------------------------------------------------------------------

#: Server-side strict-mode limits bootstrap applies to the knowledge
#: collection. Read paths must never PATCH these (#3333): a read-only
#: credential can search without collection-update permission.
STRICT_MODE_LIMITS: dict[str, int] = {
    "max_query_limit": 100,
    "max_timeout": 30,
    "search_max_hnsw_ef": 512,
    "search_max_batchsize": 10,
    "max_resident_memory_percent": 80,
}


def strict_mode_config() -> models.StrictModeConfig:
    """The canonical strict-mode configuration."""
    return models.StrictModeConfig(
        enabled=True,
        max_query_limit=STRICT_MODE_LIMITS["max_query_limit"],
        max_timeout=STRICT_MODE_LIMITS["max_timeout"],
        search_max_hnsw_ef=STRICT_MODE_LIMITS["search_max_hnsw_ef"],
        search_max_batchsize=STRICT_MODE_LIMITS["search_max_batchsize"],
        max_resident_memory_percent=STRICT_MODE_LIMITS["max_resident_memory_percent"],
    )
