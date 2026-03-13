"""Pipeline transition engine — simulates daily deal progression through stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio_evolution.models.instrument import InstrumentPosition
    from portfolio_evolution.utils.rng import SeededRNG

# Segment aliases for config key lookup (normalized lowercase)
_SEGMENT_ALIASES: dict[str, list[str]] = {
    "cre": ["cre", "commercial_real_estate", "commercial real estate", "commercialrealestate"],
    "c_and_i": ["c_and_i", "c&i", "c and i", "candi"],
    "construction": ["construction"],
}


@dataclass
class PipelineAdvanceResult:
    """Result of a single day's pipeline advance for one deal."""

    instrument_id: str
    previous_stage: str
    new_stage: str
    advanced: bool
    dropped: bool
    expired: bool
    funded: bool
    days_in_stage: int  # updated days_in_stage
    random_draw: float | None
    base_probability: float | None
    adjusted_probability: float | None
    deposit_capture_request: dict | None  # Hook for Wave 2 deposit capture


def get_base_probabilities(stage: str, config: dict) -> dict[str, float]:
    """Return {next_stage: base_daily_prob} for the given stage."""
    transitions = config.get("transitions", {})
    stage_transitions = transitions.get(stage, {})
    result: dict[str, float] = {}
    for next_stage, spec in stage_transitions.items():
        if isinstance(spec, dict) and "base_daily_prob" in spec:
            result[next_stage] = float(spec["base_daily_prob"])
    return result


def compute_age_factor(stage: str, days_in_stage: int, config: dict) -> float:
    """Compute the stage age multiplier.

    - decay model: factor = 0.5 ^ (days_in_stage / half_life_days)
    - acceleration model: factor = min(1 + (days_in_stage / ramp_days) * 0.5, max_multiplier)
    - Default: 1.0 if no config for this stage
    """
    factors = config.get("stage_age_factors", {})
    stage_config = factors.get(stage)
    if not stage_config:
        return 1.0

    model = stage_config.get("model")
    if model == "decay":
        half_life = stage_config.get("half_life_days")
        if half_life is None or half_life <= 0:
            return 1.0
        return 0.5 ** (days_in_stage / half_life)
    if model == "acceleration":
        ramp_days = stage_config.get("ramp_days")
        max_mult = stage_config.get("max_multiplier", 2.0)
        if ramp_days is None or ramp_days <= 0:
            return 1.0
        factor = 1.0 + (days_in_stage / ramp_days) * 0.5
        return min(factor, max_mult)
    return 1.0


def _segment_to_config_key(segment: str | None) -> str | None:
    """Map segment string to config key (cre, c_and_i, construction)."""
    if not segment:
        return None
    normalized = segment.lower().strip()
    for key, aliases in _SEGMENT_ALIASES.items():
        if normalized in aliases or normalized == key:
            return key
    return None


def compute_segment_factor(segment: str | None, config: dict, is_advance: bool) -> float:
    """Lookup segment advance or fallout multiplier. Default 1.0."""
    key = _segment_to_config_key(segment)
    if not key:
        return 1.0
    factors = config.get("segment_factors", {})
    segment_config = factors.get(key)
    if not segment_config:
        return 1.0
    mult_key = "advance_multiplier" if is_advance else "fallout_multiplier"
    return float(segment_config.get(mult_key, 1.0))


def compute_rating_factor(rating_numeric: int | None, config: dict, is_advance: bool) -> float:
    """Lookup rating advance or fallout multiplier. Default 1.0."""
    if rating_numeric is None:
        return 1.0
    key = str(rating_numeric)
    factors = config.get("rating_factors", {})
    rating_config = factors.get(key)
    if not rating_config:
        return 1.0
    mult_key = "advance_multiplier" if is_advance else "fallout_multiplier"
    return float(rating_config.get(mult_key, 1.0))


def advance_pipeline_day(
    position: "InstrumentPosition",
    config: dict,
    rng: "SeededRNG",
    sim_date: date,
    path_id: int = 0,
    scenario_id: str = "baseline",
) -> PipelineAdvanceResult:
    """Simulate one day for a pipeline position.

    Steps:
    1. Check expiry: if days_in_stage > max_days, return expired
    2. Get base probabilities for current stage
    3. For each possible transition (advance + dropped):
       - Compute adjusted_prob = base * age_factor * segment_factor * rating_factor
    4. Draw uniform random
    5. Compare draw against cumulative probabilities
    6. Return result (stayed, advanced, dropped, or funded if stage was closing → funded)
    """
    stage = position.pipeline_stage
    instrument_id = position.instrument_id
    days = position.days_in_stage

    # Terminal states: no change
    if stage in ("funded", "dropped", "expired"):
        return PipelineAdvanceResult(
            instrument_id=instrument_id,
            previous_stage=stage or "",
            new_stage=stage or "",
            advanced=False,
            dropped=False,
            expired=False,
            funded=False,
            days_in_stage=days,
            random_draw=None,
            base_probability=None,
            adjusted_probability=None,
            deposit_capture_request=None,
        )

    if not stage:
        return PipelineAdvanceResult(
            instrument_id=instrument_id,
            previous_stage="",
            new_stage="",
            advanced=False,
            dropped=False,
            expired=False,
            funded=False,
            days_in_stage=days,
            random_draw=None,
            base_probability=None,
            adjusted_probability=None,
            deposit_capture_request=None,
        )

    # 1. Check expiry
    expiry_config = config.get("expiry", {})
    if expiry_config.get("enabled"):
        max_days_map = expiry_config.get("max_days_in_stage", {})
        max_days = max_days_map.get(stage)
        if max_days is not None and days >= max_days:
            return PipelineAdvanceResult(
                instrument_id=instrument_id,
                previous_stage=stage,
                new_stage="expired",
                advanced=False,
                dropped=False,
                expired=True,
                funded=False,
                days_in_stage=days,
                random_draw=None,
                base_probability=None,
                adjusted_probability=None,
                deposit_capture_request=None,
            )

    # 2. Get base probabilities
    base_probs = get_base_probabilities(stage, config)
    if not base_probs:
        return PipelineAdvanceResult(
            instrument_id=instrument_id,
            previous_stage=stage,
            new_stage=stage,
            advanced=False,
            dropped=False,
            expired=False,
            funded=False,
            days_in_stage=days + 1,
            random_draw=None,
            base_probability=None,
            adjusted_probability=None,
            deposit_capture_request=None,
        )

    # 3. Compute adjusted probabilities
    age_factor = compute_age_factor(stage, days, config)
    segment = position.segment
    rating = position.internal_rating_numeric

    transitions: list[tuple[str, float, float]] = []  # (next_stage, base_prob, adjusted_prob)
    for next_stage, base_prob in base_probs.items():
        is_advance = next_stage not in ("dropped", "expired")
        seg_factor = compute_segment_factor(segment, config, is_advance)
        rating_factor = compute_rating_factor(rating, config, is_advance)
        adjusted = base_prob * age_factor * seg_factor * rating_factor
        transitions.append((next_stage, base_prob, adjusted))

    # 4. Draw uniform random
    draw = float(rng.uniform(path_id=path_id, scenario_id=scenario_id))

    # 5. Compare against cumulative probabilities
    cumul = 0.0
    for next_stage, base_prob, adjusted in transitions:
        cumul += adjusted
        if draw < cumul:
            # Transition occurred
            is_dropped = next_stage == "dropped"
            is_funded = next_stage == "funded"
            is_advanced = not is_dropped and not is_funded

            return PipelineAdvanceResult(
                instrument_id=instrument_id,
                previous_stage=stage,
                new_stage=next_stage,
                advanced=is_advanced,
                dropped=is_dropped,
                expired=False,
                funded=is_funded,
                days_in_stage=0 if (is_advanced or is_dropped or is_funded) else days + 1,
                random_draw=draw,
                base_probability=base_prob,
                adjusted_probability=adjusted,
                deposit_capture_request=None,
            )

    # 6. Stayed in stage
    return PipelineAdvanceResult(
        instrument_id=instrument_id,
        previous_stage=stage,
        new_stage=stage,
        advanced=False,
        dropped=False,
        expired=False,
        funded=False,
        days_in_stage=days + 1,
        random_draw=draw,
        base_probability=None,
        adjusted_probability=None,
        deposit_capture_request=None,
    )


def convert_to_funded(
    pipeline_pos: "InstrumentPosition",
    funding_date: date,
) -> "InstrumentPosition":
    """Convert a pipeline deal to a funded position.

    - position_type → "funded"
    - funded_amount → committed_amount (fully drawn initially, or partial for revolvers)
    - origination_date → funding_date
    - maturity_date → funding_date + expected tenor (or existing maturity_date if set)
    - pipeline_stage → None
    - days_in_stage → 0

    Returns a NEW InstrumentPosition (don't mutate the original).
    """
    from portfolio_evolution.models.instrument import InstrumentPosition

    # Compute maturity_date
    maturity_date = pipeline_pos.maturity_date
    if maturity_date is None and pipeline_pos.tenor_months is not None:
        tenor_days = int(pipeline_pos.tenor_months * 30.44)
        maturity_date = funding_date + timedelta(days=tenor_days)
    elif maturity_date is None:
        # Fallback: 60 months
        maturity_date = funding_date + timedelta(days=int(60 * 30.44))

    data = pipeline_pos.model_dump()
    data.update(
        position_type="funded",
        funded_amount=pipeline_pos.committed_amount,
        origination_date=funding_date,
        maturity_date=maturity_date,
        pipeline_stage=None,
        days_in_stage=0,
    )
    return InstrumentPosition(**data)
