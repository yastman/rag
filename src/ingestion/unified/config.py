# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

"""Configuration for unified ingestion pipeline."""

import logging
from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from src.config.qdrant_policy import resolve_collection_name


logger = logging.getLogger(__name__)


class UnifiedConfig(BaseSettings):
    """Explicit arguments win, then QDRANT_COLLECTION, then legacy aliases.

    Legacy order is COLLECTION_NAME, UNIFIED_COLLECTION_NAME, GDRIVE_COLLECTION_NAME.
    These are ingestion-only compatibility inputs: shared deployments must use
    QDRANT_COLLECTION. Conflicting legacy values require an explicit canonical choice.
    The collection_name value is the physical target, using the bot's suffix policy.
    """

    model_config = SettingsConfigDict(populate_by_name=True, env_file=None)

    sync_dir: Path = Field(
        default_factory=lambda: Path.home() / "drive-sync",
        validation_alias=AliasChoices("SYNC_DIR", "GDRIVE_SYNC_DIR"),
    )
    manifest_dir: Path | None = Field(default=None, validation_alias="MANIFEST_DIR")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, validation_alias="QDRANT_API_KEY")
    collection_name: str = Field(
        default="gdrive_documents_bge",
        validation_alias=AliasChoices(
            "QDRANT_COLLECTION",
            "COLLECTION_NAME",
            "UNIFIED_COLLECTION_NAME",
            "GDRIVE_COLLECTION_NAME",
        ),
    )
    qdrant_quantization_mode: str = Field(
        default="off", validation_alias="QDRANT_QUANTIZATION_MODE"
    )
    max_tokens_per_chunk: int = 512
    bge_m3_url: str = Field(default="http://localhost:8000", validation_alias="BGE_M3_URL")
    bge_m3_timeout: float = Field(default=300, validation_alias="BGE_M3_TIMEOUT")
    bge_m3_concurrency: int = Field(default=1, validation_alias="BGE_M3_CONCURRENCY")
    poll_interval_seconds: int = 60
    pipeline_version: str = "v3.2.1"
    supported_extensions: Annotated[frozenset[str], NoDecode] = frozenset({".md"})

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],  # noqa: ARG003 - native hook signature
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003 - environment only
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple:
        # Chunking/version/watch options remain constructor-only, as with the
        # original dataclass. Reuse native env decoding for aliased inputs.
        def ingestion_environment() -> dict[str, Any]:
            aliases = cls.model_fields["collection_name"].validation_alias
            assert isinstance(aliases, AliasChoices)
            explicit = init_settings()
            if not any(name in explicit for name in ("collection_name", *aliases.choices)):
                assert isinstance(env_settings, EnvSettingsSource)
                names = [str(name) for name in aliases.choices]
                values = {
                    name: env_settings.env_vars.get(
                        name if env_settings.case_sensitive else name.lower()
                    )
                    for name in names
                }
                legacy = {name: values[name] for name in names[1:] if values[name] is not None}
                if values[names[0]] is None and legacy:
                    if len(set(legacy.values())) > 1:
                        raise ValueError(
                            f"Conflicting collection aliases: {', '.join(legacy)}; set QDRANT_COLLECTION"
                        )
                    logger.warning(
                        "Using ingestion-only %s; set QDRANT_COLLECTION for bot/ingestion alignment",
                        next(iter(legacy)),
                    )
            return {
                name: value
                for name, value in env_settings().items()
                if name not in cls.model_fields or cls.model_fields[name].validation_alias
            }

        return init_settings, ingestion_environment

    @model_validator(mode="after")
    def physical_collection_name(self) -> Self:
        self.collection_name = resolve_collection_name(
            self.collection_name, self.qdrant_quantization_mode
        )
        return self

    @field_validator("manifest_dir", mode="before")
    @classmethod
    def empty_manifest_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    def effective_manifest_dir(self) -> Path:
        """Use MANIFEST_DIR when set, otherwise the sync directory."""
        return self.manifest_dir if self.manifest_dir is not None else self.sync_dir
