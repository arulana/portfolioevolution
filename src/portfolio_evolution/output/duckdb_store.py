"""DuckDB-backed persistent storage for simulation results.

Stores position-level history, daily aggregates, and event logs.
Supports querying across runs.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)

_duckdb_available = True
try:
    import duckdb
except ImportError:
    _duckdb_available = False
    duckdb = None  # type: ignore[misc, assignment]


class SimulationStore:
    """DuckDB-backed store for simulation output.

    Stores position-level history, daily aggregates, and event logs.
    Supports querying across runs.
    """

    def __init__(self, db_path: str | Path = "outputs/simulation.duckdb") -> None:
        """Open or create a DuckDB database."""
        self._db_path = Path(db_path)
        self._conn = None
        if not _duckdb_available:
            logger.warning(
                "DuckDB is not installed. SimulationStore will operate in no-op mode. "
                "Install with: pip install duckdb"
            )
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))

    def _ensure_connection(self) -> None:
        """Raise if DuckDB is not available."""
        if not _duckdb_available or self._conn is None:
            raise RuntimeError(
                "DuckDB is not available. Install with: pip install duckdb"
            )

    def init_tables(self) -> None:
        """Create tables if they don't exist.

        Tables:
        - positions: position-level daily snapshots
        - daily_aggregates: daily rollup metrics
        - events: transition/lifecycle events
        - runs: run metadata (manifest)
        """
        self._ensure_connection()
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id VARCHAR PRIMARY KEY,
                config_hash VARCHAR,
                config_json VARCHAR,
                engine_version VARCHAR,
                python_version VARCHAR,
                random_seed BIGINT,
                created_at TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                run_id VARCHAR,
                sim_day INTEGER,
                sim_date DATE,
                instrument_id VARCHAR,
                position_type VARCHAR,
                counterparty_id VARCHAR,
                counterparty_name VARCHAR,
                facility_id VARCHAR,
                product_type VARCHAR,
                segment VARCHAR,
                subsegment VARCHAR,
                industry VARCHAR,
                geography VARCHAR,
                currency VARCHAR,
                committed_amount DOUBLE,
                funded_amount DOUBLE,
                utilisation_rate DOUBLE,
                undrawn_amount DOUBLE,
                coupon_type VARCHAR,
                coupon_rate DOUBLE,
                spread_bps DOUBLE,
                origination_date DATE,
                maturity_date DATE,
                tenor_months INTEGER,
                internal_rating VARCHAR,
                internal_rating_numeric INTEGER,
                pd DOUBLE,
                lgd DOUBLE,
                watchlist_flag BOOLEAN,
                default_flag BOOLEAN,
                pipeline_stage VARCHAR,
                as_of_date DATE,
                PRIMARY KEY (run_id, sim_day, instrument_id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_aggregates (
                run_id VARCHAR,
                sim_day INTEGER,
                sim_date DATE,
                total_funded_balance DOUBLE,
                total_committed DOUBLE,
                total_pipeline_value DOUBLE,
                pipeline_count INTEGER,
                funded_count INTEGER,
                net_origination DOUBLE,
                net_runoff DOUBLE,
                pipeline_funded INTEGER,
                pipeline_dropped INTEGER,
                funded_matured INTEGER,
                PRIMARY KEY (run_id, sim_day)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS crm_pipeline (
                run_id VARCHAR, sim_day INTEGER, OPP_ID VARCHAR,
                BORROWER_NAME VARCHAR, STAGE VARCHAR, EXPECTED_AMOUNT DOUBLE,
                CLOSE_PROB DOUBLE, SEGMENT VARCHAR, RM_NAME VARCHAR,
                RM_CODE VARCHAR, EXPECTED_CLOSE_DATE VARCHAR,
                LAST_ACTIVITY_DATE VARCHAR, STATE VARCHAR, SOURCE VARCHAR
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS los_underwriting (
                run_id VARCHAR, sim_day INTEGER, APP_ID VARCHAR,
                BORROWER_NAME VARCHAR, UW_STAGE VARCHAR,
                REQUESTED_AMOUNT DOUBLE, APPROVED_AMOUNT DOUBLE,
                RISK_RATING VARCHAR, RATING_NUMERIC INTEGER,
                ANALYST_CODE VARCHAR, APPROVAL_DATE VARCHAR,
                EXPECTED_CLOSE_DATE VARCHAR, RATE_TYPE VARCHAR,
                EXPECTED_RATE DOUBLE, SEGMENT VARCHAR, STATE VARCHAR,
                IS_RENEWAL BOOLEAN, CONDITION_COUNT INTEGER
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS core_funded (
                run_id VARCHAR, sim_day INTEGER, ACCT_NO VARCHAR,
                BORROWER VARCHAR, CURRENT_BAL DOUBLE, COMMITTED_AMT DOUBLE,
                INT_RATE DOUBLE, RATE_TYPE VARCHAR, ORIG_DATE VARCHAR,
                MATURITY_DATE VARCHAR, AMORT_TYPE VARCHAR, PMT_FREQ VARCHAR,
                RISK_RATING VARCHAR, RISK_RATING_NUM INTEGER,
                SEGMENT VARCHAR, PRODUCT_TYPE VARCHAR, STATE VARCHAR,
                ACCRUAL_STATUS VARCHAR, COLLATERAL_TYPE VARCHAR,
                PROPERTY_TYPE VARCHAR, OWNER_OCC BOOLEAN,
                SNC_FLAG BOOLEAN, TDR_FLAG BOOLEAN, AS_OF_DATE VARCHAR
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS core_deposits (
                run_id VARCHAR, sim_day INTEGER, ACCOUNT_ID VARCHAR,
                CUSTOMER_ID VARCHAR, ACCOUNT_TYPE VARCHAR,
                CURRENT_BAL DOUBLE, INT_RATE DOUBLE, RATE_TYPE VARCHAR,
                DEPOSIT_BETA DOUBLE, OPEN_DATE VARCHAR,
                LIQUIDITY_CLASS VARCHAR, SEGMENT VARCHAR, AS_OF_DATE VARCHAR
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                run_id VARCHAR,
                event_id VARCHAR,
                sim_day INTEGER,
                event_date DATE,
                instrument_id VARCHAR,
                event_type VARCHAR,
                reason_code VARCHAR,
                previous_state VARCHAR,
                new_state VARCHAR,
                created_at TIMESTAMP
            )
        """)

    def write_daily_snapshot(
        self,
        run_id: str,
        sim_day: int,
        sim_date: date,
        positions_df: pl.DataFrame,
        aggregates_df: pl.DataFrame,
    ) -> None:
        """Write a day's data to DuckDB. Uses Polars→DuckDB zero-copy."""
        self._ensure_connection()

        # Add run_id and sim metadata if not present
        pos = positions_df
        if "run_id" not in pos.columns:
            pos = pos.with_columns(pl.lit(run_id).alias("run_id"))
        if "sim_day" not in pos.columns:
            pos = pos.with_columns(pl.lit(sim_day).alias("sim_day"))
        if "sim_date" not in pos.columns:
            pos = pos.with_columns(pl.lit(sim_date).alias("sim_date"))

        pos_cols = [
            "run_id", "sim_day", "sim_date", "instrument_id", "position_type",
            "counterparty_id", "counterparty_name", "facility_id", "product_type",
            "segment", "subsegment", "industry", "geography", "currency",
            "committed_amount", "funded_amount", "utilisation_rate", "undrawn_amount",
            "coupon_type", "coupon_rate", "spread_bps", "origination_date",
            "maturity_date", "tenor_months", "internal_rating", "internal_rating_numeric",
            "pd", "lgd", "watchlist_flag", "default_flag", "pipeline_stage", "as_of_date",
        ]
        _pos_int = {"tenor_months", "internal_rating_numeric"}
        _pos_float = {"committed_amount", "funded_amount", "utilisation_rate", "undrawn_amount", "coupon_rate", "spread_bps", "pd", "lgd"}
        _pos_bool = {"watchlist_flag", "default_flag"}
        _pos_date = {"sim_date", "origination_date", "maturity_date", "as_of_date"}
        for c in pos_cols:
            if c not in pos.columns:
                if c in _pos_int:
                    pos = pos.with_columns(pl.lit(None).cast(pl.Int64).alias(c))
                elif c in _pos_float:
                    pos = pos.with_columns(pl.lit(None).cast(pl.Float64).alias(c))
                elif c in _pos_bool:
                    pos = pos.with_columns(pl.lit(None).cast(pl.Boolean).alias(c))
                elif c in _pos_date:
                    pos = pos.with_columns(pl.lit(None).cast(pl.Date).alias(c))
                else:
                    pos = pos.with_columns(pl.lit(None).cast(pl.Utf8).alias(c))
        pos_subset = pos.select(pos_cols)

        agg = aggregates_df
        if "run_id" not in agg.columns:
            agg = agg.with_columns(pl.lit(run_id).alias("run_id"))
        if "sim_day" not in agg.columns:
            agg = agg.with_columns(pl.lit(sim_day).alias("sim_day"))
        if "sim_date" not in agg.columns:
            agg = agg.with_columns(pl.lit(sim_date).alias("sim_date"))

        agg_cols = [
            "run_id", "sim_day", "sim_date", "total_funded_balance", "total_committed",
            "total_pipeline_value", "pipeline_count", "funded_count",
            "net_origination", "net_runoff", "pipeline_funded", "pipeline_dropped",
            "funded_matured",
        ]
        agg_int_cols = {"pipeline_count", "funded_count", "pipeline_funded", "pipeline_dropped", "funded_matured"}
        for c in agg_cols:
            if c not in agg.columns:
                dtype = pl.Int64 if c in agg_int_cols else pl.Float64
                agg = agg.with_columns(pl.lit(None).cast(dtype).alias(c))
        agg_subset = agg.select(agg_cols)

        self._conn.execute(
            "DELETE FROM positions WHERE run_id = ? AND sim_day = ?",
            [run_id, sim_day],
        )
        self._conn.execute(
            "DELETE FROM daily_aggregates WHERE run_id = ? AND sim_day = ?",
            [run_id, sim_day],
        )

        self._conn.register("_pos_batch", pos_subset)
        self._conn.execute("INSERT INTO positions SELECT * FROM _pos_batch")
        self._conn.unregister("_pos_batch")

        self._conn.register("_agg_batch", agg_subset)
        self._conn.execute("INSERT INTO daily_aggregates SELECT * FROM _agg_batch")
        self._conn.unregister("_agg_batch")

    def write_system_views(
        self,
        run_id: str,
        sim_day: int,
        crm_df: pl.DataFrame | None = None,
        los_df: pl.DataFrame | None = None,
        core_df: pl.DataFrame | None = None,
        deposits_df: pl.DataFrame | None = None,
    ) -> None:
        """Write system-specific view DataFrames to their respective tables."""
        self._ensure_connection()

        for table, df in [
            ("crm_pipeline", crm_df),
            ("los_underwriting", los_df),
            ("core_funded", core_df),
            ("core_deposits", deposits_df),
        ]:
            if df is None or df.is_empty():
                continue
            batch = df.drop("SIM_DAY") if "SIM_DAY" in df.columns else df
            batch = batch.with_columns(
                pl.lit(run_id).alias("run_id"),
                pl.lit(sim_day).alias("sim_day"),
            )
            batch_name = f"_{table}_batch"
            self._conn.execute(
                f"DELETE FROM {table} WHERE run_id = ? AND sim_day = ?",
                [run_id, sim_day],
            )
            self._conn.register(batch_name, batch)
            self._conn.execute(f"INSERT INTO {table} SELECT * FROM {batch_name}")
            self._conn.unregister(batch_name)

    def write_events(self, run_id: str, events: list[dict]) -> None:
        """Write transition events."""
        if not events:
            return
        self._ensure_connection()
        rows = []
        now = datetime.now().isoformat()
        for e in events:
            rows.append({
                "run_id": run_id,
                "event_id": e.get("event_id", ""),
                "sim_day": e.get("sim_day", e.get("simulation_day")),
                "event_date": e.get("as_of_date", e.get("event_date")),
                "instrument_id": e.get("instrument_id", ""),
                "event_type": e.get("event_type", ""),
                "reason_code": e.get("reason_code", ""),
                "previous_state": json.dumps(e.get("previous_state", {})),
                "new_state": json.dumps(e.get("new_state", {})),
                "created_at": now,
            })
        df = pl.DataFrame(rows)
        self._conn.register("_events_batch", df)
        self._conn.execute("INSERT INTO events SELECT * FROM _events_batch")
        self._conn.unregister("_events_batch")

    def register_run(self, run_id: str, config: dict) -> None:
        """Register a simulation run in the runs table."""
        self._ensure_connection()
        config_json = json.dumps(config, sort_keys=True)
        config_hash = _hash_config(config_json)
        import sys
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        engine_version = config.get("engine_version", "0.1.0")
        random_seed = config.get("random_seed")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO runs (run_id, config_hash, config_json, engine_version, python_version, random_seed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [run_id, config_hash, config_json, engine_version, python_version, random_seed, datetime.now().isoformat()],
        )

    def close(self) -> None:
        """Close the DuckDB connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def query(self, sql: str, params: list | None = None) -> pl.DataFrame:
        """Run an arbitrary SQL query and return as Polars DataFrame.

        Args:
            sql: SQL query with ? placeholders.
            params: Optional list of parameters for the placeholders.
        """
        self._ensure_connection()
        if params is not None:
            result = self._conn.execute(sql, params)
        else:
            result = self._conn.execute(sql)
        return result.pl()

    def __enter__(self) -> SimulationStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def _hash_config(config_json: str) -> str:
    """SHA256 hash of config JSON."""
    import hashlib
    return hashlib.sha256(config_json.encode()).hexdigest()
