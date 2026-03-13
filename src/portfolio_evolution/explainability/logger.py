"""Explainability logger for simulation audit trail and debugging."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4


class ExplainabilityLogger:
    """Captures and stores simulation events for audit and debugging."""

    def __init__(self, enabled: bool = True, max_events: int = 1_000_000):
        """Initialize the logger."""
        self._events: list[dict] = []
        self._enabled = enabled
        self._max_events = max_events

    def _should_log(self) -> bool:
        """Return True if logging is enabled and capacity remains."""
        return self._enabled and len(self._events) < self._max_events

    def _append(self, event: dict) -> None:
        """Append event if capacity allows."""
        if self._should_log():
            self._events.append(event)

    def log_transition(
        self,
        sim_day: int,
        sim_date: date,
        instrument_id: str,
        event_type: str,
        previous_state: str,
        new_state: str,
        reason_code: str,
        random_draw: float | None = None,
        base_probability: float | None = None,
        adjusted_probability: float | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Log a state transition event."""
        if not self._enabled:
            return
        self._append({
            "event_id": uuid4().hex[:12],
            "simulation_day": sim_day,
            "as_of_date": sim_date,
            "event_type": event_type,
            "instrument_id": instrument_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "reason_code": reason_code,
            "random_draw": random_draw,
            "base_probability": base_probability,
            "adjusted_probability": adjusted_probability,
            "metadata": metadata or {},
        })

    def log_funding(
        self,
        sim_day: int,
        sim_date: date,
        pipeline_id: str,
        funded_id: str,
        amount: float,
        deposits_captured: int = 0,
    ) -> None:
        """Log a funding conversion event."""
        if not self._enabled:
            return
        self._append({
            "event_id": uuid4().hex[:12],
            "simulation_day": sim_day,
            "as_of_date": sim_date,
            "event_type": "funding",
            "pipeline_id": pipeline_id,
            "funded_id": funded_id,
            "amount": amount,
            "deposits_captured": deposits_captured,
        })

    def log_maturity(
        self,
        sim_day: int,
        sim_date: date,
        instrument_id: str,
        balance: float,
        action: str = "runoff",
    ) -> None:
        """Log a maturity event."""
        if not self._enabled:
            return
        self._append({
            "event_id": uuid4().hex[:12],
            "simulation_day": sim_day,
            "as_of_date": sim_date,
            "event_type": "maturity",
            "instrument_id": instrument_id,
            "balance": balance,
            "action": action,
        })

    def log_deposit_event(
        self,
        sim_day: int,
        sim_date: date,
        deposit_id: str,
        event_type: str,
        amount: float,
        metadata: dict | None = None,
    ) -> None:
        """Log a deposit lifecycle event."""
        if not self._enabled:
            return
        self._append({
            "event_id": uuid4().hex[:12],
            "simulation_day": sim_day,
            "as_of_date": sim_date,
            "event_type": event_type,
            "deposit_id": deposit_id,
            "amount": amount,
            "metadata": metadata or {},
        })

    def log_rating_migration(
        self,
        sim_day: int,
        sim_date: date,
        instrument_id: str,
        from_rating: str,
        to_rating: str,
        random_draw: float,
        probability: float,
    ) -> None:
        """Log a rating migration event."""
        if not self._enabled:
            return
        self._append({
            "event_id": uuid4().hex[:12],
            "simulation_day": sim_day,
            "as_of_date": sim_date,
            "event_type": "rating_migration",
            "instrument_id": instrument_id,
            "from_rating": from_rating,
            "to_rating": to_rating,
            "random_draw": random_draw,
            "probability": probability,
        })

    @property
    def events(self) -> list[dict]:
        """Get all logged events."""
        return self._events.copy()

    def get_events_for_instrument(self, instrument_id: str) -> list[dict]:
        """Filter events by instrument."""
        return [e for e in self._events if e.get("instrument_id") == instrument_id]

    def get_events_by_type(self, event_type: str) -> list[dict]:
        """Filter events by type."""
        return [e for e in self._events if e.get("event_type") == event_type]

    def get_events_for_day(self, sim_day: int) -> list[dict]:
        """Filter events by simulation day."""
        return [e for e in self._events if e.get("simulation_day") == sim_day]

    def summary(self) -> dict:
        """Return event count summary by type."""
        counts: dict[str, int] = {}
        for e in self._events:
            t = e.get("event_type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    def to_dataframe(self) -> "pl.DataFrame":
        """Convert events to Polars DataFrame."""
        import polars as pl

        if not self._events:
            return pl.DataFrame()

        return pl.from_dicts(self._events)

    def save(self, path: Path, format: str = "json") -> Path:
        """Save events to file (json or csv)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with path.open("w") as f:
                json.dump(self._events, f, indent=2, default=str)
        elif format == "csv":
            df = self.to_dataframe()
            if df.is_empty():
                path.write_text("")
            else:
                # Flatten nested dicts for CSV (Polars CSV does not support nested data)
                flattened = []
                for row in df.iter_rows(named=True):
                    flat = {}
                    for k, v in row.items():
                        if isinstance(v, (dict, list)):
                            flat[k] = json.dumps(v, default=str)
                        else:
                            flat[k] = v
                    flattened.append(flat)
                import polars as pl
                pl.DataFrame(flattened).write_csv(path)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'csv'.")

        return path
