"""Portfolio data validator — validates source data without full loading.

Produces a structured quality report with coverage, distribution stats,
categorical counts, warnings, and validation errors.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import ValidationError

from portfolio_evolution.models.instrument import InstrumentPosition
from portfolio_evolution.models.schema_config import SchemaMapping
from portfolio_evolution.utils.config_loader import load_yaml
from portfolio_evolution.utils.transforms import get_transform

# Fields that receive distribution stats (min, max, mean, median)
NUMERIC_FIELDS = {
    "funded_amount",
    "committed_amount",
    "utilisation_rate",
    "undrawn_amount",
    "coupon_rate",
    "spread_bps",
    "benchmark_rate",
    "rate_floor",
    "fee_rate",
    "purchase_price",
    "market_value",
    "carrying_value",
    "original_amount",
    "tenor_months",
    "pd",
    "lgd",
    "close_probability",
    "days_in_stage",
    "renewal_probability",
    "prepayment_probability",
    "rbc_amount",
    "earned_deferred_fees",
    "earn_interest_balance",
    "data_quality_score",
    "internal_rating_numeric",
}

# Fields that receive categorical value counts
CATEGORICAL_FIELDS = {
    "product_type",
    "segment",
    "subsegment",
    "industry",
    "industry_code",
    "geography",
    "origination_channel",
    "coupon_type",
    "amortisation_type",
    "payment_frequency",
    "payment_type",
    "seniority",
    "collateral_type",
    "collateral_code",
    "property_type",
    "purpose_code",
    "purpose_group",
    "internal_rating",
    "external_rating",
    "risk_grade_bucket",
    "pipeline_stage",
    "approval_status",
}

# Fields that need special handling for amortisation engine (actionable warnings)
AMORTISATION_CRITICAL = {"maturity_date", "amortisation_type"}


def _apply_transform(
    value: Any,
    transform_name: str | None,
    transform_params: dict[str, Any],
    schemas_base: Path | None,
) -> tuple[Any, str | None]:
    """Apply transform to a value. Returns (transformed_value, error_message).
    error_message is set when transform raises.
    """
    if transform_name is None:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None, None
        return str(value).strip() if value is not None else None, None

    fn = get_transform(transform_name)
    params = dict(transform_params)
    if schemas_base is not None and "base_path" not in params:
        params["base_path"] = schemas_base
    try:
        return fn(value, params), None
    except Exception as e:
        return None, str(e)


def _to_date_safe(val: Any) -> date | None:
    """Convert value to date for InstrumentPosition. Handles ISO string or date."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def validate_portfolio(
    data_path: Path,
    mapping_path: Path,
    dataset_key: str,
    schemas_base: Path | None = None,
) -> dict:
    """Validate source data without full loading. Returns a quality report dict.

    The report dict contains:
    - total_rows, valid_rows, error_rows
    - field_coverage (non_null_count, null_count, coverage_pct per field)
    - distribution_stats for numeric fields
    - categorical_counts for categorical fields
    - warnings (actionable, non-fatal)
    - errors (row, field, value, error)
    """
    data_path = Path(data_path)
    mapping_path = Path(mapping_path)
    base = schemas_base if schemas_base is not None else mapping_path.parent

    # 1. Load schema mapping
    raw_mapping = load_yaml(mapping_path)
    schema_mapping = SchemaMapping.model_validate(raw_mapping)

    dataset = getattr(schema_mapping, dataset_key)
    if dataset is None:
        return {
            "total_rows": 0,
            "valid_rows": 0,
            "error_rows": 0,
            "field_coverage": {},
            "distribution_stats": {},
            "categorical_counts": {},
            "warnings": [f"Dataset '{dataset_key}' not defined in schema mapping"],
            "errors": [],
        }

    # 2. Read raw data with Polars
    try:
        df = pl.read_csv(data_path, infer_schema_length=10000)
    except Exception as e:
        return {
            "total_rows": 0,
            "valid_rows": 0,
            "error_rows": 0,
            "field_coverage": {},
            "distribution_stats": {},
            "categorical_counts": {},
            "warnings": [],
            "errors": [{"row": -1, "field": "file", "value": str(data_path), "error": str(e)}],
        }

    total_rows = len(df)
    defaults = dict(dataset.defaults) if dataset.defaults else {}

    # Build target_column -> (source_column, transform, params) for each mapping
    col_map: dict[str, tuple[str, str | None, dict[str, Any]]] = {}
    for m in dataset.mappings:
        col_map[m.target_column] = (
            m.source_column,
            m.transform,
            m.transform_params or {},
        )

    # 3. Collect coverage, distribution, and categorical stats per mapped field
    field_coverage: dict[str, dict[str, Any]] = {}
    distribution_values: dict[str, list[float]] = {f: [] for f in NUMERIC_FIELDS}
    categorical_values: dict[str, list[Any]] = {f: [] for f in CATEGORICAL_FIELDS}

    for target_col, (source_col, transform_name, transform_params) in col_map.items():
        if source_col not in df.columns:
            field_coverage[target_col] = {
                "non_null_count": 0,
                "null_count": total_rows,
                "coverage_pct": 0.0,
            }
            continue

        non_null = 0
        for i in range(total_rows):
            raw = df.row(i, named=True).get(source_col)
            transformed, _ = _apply_transform(
                raw, transform_name, transform_params, base
            )
            if transformed is not None and transformed != "":
                non_null += 1
                if target_col in NUMERIC_FIELDS:
                    try:
                        v = float(transformed)
                        if math.isfinite(v):
                            distribution_values[target_col].append(v)
                    except (TypeError, ValueError):
                        pass
                if target_col in CATEGORICAL_FIELDS:
                    categorical_values[target_col].append(str(transformed))

        null_count = total_rows - non_null
        coverage_pct = (non_null / total_rows * 100.0) if total_rows > 0 else 0.0
        field_coverage[target_col] = {
            "non_null_count": non_null,
            "null_count": null_count,
            "coverage_pct": round(coverage_pct, 2),
        }

    # 4. Compute distribution_stats (only for fields with data)
    distribution_stats: dict[str, dict[str, float]] = {}
    for field, values in distribution_values.items():
        if not values:
            continue
        distribution_stats[field] = {
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "mean": round(statistics.mean(values), 4),
            "median": round(statistics.median(values), 4),
        }

    # 5. Compute categorical_counts
    categorical_counts: dict[str, dict[str, int]] = {}
    for field, values in categorical_values.items():
        if not values:
            continue
        counts: dict[str, int] = {}
        for v in values:
            key = str(v) if v is not None else ""
            if key:
                counts[key] = counts.get(key, 0) + 1
        if counts:
            categorical_counts[field] = dict(sorted(counts.items(), key=lambda x: -x[1]))

    # 6. Attempt to construct InstrumentPosition per row — collect errors
    errors: list[dict[str, Any]] = []
    valid_rows = 0

    for row_idx in range(total_rows):
        row_dict: dict[str, Any] = dict(defaults)
        row_data = df.row(row_idx, named=True)

        transform_errors: list[dict[str, Any]] = []
        for target_col, (source_col, transform_name, transform_params) in col_map.items():
            if source_col not in df.columns:
                continue
            raw = row_data.get(source_col)
            transformed, transform_err = _apply_transform(
                raw, transform_name, transform_params, base
            )
            if transform_err is not None:
                transform_errors.append({
                    "row": row_idx + 1,
                    "field": target_col,
                    "value": str(raw)[:200],
                    "error": f"Transform failed: {transform_err}",
                })
            elif transformed is not None:
                row_dict[target_col] = transformed

        errors.extend(transform_errors)

        # Fallback: counterparty_id often not mapped — use instrument_id
        if "counterparty_id" not in row_dict or not row_dict.get("counterparty_id"):
            inst_id = row_dict.get("instrument_id")
            if inst_id:
                row_dict["counterparty_id"] = str(inst_id)

        # Convert date strings to date objects for Pydantic
        for date_field in ("origination_date", "expected_close_date", "maturity_date", "renewal_date", "as_of_date"):
            if date_field in row_dict and row_dict[date_field] is not None:
                d = _to_date_safe(row_dict[date_field])
                row_dict[date_field] = d

        # Filter to only InstrumentPosition fields (exclude passthrough)
        allowed = set(InstrumentPosition.model_fields.keys())
        filtered = {k: v for k, v in row_dict.items() if k in allowed}

        try:
            InstrumentPosition(**filtered)
            if not transform_errors:
                valid_rows += 1
        except ValidationError as e:
            for err in e.errors():
                loc = err.get("loc", ())
                field = loc[0] if loc else "unknown"
                msg = err.get("msg", str(err))
                val = filtered.get(field, row_dict.get(field, ""))
                errors.append({
                    "row": row_idx + 1,
                    "field": str(field),
                    "value": str(val)[:200],
                    "error": msg,
                })
        except Exception as ex:
            errors.append({
                "row": row_idx + 1,
                "field": "unknown",
                "value": str(row_dict)[:200],
                "error": str(ex),
            })

    error_rows = total_rows - valid_rows

    # 7. Generate actionable warnings
    warnings: list[str] = []
    for field, cov in field_coverage.items():
        pct = cov["coverage_pct"]
        if pct < 50.0 and pct > 0:
            if field in AMORTISATION_CRITICAL:
                warnings.append(
                    f"{pct:.0f}% of rows missing '{field}' — "
                    "this will cause amortisation engine to skip these positions"
                )
            else:
                warnings.append(
                    f"{pct:.0f}% of rows missing '{field}'"
                )
        elif pct == 0 and field in AMORTISATION_CRITICAL:
            warnings.append(
                f"100% of rows missing '{field}' — "
                "amortisation engine will skip all positions"
            )

    # 8. Build JSON-serializable report
    report: dict[str, Any] = {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "error_rows": error_rows,
        "field_coverage": field_coverage,
        "distribution_stats": distribution_stats,
        "categorical_counts": categorical_counts,
        "warnings": warnings,
        "errors": errors[:500],  # Cap errors to avoid huge reports
    }

    return report
