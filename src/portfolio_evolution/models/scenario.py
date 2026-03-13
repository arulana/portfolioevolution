"""ScenarioDefinition — macro scenario overlays for simulation."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class MacroFactors(BaseModel):
    """Macro-economic factors that shift simulation parameters."""

    benchmark_rate_shift_bps: float = 0.0
    credit_spread_shift_bps: float = 0.0
    growth_factor: float = 1.0
    inflation_factor: float = 1.0
    unemployment_factor: float = 1.0
    sector_stress: dict[str, float] = Field(default_factory=dict)
    geography_stress: dict[str, float] = Field(default_factory=dict)


class TransitionModifiers(BaseModel):
    """Multipliers applied to base transition probabilities under a scenario."""

    booking_rate_multiplier: float = 1.0
    fallout_rate_multiplier: float = 1.0
    prepayment_multiplier: float = 1.0
    renewal_multiplier: float = 1.0
    utilisation_multiplier: float = 1.0
    downgrade_multiplier: float = 1.0
    default_multiplier: float = 1.0
    upgrade_multiplier: float = 1.0


class PricingModifiers(BaseModel):
    """Pricing shifts under a scenario."""

    new_business_spread_shift_bps: float = 0.0
    refinance_spread_shift_bps: float = 0.0


class ScenarioDefinition(BaseModel):
    """A complete scenario definition for simulation.

    Scenarios modify transition probabilities, pricing, and
    macro factors to model different economic conditions.
    """

    scenario_id: str
    name: str
    description: str = ""
    start_date: date | None = None
    end_date: date | None = None

    macro_factors: MacroFactors = Field(default_factory=MacroFactors)
    transition_modifiers: TransitionModifiers = Field(
        default_factory=TransitionModifiers
    )
    pricing_modifiers: PricingModifiers = Field(default_factory=PricingModifiers)

    model_config = {"extra": "forbid"}
