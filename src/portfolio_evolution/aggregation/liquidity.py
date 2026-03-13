"""Liquidity metrics calculator for Portfolio Evolution simulation."""

from __future__ import annotations

from dataclasses import dataclass

from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.models.instrument import InstrumentPosition


@dataclass
class LiquidityMetrics:
    """Aggregated liquidity metrics for a simulation snapshot."""

    total_deposits: float
    stable_deposits: float
    volatile_deposits: float
    stable_deposit_ratio: float  # stable / total

    loan_to_deposit_ratio: float  # LDR = total_funded / total_deposits

    # LCR proxy: weighted outflow based on stressed rates
    lcr_stressed_outflow: float
    lcr_stable_funding_ratio: float  # stable_deposits / total_funded

    # Concentration
    top_10_depositor_concentration: float  # % of deposits from top 10 counterparties
    deposit_type_concentration: dict[str, float]  # % by deposit type

    deposit_count: int
    avg_beta: float
    avg_stickiness: float


def _get_stable_categories(config: dict) -> set[str]:
    """Extract stable liquidity categories from config."""
    stable = config.get("liquidity_classification", {}).get("stable", [])
    return set(stable) if isinstance(stable, list) else set()


def _get_volatile_categories(config: dict) -> set[str]:
    """Extract volatile liquidity categories from config."""
    volatile = config.get("liquidity_classification", {}).get("volatile", [])
    return set(volatile) if isinstance(volatile, list) else set()


def _get_stressed_outflow_rates(config: dict) -> dict[str, float]:
    """Extract stressed outflow rates by liquidity category from config."""
    rates = config.get("stressed_outflow_rates", {})
    return dict(rates) if isinstance(rates, dict) else {}


def compute_deposit_stability_ratio(
    deposits: list[DepositPosition],
    config: dict,
) -> float:
    """Ratio of stable to total deposits."""
    if not deposits:
        return 0.0
    stable_cats = _get_stable_categories(config)
    total = sum(d.current_balance for d in deposits)
    if total == 0:
        return 0.0
    stable = sum(
        d.current_balance for d in deposits if d.liquidity_category in stable_cats
    )
    return round(stable / total, 4)


def compute_lcr_proxy(
    deposits: list[DepositPosition],
    config: dict,
) -> float:
    """Simplified LCR: sum(balance × stressed_outflow_rate) by liquidity category."""
    rates = _get_stressed_outflow_rates(config)
    outflow = 0.0
    for d in deposits:
        rate = rates.get(d.liquidity_category, 0.0)
        outflow += d.current_balance * rate
    return round(outflow, 2)


def compute_concentration_risk(deposits: list[DepositPosition]) -> dict:
    """Concentration metrics: top-10, by type, by segment."""
    total = sum(d.current_balance for d in deposits)
    if total == 0:
        return {
            "top_10_depositor_concentration": 0.0,
            "deposit_type_concentration": {},
            "deposit_segment_concentration": {},
        }

    # Top 10 by counterparty
    by_counterparty: dict[str, float] = {}
    for d in deposits:
        by_counterparty[d.counterparty_id] = (
            by_counterparty.get(d.counterparty_id, 0.0) + d.current_balance
        )
    sorted_cps = sorted(by_counterparty.values(), reverse=True)
    top10_sum = sum(sorted_cps[:10])
    top10_pct = round(top10_sum / total, 4)

    # By deposit type
    by_type: dict[str, float] = {}
    for d in deposits:
        by_type[d.deposit_type] = by_type.get(d.deposit_type, 0.0) + d.current_balance
    type_concentration = {
        k: round(v / total, 4) for k, v in by_type.items()
    }

    # By segment
    by_segment: dict[str, float] = {}
    for d in deposits:
        seg = d.segment or "unknown"
        by_segment[seg] = by_segment.get(seg, 0.0) + d.current_balance
    segment_concentration = {
        k: round(v / total, 4) for k, v in by_segment.items()
    }

    return {
        "top_10_depositor_concentration": top10_pct,
        "deposit_type_concentration": type_concentration,
        "deposit_segment_concentration": segment_concentration,
    }


def compute_liquidity_metrics(
    deposits: list[DepositPosition],
    funded: list[InstrumentPosition],
    config: dict,
) -> LiquidityMetrics:
    """Compute all liquidity metrics from current positions."""
    stable_cats = _get_stable_categories(config)
    volatile_cats = _get_volatile_categories(config)
    rates = _get_stressed_outflow_rates(config)

    total_deposits = sum(d.current_balance for d in deposits)
    stable_deposits = sum(
        d.current_balance for d in deposits if d.liquidity_category in stable_cats
    )
    volatile_deposits = sum(
        d.current_balance for d in deposits if d.liquidity_category in volatile_cats
    )

    stable_deposit_ratio = (
        round(stable_deposits / total_deposits, 4) if total_deposits > 0 else 0.0
    )

    total_funded = sum(p.funded_amount for p in funded)
    loan_to_deposit_ratio = (
        round(total_funded / total_deposits, 4) if total_deposits > 0 else 0.0
    )

    lcr_stressed_outflow = 0.0
    for d in deposits:
        rate = rates.get(d.liquidity_category, 0.0)
        lcr_stressed_outflow += d.current_balance * rate
    lcr_stressed_outflow = round(lcr_stressed_outflow, 2)

    lcr_stable_funding_ratio = (
        round(stable_deposits / total_funded, 4) if total_funded > 0 else 0.0
    )

    concentration = compute_concentration_risk(deposits)
    top_10_depositor_concentration = concentration["top_10_depositor_concentration"]
    deposit_type_concentration = concentration["deposit_type_concentration"]

    deposit_count = len(deposits)
    if deposit_count > 0:
        total_bal = total_deposits
        avg_beta = (
            sum(d.beta * d.current_balance for d in deposits) / total_bal
            if total_bal > 0
            else sum(d.beta for d in deposits) / deposit_count
        )
        avg_stickiness = (
            sum(d.stickiness_score * d.current_balance for d in deposits) / total_bal
            if total_bal > 0
            else sum(d.stickiness_score for d in deposits) / deposit_count
        )
    else:
        avg_beta = 0.0
        avg_stickiness = 0.0

    return LiquidityMetrics(
        total_deposits=round(total_deposits, 2),
        stable_deposits=round(stable_deposits, 2),
        volatile_deposits=round(volatile_deposits, 2),
        stable_deposit_ratio=stable_deposit_ratio,
        loan_to_deposit_ratio=loan_to_deposit_ratio,
        lcr_stressed_outflow=lcr_stressed_outflow,
        lcr_stable_funding_ratio=lcr_stable_funding_ratio,
        top_10_depositor_concentration=top_10_depositor_concentration,
        deposit_type_concentration=deposit_type_concentration,
        deposit_count=deposit_count,
        avg_beta=round(avg_beta, 4),
        avg_stickiness=round(avg_stickiness, 4),
    )
