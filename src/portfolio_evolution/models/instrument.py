"""InstrumentPosition — the canonical data model for all portfolio positions."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InstrumentPosition(BaseModel):
    """Normalized representation of a loan/facility position.

    Used for both pipeline opportunities and funded positions.
    This is the fixed contract between ingestion and simulation.
    """

    # --- IDENTIFIERS ---
    instrument_id: str
    counterparty_id: str
    counterparty_name: str | None = None
    facility_id: str | None = None
    position_type: Literal["pipeline", "pipeline_crm", "pipeline_los", "funded"]

    # --- CLASSIFICATION ---
    product_type: str | None = None
    segment: str | None = None
    subsegment: str | None = None
    industry: str | None = None
    industry_code: str | None = None
    geography: str | None = None
    currency: str = "USD"
    origination_channel: str | None = None

    # --- ECONOMICS ---
    committed_amount: float = Field(ge=0)
    funded_amount: float = Field(ge=0)
    utilisation_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    undrawn_amount: float | None = Field(default=None, ge=0)
    coupon_type: Literal["fixed", "floating", "prime", "fee_based", "other"] | None = (
        None
    )
    coupon_rate: float | None = None
    spread_bps: float | None = None
    benchmark_rate: float | None = None
    rate_floor: float | None = None
    fee_rate: float | None = None
    purchase_price: float | None = None
    market_value: float | None = None
    carrying_value: float | None = None
    original_amount: float | None = None

    # --- STRUCTURE / TERMS ---
    origination_date: date | None = None
    expected_close_date: date | None = None
    maturity_date: date | None = None
    renewal_date: date | None = None
    amortisation_type: (
        Literal["bullet", "linear", "sculpted", "revolving", "interest_only", "other"]
        | None
    ) = None
    payment_frequency: (
        Literal[
            "monthly",
            "quarterly",
            "semi_annual",
            "annual",
            "single_payment",
            "other",
        ]
        | None
    ) = None
    payment_type: str | None = None
    seniority: str | None = None
    secured_flag: bool | None = None
    collateral_type: str | None = None
    collateral_code: str | None = None
    property_type: str | None = None
    owner_occupied_flag: bool | None = None
    tenor_months: int | None = None
    purpose_code: str | None = None
    purpose_group: str | None = None

    # --- RISK ---
    internal_rating: str | None = None
    internal_rating_numeric: int | None = None
    external_rating: str | None = None
    pd: float | None = None
    lgd: float | None = None
    watchlist_flag: bool = False
    risk_grade_bucket: str | None = None
    default_flag: bool = False
    tdr_flag: bool = False
    accrual_status: bool = True
    snc_flag: bool = False

    # --- LIFECYCLE ---
    pipeline_stage: str | None = None
    approval_status: str | None = None
    close_probability: float | None = None
    days_in_stage: int = 0
    renewal_probability: float | None = None
    prepayment_probability: float | None = None
    renewed_flag: bool = False
    is_renewal: bool = False

    # --- RELATIONSHIPS ---
    relationship_manager: str | None = None
    relationship_manager_id: str | None = None
    team: str | None = None
    relationship_name: str | None = None

    # --- REGULATORY ---
    fhlb_reporting_code: str | None = None
    rbc_amount: float | None = None

    # --- INCOME ---
    earned_deferred_fees: float | None = None
    earn_interest_balance: float | None = None

    # --- METADATA ---
    data_quality_score: float | None = None
    source_system: str | None = None
    as_of_date: date

    # Passthrough for client-specific fields not in canonical model
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def compute_derived_fields(self) -> InstrumentPosition:
        """Compute utilisation_rate and undrawn_amount if not provided."""
        if self.committed_amount > 0:
            if self.utilisation_rate is None:
                self.utilisation_rate = min(
                    self.funded_amount / self.committed_amount, 1.0
                )
            if self.undrawn_amount is None:
                self.undrawn_amount = max(
                    self.committed_amount - self.funded_amount, 0.0
                )
        else:
            if self.utilisation_rate is None:
                self.utilisation_rate = 0.0
            if self.undrawn_amount is None:
                self.undrawn_amount = 0.0

        if self.tenor_months is None and self.origination_date and self.maturity_date:
            delta = self.maturity_date - self.origination_date
            self.tenor_months = max(int(delta.days / 30.44), 1)

        return self
