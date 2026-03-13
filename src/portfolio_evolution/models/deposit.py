"""DepositPosition — canonical model for bank deposit accounts.

Unlike loans (contractual instruments), deposits are behavioural balances.
The model emphasises beta, stickiness, decay, and withdrawal probability
rather than amortisation schedules and maturity dates.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class DepositPosition(BaseModel):
    """Normalized representation of a deposit account."""

    deposit_id: str
    counterparty_id: str
    relationship_id: str | None = None

    deposit_type: Literal[
        "operating",
        "corporate_transaction",
        "escrow",
        "term_deposit",
        "savings",
        "retail_checking",
        "sweep",
        "brokered",
    ]

    segment: str
    industry: str | None = None
    geography: str | None = None
    currency: str = "USD"

    # --- BALANCES ---
    current_balance: float = Field(ge=0)
    average_balance_30d: float | None = None
    committed_operating_balance: float | None = None

    # --- PRICING ---
    interest_rate: float
    rate_type: Literal["fixed", "floating"]
    benchmark: str | None = None
    spread: float | None = None
    fee_offset: float | None = None

    # --- BEHAVIOURAL ---
    beta: float = Field(ge=0.0, le=1.0, default=0.35)
    stickiness_score: float = Field(ge=0.0, le=1.0, default=0.5)
    decay_half_life_days: int | None = None
    withdrawal_probability: float | None = None

    # --- LIFECYCLE ---
    origination_date: date
    expected_duration_days: int | None = None
    linked_loan_ids: list[str] = Field(default_factory=list)

    # --- LIQUIDITY CLASSIFICATION ---
    liquidity_category: Literal[
        "stable_operational",
        "non_operational",
        "rate_sensitive",
        "volatile",
        "brokered",
    ]

    # --- RISK ---
    deposit_runoff_score: float | None = None

    # --- METADATA ---
    source: str = ""
    as_of_date: date
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class PipelineDepositExpectation(BaseModel):
    """Deposit expectations attached to a pipeline deal.

    When a pipeline loan funds and deposit_attachment_expected is True,
    the funding converter creates DepositPositions based on these fields.
    """

    deposit_attachment_expected: bool = False
    expected_operating_balance: float | None = None
    expected_term_deposit_balance: float | None = None
    deposit_cross_sell_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    deposit_beta_expected: float | None = None
