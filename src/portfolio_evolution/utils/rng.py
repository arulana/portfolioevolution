"""Seeded random number generator management for reproducible simulation."""

from __future__ import annotations

import numpy as np


class SeededRNG:
    """Manages reproducible random number generation across paths and scenarios.

    Each (path_id, scenario_id) combination gets a deterministic seed
    derived from the master seed, ensuring reproducibility.
    """

    def __init__(self, master_seed: int = 42):
        self._master_seed = master_seed
        self._generators: dict[tuple[int, str], np.random.Generator] = {}

    @property
    def master_seed(self) -> int:
        return self._master_seed

    def get_generator(
        self, path_id: int = 0, scenario_id: str = "baseline"
    ) -> np.random.Generator:
        """Get or create a deterministic generator for a (path, scenario) pair."""
        key = (path_id, scenario_id)
        if key not in self._generators:
            derived_seed = self._derive_seed(path_id, scenario_id)
            self._generators[key] = np.random.default_rng(derived_seed)
        return self._generators[key]

    def _derive_seed(self, path_id: int, scenario_id: str) -> int:
        """Derive a deterministic seed from master seed + path + scenario.

        Uses hashlib instead of hash() to avoid Python's randomized hash seeds.
        """
        import hashlib
        scenario_hash = int(hashlib.sha256(scenario_id.encode()).hexdigest()[:8], 16)
        return (self._master_seed * 1000003 + path_id * 999983 + scenario_hash) & 0xFFFFFFFF

    def reset(self) -> None:
        """Clear all cached generators (forces re-creation on next access)."""
        self._generators.clear()

    def uniform(
        self,
        size: int | tuple[int, ...] | None = None,
        path_id: int = 0,
        scenario_id: str = "baseline",
    ) -> np.ndarray | float:
        """Draw uniform [0, 1) random values."""
        rng = self.get_generator(path_id, scenario_id)
        return rng.random(size=size)

    def normal(
        self,
        loc: float = 0.0,
        scale: float = 1.0,
        size: int | tuple[int, ...] | None = None,
        path_id: int = 0,
        scenario_id: str = "baseline",
    ) -> np.ndarray | float:
        """Draw from normal distribution."""
        rng = self.get_generator(path_id, scenario_id)
        return rng.normal(loc=loc, scale=scale, size=size)
