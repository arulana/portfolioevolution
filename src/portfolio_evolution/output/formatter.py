"""Configurable output formatter for simulation results.

Maps canonical InstrumentPosition data to target schemas and writes
to multiple output formats.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from portfolio_evolution.models.instrument import InstrumentPosition
from portfolio_evolution.utils.transforms import TRANSFORM_REGISTRY, get_transform


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_transform_defs(mapping_path: Path | None) -> dict[str, dict[str, Any]]:
    """Load transform definitions from output_mapping.yaml."""
    if mapping_path is None or not mapping_path.exists():
        return {}
    data = _load_yaml(mapping_path)
    return data.get("transforms", {})


def _apply_transform(
    value: Any,
    transform_name: str | None,
    transform_defs: dict[str, dict[str, Any]],
) -> Any:
    """Apply a transform to a value if defined."""
    if transform_name is None or not transform_defs:
        return value
    defn = transform_defs.get(transform_name)
    if defn is None:
        return value
    op = defn.get("operation")
    if op == "multiply":
        factor = defn.get("factor", 1.0)
        if value is None:
            return None
        try:
            return float(value) * factor
        except (TypeError, ValueError):
            return value
    if op == "map":
        mapping = defn.get("mapping", {})
        if value is None:
            return mapping.get("null", "")
        key = str(value).lower() if isinstance(value, bool) else str(value)
        return mapping.get(key, value)
    if op == "date_format":
        fmt = defn.get("format", "%Y-%m-%d")
        if value is None:
            return None
        if isinstance(value, date):
            return value.strftime(fmt)
        return value
    if transform_name in TRANSFORM_REGISTRY:
        fn = get_transform(transform_name)
        return fn(value, defn)
    return value


def format_positions(
    positions: list[InstrumentPosition],
    target_schema_path: Path | None = None,
    output_mapping_path: Path | None = None,
) -> pl.DataFrame:
    """Convert positions to a Polars DataFrame using target schema mapping.

    If target_schema_path is provided, use it to select and rename columns.
    If not provided, dump all canonical fields.
    """
    if not positions:
        return pl.DataFrame()

    transform_defs = _load_transform_defs(output_mapping_path)

    if target_schema_path is None or not target_schema_path.exists():
        # Dump all canonical fields
        rows = [p.model_dump(mode="json") for p in positions]
        return pl.DataFrame(rows)

    schema_data = _load_yaml(target_schema_path)
    columns = schema_data.get("portfolio_rollforward", {}).get("columns", [])
    if not columns:
        rows = [p.model_dump(mode="json") for p in positions]
        return pl.DataFrame(rows)

    # Build canonical DataFrame first
    rows = [p.model_dump(mode="json") for p in positions]
    df = pl.DataFrame(rows)

    # Select and rename with transforms
    out_data: dict[str, list[Any]] = {}
    for col_def in columns:
        source = col_def.get("source")
        target = col_def.get("target", source)
        transform = col_def.get("transform")
        if source not in df.columns:
            continue
        values = df[source].to_list()
        out_data[target] = [
            _apply_transform(v, transform, transform_defs) for v in values
        ]
    return pl.DataFrame(out_data)


def write_output(
    df: pl.DataFrame,
    output_dir: Path,
    filename: str,
    formats: list[str] | None = None,
) -> list[Path]:
    """Write a DataFrame to one or more output formats.

    Supports: csv, parquet, json
    Returns list of written file paths.
    """
    if formats is None:
        formats = ["csv"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    base = output_dir / filename
    for fmt in formats:
        f = fmt.lower().strip()
        if f == "csv":
            p = base.with_suffix(".csv")
            df.write_csv(p)
            written.append(p)
        elif f == "parquet":
            p = base.with_suffix(".parquet")
            df.write_parquet(p)
            written.append(p)
        elif f == "json":
            p = base.with_suffix(".json")
            df.write_json(p)
            written.append(p)
    return written


def format_daily_snapshot(
    funded: list[InstrumentPosition],
    pipeline: list[InstrumentPosition],
    sim_day: int,
    sim_date: date,
) -> dict[str, pl.DataFrame]:
    """Create daily snapshot DataFrames.

    Returns:
    - "positions": all positions with sim_day and sim_date columns added
    - "aggregates": daily summary (total funded balance, pipeline count, etc.)
    """
    all_positions = funded + pipeline
    if not all_positions:
        positions_df = pl.DataFrame(
            schema={
                "sim_day": pl.Int64,
                "sim_date": pl.Date,
                "instrument_id": pl.Utf8,
                "position_type": pl.Utf8,
            }
        )
    else:
        rows = [p.model_dump(mode="json") for p in all_positions]
        positions_df = pl.DataFrame(rows)
        positions_df = positions_df.with_columns(
            pl.lit(sim_day).alias("sim_day"),
            pl.lit(sim_date).alias("sim_date"),
        )

    total_funded_balance = sum(p.funded_amount for p in funded)
    total_committed = sum(p.committed_amount for p in funded)
    total_pipeline_value = sum(p.committed_amount for p in pipeline)
    funded_count = len(funded)
    pipeline_count = len(pipeline)

    aggregates_df = pl.DataFrame(
        {
            "sim_day": [sim_day],
            "sim_date": [sim_date],
            "total_funded_balance": [total_funded_balance],
            "total_committed": [total_committed],
            "total_pipeline_value": [total_pipeline_value],
            "pipeline_count": [pipeline_count],
            "funded_count": [funded_count],
        }
    )

    return {"positions": positions_df, "aggregates": aggregates_df}
