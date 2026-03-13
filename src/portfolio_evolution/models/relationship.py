"""BankRelationship — links loans and deposits at the counterparty level.

Enables deposit expectations at loan origination, cross-sell modelling,
relationship-level balance behaviour, and deposit capture probability.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BankRelationship(BaseModel):
    """Represents a bank-counterparty relationship spanning credit and deposits."""

    relationship_id: str
    counterparty_id: str
    segment: str
    relationship_manager: str | None = None

    primary_product: Literal["credit", "deposits", "treasury", "mixed"]

    credit_facilities: list[str] = Field(default_factory=list)
    deposit_accounts: list[str] = Field(default_factory=list)

    cross_sell_score: float = Field(ge=0.0, le=1.0, default=0.0)
    deposit_attachment_ratio: float = Field(ge=0.0, default=0.0)

    model_config = {"extra": "forbid"}
