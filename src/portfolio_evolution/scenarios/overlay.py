"""Scenario overlay engine — applies macro-economic overlays to engine parameters."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from portfolio_evolution.utils.config_loader import load_yaml


@dataclass
class ScenarioOverlay:
    """Loaded scenario with ready-to-apply modifiers."""

    scenario_id: str
    name: str
    description: str
    macro_factors: dict
    transition_modifiers: dict
    pricing_modifiers: dict
    deposit_modifiers: dict


def load_scenarios(scenario_paths: list[str | Path]) -> list[ScenarioOverlay]:
    """Load scenario definitions from YAML files."""
    overlays: list[ScenarioOverlay] = []
    for path in scenario_paths:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")
        data = load_yaml(path)
        overlays.append(_parse_scenario(data))
    return overlays


def _parse_scenario(data: dict) -> ScenarioOverlay:
    """Parse raw YAML dict into ScenarioOverlay."""
    return ScenarioOverlay(
        scenario_id=str(data.get("scenario_id", "unknown")),
        name=str(data.get("name", "")),
        description=str(data.get("description", "")),
        macro_factors=dict(data.get("macro_factors", {})),
        transition_modifiers=dict(data.get("transition_modifiers", {})),
        pricing_modifiers=dict(data.get("pricing_modifiers", {})),
        deposit_modifiers=dict(data.get("deposit_modifiers", {})),
    )


def _get_multiplier(modifiers: dict, key: str, default: float = 1.0) -> float:
    """Get multiplier from modifiers dict with neutral default."""
    val = modifiers.get(key)
    if val is None:
        return default
    return float(val)


def _clamp_probability(p: float) -> float:
    """Clamp probability to [0, 1]."""
    return max(0.0, min(1.0, p))


def _normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    """Re-normalize probability dict so values sum to 1.0."""
    total = sum(probs.values())
    if total <= 0:
        return probs
    return {k: _clamp_probability(v / total) for k, v in probs.items()}


def apply_pipeline_overlay(
    base_probabilities: dict[str, float],
    overlay: ScenarioOverlay,
) -> dict[str, float]:
    """Apply scenario to pipeline transition probabilities.

    - Advance probs multiplied by booking_rate_multiplier
    - Fallout probs multiplied by fallout_rate_multiplier
    - Probabilities clamped to [0, 1]
    - Returns a new dict; does not mutate input.
    """
    booking_mult = _get_multiplier(
        overlay.transition_modifiers, "booking_rate_multiplier"
    )
    fallout_mult = _get_multiplier(
        overlay.transition_modifiers, "fallout_rate_multiplier"
    )

    result: dict[str, float] = {}
    for next_stage, prob in base_probabilities.items():
        is_fallout = next_stage in ("dropped", "expired")
        mult = fallout_mult if is_fallout else booking_mult
        result[next_stage] = _clamp_probability(float(prob) * mult)
    return result


def _get_rating_index(rating: str, ratings_list: list[str]) -> int:
    """Return 1-based index of rating in the ordered list."""
    try:
        return ratings_list.index(rating) + 1
    except ValueError:
        raise ValueError(
            f"Unknown rating: {rating}. Expected one of {ratings_list}"
        )


def apply_rating_overlay(
    base_transition_probs: dict[str, float],
    current_rating: str,
    overlay: ScenarioOverlay,
    ratings_list: list[str],
) -> dict[str, float]:
    """Apply scenario to rating migration.

    - Downgrade columns multiplied by downgrade_multiplier
    - Default columns multiplied by default_multiplier
    - Upgrade columns multiplied by upgrade_multiplier
    - Re-normalize after modification so row sums to 1.0
    - Returns a new dict; does not mutate input.
    """
    downgrade_mult = _get_multiplier(
        overlay.transition_modifiers, "downgrade_multiplier"
    )
    default_mult = _get_multiplier(
        overlay.transition_modifiers, "default_multiplier"
    )
    upgrade_mult = _get_multiplier(
        overlay.transition_modifiers, "upgrade_multiplier"
    )

    current_idx = _get_rating_index(current_rating, ratings_list)

    result: dict[str, float] = {}
    for target_rating, prob in base_transition_probs.items():
        target_idx = _get_rating_index(target_rating, ratings_list)
        if target_rating == "D":
            mult = default_mult
        elif target_idx > current_idx:
            mult = downgrade_mult
        elif target_idx < current_idx:
            mult = upgrade_mult
        else:
            mult = 1.0  # stable (same rating)
        result[target_rating] = _clamp_probability(float(prob) * mult)

    return _normalize_probs(result)


def apply_deposit_overlay(
    base_config: dict,
    overlay: ScenarioOverlay,
) -> dict:
    """Apply scenario to deposit config.

    - Modify runoff rates by deposit_runoff_multiplier (half_life / multiplier)
    - Shift betas by deposit_beta_shift
    - Modify operating balances by operating_balance_multiplier
    - Modify capture probabilities by deposit_capture_multiplier
    - Returns a deep copy; does not mutate input.
    """
    dep = overlay.deposit_modifiers
    runoff_mult = _get_multiplier(dep, "deposit_runoff_multiplier")
    beta_shift = dep.get("deposit_beta_shift")
    if beta_shift is None:
        beta_shift = 0.0
    else:
        beta_shift = float(beta_shift)
    op_bal_mult = _get_multiplier(dep, "operating_balance_multiplier")
    capture_mult = _get_multiplier(dep, "deposit_capture_multiplier")

    result = copy.deepcopy(base_config)

    # Runoff: half_life / multiplier (shorter half_life = faster runoff)
    if runoff_mult != 1.0:
        decay = result.get("decay", {})
        if isinstance(decay, dict):
            decay = dict(decay)
            half_lives = decay.get("default_half_life_days", {})
            if isinstance(half_lives, dict):
                new_hl: dict = {}
                for dt, hl in half_lives.items():
                    if hl is not None and isinstance(hl, (int, float)) and hl > 0:
                        new_hl[dt] = hl / runoff_mult
                    else:
                        new_hl[dt] = hl
                decay["default_half_life_days"] = new_hl
                result["decay"] = decay

    # Beta shift
    if beta_shift != 0.0:
        rate_sens = result.get("rate_sensitivity", {})
        if isinstance(rate_sens, dict):
            rate_sens = dict(rate_sens)
            betas = rate_sens.get("default_betas", {})
            if isinstance(betas, dict):
                new_betas = {
                    k: max(0.0, min(1.0, float(v) + beta_shift))
                    if isinstance(v, (int, float))
                    else v
                    for k, v in betas.items()
                }
                rate_sens["default_betas"] = new_betas
                result["rate_sensitivity"] = rate_sens

    # Operating balance ratio
    if op_bal_mult != 1.0:
        util = result.get("utilisation_linkage", {})
        if isinstance(util, dict):
            util = dict(util)
            ratio = util.get("operating_balance_ratio")
            if isinstance(ratio, (int, float)):
                util["operating_balance_ratio"] = max(
                    0.0, float(ratio) * op_bal_mult
                )
            result["utilisation_linkage"] = util

    # Capture probabilities
    if capture_mult != 1.0:
        capture = result.get("capture", {})
        if isinstance(capture, dict):
            capture = dict(capture)
            base_probs = capture.get("base_probability", {})
            if isinstance(base_probs, dict):
                new_probs = {
                    k: _clamp_probability(float(v) * capture_mult)
                    if isinstance(v, (int, float))
                    else v
                    for k, v in base_probs.items()
                }
                capture["base_probability"] = new_probs
                result["capture"] = capture

    return result


def get_benchmark_rate_change(overlay: ScenarioOverlay) -> float:
    """Extract benchmark rate change in bps from scenario."""
    val = overlay.macro_factors.get("benchmark_rate_shift_bps")
    if val is None:
        return 0.0
    return float(val)
