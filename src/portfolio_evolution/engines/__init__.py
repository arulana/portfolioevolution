"""Core simulation engines."""

from portfolio_evolution.engines.pipeline_engine import (
    PipelineAdvanceResult,
    advance_pipeline_day,
    compute_age_factor,
    compute_rating_factor,
    compute_segment_factor,
    convert_to_funded,
    get_base_probabilities,
)

from portfolio_evolution.engines.funded_engine import (
    FundedEvolutionResult,
    check_maturity,
    compute_daily_amortisation,
    evolve_funded_day,
)

from portfolio_evolution.engines.rating_engine import (
    RatingMigrationResult,
    annual_to_daily_prob,
    annual_to_monthly_prob,
    get_transition_probs,
    migrate_rating,
)

from portfolio_evolution.engines.deposit_engine import (
    DepositEvolutionResult,
    evolve_deposit_day,
)

from portfolio_evolution.engines.deposit_capture import (
    DepositCaptureResult,
    capture_deposits_at_funding,
)

from portfolio_evolution.engines.deposit_pricing import (
    DepositPricingResult,
    reprice_deposit,
)

__all__ = [
    "PipelineAdvanceResult",
    "advance_pipeline_day",
    "compute_age_factor",
    "compute_rating_factor",
    "compute_segment_factor",
    "convert_to_funded",
    "get_base_probabilities",
    "FundedEvolutionResult",
    "check_maturity",
    "compute_daily_amortisation",
    "evolve_funded_day",
    "RatingMigrationResult",
    "annual_to_daily_prob",
    "annual_to_monthly_prob",
    "get_transition_probs",
    "migrate_rating",
    "DepositEvolutionResult",
    "evolve_deposit_day",
    "DepositCaptureResult",
    "capture_deposits_at_funding",
    "DepositPricingResult",
    "reprice_deposit",
]
