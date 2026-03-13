"""Schema configuration models for source → canonical → target mapping."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    """Maps a single source column to a canonical field."""

    source_column: str
    target_column: str
    transform: str | None = None
    transform_params: dict[str, Any] = Field(default_factory=dict)


class PassthroughColumn(BaseModel):
    """A source column to carry through as a custom field."""

    source_column: str


class DatasetMapping(BaseModel):
    """Complete mapping for a single dataset (funded or pipeline)."""

    mappings: list[ColumnMapping]
    defaults: dict[str, Any] = Field(default_factory=dict)
    passthrough: list[PassthroughColumn] = Field(default_factory=list)


class SchemaMapping(BaseModel):
    """Top-level schema mapping configuration (loaded from schema_mapping.yaml)."""

    version: str = "1.0"
    source_type: str = ""
    description: str = ""
    funded_portfolio: DatasetMapping | None = None
    pipeline: DatasetMapping | None = None


class ColumnDefinition(BaseModel):
    """Describes a single column in a source schema."""

    name: str
    type: str
    required: bool = False
    description: str = ""


class DatasetSchema(BaseModel):
    """Schema definition for a single dataset."""

    file_format: str = "csv"
    encoding: str = "utf-8"
    delimiter: str = ","
    date_format: str = "%Y-%m-%d"
    description: str = ""
    columns: list[ColumnDefinition] = Field(default_factory=list)


class SourceSchemaConfig(BaseModel):
    """Top-level source schema config (loaded from source_schema.yaml)."""

    version: str = "1.0"
    description: str = ""
    funded_portfolio: DatasetSchema | None = None
    pipeline: DatasetSchema | None = None
