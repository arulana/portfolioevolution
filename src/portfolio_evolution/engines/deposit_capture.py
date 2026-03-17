"""Deposit capture engine — create deposits when loans fund."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.models.instrument import InstrumentPosition
from portfolio_evolution.models.relationship import BankRelationship
from portfolio_evolution.utils.rng import SeededRNG
from portfolio_evolution.utils.transforms import normalize_segment_key


@dataclass
class DepositCaptureResult:
    """Result of deposit capture attempt at loan funding."""

    captured: bool
    deposits_created: list[DepositPosition]
    probability_used: float
    random_draw: float


def capture_deposits_at_funding(
    funded_position: InstrumentPosition,
    config: dict,
    rng: SeededRNG,
    sim_date: date,
    relationship: BankRelationship | None = None,
) -> DepositCaptureResult:
    """Attempt to capture deposits when a loan funds.

    Steps:
    1. Look up base capture probability by segment from config
    2. Apply relationship multiplier if relationship exists
    3. Draw random — if below probability, create deposits
    4. Create operating deposit = funded_amount × operating_balance_ratio
    5. Optionally create term deposit based on cross-sell probability
    6. Return result with created deposits
    """
    capture_config = config.get("capture", {})
    if not capture_config.get("enabled", True):
        return DepositCaptureResult(
            captured=False,
            deposits_created=[],
            probability_used=0.0,
            random_draw=0.0,
        )

    base_probs = capture_config.get("base_probability", {})
    segment = normalize_segment_key(funded_position.segment) or "other_services"
    base_prob = base_probs.get(segment, 0.5)

    factors = capture_config.get("factors", {})
    probability = base_prob

    if relationship is not None:
        probability *= factors.get("relationship_multiplier", 1.0)

    probability = min(1.0, probability)

    draw = float(rng.uniform(path_id=0, scenario_id="baseline"))

    if draw >= probability:
        return DepositCaptureResult(
            captured=False,
            deposits_created=[],
            probability_used=probability,
            random_draw=draw,
        )

    deposits_created: list[DepositPosition] = []
    util_config = config.get("utilisation_linkage", {})
    operating_ratio = util_config.get("operating_balance_ratio", 0.15)
    funded_amount = funded_position.funded_amount
    instrument_id = funded_position.instrument_id
    counterparty_id = funded_position.counterparty_id
    relationship_id = relationship.relationship_id if relationship else None

    # 4. Create operating deposit
    operating_balance = funded_amount * operating_ratio
    operating_deposit = DepositPosition(
        deposit_id=f"DEP-{instrument_id}-0",
        counterparty_id=counterparty_id,
        relationship_id=relationship_id,
        deposit_type="operating",
        segment=segment or "other_services",
        current_balance=operating_balance,
        average_balance_30d=operating_balance,
        interest_rate=0.0,
        rate_type="floating",
        liquidity_category="stable_operational",
        origination_date=sim_date,
        linked_loan_ids=[instrument_id],
        as_of_date=sim_date,
        source="capture_at_funding",
    )
    deposits_created.append(operating_deposit)

    # 5. Optionally create term deposit based on cross-sell probability
    cross_sell_prob = 0.0
    if relationship is not None:
        cross_sell_prob = relationship.cross_sell_score
    cross_sell_prob = min(1.0, max(0.0, cross_sell_prob))

    cross_sell_draw = float(rng.uniform(path_id=0, scenario_id="baseline"))

    if cross_sell_prob > 0 and cross_sell_draw < cross_sell_prob:
        term_balance = funded_amount * 0.1  # 10% of funded as term (config could add this)
        term_deposit = DepositPosition(
            deposit_id=f"DEP-{instrument_id}-1",
            counterparty_id=counterparty_id,
            relationship_id=relationship_id,
            deposit_type="term_deposit",
            segment=segment or "other_services",
            current_balance=term_balance,
            average_balance_30d=term_balance,
            interest_rate=0.0,
            rate_type="fixed",
            liquidity_category="rate_sensitive",
            origination_date=sim_date,
            linked_loan_ids=[instrument_id],
            as_of_date=sim_date,
            source="capture_at_funding",
        )
        deposits_created.append(term_deposit)

    return DepositCaptureResult(
        captured=True,
        deposits_created=deposits_created,
        probability_used=probability,
        random_draw=draw,
    )
