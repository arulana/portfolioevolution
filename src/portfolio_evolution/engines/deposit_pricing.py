"""Deposit pricing engine — reprice deposits based on beta model."""

from __future__ import annotations

from dataclasses import dataclass

from portfolio_evolution.models.deposit import DepositPosition


@dataclass
class DepositPricingResult:
    """Result of repricing a deposit."""

    deposit_id: str
    previous_rate: float
    new_rate: float
    rate_change: float


def reprice_deposit(
    deposit: DepositPosition,
    config: dict,
    benchmark_rate_change_bps: float = 0.0,
) -> DepositPricingResult:
    """Reprice a deposit based on beta model.

    new_rate = current_rate + (beta × benchmark_rate_change_bps / 10000)
    Rate floor = 0.0 (no negative rates)
    """
    previous_rate = deposit.interest_rate
    beta = deposit.beta

    rate_change = beta * benchmark_rate_change_bps / 10000.0
    new_rate = max(0.0, previous_rate + rate_change)

    return DepositPricingResult(
        deposit_id=deposit.deposit_id,
        previous_rate=previous_rate,
        new_rate=new_rate,
        rate_change=rate_change,
    )
