"""Business day calendar engine for simulation time stepping.

Generates the sequence of simulation days, handling weekends, holidays,
and month-end boundaries.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator


_US_HOLIDAYS_2026_2028 = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
    date(2026, 5, 25), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 10, 12), date(2026, 11, 11), date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15),
    date(2027, 5, 31), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 10, 11), date(2027, 11, 11), date(2027, 11, 25),
    date(2027, 12, 24),
    date(2028, 1, 3), date(2028, 1, 17), date(2028, 2, 21),
    date(2028, 5, 29), date(2028, 7, 4), date(2028, 9, 4),
    date(2028, 10, 9), date(2028, 11, 10), date(2028, 11, 23),
    date(2028, 12, 25),
}


def is_business_day(d: date, country: str = "US") -> bool:
    """Check if a date is a business day (not weekend, not holiday)."""
    if d.weekday() >= 5:
        return False
    if country == "US" and d in _US_HOLIDAYS_2026_2028:
        return False
    return True


def next_business_day(d: date, country: str = "US") -> date:
    """Return the next business day on or after the given date."""
    while not is_business_day(d, country):
        d += timedelta(days=1)
    return d


def is_month_end(d: date) -> bool:
    """Check if this is the last calendar day of the month."""
    next_day = d + timedelta(days=1)
    return next_day.month != d.month


def is_business_month_end(d: date, country: str = "US") -> bool:
    """Check if this is the last business day of the month."""
    if not is_business_day(d, country):
        return False
    check = d + timedelta(days=1)
    while check.month == d.month:
        if is_business_day(check, country):
            return False
        check += timedelta(days=1)
    return True


def is_quarter_end(d: date) -> bool:
    """Check if this date is the last day of a quarter (Mar, Jun, Sep, Dec)."""
    return is_month_end(d) and d.month in (3, 6, 9, 12)


class SimulationCalendar:
    """Generates the day-by-day schedule for a simulation run.

    Handles business day filtering, month-end markers, and period boundaries.
    """

    def __init__(
        self,
        start_date: date,
        horizon_days: int,
        business_days_only: bool = True,
        country: str = "US",
    ):
        self._start_date = start_date
        self._horizon_days = horizon_days
        self._business_days_only = business_days_only
        self._country = country
        self._days: list[SimulationDay] = []
        self._build()

    def _build(self) -> None:
        """Pre-compute the full day schedule."""
        current = self._start_date
        sim_day = 0
        calendar_days = 0

        while sim_day < self._horizon_days:
            if self._business_days_only and not is_business_day(current, self._country):
                current += timedelta(days=1)
                calendar_days += 1
                continue

            day = SimulationDay(
                sim_day=sim_day,
                calendar_day=calendar_days,
                date=current,
                is_month_end=is_business_month_end(current, self._country)
                if self._business_days_only
                else is_month_end(current),
                is_quarter_end=is_quarter_end(current),
            )
            self._days.append(day)
            sim_day += 1
            calendar_days += 1
            current += timedelta(days=1)

    @property
    def start_date(self) -> date:
        return self._start_date

    @property
    def end_date(self) -> date:
        return self._days[-1].date if self._days else self._start_date

    @property
    def total_days(self) -> int:
        return len(self._days)

    def __len__(self) -> int:
        return len(self._days)

    def __iter__(self) -> Iterator[SimulationDay]:
        return iter(self._days)

    def __getitem__(self, idx: int) -> SimulationDay:
        return self._days[idx]

    def month_end_days(self) -> list[SimulationDay]:
        """Return only the month-end days."""
        return [d for d in self._days if d.is_month_end]


class SimulationDay:
    """A single day in the simulation schedule."""

    __slots__ = ("sim_day", "calendar_day", "date", "is_month_end", "is_quarter_end")

    def __init__(
        self,
        sim_day: int,
        calendar_day: int,
        date: date,
        is_month_end: bool = False,
        is_quarter_end: bool = False,
    ):
        self.sim_day = sim_day
        self.calendar_day = calendar_day
        self.date = date
        self.is_month_end = is_month_end
        self.is_quarter_end = is_quarter_end

    def __repr__(self) -> str:
        flags = []
        if self.is_month_end:
            flags.append("ME")
        if self.is_quarter_end:
            flags.append("QE")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        return f"Day({self.sim_day}, {self.date}{flag_str})"
