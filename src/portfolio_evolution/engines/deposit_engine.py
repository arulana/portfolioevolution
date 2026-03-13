"""Deposit evolution engine — daily decay, rate-sensitive withdrawals, utilisation linkage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.utils.rng import SeededRNG


@dataclass
class DepositEvolutionResult:
    """Result of one day's evolution for a deposit."""

    position: DepositPosition  # Updated deposit
    balance_change: float  # Change in balance this day
    withdrawal_amount: float  # Amount withdrawn
    inflow_amount: float  # Amount flowed in
    decay_applied: bool


def evolve_deposit_day(
    deposit: DepositPosition,
    config: dict,
    rng: SeededRNG,
    sim_date: date,
    linked_loan_utilisation: float | None = None,
    linked_loan_amount: float | None = None,
    benchmark_rate_change_bps: float = 0.0,
) -> DepositEvolutionResult:
    """Evolve a deposit for one day.

    Steps:
    1. Apply natural decay: balance *= 0.5 ^ (1 / half_life_days) if decay enabled
    2. Apply rate-sensitive withdrawals: if benchmark_rate_change_bps > 0,
       withdrawal_prob = withdrawal_base × (1 + beta × rate_change_bps / 100)
       Draw random, if hit → withdraw (rate_change × beta × balance) portion
    3. Apply utilisation linkage: if operating deposit and linked_loan_utilisation provided,
       adjust balance toward (loan_utilisation × operating_balance_ratio × linked_loan_amount)
    4. Return result with updated position
    """
    balance = deposit.current_balance
    withdrawal_amount = 0.0
    inflow_amount = 0.0
    decay_applied = False

    # --- 1. Natural decay ---
    decay_config = config.get("decay", {})
    if decay_config.get("enabled", True):
        half_life = deposit.decay_half_life_days
        if half_life is None:
            defaults = decay_config.get("default_half_life_days", {})
            half_life = defaults.get(deposit.deposit_type)

        if half_life is not None and half_life > 0:
            daily_decay = 1.0 - (0.5 ** (1.0 / half_life))
            balance = balance * (1.0 - daily_decay)
            decay_applied = True

    # --- 2. Rate-sensitive withdrawals ---
    rate_config = config.get("rate_sensitivity", {})
    if rate_config.get("enabled", True) and benchmark_rate_change_bps > 0:
        beta = deposit.beta
        withdrawal_base = deposit.withdrawal_probability
        if withdrawal_base is None:
            defaults = rate_config.get("withdrawal_base", {})
            withdrawal_base = defaults.get(deposit.deposit_type, 0.001)

        withdrawal_prob = withdrawal_base * (
            1.0 + beta * benchmark_rate_change_bps / 100.0
        )
        draw = float(rng.uniform(path_id=0, scenario_id="baseline"))

        if draw < withdrawal_prob:
            # Withdraw portion: (rate_change_bps/10000) × beta × balance
            portion = (benchmark_rate_change_bps / 10000.0) * beta
            withdrawal_amount = min(balance * portion, balance)
            balance = max(0.0, balance - withdrawal_amount)

    # --- 3. Utilisation linkage (operating deposits only) ---
    util_config = config.get("utilisation_linkage", {})
    if (
        util_config.get("enabled", True)
        and deposit.deposit_type == "operating"
        and linked_loan_utilisation is not None
        and linked_loan_amount is not None
        and linked_loan_amount > 0
    ):
        ratio = util_config.get("operating_balance_ratio", 0.15)
        target_balance = (
            linked_loan_utilisation * ratio * linked_loan_amount
        )
        # Adjust toward target (partial adjustment for daily step)
        diff = target_balance - balance
        # Use stickiness to control adjustment speed: lower stickiness = faster adjustment
        adjustment_factor = 1.0 - (deposit.stickiness_score * 0.9)  # 0.1 to 1.0
        balance = balance + diff * adjustment_factor
        balance = max(0.0, balance)
        if diff > 0:
            inflow_amount = diff * adjustment_factor
        else:
            withdrawal_amount += abs(diff) * adjustment_factor

    balance_change = balance - deposit.current_balance

    updated_position = deposit.model_copy(
        update={
            "current_balance": balance,
            "as_of_date": sim_date,
        }
    )

    return DepositEvolutionResult(
        position=updated_position,
        balance_change=balance_change,
        withdrawal_amount=withdrawal_amount,
        inflow_amount=inflow_amount,
        decay_applied=decay_applied,
    )
