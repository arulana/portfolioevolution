"""Rating migration engine — simulates credit rating transitions using a transition matrix."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from portfolio_evolution.models.instrument import InstrumentPosition
from portfolio_evolution.utils.rng import SeededRNG


@dataclass
class RatingMigrationResult:
    """Result of a rating migration check."""

    instrument_id: str
    previous_rating: str
    new_rating: str
    migrated: bool
    direction: str  # "upgrade", "downgrade", "stable", "default"
    random_draw: float | None
    probability_used: float | None


def annual_to_daily_prob(annual_prob: float) -> float:
    """Convert annual transition probability to daily.

    Formula: 1 - (1 - annual_prob) ^ (1/365)
    """
    return 1.0 - (1.0 - annual_prob) ** (1.0 / 365.0)


def annual_to_monthly_prob(annual_prob: float) -> float:
    """Convert annual transition probability to monthly.

    Formula: 1 - (1 - annual_prob) ^ (1/12)
    """
    return 1.0 - (1.0 - annual_prob) ** (1.0 / 12.0)


def _get_rating_index(rating: str, ratings: list[str]) -> int:
    """Return 1-based index of rating in the ordered list (AAA=1, D=9)."""
    try:
        return ratings.index(rating) + 1
    except ValueError:
        raise ValueError(f"Unknown rating: {rating}. Expected one of {ratings}")


def _convert_cadence(annual_probs: list[float], cadence: str) -> list[float]:
    """Convert annual probabilities to daily or monthly based on cadence."""
    if cadence == "daily":
        return [annual_to_daily_prob(p) for p in annual_probs]
    if cadence == "monthly":
        return [annual_to_monthly_prob(p) for p in annual_probs]
    raise ValueError(f"Unknown cadence: {cadence}. Expected 'daily' or 'monthly'")


def get_transition_probs(
    current_rating: str,
    config: dict,
    watchlist: bool = False,
    scenario_id: str = "baseline",
    segment: str | None = None,
) -> dict[str, float]:
    """Get transition probabilities for a rating.

    Steps:
    1. Look up the row in the annual transition matrix
    2. Convert to daily or monthly based on cadence config
    3. If watchlist, multiply downgrade columns by watchlist_downgrade_multiplier
    4. Apply scenario stress multiplier to downgrade/default columns
    5. Apply segment adjustment
    6. Re-normalize so row sums to 1.0
    7. Return {target_rating: probability}
    """
    atm = config.get("annual_transition_matrix", {})
    ratings: list[str] = atm.get("ratings", [])
    matrix: dict = atm.get("matrix", {})

    if current_rating not in matrix:
        raise ValueError(f"No transition row for rating: {current_rating}")

    annual_row = matrix[current_rating]
    cadence = config.get("cadence", "monthly")
    probs = _convert_cadence(annual_row, cadence)

    current_idx = _get_rating_index(current_rating, ratings)
    watchlist_mult = (
        config.get("watchlist_downgrade_multiplier", 1.0) if watchlist else 1.0
    )
    scenario_mult = config.get("scenario_stress_multipliers", {}).get(
        scenario_id, 1.0
    )
    segment_adjustments = config.get("segment_adjustments", {})
    segment_mult = 1.0
    if segment and segment in segment_adjustments:
        seg_cfg = segment_adjustments[segment]
        if isinstance(seg_cfg, dict):
            segment_mult = seg_cfg.get("downgrade_multiplier", 1.0)
        else:
            segment_mult = 1.0

    # Apply multipliers to downgrade columns (index > current)
    result_probs: list[float] = []
    for i, p in enumerate(probs):
        target_idx = i + 1
        if target_idx > current_idx:
            p *= watchlist_mult * scenario_mult * segment_mult
        result_probs.append(p)

    # Re-normalize so row sums to 1.0
    total = sum(result_probs)
    if total <= 0:
        total = 1.0
    result_probs = [p / total for p in result_probs]

    return dict(zip(ratings, result_probs))


def migrate_rating(
    position: InstrumentPosition,
    config: dict,
    rng: SeededRNG,
    sim_date: date,
    path_id: int = 0,
    scenario_id: str = "baseline",
) -> RatingMigrationResult:
    """Attempt a rating migration for one position.

    Steps:
    1. If current rating is in absorbing_states, return stable (no migration)
    2. Get transition probabilities
    3. Draw uniform random
    4. Walk cumulative probabilities to determine new rating
    5. Return result with direction
    """
    instrument_id = position.instrument_id
    current_rating = position.internal_rating or "BBB"
    absorbing = config.get("absorbing_states", ["D"])

    if current_rating in absorbing:
        return RatingMigrationResult(
            instrument_id=instrument_id,
            previous_rating=current_rating,
            new_rating=current_rating,
            migrated=False,
            direction="stable",
            random_draw=None,
            probability_used=None,
        )

    probs = get_transition_probs(
        current_rating,
        config,
        watchlist=position.watchlist_flag,
        scenario_id=scenario_id,
        segment=position.segment,
    )

    draw = float(rng.uniform(path_id=path_id, scenario_id=scenario_id))
    ratings = list(probs.keys())
    cum = 0.0
    new_rating = ratings[-1]
    probability_used = 0.0

    for r, p in probs.items():
        cum += p
        if draw < cum:
            new_rating = r
            probability_used = p
            break

    ratings_list = config.get("annual_transition_matrix", {}).get(
        "ratings", ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "D"]
    )
    current_idx = _get_rating_index(current_rating, ratings_list)
    new_idx = _get_rating_index(new_rating, ratings_list)

    if new_rating == "D":
        direction = "default"
    elif new_rating == current_rating:
        direction = "stable"
    elif new_idx < current_idx:
        direction = "upgrade"
    else:
        direction = "downgrade"

    return RatingMigrationResult(
        instrument_id=instrument_id,
        previous_rating=current_rating,
        new_rating=new_rating,
        migrated=new_rating != current_rating,
        direction=direction,
        random_draw=draw,
        probability_used=probability_used,
    )
