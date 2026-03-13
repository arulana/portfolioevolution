"""Daily roll-forward aggregation for simulation output.

Computes daily portfolio metrics from position-level state.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from portfolio_evolution.models import InstrumentPosition


def compute_daily_aggregates(
    funded: list[InstrumentPosition],
    pipeline: list[InstrumentPosition],
    sim_day: int,
    sim_date: date,
    new_fundings: int = 0,
    new_funding_amount: float = 0.0,
    maturities: int = 0,
    maturity_amount: float = 0.0,
    dropped_deals: int = 0,
) -> dict[str, Any]:
    """Compute a daily aggregate snapshot from current positions.

    Returns a flat dict suitable for DataFrame row or DuckDB insert.
    """
    total_funded_balance = sum(p.funded_amount for p in funded)
    total_committed = sum(p.committed_amount for p in funded)
    total_undrawn = sum((p.undrawn_amount or 0.0) for p in funded)
    total_pipeline_value = sum(p.committed_amount for p in pipeline)

    segment_funded: dict[str, float] = {}
    rating_funded: dict[str, float] = {}
    for p in funded:
        seg = p.segment or "unknown"
        segment_funded[seg] = segment_funded.get(seg, 0.0) + p.funded_amount
        rtg = p.internal_rating or "unrated"
        rating_funded[rtg] = rating_funded.get(rtg, 0.0) + p.funded_amount

    pipeline_by_stage: dict[str, int] = {}
    for p in pipeline:
        stage = p.pipeline_stage or "unknown"
        pipeline_by_stage[stage] = pipeline_by_stage.get(stage, 0) + 1

    avg_utilisation = (
        total_funded_balance / total_committed if total_committed > 0 else 0.0
    )

    return {
        "sim_day": sim_day,
        "sim_date": sim_date.isoformat(),
        "funded_count": len(funded),
        "pipeline_count": len(pipeline),
        "total_funded_balance": round(total_funded_balance, 2),
        "total_committed": round(total_committed, 2),
        "total_undrawn": round(total_undrawn, 2),
        "total_pipeline_value": round(total_pipeline_value, 2),
        "avg_utilisation": round(avg_utilisation, 4),
        "new_fundings": new_fundings,
        "new_funding_amount": round(new_funding_amount, 2),
        "maturities": maturities,
        "maturity_amount": round(maturity_amount, 2),
        "dropped_deals": dropped_deals,
        "segment_funded_balance": segment_funded,
        "rating_funded_balance": rating_funded,
        "pipeline_by_stage": pipeline_by_stage,
    }


def compute_period_summary(
    daily_aggregates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize a list of daily aggregates into a period summary."""
    if not daily_aggregates:
        return {}

    first = daily_aggregates[0]
    last = daily_aggregates[-1]

    total_new_fundings = sum(d["new_fundings"] for d in daily_aggregates)
    total_new_funding_amt = sum(d["new_funding_amount"] for d in daily_aggregates)
    total_maturities = sum(d["maturities"] for d in daily_aggregates)
    total_maturity_amt = sum(d["maturity_amount"] for d in daily_aggregates)
    total_dropped = sum(d["dropped_deals"] for d in daily_aggregates)

    return {
        "period_start": first["sim_date"],
        "period_end": last["sim_date"],
        "days": len(daily_aggregates),
        "opening_funded_balance": first["total_funded_balance"],
        "closing_funded_balance": last["total_funded_balance"],
        "net_change": round(last["total_funded_balance"] - first["total_funded_balance"], 2),
        "total_new_fundings": total_new_fundings,
        "total_new_funding_amount": round(total_new_funding_amt, 2),
        "total_maturities": total_maturities,
        "total_maturity_amount": round(total_maturity_amt, 2),
        "total_dropped_deals": total_dropped,
        "opening_pipeline_count": first["pipeline_count"],
        "closing_pipeline_count": last["pipeline_count"],
    }
