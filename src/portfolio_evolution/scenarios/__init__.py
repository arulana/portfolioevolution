"""Scenario engine for macro overlays."""

from portfolio_evolution.scenarios.overlay import (
    ScenarioOverlay,
    apply_deposit_overlay,
    apply_pipeline_overlay,
    apply_rating_overlay,
    get_benchmark_rate_change,
    load_scenarios,
)

__all__ = [
    "ScenarioOverlay",
    "load_scenarios",
    "apply_pipeline_overlay",
    "apply_rating_overlay",
    "apply_deposit_overlay",
    "get_benchmark_rate_change",
]
