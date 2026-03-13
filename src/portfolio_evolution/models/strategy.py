"""StrategySignal — represents management direction for simulation overlays."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class StrategySignal(BaseModel):
    """A management strategy signal that modifies simulation behaviour.

    Can be sourced from earnings calls, investor presentations,
    manual input, or policy documents.
    """

    signal_id: str
    source_type: Literal[
        "earnings_call", "investor_presentation", "manual", "policy"
    ]
    statement_text: str
    effective_date: date
    expiry_date: date | None = None

    dimension: Literal[
        "segment",
        "industry",
        "geography",
        "product_type",
        "rating_band",
        "tenor",
        "pricing",
        "utilisation",
        "risk_appetite",
    ]
    target_value: str | float | dict[str, Any] | None = None
    direction: Literal[
        "increase", "decrease", "tighten", "loosen", "maintain", "rotate"
    ]
    magnitude: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    translation_rule: str | None = None

    model_config = {"extra": "forbid"}

    def is_active(self, check_date: date) -> bool:
        """Whether this signal is active on the given date."""
        if check_date < self.effective_date:
            return False
        if self.expiry_date and check_date > self.expiry_date:
            return False
        return True


class StrategyModifiers(BaseModel):
    """Quantitative modifiers derived from strategy signals.

    Applied as multipliers to base transition probabilities.
    """

    pipeline_inflow_multiplier: float = 1.0
    approval_multiplier: float = 1.0
    pricing_shift_bps: float = 0.0
    fallout_multiplier: float = 1.0
    renewal_multiplier: float = 1.0
    prepayment_multiplier: float = 1.0
    utilisation_multiplier: float = 1.0
    downgrade_multiplier: float = 1.0
    tenor_multiplier: float = 1.0

    segment_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)
