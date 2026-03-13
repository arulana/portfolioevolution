"""Schema auto-inferrer — analyzes source data and proposes column mappings.

Given a CSV file, inspects column names, data types, and sample values to
suggest how each column maps to the canonical InstrumentPosition schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import yaml

from portfolio_evolution.utils.config_loader import load_yaml

# Canonical fields and their expected types / common source aliases
_CANONICAL_HINTS: dict[str, dict[str, Any]] = {
    "instrument_id": {
        "type": "string",
        "aliases": ["acctno", "account_no", "loan_id", "loan_number", "deal_id", "opp_id", "facility_id"],
        "required": True,
    },
    "counterparty_id": {
        "type": "string",
        "aliases": ["borrower_id", "customer_id", "cust_id", "counterparty_id", "cif"],
        "required": True,
    },
    "counterparty_name": {
        "type": "string",
        "aliases": ["borrower_name", "borrower", "customer_name", "name", "obligor"],
    },
    "committed_amount": {
        "type": "float",
        "aliases": ["cmt", "commitment", "committed", "commitment_amount", "approved_amount", "expected_amount"],
        "is_currency": True,
    },
    "funded_amount": {
        "type": "float",
        "aliases": ["currbal", "current_balance", "outstanding", "balance", "funded", "principal_balance"],
        "is_currency": True,
    },
    "coupon_rate": {
        "type": "float",
        "aliases": ["rate_over_split", "interest_rate", "rate", "coupon", "note_rate"],
        "is_percent": True,
    },
    "origination_date": {
        "type": "date",
        "aliases": ["original_note_date", "orig_date", "origination", "booking_date", "close_date"],
    },
    "maturity_date": {
        "type": "date",
        "aliases": ["maturity_date", "maturity", "mat_date"],
    },
    "internal_rating": {
        "type": "string",
        "aliases": ["risk_rating", "rating", "internal_rating", "risk_grade", "grade"],
    },
    "segment": {
        "type": "string",
        "aliases": ["classgroup", "segment", "class_group", "portfolio_segment", "loan_segment"],
    },
    "product_type": {
        "type": "string",
        "aliases": ["classcodedescriptions", "product_type", "loan_type", "product_class", "loan_category"],
    },
    "geography": {
        "type": "string",
        "aliases": ["stabbr", "state", "state_code", "geography", "region"],
    },
    "pipeline_stage": {
        "type": "string",
        "aliases": ["stage", "pipeline_stage", "deal_stage", "status"],
    },
    "payment_frequency": {
        "type": "string",
        "aliases": ["payment_frequency", "pay_freq", "frequency"],
    },
    "payment_type": {
        "type": "string",
        "aliases": ["payment_type", "amort_type", "pay_type"],
    },
    "collateral_type": {
        "type": "string",
        "aliases": ["collcodedescription", "collateral_type", "collateral", "coll_type"],
    },
    "property_type": {
        "type": "string",
        "aliases": ["proptypedesc", "property_type", "property_type_code", "prop_type"],
    },
    "relationship_manager": {
        "type": "string",
        "aliases": ["respname", "rm_name", "relationship_manager", "officer"],
    },
    "industry": {
        "type": "string",
        "aliases": ["reportgroup", "industry", "industry_desc", "sector"],
    },
    "industry_code": {
        "type": "string",
        "aliases": ["naics_code", "naics", "sic_code", "industry_code"],
    },
    "as_of_date": {
        "type": "date",
        "aliases": ["monthend", "as_of_date", "report_date", "snapshot_date"],
        "required": True,
    },
}


def _normalize(name: str) -> str:
    """Normalize a column name for fuzzy matching."""
    return name.lower().replace(" ", "_").replace("-", "_").strip()


def _infer_column_type(series: pl.Series) -> str:
    """Infer the logical type of a column from its data."""
    dtype = series.dtype

    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
        return "integer"
    if dtype in (pl.Float32, pl.Float64):
        return "float"
    if dtype == pl.Boolean:
        return "boolean"
    if dtype == pl.Date:
        return "date"
    if dtype == pl.Datetime:
        return "datetime"

    sample = series.drop_nulls().head(20).to_list()
    if not sample:
        return "string"

    sample_strs = [str(s).strip() for s in sample]

    if all(s.upper() in ("TRUE", "FALSE", "YES", "NO", "Y", "N", "1", "0", "T", "F") for s in sample_strs if s):
        return "boolean"

    currency_count = sum(1 for s in sample_strs if s.startswith("$") or s.startswith("($"))
    if currency_count > len(sample_strs) * 0.5:
        return "currency"

    pct_count = sum(1 for s in sample_strs if s.endswith("%"))
    if pct_count > len(sample_strs) * 0.5:
        return "percent"

    date_indicators = ["/", "-"]
    date_count = sum(1 for s in sample_strs if any(d in s for d in date_indicators) and len(s) <= 12)
    if date_count > len(sample_strs) * 0.5:
        return "date"

    numeric_count = 0
    for s in sample_strs:
        try:
            float(s.replace(",", ""))
            numeric_count += 1
        except ValueError:
            pass
    if numeric_count > len(sample_strs) * 0.7:
        return "float"

    return "string"


def _suggest_transform(inferred_type: str, canonical_hint: dict[str, Any] | None) -> str | None:
    """Suggest a transform based on inferred type and target hint."""
    if canonical_hint:
        if canonical_hint.get("is_currency") and inferred_type == "currency":
            return "currency_to_float"
        if canonical_hint.get("is_percent") and inferred_type in ("percent", "float"):
            return "percent_to_decimal"

    type_transforms = {
        "currency": "currency_to_float",
        "percent": "percent_to_decimal",
        "date": "to_date",
        "boolean": "to_bool",
    }
    return type_transforms.get(inferred_type)


def infer_schema(
    data_path: str | Path,
    canonical_schema_path: str | Path | None = None,
    sample_rows: int = 100,
) -> dict[str, Any]:
    """Analyze a source data file and propose column mappings to canonical schema.

    Returns a dict with:
    - columns: list of column analyses
    - suggested_mapping: draft schema_mapping.yaml content
    - unmapped_columns: columns that couldn't be matched
    - coverage_summary: how many canonical fields were matched
    """
    data_path = Path(data_path)

    if not data_path.exists():
        raise FileNotFoundError(f"Source file not found: {data_path}")

    if data_path.suffix.lower() == ".csv":
        df = pl.read_csv(data_path, n_rows=sample_rows, infer_schema_length=0)
    elif data_path.suffix.lower() == ".parquet":
        df = pl.read_parquet(data_path, n_rows=sample_rows)
    else:
        raise ValueError(f"Unsupported file format: {data_path.suffix}")

    columns_analysis = []
    matched_canonical: dict[str, str] = {}
    unmapped = []

    for col_name in df.columns:
        norm = _normalize(col_name)
        series = df[col_name]
        inferred_type = _infer_column_type(series)

        non_null = series.drop_nulls().len()
        total = len(series)
        sample_values = series.drop_nulls().head(5).to_list()

        best_match = None
        best_score = 0.0
        best_hint = None

        for canonical_field, hint in _CANONICAL_HINTS.items():
            if canonical_field in matched_canonical:
                continue

            for alias in hint.get("aliases", []):
                if _normalize(alias) == norm:
                    best_match = canonical_field
                    best_score = 1.0
                    best_hint = hint
                    break
                if norm in _normalize(alias) or _normalize(alias) in norm:
                    score = 0.7
                    if score > best_score:
                        best_match = canonical_field
                        best_score = score
                        best_hint = hint

            if best_score == 1.0:
                break

        transform = _suggest_transform(inferred_type, best_hint) if best_match else None

        col_info: dict[str, Any] = {
            "name": col_name,
            "inferred_type": inferred_type,
            "non_null_count": non_null,
            "null_count": total - non_null,
            "sample_values": [str(v) for v in sample_values[:5]],
            "suggested_canonical_field": best_match,
            "match_confidence": best_score,
            "suggested_transform": transform,
        }
        columns_analysis.append(col_info)

        if best_match and best_score >= 0.7:
            matched_canonical[best_match] = col_name
        else:
            unmapped.append(col_name)

    required_canonical = [f for f, h in _CANONICAL_HINTS.items() if h.get("required")]
    missing_required = [f for f in required_canonical if f not in matched_canonical]

    total_canonical = len(_CANONICAL_HINTS)
    matched_count = len(matched_canonical)

    suggested_mapping = _build_draft_mapping(matched_canonical, columns_analysis)

    return {
        "source_file": str(data_path),
        "total_source_columns": len(df.columns),
        "total_canonical_fields": total_canonical,
        "columns": columns_analysis,
        "matched_fields": matched_canonical,
        "unmapped_columns": unmapped,
        "missing_required_fields": missing_required,
        "coverage_summary": {
            "matched": matched_count,
            "total": total_canonical,
            "coverage_pct": round(matched_count / total_canonical * 100, 1) if total_canonical else 0,
        },
        "suggested_mapping": suggested_mapping,
    }


def _build_draft_mapping(
    matched: dict[str, str],
    columns_analysis: list[dict],
) -> dict:
    """Build a draft schema_mapping.yaml structure from matched fields."""
    col_lookup = {c["name"]: c for c in columns_analysis}

    mappings = []
    for canonical_field, source_col in matched.items():
        entry: dict[str, Any] = {
            "source_column": source_col,
            "target_column": canonical_field,
        }
        col_info = col_lookup.get(source_col, {})
        transform = col_info.get("suggested_transform")
        if transform:
            entry["transform"] = transform
        else:
            entry["transform"] = None
        mappings.append(entry)

    return {
        "version": "1.0",
        "source_type": "auto_inferred",
        "description": "Auto-inferred mapping — review and adjust before use",
        "funded_portfolio": {
            "mappings": mappings,
            "defaults": {
                "position_type": "funded",
                "currency": "USD",
            },
            "passthrough": [],
        },
    }


def save_inferred_mapping(result: dict, output_path: str | Path) -> None:
    """Save the suggested mapping as a YAML file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mapping = result["suggested_mapping"]
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(mapping, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
