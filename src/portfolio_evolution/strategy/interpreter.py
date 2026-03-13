"""Strategy interpreter — converts management strategy signals to engine adjustments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from portfolio_evolution.models import StrategySignal
from portfolio_evolution.utils.config_loader import load_yaml


@dataclass
class StrategyAdjustment:
    """Computed adjustment from a strategy signal."""

    signal_id: str
    target_segment: str | None
    pipeline_booking_multiplier: float  # 1.0 = no change
    pipeline_fallout_multiplier: float
    funded_prepayment_multiplier: float
    funded_renewal_multiplier: float
    deposit_capture_multiplier: float
    deposit_pricing_shift_bps: float


def _magnitude_bucket(magnitude: float) -> str:
    """Map magnitude float to high/medium/low."""
    if magnitude >= 0.6:
        return "high"
    if magnitude >= 0.3:
        return "medium"
    return "low"


def _direction_category(direction: str) -> str:
    """Map direction to increase/decrease/maintain."""
    if direction in ("increase", "loosen"):
        return "increase"
    if direction in ("decrease", "tighten"):
        return "decrease"
    return "maintain"


def interpret_signal(signal: StrategySignal, sim_date: date) -> StrategyAdjustment | None:
    """Convert a strategy signal to engine adjustments.

    Returns None if signal is not active on sim_date.

    Direction + magnitude mapping:
    - increase + high: booking × 1.3, fallout × 0.7, renewal × 1.2
    - increase + medium: booking × 1.15, fallout × 0.85, renewal × 1.1
    - decrease + high: booking × 0.7, fallout × 1.3, renewal × 0.8
    - maintain: all × 1.0
    """
    if not signal.is_active(sim_date):
        return None

    direction = _direction_category(signal.direction)
    magnitude = _magnitude_bucket(signal.magnitude)

    target_segment: str | None = None
    if signal.dimension == "segment" and isinstance(signal.target_value, str):
        target_segment = signal.target_value

    if direction == "maintain":
        return StrategyAdjustment(
            signal_id=signal.signal_id,
            target_segment=target_segment,
            pipeline_booking_multiplier=1.0,
            pipeline_fallout_multiplier=1.0,
            funded_prepayment_multiplier=1.0,
            funded_renewal_multiplier=1.0,
            deposit_capture_multiplier=1.0,
            deposit_pricing_shift_bps=0.0,
        )

    if direction == "increase":
        if magnitude == "high":
            return StrategyAdjustment(
                signal_id=signal.signal_id,
                target_segment=target_segment,
                pipeline_booking_multiplier=1.3,
                pipeline_fallout_multiplier=0.7,
                funded_prepayment_multiplier=1.0,
                funded_renewal_multiplier=1.2,
                deposit_capture_multiplier=1.2,
                deposit_pricing_shift_bps=25.0,
            )
        if magnitude == "medium":
            return StrategyAdjustment(
                signal_id=signal.signal_id,
                target_segment=target_segment,
                pipeline_booking_multiplier=1.15,
                pipeline_fallout_multiplier=0.85,
                funded_prepayment_multiplier=1.0,
                funded_renewal_multiplier=1.1,
                deposit_capture_multiplier=1.1,
                deposit_pricing_shift_bps=10.0,
            )
        # low: mild increase
        return StrategyAdjustment(
            signal_id=signal.signal_id,
            target_segment=target_segment,
            pipeline_booking_multiplier=1.05,
            pipeline_fallout_multiplier=0.95,
            funded_prepayment_multiplier=1.0,
            funded_renewal_multiplier=1.05,
            deposit_capture_multiplier=1.05,
            deposit_pricing_shift_bps=5.0,
        )

    # direction == "decrease"
    if magnitude == "high":
        return StrategyAdjustment(
            signal_id=signal.signal_id,
            target_segment=target_segment,
            pipeline_booking_multiplier=0.7,
            pipeline_fallout_multiplier=1.3,
            funded_prepayment_multiplier=1.2,
            funded_renewal_multiplier=0.8,
            deposit_capture_multiplier=0.8,
            deposit_pricing_shift_bps=-25.0,
        )
    if magnitude == "medium":
        return StrategyAdjustment(
            signal_id=signal.signal_id,
            target_segment=target_segment,
            pipeline_booking_multiplier=0.85,
            pipeline_fallout_multiplier=1.15,
            funded_prepayment_multiplier=1.1,
            funded_renewal_multiplier=0.9,
            deposit_capture_multiplier=0.9,
            deposit_pricing_shift_bps=-10.0,
        )
    # low: mild decrease
    return StrategyAdjustment(
        signal_id=signal.signal_id,
        target_segment=target_segment,
        pipeline_booking_multiplier=0.95,
        pipeline_fallout_multiplier=1.05,
        funded_prepayment_multiplier=1.02,
        funded_renewal_multiplier=0.95,
        deposit_capture_multiplier=0.95,
        deposit_pricing_shift_bps=-5.0,
    )


def _parse_signal_dict(raw: dict) -> dict:
    """Parse date strings in raw signal dict for Pydantic validation."""
    result = raw.copy()
    for key in ("effective_date", "expiry_date"):
        if key in result and result[key] is not None:
            val = result[key]
            if isinstance(val, str):
                result[key] = date.fromisoformat(val)
    return result


def load_archetype_signals(archetype_path: Path) -> list[StrategySignal]:
    """Load strategy signals from an archetype config.

    Expects a 'strategy_signals' key in the YAML. Returns empty list if absent
    or file not found.
    """
    try:
        data = load_yaml(archetype_path)
    except FileNotFoundError:
        return []

    if not data or "strategy_signals" not in data:
        return []

    signals: list[StrategySignal] = []
    for raw in data["strategy_signals"]:
        if not isinstance(raw, dict):
            continue
        try:
            parsed = _parse_signal_dict(raw)
            sig = StrategySignal.model_validate(parsed)
            signals.append(sig)
        except Exception:
            continue

    return signals


def _neutral_adjustment() -> StrategyAdjustment:
    """Return neutral adjustment (1.0 multipliers, 0 shifts)."""
    return StrategyAdjustment(
        signal_id="",
        target_segment=None,
        pipeline_booking_multiplier=1.0,
        pipeline_fallout_multiplier=1.0,
        funded_prepayment_multiplier=1.0,
        funded_renewal_multiplier=1.0,
        deposit_capture_multiplier=1.0,
        deposit_pricing_shift_bps=0.0,
    )


def compute_aggregate_adjustment(
    adjustments: list[StrategyAdjustment],
    segment: str | None = None,
) -> StrategyAdjustment:
    """Combine multiple active strategy adjustments.

    - Filter to adjustments matching segment (or segment=None for global)
    - Multiply all multipliers together
    - Sum all shifts
    """
    if not adjustments:
        return _neutral_adjustment()

    filtered: list[StrategyAdjustment] = []
    for adj in adjustments:
        if adj.target_segment is None or adj.target_segment == segment:
            filtered.append(adj)

    if not filtered:
        return _neutral_adjustment()

    booking = 1.0
    fallout = 1.0
    prepayment = 1.0
    renewal = 1.0
    capture = 1.0
    shift_bps = 0.0

    for adj in filtered:
        booking *= adj.pipeline_booking_multiplier
        fallout *= adj.pipeline_fallout_multiplier
        prepayment *= adj.funded_prepayment_multiplier
        renewal *= adj.funded_renewal_multiplier
        capture *= adj.deposit_capture_multiplier
        shift_bps += adj.deposit_pricing_shift_bps

    signal_ids = ";".join(a.signal_id for a in filtered)
    return StrategyAdjustment(
        signal_id=signal_ids,
        target_segment=segment,
        pipeline_booking_multiplier=booking,
        pipeline_fallout_multiplier=fallout,
        funded_prepayment_multiplier=prepayment,
        funded_renewal_multiplier=renewal,
        deposit_capture_multiplier=capture,
        deposit_pricing_shift_bps=shift_bps,
    )
