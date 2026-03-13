"""YAML-driven data loader for Portfolio Evolution simulation engine.

Reads CSV/Parquet/Excel files and maps source columns to canonical InstrumentPosition
using configurable schema mappings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from portfolio_evolution.models.instrument import InstrumentPosition
from portfolio_evolution.models.schema_config import SchemaMapping
from portfolio_evolution.utils.config_loader import load_yaml
from portfolio_evolution.utils.transforms import get_transform


def _read_dataframe(path: Path) -> pl.DataFrame:
    """Read CSV, Parquet, or Excel file into a Polars DataFrame."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        # Read as strings to handle mixed types (e.g. "No Data Available")
        return pl.read_csv(path, infer_schema_length=0)
    if suffix == ".parquet":
        return pl.read_parquet(path)
    if suffix in (".xlsx", ".xls"):
        # Polars doesn't support Excel; fall back to pandas
        import pandas as pd

        pdf = pd.read_excel(path)
        return pl.from_pandas(pdf)
    raise ValueError(
        f"Unsupported file format: {suffix}. Use .csv, .parquet, .xlsx, or .xls"
    )


def _apply_transform(
    value: Any,
    transform_name: str | None,
    transform_params: dict[str, Any],
    schemas_base: Path | None,
) -> Any:
    """Apply a transform to a value, injecting base_path for lookups."""
    if transform_name is None:
        return value
    fn = get_transform(transform_name)
    params = dict(transform_params)
    if schemas_base is not None:
        params["base_path"] = schemas_base
    return fn(value, params)


def load_portfolio(
    data_path: Path,
    mapping_path: Path,
    dataset_key: str,
    schemas_base: Path | None = None,
) -> list[InstrumentPosition]:
    """Load a CSV/Parquet/Excel file and map to canonical InstrumentPosition objects.

    Steps:
    1. Load the schema mapping YAML
    2. Read the data file (detect format from extension)
    3. For each row, apply column mappings (with transforms)
    4. Apply defaults for missing fields
    5. Collect passthrough columns into custom_fields
    6. Validate each row through InstrumentPosition model
    7. Return list of valid positions (collect errors for reporting)

    Args:
        data_path: Path to the data file (CSV, Parquet, or Excel).
        mapping_path: Path to the schema mapping YAML.
        dataset_key: "funded_portfolio" or "pipeline".
        schemas_base: Base path for resolving relative paths in transform_params
            (e.g. mapping_file: "lookups/rating_crosswalk.yaml").

    Returns:
        List of validated InstrumentPosition objects.

    Raises:
        FileNotFoundError: If data or mapping file not found.
        ValueError: If file format unsupported, data empty, or validation fails.
    """
    mapping_path = Path(mapping_path)
    if not mapping_path.exists():
        raise FileNotFoundError(f"Schema mapping file not found: {mapping_path}")

    # 1. Load schema mapping
    raw_mapping = load_yaml(mapping_path)
    schema = SchemaMapping.model_validate(raw_mapping)

    dataset_mapping = getattr(schema, dataset_key)
    if dataset_mapping is None:
        raise ValueError(
            f"Dataset key '{dataset_key}' not found in schema mapping. "
            f"Available: funded_portfolio, pipeline"
        )

    # Resolve schemas_base: use mapping file's parent if not provided
    base = schemas_base
    if base is None:
        base = mapping_path.parent

    # 2. Read data file
    df = _read_dataframe(Path(data_path))
    if df.is_empty():
        raise ValueError(f"Data file is empty: {data_path}")

    # 3-6. Map each row
    positions: list[InstrumentPosition] = []
    errors: list[str] = []

    for row_idx, row in enumerate(df.iter_rows(named=True)):
        # Build target dict from mappings (one source can map to multiple targets)
        target: dict[str, Any] = {}

        for mapping in dataset_mapping.mappings:
            if mapping.source_column not in row:
                continue  # Optional source column missing
            raw_value = row[mapping.source_column]
            transformed = _apply_transform(
                raw_value,
                mapping.transform,
                mapping.transform_params,
                base,
            )
            target[mapping.target_column] = transformed

        # 4. Apply defaults for missing fields
        for key, default_val in dataset_mapping.defaults.items():
            if key not in target:
                target[key] = default_val

        # 5. Passthrough columns -> custom_fields
        custom: dict[str, Any] = {}
        for passthrough in dataset_mapping.passthrough:
            if passthrough.source_column in row:
                custom[passthrough.source_column] = row[passthrough.source_column]
        target["custom_fields"] = custom

        # counterparty_id defaults to instrument_id if not mapped
        if "counterparty_id" not in target and "instrument_id" in target:
            target["counterparty_id"] = target["instrument_id"]

        # 6. Validate through InstrumentPosition
        try:
            pos = InstrumentPosition.model_validate(target)
            positions.append(pos)
        except Exception as e:
            errors.append(f"Row {row_idx + 1}: {e}")

    if errors:
        summary = "\n".join(errors[:10])
        if len(errors) > 10:
            summary += f"\n... and {len(errors) - 10} more errors"
        raise ValueError(
            f"Validation failed for {len(errors)} row(s) in {data_path}:\n{summary}"
        )

    return positions


def load_from_config(
    config: dict,
    base_dir: Path | None = None,
) -> dict[str, list[InstrumentPosition]]:
    """Load all portfolios from a master config dict.

    Supports both single-portfolio mode (funded_file/pipeline_file) and
    multi-portfolio mode (portfolios list).

    Returns dict like {"funded": [...], "pipeline": [...]} or
    {"C&I_funded": [...], "C&I_pipeline": [...], "CRE_funded": [...], ...}

    Args:
        config: Master config dict (from load_yaml or load_config_with_preset).
        base_dir: Base directory for resolving relative paths. Defaults to
            current working directory.

    Returns:
        Dict mapping portfolio keys to lists of InstrumentPosition.
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    result: dict[str, list[InstrumentPosition]] = {}

    portfolios = config.get("portfolios")
    if portfolios:
        # Multi-portfolio mode
        for p in portfolios:
            name = p.get("name", "unknown")
            schema_path = base / p.get("schema_mapping", config.get("schema_mapping", ""))
            schemas_base = schema_path.parent

            if "funded_file" in p:
                funded_path = base / p["funded_file"]
                result[f"{name}_funded"] = load_portfolio(
                    funded_path,
                    schema_path,
                    "funded_portfolio",
                    schemas_base=schemas_base,
                )
            if "pipeline_file" in p:
                pipeline_path = base / p["pipeline_file"]
                result[f"{name}_pipeline"] = load_portfolio(
                    pipeline_path,
                    schema_path,
                    "pipeline",
                    schemas_base=schemas_base,
                )
    else:
        # Single-portfolio mode
        schema_path = base / config.get("schema_mapping", "schemas/schema_mapping.yaml")
        schemas_base = schema_path.parent

        if "funded_file" in config:
            funded_path = base / config["funded_file"]
            result["funded"] = load_portfolio(
                funded_path,
                schema_path,
                "funded_portfolio",
                schemas_base=schemas_base,
            )
        if "pipeline_file" in config:
            pipeline_path = base / config["pipeline_file"]
            result["pipeline"] = load_portfolio(
                pipeline_path,
                schema_path,
                "pipeline",
                schemas_base=schemas_base,
            )

    return result


def load_deposits_csv(
    file_path: Path,
) -> list:
    """Load deposit positions from a CSV file.

    Uses a simple direct mapping from common column names to DepositPosition fields.
    Returns a list of DepositPosition objects.
    """
    import csv
    from datetime import date as date_type

    from portfolio_evolution.models.deposit import DepositPosition

    _TYPE_MAP = {
        "checking": "operating", "dda": "operating", "operating": "operating",
        "savings": "savings", "money_market": "savings",
        "cd": "term_deposit", "time_deposit": "term_deposit", "term_deposit": "term_deposit",
        "escrow": "escrow", "sweep": "sweep", "brokered": "brokered",
        "corporate_transaction": "corporate_transaction", "retail_checking": "retail_checking",
    }
    _LIQ_VALID = {"stable_operational", "non_operational", "rate_sensitive", "volatile", "brokered"}

    deposits = []
    with open(file_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                raw_type = row.get("ACCOUNT_TYPE", row.get("deposit_type", "operating"))
                dep_type = _TYPE_MAP.get(raw_type.lower().strip(), "operating")

                raw_rate = float(row.get("INT_RATE", row.get("interest_rate", 0)))
                rate = raw_rate / 100.0 if raw_rate > 1.0 else raw_rate

                raw_liq = row.get("LIQUIDITY_CLASS", row.get("liquidity_category", "non_operational"))
                liq = raw_liq.lower().strip().replace(" ", "_")
                liq = liq if liq in _LIQ_VALID else "non_operational"

                raw_rt = row.get("RATE_TYPE", row.get("rate_type", "floating")).lower().strip()
                rate_type = raw_rt if raw_rt in ("fixed", "floating") else "floating"

                dep = DepositPosition(
                    deposit_id=row.get("ACCOUNT_ID", row.get("deposit_id", "")),
                    counterparty_id=row.get("CUSTOMER_ID", row.get("counterparty_id", "")),
                    deposit_type=dep_type,
                    segment=row.get("SEGMENT", row.get("segment", "commercial")),
                    current_balance=float(row.get("CURRENT_BAL", row.get("current_balance", 0))),
                    interest_rate=rate,
                    rate_type=rate_type,
                    beta=float(row.get("DEPOSIT_BETA", row.get("beta", 0.35))),
                    origination_date=date_type.fromisoformat(
                        row.get("OPEN_DATE", row.get("origination_date", "2024-01-01"))
                    ),
                    liquidity_category=liq,
                    as_of_date=date_type.fromisoformat(
                        row.get("AS_OF_DATE", row.get("as_of_date", "2025-12-31"))
                    ),
                )
                deposits.append(dep)
            except Exception:
                continue

    return deposits
