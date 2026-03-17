"""Reusable data transforms for schema mapping.

Each transform is a callable that takes a value and optional params,
and returns the transformed value. Registered in TRANSFORM_REGISTRY.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from portfolio_evolution.utils.config_loader import load_lookup

TransformFn = Callable[[Any, dict[str, Any]], Any]

_lookup_cache: dict[str, dict[str, str]] = {}


def _get_lookup(mapping_file: str, base_path: Path | None = None) -> dict[str, str]:
    """Load and cache a lookup crosswalk."""
    cache_key = str(mapping_file)
    if cache_key not in _lookup_cache:
        path = Path(mapping_file) if base_path is None else base_path / mapping_file
        _lookup_cache[cache_key] = load_lookup(path)
    return _lookup_cache[cache_key]


def clear_lookup_cache() -> None:
    """Clear the lookup cache (useful for testing)."""
    _lookup_cache.clear()


def _strip_currency(value: Any) -> float:
    """Remove $, commas, parentheses from currency strings and convert to float."""
    if value is None or value == "":
        return 0.0
    s = str(value).strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
    if s == "" or s == "-":
        return 0.0
    result = float(s)
    return -result if negative else result


def normalize_segment_key(segment: str | None) -> str | None:
    """Normalize a segment name to a clean YAML-safe config key.

    Handles Karen's industry sector names (e.g. 'Admin & Waste Mgmt')
    and legacy lending categories (e.g. 'cre', 'C&I').
    """
    if not segment:
        return None
    key = segment.lower().strip()
    key = key.replace("&", "_and_")
    key = key.replace(" ", "_")
    while "__" in key:
        key = key.replace("__", "_")
    return key.strip("_")


# Lending category groupings — maps normalized sector key to its category.
# Used for reporting / aggregation, not for config lookup.
SECTOR_TO_LENDING_CATEGORY: dict[str, str] = {
    "real_estate_and_leasing": "cre",
    "agriculture": "c_and_i",
    "manufacturing": "c_and_i",
    "mining_and_extraction": "c_and_i",
    "wholesale_trade": "c_and_i",
    "retail_trade": "c_and_i",
    "transportation": "c_and_i",
    "information": "c_and_i",
    "technology": "c_and_i",
    "professional_services": "c_and_i",
    "admin_and_waste_mgmt": "c_and_i",
    "other_services": "c_and_i",
    "holding_companies": "c_and_i",
    "utilities": "c_and_i",
    "construction": "construction",
    "government": "specialty",
    "education": "specialty",
    "healthcare": "specialty",
    "finance_and_insurance": "specialty",
    "arts_and_recreation": "specialty",
    "food_and_accommodation": "specialty",
}


# --- Transform implementations ---


def to_float(value: Any, params: dict[str, Any] | None = None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def to_int(value: Any, params: dict[str, Any] | None = None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None


def to_date(value: Any, params: dict[str, Any] | None = None) -> str | None:
    """Parse date string. Returns ISO format string."""
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip()
    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def to_bool(value: Any, params: dict[str, Any] | None = None) -> bool:
    if value is None:
        return False
    s = str(value).strip().upper()
    return s in ("TRUE", "1", "YES", "Y", "T")


def invert_bool(value: Any, params: dict[str, Any] | None = None) -> bool:
    """Invert a boolean — used for Accrual where FALSE means non-accrual."""
    return not to_bool(value, params)


def percent_to_decimal(value: Any, params: dict[str, Any] | None = None) -> float | None:
    f = to_float(value)
    if f is None:
        return None
    if f > 1.0:
        return f / 100.0
    return f


def bps_to_decimal(value: Any, params: dict[str, Any] | None = None) -> float | None:
    f = to_float(value)
    if f is None:
        return None
    return f / 10000.0


def currency_to_float(value: Any, params: dict[str, Any] | None = None) -> float:
    return _strip_currency(value)


def rate_basis_to_bps(value: Any, params: dict[str, Any] | None = None) -> float | None:
    """Convert rate adjustment basis (in percentage points) to basis points."""
    f = to_float(value)
    if f is None:
        return None
    return f * 100.0


def uppercase(value: Any, params: dict[str, Any] | None = None) -> str | None:
    if value is None:
        return None
    return str(value).upper()


def lowercase(value: Any, params: dict[str, Any] | None = None) -> str | None:
    if value is None:
        return None
    return str(value).lower()


def strip(value: Any, params: dict[str, Any] | None = None) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def default_if_null(value: Any, params: dict[str, Any] | None = None) -> Any:
    if value is None or str(value).strip() == "":
        return params.get("default") if params else None
    return value


def multiply(value: Any, params: dict[str, Any] | None = None) -> float | None:
    f = to_float(value)
    if f is None:
        return None
    factor = params.get("factor", 1.0) if params else 1.0
    return f * factor


def lookup_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    """Generic lookup transform using a crosswalk YAML."""
    if value is None:
        return None
    mapping_file = params.get("mapping_file", "") if params else ""
    base_path = Path(params.get("base_path", "schemas")) if params else Path("schemas")
    lookup = _get_lookup(mapping_file, base_path)
    return lookup.get(str(value).strip(), str(value))


def rating_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def stage_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def segment_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def product_type_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def rate_type_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def payment_freq_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def payment_type_normalize(value: Any, params: dict[str, Any] | None = None) -> str | None:
    """Normalize the many payment type variations into canonical forms."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if s in ("P&I", "P+I", "PRINCIPAL & INTEREST", "PRINCIPAL AND INTEREST"):
        return "P&I"
    if s in ("INTEREST", "I.O.", "INTEREST ONLY", "IO"):
        return "Interest Only"
    if s in ("SINGLE PAYMENT AT MATURITY", "BALLOON"):
        return "Bullet"
    return str(value).strip()


def amort_type_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def risk_bucket_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def property_type_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def owner_occ_to_bool(value: Any, params: dict[str, Any] | None = None) -> bool:
    """Convert Owner Occupied Code (0=NOO, 9=OO) to boolean."""
    if value is None:
        return False
    s = str(value).strip()
    return s == "9" or s.upper() in ("TRUE", "YES", "1", "OO")


def deposit_type_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


def deposit_liquidity_map(value: Any, params: dict[str, Any] | None = None) -> str | None:
    return lookup_map(value, params)


# --- Registry ---

TRANSFORM_REGISTRY: dict[str, TransformFn] = {
    "to_float": to_float,
    "to_int": to_int,
    "to_date": to_date,
    "to_bool": to_bool,
    "invert_bool": invert_bool,
    "percent_to_decimal": percent_to_decimal,
    "bps_to_decimal": bps_to_decimal,
    "currency_to_float": currency_to_float,
    "rate_basis_to_bps": rate_basis_to_bps,
    "uppercase": uppercase,
    "lowercase": lowercase,
    "strip": strip,
    "default_if_null": default_if_null,
    "multiply": multiply,
    "rating_map": rating_map,
    "stage_map": stage_map,
    "segment_map": segment_map,
    "product_type_map": product_type_map,
    "rate_type_map": rate_type_map,
    "payment_freq_map": payment_freq_map,
    "payment_type_normalize": payment_type_normalize,
    "amort_type_map": amort_type_map,
    "risk_bucket_map": risk_bucket_map,
    "property_type_map": property_type_map,
    "owner_occ_to_bool": owner_occ_to_bool,
    "rate_basis_to_bps": rate_basis_to_bps,
    "deposit_type_map": deposit_type_map,
    "deposit_liquidity_map": deposit_liquidity_map,
}


def get_transform(name: str) -> TransformFn:
    """Get a transform function by name."""
    if name not in TRANSFORM_REGISTRY:
        raise ValueError(
            f"Unknown transform '{name}'. "
            f"Available: {sorted(TRANSFORM_REGISTRY.keys())}"
        )
    return TRANSFORM_REGISTRY[name]
