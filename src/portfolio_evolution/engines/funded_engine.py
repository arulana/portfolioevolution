"""Funded evolution engine — daily amortisation, maturity, and position lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from portfolio_evolution.models.instrument import InstrumentPosition


@dataclass
class FundedEvolutionResult:
    """Result of one day's evolution for a funded position."""

    position: InstrumentPosition  # Updated position (or original if matured)
    matured: bool
    amortisation_amount: float  # How much principal was paid down today
    events: list  # TransitionEvents generated
    deposit_capture_request: dict | None  # Hook for Wave 2 — always None for now


def compute_daily_amortisation(
    position: InstrumentPosition,
    config: dict,
    sim_date: date,
) -> float:
    """Compute the daily amortisation amount based on type.

    - linear: funded_amount / remaining_days_to_maturity
      (remaining_days = (maturity_date - sim_date).days, minimum 1)
    - bullet: 0.0 (full repayment at maturity)
    - interest_only: 0.0
    - revolving: 0.0
    - sculpted: 0.0 (placeholder — would read schedule)
    - None/other: 0.0

    Never returns negative. Never reduces balance below 0.
    """
    if position.funded_amount <= 0:
        return 0.0

    amort_type = position.amortisation_type

    if amort_type == "linear":
        if position.maturity_date is None:
            return 0.0
        remaining_days = (position.maturity_date - sim_date).days
        if remaining_days <= 0:
            return 0.0
        remaining_days = max(remaining_days, 1)
        daily_amount = position.funded_amount / remaining_days
        return min(daily_amount, position.funded_amount)

    if amort_type in ("bullet", "interest_only", "revolving", "sculpted"):
        return 0.0

    # None or "other"
    return 0.0


def check_maturity(
    position: InstrumentPosition,
    config: dict,
    sim_date: date,
) -> bool:
    """Check if position has reached or passed maturity.

    Returns True if maturity_date is not None and
    sim_date > maturity_date + grace_period_days.
    """
    if position.maturity_date is None:
        return False

    maturity_config = config.get("maturity", {})
    grace_period_days = maturity_config.get("grace_period_days", 0)
    cutoff = position.maturity_date + timedelta(days=grace_period_days)
    return sim_date > cutoff


def evolve_funded_day(
    position: InstrumentPosition,
    config: dict,
    sim_date: date,
) -> FundedEvolutionResult:
    """Evolve a funded position for one day.

    Steps:
    1. Check maturity → if matured, return with matured=True
    2. Compute daily amortisation
    3. Create new position with reduced funded_amount
    4. Return result

    The new position must be a fresh InstrumentPosition (construct from dict),
    not a mutation of the original. Update as_of_date to sim_date.
    """
    if check_maturity(position, config, sim_date):
        return FundedEvolutionResult(
            position=position,
            matured=True,
            amortisation_amount=0.0,
            events=[],
            deposit_capture_request=None,
        )

    amort = compute_daily_amortisation(position, config, sim_date)
    new_funded = max(0.0, position.funded_amount - amort)

    data = position.model_dump()
    data["funded_amount"] = new_funded
    data["as_of_date"] = sim_date

    updated_position = InstrumentPosition(**data)

    return FundedEvolutionResult(
        position=updated_position,
        matured=False,
        amortisation_amount=amort,
        events=[],
        deposit_capture_request=None,
    )
