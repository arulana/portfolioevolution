"""Event models for simulation audit trail and explainability."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


class TransitionEvent(BaseModel):
    """Records a single state transition for explainability.

    Every non-trivial change in position state produces one of these.
    """

    event_id: str
    simulation_day: int
    as_of_date: date
    path_id: int = 0
    scenario_id: str = "baseline"

    instrument_id: str
    position_type: str
    event_type: str  # e.g., stage_advance, funding, amortisation, maturity, rating_change, etc.

    previous_state: dict[str, Any] = {}
    new_state: dict[str, Any] = {}

    reason_code: str
    triggering_rule: str | None = None
    random_draw: float | None = None
    base_probability: float | None = None
    adjusted_probability: float | None = None
    strategy_modifier: float | None = None
    scenario_modifier: float | None = None


class SimulationEvent(BaseModel):
    """Aggregate event for a simulation day."""

    simulation_day: int
    as_of_date: date
    path_id: int = 0
    scenario_id: str = "baseline"

    pipeline_advances: int = 0
    pipeline_funded: int = 0
    pipeline_dropped: int = 0
    funded_matured: int = 0
    funded_renewed: int = 0
    funded_prepaid: int = 0
    rating_upgrades: int = 0
    rating_downgrades: int = 0
    new_defaults: int = 0

    total_funded_balance: float = 0.0
    total_committed: float = 0.0
    total_pipeline_value: float = 0.0
    net_origination: float = 0.0
    net_runoff: float = 0.0
