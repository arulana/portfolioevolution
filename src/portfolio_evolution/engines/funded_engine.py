"""Funded evolution engine — daily amortisation, maturity, renewal, and position lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from portfolio_evolution.models.instrument import InstrumentPosition

if TYPE_CHECKING:
    from portfolio_evolution.utils.rng import SeededRNG


@dataclass
class FundedEvolutionResult:
    """Result of one day's evolution for a funded position."""

    position: InstrumentPosition
    matured: bool
    prepaid: bool
    amortisation_amount: float
    events: list
    deposit_capture_request: dict | None


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


def _get_prepayment_probability(
    position: InstrumentPosition,
    config: dict,
) -> float:
    """Look up daily prepayment probability from config with segment overrides."""
    prepay_cfg = config.get("prepayment", {})
    if not prepay_cfg.get("enabled", False):
        return 0.0

    min_age = prepay_cfg.get("minimum_age_days", 90)
    if position.origination_date:
        age = (position.as_of_date - position.origination_date).days
        if age < min_age:
            return 0.0

    base = prepay_cfg.get("base_daily_probability", 0.0005)

    seg_overrides = prepay_cfg.get("segment_overrides", {})
    if position.segment:
        seg_key = position.segment.lower().replace(" ", "_")
        if seg_key in seg_overrides:
            base = float(seg_overrides[seg_key])

    return base


def evolve_funded_day(
    position: InstrumentPosition,
    config: dict,
    sim_date: date,
    rng: "SeededRNG | None" = None,
) -> FundedEvolutionResult:
    """Evolve a funded position for one day.

    Steps:
    1. Check maturity
    2. Check prepayment (stochastic)
    3. Compute daily amortisation
    4. Return updated position
    """
    if check_maturity(position, config, sim_date):
        return FundedEvolutionResult(
            position=position,
            matured=True,
            prepaid=False,
            amortisation_amount=0.0,
            events=[],
            deposit_capture_request=None,
        )

    if rng is not None:
        prepay_prob = _get_prepayment_probability(position, config)
        if prepay_prob > 0:
            draw = float(rng.uniform())
            if draw < prepay_prob:
                return FundedEvolutionResult(
                    position=position,
                    matured=False,
                    prepaid=True,
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
        prepaid=False,
        amortisation_amount=amort,
        events=[],
        deposit_capture_request=None,
    )


@dataclass
class RenewalResult:
    """Result of a renewal decision for a matured position."""

    renewed: bool
    renewal_position: InstrumentPosition | None
    random_draw: float | None


def _get_renewal_probability(
    position: InstrumentPosition,
    config: dict,
) -> float:
    """Look up renewal probability from config, with segment and rating overrides."""
    renewal_cfg = config.get("renewal", {})
    base = renewal_cfg.get("base_renewal_probability", 0.65)

    seg_overrides = renewal_cfg.get("segment_overrides", {})
    if position.segment:
        seg_key = position.segment.lower().replace(" ", "_")
        if seg_key in seg_overrides:
            base = float(seg_overrides[seg_key])

    rat_overrides = renewal_cfg.get("rating_overrides", {})
    if position.internal_rating_numeric is not None:
        rat_key = str(position.internal_rating_numeric)
        if rat_key in rat_overrides:
            base = float(rat_overrides[rat_key])

    return base


def attempt_renewal(
    position: InstrumentPosition,
    config: dict,
    rng: "SeededRNG",
    sim_date: date,
) -> RenewalResult:
    """Decide whether a matured position renews and re-enters underwriting.

    If renewed, creates a new pipeline_los position with:
    - pipeline_stage = "underwriting"
    - is_renewal = True
    - Same counterparty, segment, rating
    - Potentially adjusted rate
    - New maturity based on renewal_term_months or original tenor
    """
    renewal_cfg = config.get("renewal", {})
    if not renewal_cfg.get("enabled", False):
        return RenewalResult(renewed=False, renewal_position=None, random_draw=None)

    prob = _get_renewal_probability(position, config)
    draw = float(rng.uniform())

    if draw >= prob:
        return RenewalResult(renewed=False, renewal_position=None, random_draw=draw)

    rate_adj_bps = renewal_cfg.get("renewal_rate_adjustment_bps", 0)
    new_rate = position.coupon_rate
    if new_rate is not None and rate_adj_bps:
        new_rate = new_rate + (float(rate_adj_bps) / 10000.0)

    renewal_term = renewal_cfg.get("renewal_term_months")
    if renewal_term is None:
        renewal_term = position.tenor_months or 60

    data = position.model_dump()
    data.update(
        instrument_id=f"RNW-{position.instrument_id}-{sim_date.isoformat()}",
        position_type="pipeline_los",
        source_system="los",
        pipeline_stage="underwriting",
        days_in_stage=0,
        is_renewal=True,
        renewed_flag=True,
        funded_amount=0.0,
        committed_amount=position.funded_amount,
        origination_date=None,
        maturity_date=None,
        tenor_months=int(renewal_term),
        coupon_rate=new_rate,
        as_of_date=sim_date,
    )

    renewal_pos = InstrumentPosition(**data)
    return RenewalResult(renewed=True, renewal_position=renewal_pos, random_draw=draw)
