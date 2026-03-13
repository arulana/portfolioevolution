"""Pure feature engineering functions for InstrumentPosition.

All functions are stateless and handle None/missing gracefully.
"""

from __future__ import annotations

from datetime import date

from portfolio_evolution.models.instrument import InstrumentPosition


def _months_between(d1: date, d2: date) -> int:
    """Compute approximate months between two dates."""
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def derive_tenor_bucket(position: InstrumentPosition) -> str:
    """Categorize tenor into buckets.

    Rules:
    - short: <= 12 months
    - medium: 13-60 months (1-5 years)
    - long: 61-120 months (5-10 years)
    - very_long: > 120 months (10+ years)

    Uses tenor_months if available, else computes from origination_date/maturity_date.
    Returns "unknown" if no data available.
    """
    tenor = position.tenor_months
    if tenor is None and position.origination_date and position.maturity_date:
        tenor = _months_between(position.origination_date, position.maturity_date)
    if tenor is None:
        return "unknown"
    if tenor <= 12:
        return "short"
    if tenor <= 60:
        return "medium"
    if tenor <= 120:
        return "long"
    return "very_long"


def compute_undrawn_amount(position: InstrumentPosition) -> float:
    """Compute undrawn commitment. Already on the model but this is the standalone version."""
    return max(position.committed_amount - position.funded_amount, 0.0)


def derive_rating_band(position: InstrumentPosition) -> str:
    """Map internal rating to risk band.

    Rules (based on numeric rating):
    - 1-3: investment_grade
    - 4: near_investment_grade
    - 5-6: substandard
    - 7: doubtful
    - 8-9: loss
    - None: unrated
    """
    n = position.internal_rating_numeric
    if n is None:
        return "unrated"
    if n <= 3:
        return "investment_grade"
    if n == 4:
        return "near_investment_grade"
    if n <= 6:
        return "substandard"
    if n == 7:
        return "doubtful"
    if n <= 9:
        return "loss"
    return "unrated"


def map_industry_to_taxonomy(position: InstrumentPosition) -> str:
    """Map industry/NAICS code to a broad sector.

    Uses a simple lookup: if industry contains keywords like "real estate", "construction", etc.
    Returns the broad sector name. Returns "other" if no match.

    Broad sectors: real_estate, construction, healthcare, manufacturing,
    retail_trade, professional_services, finance_insurance, accommodation_food,
    transportation, technology, energy, agriculture, government, other
    """
    text = ""
    if position.industry:
        text = position.industry.lower()
    if position.industry_code:
        text = f"{text} {position.industry_code}".strip().lower()
    if not text:
        return "other"

    # Keyword-based mapping (order matters for overlapping terms)
    _KEYWORDS: list[tuple[list[str], str]] = [
        (["real estate", "realestate", "property"], "real_estate"),
        (["construction", "contractor"], "construction"),
        (["healthcare", "health care", "hospital", "medical"], "healthcare"),
        (["manufacturing", "fabrication"], "manufacturing"),
        (["retail", "wholesale"], "retail_trade"),
        (["professional services", "legal", "accounting", "consulting"], "professional_services"),
        (["finance", "insurance", "banking", "credit"], "finance_insurance"),
        (["accommodation", "food", "hospitality", "restaurant", "hotel"], "accommodation_food"),
        (["transportation", "logistics", "shipping", "trucking"], "transportation"),
        (["technology", "software", "telecom", "it services"], "technology"),
        (["energy", "oil", "gas", "utilities", "power"], "energy"),
        (["agriculture", "farming", "agribusiness"], "agriculture"),
        (["government", "public sector", "municipal"], "government"),
    ]
    for keywords, sector in _KEYWORDS:
        if any(kw in text for kw in keywords):
            return sector
    return "other"


def derive_repricing_bucket(position: InstrumentPosition) -> str:
    """Classify repricing risk.

    Rules:
    - Floating/prime rate: "immediate"
    - Fixed rate with maturity in < 1y: "within_1y"
    - Fixed rate with maturity 1-3y: "1y_to_3y"
    - Fixed rate with maturity 3-5y: "3y_to_5y"
    - Fixed rate with maturity 5y+: "beyond_5y"
    - Fixed rate with no maturity: "fixed"
    """
    ct = position.coupon_type
    if ct in ("floating", "prime"):
        return "immediate"

    if ct != "fixed":
        return "unknown"

    # Fixed rate — need remaining maturity
    as_of = position.as_of_date
    mat = position.maturity_date
    if mat is None:
        return "fixed"

    remaining_months = _months_between(as_of, mat)
    if remaining_months < 0:
        return "past_due"
    if remaining_months < 12:
        return "within_1y"
    if remaining_months < 36:
        return "1y_to_3y"
    if remaining_months < 60:
        return "3y_to_5y"
    return "beyond_5y"


def derive_maturity_bucket(position: InstrumentPosition) -> str:
    """Classify remaining maturity into buckets.

    Uses as_of_date and maturity_date to compute remaining months.
    Buckets: "past_due", "within_6m", "6m_to_1y", "1y_to_3y", "3y_to_5y", "5y_to_10y", "beyond_10y", "unknown"
    """
    as_of = position.as_of_date
    mat = position.maturity_date
    if mat is None:
        return "unknown"

    remaining_months = _months_between(as_of, mat)
    if remaining_months < 0:
        return "past_due"
    if remaining_months < 6:
        return "within_6m"
    if remaining_months < 12:
        return "6m_to_1y"
    if remaining_months < 36:
        return "1y_to_3y"
    if remaining_months < 60:
        return "3y_to_5y"
    if remaining_months < 120:
        return "5y_to_10y"
    return "beyond_10y"


def enrich_position(position: InstrumentPosition) -> dict[str, str | float]:
    """Compute all derived features for a position. Returns dict of feature_name -> value.

    Calls all the above functions and returns results as a flat dict.
    This dict can be stored alongside the position or merged into custom_fields.
    """
    return {
        "tenor_bucket": derive_tenor_bucket(position),
        "undrawn_amount": compute_undrawn_amount(position),
        "rating_band": derive_rating_band(position),
        "industry_taxonomy": map_industry_to_taxonomy(position),
        "repricing_bucket": derive_repricing_bucket(position),
        "maturity_bucket": derive_maturity_bucket(position),
    }
