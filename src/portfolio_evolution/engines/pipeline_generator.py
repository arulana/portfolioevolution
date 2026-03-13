"""Pipeline inflow generator — synthetic new deals flowing into the simulation each day."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from portfolio_evolution.models import InstrumentPosition
from portfolio_evolution.utils.rng import SeededRNG

# Rating numeric (1-9) -> internal_rating string
RATING_MAP: dict[int, str] = {
    1: "AAA",
    2: "AA",
    3: "A",
    4: "BBB",
    5: "BB",
    6: "B",
    7: "CCC",
    8: "CC",
    9: "D",
}


@dataclass
class PipelineInflowConfig:
    """Parsed inflow configuration."""

    enabled: bool
    deals_per_week: float
    segment_weights: dict[str, float]
    avg_deal_size: float
    deal_size_std: float
    seasonality: bool
    rating_distribution: list[float]  # 9 values for ratings 1-9


def parse_inflow_config(config: dict) -> PipelineInflowConfig:
    """Parse the pipeline.inflow section of master_config."""
    pipeline_cfg = config.get("pipeline", {})
    inflow = pipeline_cfg.get("inflow", {})
    return PipelineInflowConfig(
        enabled=pipeline_cfg.get("new_pipeline_inflow", False),
        deals_per_week=inflow.get("deals_per_week", 8),
        segment_weights=inflow.get(
            "segment_weights",
            {
                "cre": 0.40,
                "c_and_i": 0.35,
                "construction": 0.15,
                "consumer": 0.10,
            },
        ),
        avg_deal_size=inflow.get("avg_deal_size", 2_500_000),
        deal_size_std=inflow.get("deal_size_std", 1_500_000),
        seasonality=inflow.get("seasonality", True),
        rating_distribution=inflow.get(
            "rating_distribution",
            [0.05, 0.10, 0.20, 0.30, 0.20, 0.10, 0.03, 0.01, 0.01],
        ),
    )


def _seasonality_factor(d: date) -> float:
    """Seasonal multiplier: Q4 slower (0.7), Q1 ramp (1.1), Q2-Q3 normal (1.0)."""
    month = d.month
    if month in (10, 11, 12):
        return 0.7
    if month in (1, 2, 3):
        return 1.1
    return 1.0


def generate_daily_inflow(
    config: PipelineInflowConfig,
    rng: SeededRNG,
    sim_date: date,
    existing_count: int = 0,
) -> list[InstrumentPosition]:
    """Generate new pipeline deals for one day.

    Average deals per day = deals_per_week / 5 (business days).
    Actual count is Poisson-distributed for realism.
    Apply seasonality if enabled.

    Each new deal:
    - instrument_id: f"NEW-{sim_date.isoformat()}-{seq:03d}"
    - counterparty_id: f"CPTY-NEW-{sim_date.isoformat()}-{seq:03d}"
    - position_type: "pipeline"
    - pipeline_stage: "lead"
    - days_in_stage: 0
    - committed_amount: drawn from normal(avg_deal_size, deal_size_std), min 100_000
    - funded_amount: 0.0
    - segment: weighted random choice from segment_weights
    - internal_rating_numeric: drawn from rating_distribution
    - internal_rating: mapped from numeric (1=AAA, 2=AA, 3=A, 4=BBB, 5=BB, 6=B, 7=CCC, 8=CC, 9=D)
    - coupon_type: random choice ["fixed", "floating"] with 40/60 split
    - coupon_rate: normal(0.06, 0.015), clamp to [0.02, 0.12]
    - as_of_date: sim_date
    """
    if not config.enabled:
        return []

    gen = rng.get_generator()

    # Average deals per day (5 business days per week)
    avg_per_day = config.deals_per_week / 5.0
    if config.seasonality:
        avg_per_day *= _seasonality_factor(sim_date)

    count = int(gen.poisson(avg_per_day))
    if count <= 0:
        return []

    segments = list(config.segment_weights.keys())
    seg_probs = list(config.segment_weights.values())
    total = sum(seg_probs)
    if total > 0:
        seg_probs = [p / total for p in seg_probs]
    else:
        seg_probs = [1.0 / len(segments)] * len(segments)

    rating_probs = config.rating_distribution
    total_rating = sum(rating_probs)
    if total_rating > 0:
        rating_probs = [p / total_rating for p in rating_probs]
    else:
        rating_probs = [1.0 / 9] * 9

    result: list[InstrumentPosition] = []
    for seq in range(count):
        instrument_id = f"NEW-{sim_date.isoformat()}-{seq:03d}"
        counterparty_id = f"CPTY-NEW-{sim_date.isoformat()}-{seq:03d}"

        committed = float(gen.normal(config.avg_deal_size, config.deal_size_std))
        committed = max(committed, 100_000.0)

        segment = str(gen.choice(segments, p=seg_probs))
        rating_numeric = int(gen.choice([1, 2, 3, 4, 5, 6, 7, 8, 9], p=rating_probs))
        internal_rating = RATING_MAP.get(rating_numeric, "B")

        coupon_type = str(gen.choice(["fixed", "floating"], p=[0.4, 0.6]))
        coupon_rate = float(gen.normal(0.06, 0.015))
        coupon_rate = max(0.02, min(0.12, coupon_rate))

        pos = InstrumentPosition(
            instrument_id=instrument_id,
            counterparty_id=counterparty_id,
            counterparty_name=None,
            position_type="pipeline",
            pipeline_stage="lead",
            days_in_stage=0,
            committed_amount=committed,
            funded_amount=0.0,
            segment=segment,
            internal_rating_numeric=rating_numeric,
            internal_rating=internal_rating,
            coupon_type=coupon_type,
            coupon_rate=coupon_rate,
            as_of_date=sim_date,
        )
        result.append(pos)

    return result
