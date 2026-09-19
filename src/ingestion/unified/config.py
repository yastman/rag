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

from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, PydanticBaseSettingsSource, SettingsConfigDict


class UnifiedConfig(BaseSettings):
    """Unified ingestion configuration; explicit arguments override environment aliases."""

    model_config = SettingsConfigDict(populate_by_name=True, env_file=None)

    sync_dir: Path = Field(
        default_factory=lambda: Path.home() / "drive-sync",
        validation_alias=AliasChoices("SYNC_DIR", "GDRIVE_SYNC_DIR"),
    )
    manifest_dir: Path | None = Field(default=None, validation_alias="MANIFEST_DIR")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, validation_alias="QDRANT_API_KEY")
    collection_name: str = Field(
        default="file_documents_bge",
        validation_alias=AliasChoices(
            "COLLECTION_NAME", "UNIFIED_COLLECTION_NAME", "GDRIVE_COLLECTION_NAME"
        ),
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
            return {
                name: value
                for name, value in env_settings().items()
                if name not in cls.model_fields or cls.model_fields[name].validation_alias
            }

        return init_settings, ingestion_environment

    @field_validator("manifest_dir", mode="before")
    @classmethod
    def empty_manifest_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    def effective_manifest_dir(self) -> Path:
        """Use MANIFEST_DIR when set, otherwise the sync directory."""
        return self.manifest_dir if self.manifest_dir is not None else self.sync_dir
