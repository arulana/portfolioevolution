"""Balance sheet aggregation for Portfolio Evolution simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from portfolio_evolution.aggregation.liquidity import (
    LiquidityMetrics,
    compute_liquidity_metrics,
)
from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.models.instrument import InstrumentPosition


@dataclass
class BalanceSheetSnapshot:
    """Full balance sheet snapshot combining loans and deposits."""

    sim_day: int
    sim_date: str  # ISO format

    # Assets
    total_funded_loans: float
    total_committed: float
    total_undrawn: float
    pipeline_expected_value: float

    # Liabilities
    total_deposits: float
    stable_deposits: float
    volatile_deposits: float

    # Ratios
    loan_to_deposit_ratio: float
    net_interest_margin_proxy: float  # (avg_loan_rate - avg_deposit_rate) weighted by balance
    deposit_attachment_ratio: float  # deposits_linked_to_loans / total_deposits

    # Liquidity
    liquidity_metrics: LiquidityMetrics | None


def _get_stable_categories(config: dict) -> set[str]:
    """Extract stable liquidity categories from config."""
    stable = config.get("liquidity_classification", {}).get("stable", [])
    return set(stable) if isinstance(stable, list) else set()


def _get_volatile_categories(config: dict) -> set[str]:
    """Extract volatile liquidity categories from config."""
    volatile = config.get("liquidity_classification", {}).get("volatile", [])
    return set(volatile) if isinstance(volatile, list) else set()


def compute_balance_sheet(
    funded: list[InstrumentPosition],
    pipeline: list[InstrumentPosition],
    deposits: list[DepositPosition],
    config: dict,
    sim_day: int,
    sim_date: date,
) -> BalanceSheetSnapshot:
    """Compute full balance sheet snapshot combining loans and deposits."""
    # Assets
    total_funded_loans = sum(p.funded_amount for p in funded)
    total_committed = sum(p.committed_amount for p in funded)
    total_undrawn = sum((p.undrawn_amount or 0.0) for p in funded)
    pipeline_expected_value = sum(p.committed_amount for p in pipeline)

    # Liabilities
    total_deposits = sum(d.current_balance for d in deposits)
    stable_cats = _get_stable_categories(config)
    volatile_cats = _get_volatile_categories(config)
    stable_deposits = sum(
        d.current_balance for d in deposits if d.liquidity_category in stable_cats
    )
    volatile_deposits = sum(
        d.current_balance for d in deposits if d.liquidity_category in volatile_cats
    )

    # LDR
    loan_to_deposit_ratio = (
        round(total_funded_loans / total_deposits, 4) if total_deposits > 0 else 0.0
    )

    # NIM proxy: (weighted avg loan rate - weighted avg deposit rate)
    weighted_loan_rate = sum(
        (p.coupon_rate or 0.0) * p.funded_amount for p in funded
    )
    total_funded_for_rate = total_funded_loans
    avg_loan_rate = (
        weighted_loan_rate / total_funded_for_rate if total_funded_for_rate > 0 else 0.0
    )

    weighted_deposit_rate = sum(d.interest_rate * d.current_balance for d in deposits)
    avg_deposit_rate = (
        weighted_deposit_rate / total_deposits if total_deposits > 0 else 0.0
    )
    net_interest_margin_proxy = round(avg_loan_rate - avg_deposit_rate, 4)

    # Deposit attachment: deposits with linked_loan_ids / total_deposits
    linked_balance = sum(
        d.current_balance for d in deposits if d.linked_loan_ids
    )
    deposit_attachment_ratio = (
        round(linked_balance / total_deposits, 4) if total_deposits > 0 else 0.0
    )

    # Liquidity metrics
    liquidity_metrics = (
        compute_liquidity_metrics(deposits, funded, config)
        if (deposits or funded)
        else None
    )

    return BalanceSheetSnapshot(
        sim_day=sim_day,
        sim_date=sim_date.isoformat(),
        total_funded_loans=round(total_funded_loans, 2),
        total_committed=round(total_committed, 2),
        total_undrawn=round(total_undrawn, 2),
        pipeline_expected_value=round(pipeline_expected_value, 2),
        total_deposits=round(total_deposits, 2),
        stable_deposits=round(stable_deposits, 2),
        volatile_deposits=round(volatile_deposits, 2),
        loan_to_deposit_ratio=loan_to_deposit_ratio,
        net_interest_margin_proxy=net_interest_margin_proxy,
        deposit_attachment_ratio=deposit_attachment_ratio,
        liquidity_metrics=liquidity_metrics,
    )
